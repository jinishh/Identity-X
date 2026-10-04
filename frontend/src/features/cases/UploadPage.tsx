import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, FileUp, Fingerprint, FlaskConical, ShieldCheck, ShieldX, X } from '@/components/icons'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiProblem, api, postForm, unwrap, type Schemas } from '@/api/client'
import { HashChip, SensitivityBadge } from '@/components/domain'
import { PipelineSteps } from '@/components/Pipeline'
import { Button, Card, CardHeader, ErrorState, Field, Input, Select, Skeleton } from '@/components/ui'
import { cn } from '@/lib/cn'
import { DOC_TYPE_LABEL, fmtBytes } from '@/lib/format'
import { sha256File } from '@/lib/hash'

const ORDER = ['INTERNAL', 'CONFIDENTIAL', 'RESTRICTED', 'VICTIM_PROTECTED']
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.tif,.tiff'

function guessType(name: string): string {
  const n = name.toLowerCase()
  if (n.includes('fir')) return 'FIR'
  if (n.includes('witness') || /\bws\d/.test(n)) return 'WITNESS_STATEMENT'
  if (n.includes('seiz')) return 'SEIZURE_MEMO'
  if (n.includes('fsl') || n.includes('forensic')) return 'FORENSIC_REPORT'
  if (n.includes('cctv') || n.includes('cam')) return 'CCTV_STILL'
  if (n.includes('charge')) return 'CHARGESHEET'
  if (n.includes('medical') || n.includes('mlc')) return 'MEDICAL_REPORT'
  return 'WITNESS_STATEMENT'
}

export function UploadPage() {
  const { caseId = '' } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const c = useQuery({ queryKey: ['case', caseId], queryFn: () => unwrap(api.GET('/cases/{caseId}', { params: { path: { caseId } } })) })

  const [file, setFile] = useState<File | null>(null)
  const [hash, setHash] = useState<string | null>(null)
  const [hashing, setHashing] = useState(false)
  const [title, setTitle] = useState('')
  const [docType, setDocType] = useState('WITNESS_STATEMENT')
  const [sens, setSens] = useState('')
  const [tamper, setTamper] = useState(false)
  const [drag, setDrag] = useState(false)
  const [accepted, setAccepted] = useState<Schemas['UploadAccepted'] | null>(null)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => { if (c.data && !sens) setSens(c.data.default_sensitivity) }, [c.data, sens])

  const pick = async (f: File) => {
    setFile(f); setHash(null); setAccepted(null); upload.reset()
    setTitle(f.name.replace(/\.[^.]+$/, '').split(/[_\s-]+/).filter(Boolean)
      .map((w) => (/\d/.test(w) ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1))).join(' '))
    setDocType(guessType(f.name))
    setHashing(true)
    const [h] = await Promise.all([sha256File(f), new Promise((r) => setTimeout(r, 650))])
    setHash(h); setHashing(false)
  }

  const upload = useMutation({
    mutationFn: async () => {
      let body: Blob = file!
      if (tamper) {  // demo: change one byte AFTER fingerprinting, as if altered in transit
        const bytes = new Uint8Array(await file!.arrayBuffer())
        bytes[bytes.length - 2] ^= 0x01
        body = new Blob([bytes], { type: file!.type })
      }
      const form = new FormData()
      form.append('file', body, file!.name)
      form.append('metadata', JSON.stringify({ title, doc_type: docType, sensitivity: sens, client_sha256: hash }))
      return postForm<Schemas['UploadAccepted']>(`/cases/${caseId}/documents`, form)
    },
    onSuccess: setAccepted,
  })

  const proc = useQuery({
    queryKey: ['processing', accepted?.version_id],
    queryFn: () => unwrap(api.GET('/versions/{versionId}/processing', { params: { path: { versionId: accepted!.version_id } } })),
    enabled: !!accepted,
    refetchInterval: (q) => (['READY', 'FAILED', 'QUARANTINED'].includes(q.state.data?.status ?? '') ? false : 400),
  })
  const done = ['READY', 'FAILED', 'QUARANTINED'].includes(proc.data?.status ?? '')
  useEffect(() => { if (done) qc.invalidateQueries({ queryKey: ['case-docs', caseId] }) }, [done, qc, caseId])

  if (!c.data) return c.error ? <ErrorState error={c.error} /> : <Skeleton className="h-96" />
  const minIdx = ORDER.indexOf(c.data.default_sensitivity)
  const err = upload.error as ApiProblem | null
  const step = accepted ? 3 : hash ? 2 : file ? 1 : 0

  return (
    <div className="mx-auto max-w-4xl">
      <Link to={`/cases/${caseId}`} className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink"><ArrowLeft className="size-3.5" />{c.data.case_number}</Link>
      <h1 className="serif text-[30px] leading-[1.12] font-semibold tracking-[-0.01em]">Upload a document</h1>
      <p className="mt-1 text-muted">The file is fingerprinted on this computer first, then sealed by the server. You will see every step.</p>

      <ol className="my-6 flex items-center gap-2 text-[12.5px]">
        {['Choose file', 'Fingerprint', 'Describe', 'Seal'].map((s, i) => (
          <li key={s} className="flex items-center gap-2">
            <span className={cn('flex size-6 items-center justify-center rounded-full text-[11px] font-semibold',
              i < step ? 'bg-ok text-white' : i === step ? 'bg-brand text-white' : 'bg-sunken text-muted')}>
              {i < step ? <Check className="size-3.5" /> : i + 1}
            </span>
            <span className={i <= step ? 'font-medium text-ink' : 'text-muted'}>{s}</span>
            {i < 3 && <span className="mx-1 h-px w-8 bg-line-strong" />}
          </li>
        ))}
      </ol>

      {!accepted && (
        <div className="grid gap-5 md:grid-cols-[1fr_1.1fr]">
          <Card className="p-4">
            <div onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) pick(f) }}
              onClick={() => input.current?.click()}
              className={cn('flex cursor-pointer flex-col items-center justify-center rounded-[6px] border-2 border-dashed px-4 py-10 text-center transition-colors',
                drag ? 'border-brand bg-navy-50' : 'border-line-strong hover:border-brand/60 hover:bg-[#fffdf8]')}>
              <FileUp className="mb-2 size-7 text-brand" />
              <p className="font-medium">{file ? file.name : 'Drop a file or click to choose'}</p>
              <p className="mt-1 text-[12px] text-muted">{file ? fmtBytes(file.size) : 'PDF, JPEG, PNG or TIFF · up to 50 MB'}</p>
              <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) pick(f); e.target.value = '' }} />
            </div>
            {file && (
              <div className="mt-4 rounded-[6px] border border-line bg-canvas p-3">
                <div className="flex items-center gap-2 text-[13px] font-medium"><Fingerprint className="size-4 text-brand" />Browser fingerprint (SHA-256)</div>
                {hashing ? (
                  <div className="mt-2"><div className="h-1.5 overflow-hidden rounded-full bg-sunken"><div className="h-full w-1/2 animate-pulse rounded-full bg-brand" /></div>
                    <p className="mt-1.5 text-[12px] text-muted">Computing on this device…</p></div>
                ) : hash && (
                  <p className="mt-2 font-mono text-[11.5px] leading-relaxed break-all text-ink-2 animate-step-in">{hash}</p>
                )}
                <p className="mt-2 text-[11.5px] text-muted">The server recomputes this. If even one byte changes on the way, the upload is rejected.</p>
              </div>
            )}
          </Card>

          <Card>
            <CardHeader title="Describe the document" />
            <form className="space-y-4 p-4" onSubmit={(e) => { e.preventDefault(); upload.mutate() }}>
              <Field label="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} disabled={!file} placeholder="Witness statement WS-3 (bus conductor)" /></Field>
              <Field label="Document type">
                <Select value={docType} onChange={(e) => setDocType(e.target.value)} disabled={!file}>
                  {Object.entries(DOC_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </Select>
              </Field>
              <Field label="Sensitivity" hint={minIdx > 0 ? `This case requires at least ${ORDER[minIdx].replace('_', ' ').toLowerCase()}.` : undefined}>
                <div className="flex flex-wrap gap-1.5">
                  {ORDER.map((s, i) => (
                    <button key={s} type="button" disabled={!file || i < minIdx} onClick={() => setSens(s)}
                      className={cn('rounded-[4px] p-0.5 transition-all disabled:opacity-35', sens === s ? 'ring-2 ring-brand ring-offset-1 ring-offset-surface' : '')}>
                      <SensitivityBadge value={s} withTip={false} />
                    </button>
                  ))}
                </div>
              </Field>
              <label className="flex items-start gap-2 rounded-[4px] border border-dashed border-line-strong px-3 py-2 text-[12px] text-muted">
                <input type="checkbox" checked={tamper} onChange={(e) => setTamper(e.target.checked)} className="mt-0.5 accent-bad" />
                <span><FlaskConical className="mr-1 inline size-3.5" />Demo: alter one byte after fingerprinting (simulates tampering in transit)</span>
              </label>
              {err && (
                <div className="flex items-start gap-2 rounded-[6px] border border-bad-line bg-bad-bg px-3 py-2.5 text-[13px]">
                  <ShieldX className="mt-0.5 size-4 shrink-0 text-bad" />
                  <div><p className="font-semibold text-bad">{err.message}</p><p className="text-ink-2">{err.detail}</p>
                    {err.code === 'HASH_MISMATCH' && <p className="mt-1 text-[12px] text-muted">Nothing was stored. The attempt and a security alert were recorded.</p>}</div>
                </div>
              )}
              <Button type="submit" size="lg" className="w-full" loading={upload.isPending} disabled={!hash || title.length < 3}>
                <ShieldCheck className="size-4" />Seal & upload
              </Button>
            </form>
          </Card>
        </div>
      )}

      {accepted && (
        <Card className="animate-pop-in">
          <CardHeader title={proc.data?.status === 'READY' ? 'Sealed into the vault' : proc.data?.status === 'QUARANTINED' ? 'Quarantined' : 'Sealing…'}
            subtitle={<span className="font-mono">{title}</span>}
            actions={proc.data?.status === 'READY' && <Button onClick={() => nav(`/documents/${accepted.document_id}`)}>Open document</Button>} />
          <div className="p-5">
            {proc.data ? <PipelineSteps steps={proc.data.steps} /> : <Skeleton className="h-64" />}
          </div>
          {proc.data?.status === 'READY' && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line bg-ok-bg/60 px-5 py-3 text-[13px] animate-fade-in">
              <span className="flex items-center gap-1.5 font-medium text-ok"><ShieldCheck className="size-4" />Receipt</span>
              <span>Version <strong>v{accepted.version_no}</strong></span>
              <span className="flex items-center gap-1.5">SHA-256 <HashChip value={accepted.sha256} /></span>
              <button onClick={() => { setFile(null); setHash(null); setAccepted(null); upload.reset() }} className="ml-auto text-brand hover:underline">Upload another</button>
            </div>
          )}
          {proc.data?.status === 'QUARANTINED' && (
            <div className="flex items-center gap-2 border-t border-bad-line bg-bad-bg px-5 py-3 text-[13px] text-bad"><X className="size-4" />Malware signature found. The file was isolated and never entered the vault. Security has been alerted.</div>
          )}
        </Card>
      )}
    </div>
  )
}
