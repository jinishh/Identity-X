import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRightLeft, Check, ExternalLink, FileJson, Lock, Minus, Plus, ShieldCheck, Upload, X } from '@/components/icons'
import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { api, postForm, unwrap, type Schemas } from '@/api/client'
import { HashChip, Stamp, Timeline, UserChip } from '@/components/domain'
import { PipelineSteps } from '@/components/Pipeline'
import { Badge, Button, Dialog, EmptyState, ErrorState, Field, Input, KV, Select, Skeleton, Textarea } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/cn'
import { fmtBytes, fmtDate, fmtDateTime, fmtRelative, humanize } from '@/lib/format'
import { sha256File } from '@/lib/hash'

type Doc = Schemas['Document']
type Version = Schemas['Version']

// ───────────── Integrity ─────────────
const CHECK_LABEL: Record<string, [string, string]> = {
  object_present: ['Stored object present', 'The encrypted file exists in the vault'],
  object_locked: ['Write-once lock active', 'Cannot be overwritten or deleted'],
  ciphertext_hash_match: ['Ciphertext unchanged', 'Stored bytes match their recorded hash'],
  decrypts: ['Decrypts & authenticates', 'AES-256-GCM authentication tag is valid'],
  plaintext_hash_match: ['Content matches SHA-256', 'Recomputed fingerprint equals the one sealed at intake'],
  manifest_hash_match: ['Manifest unchanged', 'Canonical manifest hash matches'],
  signature_valid: ['Signature valid', 'Ed25519 signature over the manifest verifies'],
  audit_anchored: ['Anchored in audit chain', 'Sealing event exists and its hash is intact'],
  version_link_valid: ['Linked to previous version', 'Version chain is unbroken'],
}

export function IntegrityPanel({ version, doc }: { version: Version; doc: Doc }) {
  const qc = useQueryClient()
  const [result, setResult] = useState<Schemas['VerificationResult'] | null>(null)
  const [shown, setShown] = useState(0)
  const [manifestOpen, setManifestOpen] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  const verify = useMutation({
    mutationFn: () => unwrap(api.POST('/versions/{versionId}/verify', { params: { path: { versionId: version.id } } })),
    onSuccess: (r) => {
      setResult(r); setShown(0)
      let i = 0
      window.clearInterval(timer.current)
      timer.current = window.setInterval(() => { i++; setShown(i); if (i >= r.checks.length) window.clearInterval(timer.current) }, 140)
      qc.invalidateQueries({ queryKey: ['versions', doc.id] })
      qc.invalidateQueries({ queryKey: ['doc-timeline', doc.id] })
    },
  })
  useEffect(() => { setResult(null); setShown(0) }, [version.id])
  useEffect(() => () => window.clearInterval(timer.current), [])
  const canVerify = doc.access.actions.includes('document:verify')
  const finished = result && shown >= result.checks.length

  return (
    <div className="space-y-4">
      <div className="rounded-[6px] border border-line bg-canvas p-3">
        <KV label="SHA-256"><HashChip value={version.sha256} /></KV>
        <KV label="Manifest hash"><HashChip value={version.manifest_sha256} /></KV>
        <KV label="Signed by key"><span className="font-mono text-[12px]">{version.signing_key_id ?? '—'}</span></KV>
        <KV label="Storage"><span className="flex items-center gap-1 text-lock"><Lock className="size-3.5" />Write-once until {fmtDate(version.object_lock.retain_until)}</span></KV>
        <KV label="Size">{fmtBytes(version.size_bytes)} · {version.detected_mime}</KV>
        <KV label="Last verified">{version.last_verification ? <span className={version.last_verification.overall === 'VERIFIED' ? 'text-ok' : 'text-bad'}>{humanize(version.last_verification.overall)} · {fmtRelative(version.last_verification.at)}</span> : 'Never'}</KV>
      </div>

      <div className="flex gap-2">
        <Button className="flex-1" onClick={() => verify.mutate()} loading={verify.isPending} disabled={!canVerify || version.processing_status !== 'READY'}>
          <ShieldCheck className="size-4" />Verify integrity now
        </Button>
        <Button variant="secondary" onClick={() => setManifestOpen(true)} disabled={!version.manifest_sha256}><FileJson className="size-4" />Manifest</Button>
      </div>
      {verify.error && <ErrorState error={verify.error} />}

      {result && (
        <div className="overflow-hidden rounded-[6px] border border-line">
          {finished && (
            <div className={cn('flex items-center gap-4 border-b px-4 py-4', result.overall === 'VERIFIED' ? 'border-ok-line bg-ok-bg/60' : 'border-bad-line bg-bad-bg/70')}>
              <Stamp size="lg" animate tone={result.overall === 'VERIFIED' ? 'green' : 'red'} rotate={-5}>
                {result.overall === 'VERIFIED' ? 'Verified' : 'Tampered'}
              </Stamp>
              <p className="text-[13.5px] text-ink-2">
                {result.overall === 'VERIFIED'
                  ? 'Byte for byte, this is the file that was sealed. Checked just now; the check itself is in the ledger.'
                  : 'This file no longer matches what was sealed. An alert has gone to the supervisor and the audit cell.'}
              </p>
            </div>
          )}
          <ul className="divide-y divide-line">
            {result.checks.map((c, i) => {
              const [label, desc] = CHECK_LABEL[c.name] ?? [c.name, '']
              const visible = i < shown
              return (
                <li key={c.name} className={cn('flex items-start gap-2.5 px-3 py-2 transition-opacity duration-200', visible ? 'opacity-100' : 'opacity-0')}>
                  <span className={cn('mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full',
                    c.status === 'PASS' ? 'bg-ok text-white' : c.status === 'FAIL' ? 'bg-bad text-white' : 'bg-sunken text-muted')}>
                    {c.status === 'PASS' ? <Check className="size-3" /> : c.status === 'FAIL' ? <X className="size-3" /> : <Minus className="size-3" />}
                  </span>
                  <div className="min-w-0 text-[13px]">
                    <div className={cn('font-medium', c.status === 'FAIL' && 'text-bad')}>{label}</div>
                    <div className="text-[12px] text-muted">{c.detail ?? desc}</div>
                    {c.status === 'FAIL' && c.expected && (
                      <div className="mt-1 space-y-0.5 font-mono text-[11px]">
                        <div>expected <span className="text-ok">{c.expected.slice(0, 24)}…</span></div>
                        <div>actual&nbsp;&nbsp; <span className="text-bad">{(c.actual ?? 'none').slice(0, 24)}…</span></div>
                      </div>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      )}
      <ManifestDialog open={manifestOpen} onOpenChange={setManifestOpen} versionId={version.id} />
    </div>
  )
}

function ManifestDialog({ open, onOpenChange, versionId }: { open: boolean; onOpenChange: (o: boolean) => void; versionId: string }) {
  const q = useQuery({
    queryKey: ['manifest', versionId],
    queryFn: () => unwrap(api.GET('/versions/{versionId}/manifest', { params: { path: { versionId } } })),
    enabled: open,
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange} width="max-w-2xl" title="Signed manifest"
      description="The exact canonical (RFC 8785) JSON that was signed. Anyone with the public key can verify it offline.">
      {q.data ? (
        <div className="space-y-3">
          <pre className="max-h-80 overflow-auto rounded-[6px] bg-navy-950 p-3 font-mono text-[11.5px] leading-relaxed text-[#cfe3ff]">{JSON.stringify(q.data.manifest, null, 2)}</pre>
          <div className="rounded-[6px] border border-line p-3">
            <KV label="Algorithm">{q.data.algorithm}</KV>
            <KV label="Key ID" mono>{q.data.signing_key_id}</KV>
            <KV label="Manifest SHA-256"><HashChip value={q.data.manifest_sha256} /></KV>
            <div className="pt-1.5 text-[12px] text-muted">Signature (base64)</div>
            <p className="font-mono text-[11px] break-all text-ink-2">{q.data.signature}</p>
          </div>
        </div>
      ) : <Skeleton className="h-64" />}
    </Dialog>
  )
}

// ───────────── Versions ─────────────
export function VersionsPanel({ doc, versions, selected, onSelect }: { doc: Doc; versions: Version[]; selected?: string; onSelect: (id: string) => void }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [hash, setHash] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const up = useMutation({
    mutationFn: () => {
      const f = new FormData()
      f.append('file', file!, file!.name); f.append('client_sha256', hash!); f.append('change_note', note)
      return postForm<Schemas['UploadAccepted']>(`/documents/${doc.id}/versions`, f)
    },
    onSuccess: (r) => { setPending(r.version_id); setOpen(false); setFile(null); setHash(null); setNote('') },
  })
  const proc = useQuery({
    queryKey: ['processing', pending],
    queryFn: () => unwrap(api.GET('/versions/{versionId}/processing', { params: { path: { versionId: pending! } } })),
    enabled: !!pending,
    refetchInterval: (q) => (['READY', 'FAILED', 'QUARANTINED'].includes(q.state.data?.status ?? '') ? false : 400),
  })
  useEffect(() => {
    if (proc.data?.status === 'READY') {
      qc.invalidateQueries({ queryKey: ['versions', doc.id] }); qc.invalidateQueries({ queryKey: ['doc', doc.id] })
      toast.success('New version sealed. Earlier versions are unchanged.')
      const t = setTimeout(() => setPending(null), 1500)
      return () => clearTimeout(t)
    }
  }, [proc.data?.status, qc, doc.id])

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[12.5px] text-muted">Every version is kept. Earlier versions can be viewed but never changed.</p>
        {doc.access.actions.includes('document:new_version') && <Button size="sm" variant="secondary" onClick={() => setOpen(true)}><Plus className="size-3.5" />New version</Button>}
      </div>
      {pending && proc.data && proc.data.status !== 'READY' && (
        <div className="rounded-[6px] border border-line p-3"><PipelineSteps steps={proc.data.steps} /></div>
      )}
      <ol className="space-y-2">
        {versions.map((v) => (
          <li key={v.id}>
            <button onClick={() => onSelect(v.id)} className={cn('w-full rounded-[6px] border p-3 text-left transition-colors',
              v.id === selected ? 'border-brand bg-navy-50/60' : 'border-line hover:border-line-strong')}>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 font-medium">v{v.version_no}
                  {v.id === doc.current_version?.id && <Badge tone="brand">Current</Badge>}
                  {v.review_status !== 'NOT_REQUIRED' && <Badge tone={v.review_status === 'APPROVED' ? 'ok' : v.review_status === 'RETURNED' ? 'bad' : 'warn'}>Review: {humanize(v.review_status)}</Badge>}
                </span>
                <span className="flex items-center gap-1 text-[12px] text-lock"><Lock className="size-3" />Immutable</span>
              </div>
              {v.change_note && <p className="mt-1 text-[13px] text-ink-2">“{v.change_note}”</p>}
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px] text-muted">
                <span>{v.uploaded_by.full_name} · {fmtDateTime(v.uploaded_at)}</span>
                <HashChip value={v.sha256} />
              </div>
              {v.prev_version_sha256 && <div className="mt-1 text-[11.5px] text-muted">links to previous <span className="font-mono">{v.prev_version_sha256.slice(0, 10)}…</span></div>}
            </button>
          </li>
        ))}
      </ol>
      <Dialog open={open} onOpenChange={setOpen} title="Upload a new version" description="The current version stays in the vault, unchanged."
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={up.isPending} disabled={!hash || note.trim().length < 5} onClick={() => up.mutate()}><Upload className="size-4" />Seal new version</Button></>}>
        <div className="space-y-3">
          <Input type="file" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff" className="py-1.5" onChange={async (e) => { const f = e.target.files?.[0]; if (f) { setFile(f); setHash(await sha256File(f)) } }} />
          {hash && <p className="font-mono text-[11px] break-all text-muted">SHA-256 {hash}</p>}
          <Field label="What changed?"><Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Corrected the date of incident" /></Field>
          {up.error && <ErrorState error={up.error} />}
        </div>
      </Dialog>
    </div>
  )
}

// ───────────── Custody ─────────────
export function CustodyPanel({ doc }: { doc: Doc }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['doc-timeline', doc.id], queryFn: () => unwrap(api.GET('/documents/{documentId}/timeline', { params: { path: { documentId: doc.id } } })) })
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [to, setTo] = useState<Schemas['UserSummary'] | null>(null)
  const [reason, setReason] = useState('')
  const dir = useQuery({ queryKey: ['directory', search], queryFn: () => unwrap(api.GET('/directory', { params: { query: { q: search } } })), enabled: search.length >= 2 })
  const m = useMutation({
    mutationFn: () => unwrap(api.POST('/documents/{documentId}/custody-transfers', { params: { path: { documentId: doc.id } }, body: { to_user_id: to!.id, reason } })),
    onSuccess: () => { setOpen(false); toast.success(`Transfer sent to ${to!.full_name} — custody moves when they accept.`); qc.invalidateQueries({ queryKey: ['doc-timeline', doc.id] }) },
  })
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-[6px] border border-line bg-canvas px-3 py-2.5">
        <div><div className="text-[12px] text-muted">Current custodian</div><UserChip user={doc.custodian} /></div>
        {doc.access.actions.includes('document:custody_transfer') && <Button size="sm" variant="secondary" onClick={() => setOpen(true)}><ArrowRightLeft className="size-3.5" />Transfer</Button>}
      </div>
      <div className="max-h-[560px] overflow-y-auto pr-1">
        {q.data ? <Timeline events={[...q.data].reverse()} /> : <Skeleton className="h-60" />}
      </div>
      <Dialog open={open} onOpenChange={setOpen} title="Transfer custody" description="The recipient must accept. Until then custody does not change."
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button disabled={!to || reason.length < 10} loading={m.isPending} onClick={() => m.mutate()}>Send transfer</Button></>}>
        <div className="space-y-3">
          <Field label="Recipient"><Input value={search} onChange={(e) => { setSearch(e.target.value); setTo(null) }} placeholder="Name or service ID" /></Field>
          {search.length >= 2 && !to && <ul className="max-h-40 overflow-y-auto rounded-[4px] border border-line">{dir.data?.map((u) => <li key={u.id}><button onClick={() => setTo(u)} className="w-full px-3 py-2 text-left hover:bg-[#fffdf8]"><UserChip user={u} /></button></li>)}</ul>}
          {to && <div className="rounded-[4px] border border-line px-3 py-2"><UserChip user={to} /></div>}
          <Field label="Reason"><Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Sealed exhibit sent to FSL for examination" /></Field>
          {m.error && <ErrorState error={m.error} />}
        </div>
      </Dialog>
    </div>
  )
}

// ───────────── Sharing ─────────────
const SCOPES: Record<string, string[]> = {
  INTERNAL: ['VIEW_REDACTED', 'VIEW', 'DOWNLOAD'], CONFIDENTIAL: ['VIEW'], RESTRICTED: ['VIEW'], VICTIM_PROTECTED: ['VIEW_REDACTED'],
}
const MAX_DAYS: Record<string, number> = { INTERNAL: 30, CONFIDENTIAL: 14, RESTRICTED: 7, VICTIM_PROTECTED: 7 }

export function SharingPanel({ doc }: { doc: Doc }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['shares', doc.id], queryFn: () => unwrap(api.GET('/documents/{documentId}/shares', { params: { path: { documentId: doc.id } } })) })
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [who, setWho] = useState<Schemas['UserSummary'] | null>(null)
  const scopes = SCOPES[doc.sensitivity]
  const [scope, setScope] = useState(scopes[0])
  const [days, setDays] = useState(Math.min(7, MAX_DAYS[doc.sensitivity]))
  const [reason, setReason] = useState('')
  const dir = useQuery({ queryKey: ['directory', search], queryFn: () => unwrap(api.GET('/directory', { params: { query: { q: search } } })), enabled: search.length >= 2 })
  const m = useMutation({
    mutationFn: () => unwrap(api.POST('/documents/{documentId}/shares', {
      params: { path: { documentId: doc.id } },
      body: { grantee_user_id: who!.id, scope: scope as never, expires_at: new Date(Date.now() + days * 86400_000).toISOString(), reason },
    })),
    onSuccess: () => { setOpen(false); setWho(null); setSearch(''); setReason(''); toast.success('Share requested — awaiting supervisor approval') },
  })
  const revoke = useMutation({
    mutationFn: (id: string) => unwrap(api.POST('/shares/{shareId}/revoke', { params: { path: { shareId: id } }, body: { reason: 'Access no longer required' } })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['shares', doc.id] }); toast.success('Share revoked') },
  })
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[12.5px] text-muted">Shares are approved by a supervisor, limited in scope and expire automatically.</p>
        {doc.access.actions.includes('document:share_request') && <Button size="sm" variant="secondary" onClick={() => setOpen(true)}><Plus className="size-3.5" />Request share</Button>}
      </div>
      {!q.data ? <Skeleton className="h-24" /> : q.data.length === 0 ? <EmptyState title="Not shared outside the case" /> : (
        <ul className="space-y-2">
          {q.data.map((s) => (
            <li key={s.id} className={cn('rounded-[6px] border border-line p-3', !s.active && 'opacity-60')}>
              <div className="flex items-center justify-between gap-2">
                <UserChip user={s.grantee} />
                <Badge tone={s.active ? 'ok' : 'neutral'}>{s.active ? humanize(s.scope) : s.revoked_at ? 'Revoked' : 'Expired'}</Badge>
              </div>
              <div className="mt-1.5 flex items-center justify-between text-[12px] text-muted">
                <span>Approved by {s.approved_by?.full_name ?? '—'} · {s.active ? `expires ${fmtRelative(s.expires_at)}` : fmtDate(s.revoked_at ?? s.expires_at)}</span>
                {s.active && doc.access.actions.includes('document:share_request') && <button onClick={() => revoke.mutate(s.id)} className="text-bad hover:underline">Revoke</button>}
              </div>
            </li>
          ))}
        </ul>
      )}
      <Dialog open={open} onOpenChange={setOpen} title="Request to share" description={`${humanize(doc.sensitivity)} documents can be shared as ${scopes.map(humanize).join(' / ')} for at most ${MAX_DAYS[doc.sensitivity]} days.`}
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button disabled={!who || reason.length < 10} loading={m.isPending} onClick={() => m.mutate()}>Send for approval</Button></>}>
        <div className="space-y-3">
          <Field label="Share with"><Input value={search} onChange={(e) => { setSearch(e.target.value); setWho(null) }} placeholder="Name or service ID" /></Field>
          {search.length >= 2 && !who && <ul className="max-h-40 overflow-y-auto rounded-[4px] border border-line">{dir.data?.map((u) => <li key={u.id}><button onClick={() => setWho(u)} className="w-full px-3 py-2 text-left hover:bg-[#fffdf8]"><UserChip user={u} /></button></li>)}</ul>}
          {who && <div className="rounded-[4px] border border-line px-3 py-2"><UserChip user={who} /></div>}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Scope"><Select value={scope} onChange={(e) => setScope(e.target.value)}>{scopes.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</Select></Field>
            <Field label="Expires in (days)"><Input type="number" min={1} max={MAX_DAYS[doc.sensitivity]} value={days} onChange={(e) => setDays(Math.max(1, Math.min(MAX_DAYS[doc.sensitivity], Number(e.target.value))))} /></Field>
          </div>
          <Field label="Reason"><Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Trial preparation for hearing on 13 Oct" /></Field>
          {m.error && <ErrorState error={m.error} />}
        </div>
      </Dialog>
    </div>
  )
}

// ───────────── §63 certificates ─────────────
export function CertificatesPanel({ doc, version }: { doc: Doc; version: Version }) {
  const qc = useQueryClient()
  const { me } = useAuth()
  const q = useQuery({ queryKey: ['certs', version.id], queryFn: () => unwrap(api.GET('/versions/{versionId}/certificates', { params: { path: { versionId: version.id } } })) })
  const [open, setOpen] = useState(false)
  const [name, setName] = useState(me!.full_name)
  const [desig, setDesig] = useState(`${me!.rank ?? ''}, ${me!.unit_name}`)
  const [purpose, setPurpose] = useState('')
  const m = useMutation({
    mutationFn: () => unwrap(api.POST('/versions/{versionId}/certificates', { params: { path: { versionId: version.id } }, body: { signatory_name: name, signatory_designation: desig, purpose: purpose || undefined } })),
    onSuccess: () => { setOpen(false); qc.invalidateQueries({ queryKey: ['certs', version.id] }); toast.success('Certificate generated') },
  })
  return (
    <div className="space-y-3">
      <div className="border-l-[3px] border-stamp bg-stamp-bg/60 p-3 text-[13px] text-ink-2">
        Bharatiya Sakshya Adhiniyam §63 requires a certificate for electronic records. We pre-fill Part A and the hash for Part B —
        <strong className="font-semibold"> it still needs the signatures of the person in charge and the expert.</strong>
      </div>
      {doc.access.actions.includes('certificate:issue') && <Button className="w-full" onClick={() => setOpen(true)}><Plus className="size-4" />Generate §63 certificate for v{version.version_no}</Button>}
      {!q.data ? <Skeleton className="h-24" /> : q.data.length === 0 ? <EmptyState title="No certificates for this version" /> : q.data.map((c) => (
        <div key={c.id} className="flex gap-3 rounded-[6px] border border-line p-3 animate-pop-in">
          <div className="rounded-[4px] border border-line bg-white p-1.5"><QRCodeSVG value={c.verify_url ?? ''} size={84} /></div>
          <div className="min-w-0 flex-1 text-[13px]">
            <div className="flex items-center justify-between gap-2"><span className="font-mono font-medium">{c.cert_number}</span><Badge tone={c.status === 'ISSUED' ? 'ok' : 'bad'}>{humanize(c.status)}</Badge></div>
            <div className="mt-0.5 text-[12px] text-muted">Issued {fmtDateTime(c.issued_at)} by {c.issued_by.full_name}</div>
            <div className="mt-1 text-[12px]">Verification code <span className="font-mono font-medium tracking-wider">{c.verification_code}</span></div>
            <div className="mt-2 flex gap-2">
              {c.pdf_url && <a href={c.pdf_url} target="_blank" rel="noreferrer"><Button size="sm" variant="secondary"><ExternalLink className="size-3.5" />Open PDF</Button></a>}
              <a href={`/verify/${c.verification_code}`} target="_blank" rel="noreferrer"><Button size="sm" variant="ghost">Public check</Button></a>
            </div>
          </div>
        </div>
      ))}
      <Dialog open={open} onOpenChange={setOpen} title="Generate §63 certificate" description="The person in charge of the computer resource signs Part A; an expert completes Part B."
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={m.isPending} disabled={name.length < 3} onClick={() => m.mutate()}>Generate</Button></>}>
        <div className="space-y-3">
          <Field label="Person in charge (signatory)"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Designation"><Input value={desig} onChange={(e) => setDesig(e.target.value)} /></Field>
          <Field label="Purpose (optional)"><Input value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="Production before Sessions Court, Navagarh" /></Field>
          {m.error && <ErrorState error={m.error} />}
        </div>
      </Dialog>
    </div>
  )
}

// ───────────── Entities ─────────────
export function EntitiesPanel({ version }: { version: Version }) {
  const q = useQuery({ queryKey: ['entities', version.id], queryFn: () => unwrap(api.GET('/versions/{versionId}/entities', { params: { path: { versionId: version.id } } })) })
  if (!q.data) return <Skeleton className="h-40" />
  if (!q.data.length) return <EmptyState title="No entities extracted" body={version.ocr_status === 'NOT_APPLICABLE' ? 'This file has no text layer (OCR for scans is on the roadmap).' : undefined} />
  const groups = q.data.reduce<Record<string, typeof q.data>>((acc, e) => { (acc[e.type] ??= []).push(e); return acc }, {})
  return (
    <div className="space-y-3">
      <p className="text-[12.5px] text-muted">Extracted automatically to speed up search and redaction. Personal data is masked unless you may see the original.</p>
      {Object.entries(groups).map(([type, list]) => (
        <div key={type}>
          <div className="mb-1.5 text-[12px] font-medium text-muted">{humanize(type)}</div>
          <div className="flex flex-wrap gap-1.5">
            {[...new Map(list.map((e) => [e.value, e])).values()].map((e) => (
              <Badge key={e.id} tone={e.is_victim_identifier ? 'victim' : e.is_pii ? 'warn' : 'neutral'}>
                <span className={e.value.includes('█') ? 'font-mono' : ''}>{e.value}</span>
                <span className="text-[10.5px] opacity-60">p{e.page_no}</span>
              </Badge>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
