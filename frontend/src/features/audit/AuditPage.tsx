import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Link2, Lock, ShieldCheck } from '@/components/icons'
import { useState } from 'react'
import { api, tokenStore, unwrap, type Schemas } from '@/api/client'
import { eventTone, HashChip, Stamp } from '@/components/domain'
import { Badge, Button, Card, Dialog, ErrorState, KV, PageHeader, Select, Skeleton, Tab, TabList, TabPanel, Tabs } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/cn'
import { fmtDateTime, humanize } from '@/lib/format'

const ACTIONS = ['ACCESS_DENIED', 'DOCUMENT_UPLOADED', 'VERSION_CREATED', 'DOCUMENT_VIEWED', 'REDACTED_VIEWED', 'DOCUMENT_DOWNLOADED',
  'SHARE_GRANTED', 'CUSTODY_TRANSFERRED', 'CERTIFICATE_ISSUED', 'PUBLIC_VERIFICATION', 'INTEGRITY_VERIFIED', 'INTEGRITY_FAILED',
  'CHAIN_VERIFIED', 'CHAIN_BROKEN', 'CHECKPOINT_CREATED', 'AUTH_LOGIN_SUCCEEDED', 'AUTH_LOGIN_FAILED', 'DEMO_TAMPER_EXECUTED']

const BREAK_TEXT: Record<string, string> = {
  EVENT_HASH: 'An event was edited after it was written — its contents no longer match its hash.',
  PREV_HASH_LINK: 'An event was inserted or removed — the chain link is broken.',
  SEQ_GAP: 'An event is missing from the sequence.',
  CHECKPOINT_HEAD: 'The chain was rewritten: it no longer matches the sealed checkpoint stored outside the database.',
  CHECKPOINT_MERKLE: 'The chain was rewritten: the Merkle root no longer matches the sealed checkpoint.',
  CHECKPOINT_SIGNATURE: 'A checkpoint signature is invalid — it was forged.',
  CHECKPOINT_WORM_COPY: 'A checkpoint differs from its sealed write-once copy.',
}

export function AuditPage() {
  const { me } = useAuth()
  const qc = useQueryClient()
  const [action, setAction] = useState('')
  const [outcome, setOutcome] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<number | null>(null)
  const events = useQuery({
    queryKey: ['audit', action, outcome, page],
    queryFn: () => unwrap(api.GET('/audit/events', { params: { query: { action: (action || undefined) as never, outcome: (outcome || undefined) as never, page, page_size: 25 } } })),
    placeholderData: keepPreviousData,
  })
  const verify = useMutation({
    mutationFn: () => unwrap(api.POST('/audit/verify-chain')),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['audit'] }); qc.invalidateQueries({ queryKey: ['alerts'] }) },
  })
  const isAuditor = me!.role === 'AUDITOR'
  const r = verify.data

  const exportCsv = async () => {
    const res = await fetch('/api/v1/audit/export', { headers: { Authorization: `Bearer ${tokenStore.get()}` } })
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a'); a.href = url; a.download = 'audit-ledger.csv'; a.click()
  }

  return (
    <>
      <PageHeader title="Audit ledger" subtitle="Append-only and hash-chained. Each event's hash covers the one before it; every 50 events are sealed into a signed checkpoint kept outside the database."
        actions={isAuditor && <>
          <Button variant="secondary" onClick={exportCsv}><Download className="size-4" />Export CSV</Button>
          <Button onClick={() => verify.mutate()} loading={verify.isPending}><ShieldCheck className="size-4" />Verify entire chain</Button>
        </>} />

      {verify.isPending && (
        <Card className="mb-5 overflow-hidden"><div className="px-4 py-3 text-[13px] text-muted">Recomputing every hash and checking sealed checkpoints…</div><div className="h-1 animate-pulse bg-brand" /></Card>
      )}
      {r && !verify.isPending && (
        <Card className={cn('mb-5 overflow-hidden animate-pop-in', r.status === 'VALID' ? 'border-ok-line' : 'border-bad-line')}>
          <div className={cn('flex items-start gap-4 px-5 py-4', r.status === 'VALID' ? 'bg-ok-bg' : 'bg-bad-bg')}>
            <Stamp size="lg" animate tone={r.status === 'VALID' ? 'green' : 'red'} rotate={-5} className="shrink-0">{r.status === 'VALID' ? 'Intact' : 'Broken'}</Stamp>
            <div className="min-w-0">
              <div className={cn('serif text-[20px] font-semibold', r.status === 'VALID' ? 'text-ok' : 'text-bad')}>
                {r.status === 'VALID' ? 'Chain intact' : `Chain broken at event #${r.first_break?.seq}`}
              </div>
              <p className="text-[13.5px] text-ink-2">
                {r.status === 'VALID'
                  ? `All ${r.events_checked.toLocaleString('en-IN')} events recomputed and ${r.checkpoints_checked} sealed checkpoints matched in ${r.duration_ms} ms.`
                  : BREAK_TEXT[r.first_break?.check ?? ''] ?? r.first_break?.check}
              </p>
              {r.first_break && (
                <div className="mt-2 space-y-0.5 font-mono text-[11.5px]">
                  <div>check&nbsp;&nbsp;&nbsp; {r.first_break.check}{r.first_break.checkpoint_id ? ` (checkpoint #${r.first_break.checkpoint_id})` : ''}</div>
                  <div>expected <span className="text-ok">{String(r.first_break.expected).slice(0, 40)}</span></div>
                  <div>actual&nbsp;&nbsp; <span className="text-bad">{String(r.first_break.actual).slice(0, 40)}</span></div>
                  <button onClick={() => setOpen(r.first_break!.seq!)} className="mt-1 font-sans text-[12.5px] text-brand hover:underline">Inspect event #{r.first_break.seq}</button>
                </div>
              )}
            </div>
            <div className="ml-auto shrink-0 text-right text-[12px] text-muted">head #{r.head_seq}<br /><HashChip value={r.head_hash} /></div>
          </div>
        </Card>
      )}
      {verify.error && <ErrorState error={verify.error} className="mb-5" />}

      <Tabs defaultValue="events">
        <TabList className="mb-4"><Tab value="events">Events</Tab>{isAuditor && <Tab value="checkpoints">Sealed checkpoints</Tab>}</TabList>
        <TabPanel value="events">
          <Card>
            <div className="flex flex-wrap gap-2 border-b border-line p-3">
              <Select value={action} onChange={(e) => { setAction(e.target.value); setPage(1) }} className="w-64">
                <option value="">All actions</option>{ACTIONS.map((a) => <option key={a} value={a}>{humanize(a)}</option>)}
              </Select>
              <Select value={outcome} onChange={(e) => { setOutcome(e.target.value); setPage(1) }} className="w-44">
                <option value="">All outcomes</option><option value="SUCCESS">Success</option><option value="DENIED">Denied</option><option value="FAILED">Failed</option>
              </Select>
              <div className="ml-auto self-center text-[12.5px] text-muted">{events.data?.total.toLocaleString('en-IN')} events</div>
            </div>
            {!events.data ? <Skeleton className="m-4 h-96" /> : (
              <div className="overflow-x-auto"><table className="ledger w-full min-w-[680px] text-[13.5px]">
                <thead><tr className="text-left">
                  <th className="px-4 py-2 font-medium">#</th><th className="px-3 py-2 font-medium">Time</th><th className="px-3 py-2 font-medium">Actor</th>
                  <th className="px-3 py-2 font-medium">Event</th><th className="px-3 py-2 font-medium">Case</th><th className="px-4 py-2 font-medium">Hash link</th>
                </tr></thead>
                <tbody>
                  {events.data.items.map((e) => {
                    const tone = eventTone(e)
                    return (
                      <tr key={e.seq} onClick={() => setOpen(e.seq)} className="cursor-pointer hover:bg-[#fffdf8]">
                        <td className="px-4 py-2.5 font-mono text-[12px] text-muted">{e.seq}</td>
                        <td className="px-3 py-2.5 whitespace-nowrap text-muted">{fmtDateTime(e.occurred_at)}</td>
                        <td className="px-3 py-2.5 whitespace-nowrap">{e.actor ? <span>{e.actor.full_name}<span className="block text-[11.5px] text-muted">{e.actor.service_id}</span></span> : <span className="text-muted">System</span>}</td>
                        <td className="px-3 py-2.5">
                          <div className="flex items-center gap-2">
                            <span className={cn('size-2 shrink-0 rounded-full', { ok: 'bg-ok', bad: 'bg-bad', warn: 'bg-saffron', lock: 'bg-lock', neutral: 'bg-faint' }[tone])} />
                            <span className="text-ink">{e.summary}</span>
                          </div>
                          {e.purpose && <div className="ml-4 text-[12px] text-warn">Purpose: {e.purpose}</div>}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-[12px] text-brand">{e.case_number ?? '—'}</td>
                        <td className="px-4 py-2.5 whitespace-nowrap"><span className="flex items-center gap-1"><HashChip value={e.prev_hash} /><Link2 className="size-3 text-faint" /><HashChip value={e.event_hash} /></span></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table></div>
            )}
            <div className="flex items-center justify-end gap-2 border-t border-line px-4 py-2.5">
              <Button size="sm" variant="secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>Newer</Button>
              <span className="text-[12.5px] text-muted">Page {page}</span>
              <Button size="sm" variant="secondary" disabled={!events.data || page * 25 >= events.data.total} onClick={() => setPage(page + 1)}>Older</Button>
            </div>
          </Card>
        </TabPanel>
        {isAuditor && <TabPanel value="checkpoints"><Checkpoints /></TabPanel>}
      </Tabs>
      <EventDialog seq={open} onClose={() => setOpen(null)} />
    </>
  )
}

function Checkpoints() {
  const q = useQuery({ queryKey: ['checkpoints'], queryFn: () => unwrap(api.GET('/audit/checkpoints', { params: { query: { page_size: 100 } } })) })
  if (!q.data) return <Skeleton className="h-64" />
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {q.data.items.map((c: Schemas['Checkpoint']) => (
        <Card key={c.id} className="p-4">
          <div className="flex items-center justify-between"><span className="flex items-center gap-1.5 font-medium"><Lock className="size-4 text-lock" />Checkpoint #{c.id}</span><Badge tone="lock">Sealed</Badge></div>
          <p className="mt-1 text-[12.5px] text-muted">Events {c.from_seq}–{c.to_seq} · {fmtDateTime(c.created_at)}</p>
          <div className="mt-2 border-t border-line pt-2">
            <KV label="Merkle root"><HashChip value={c.merkle_root} /></KV>
            <KV label="Head hash"><HashChip value={c.head_hash} /></KV>
            <KV label="Signed (Ed25519)"><span className="font-mono text-[11.5px]">{c.signing_key_id}</span></KV>
            <KV label="Sealed copy"><span className="font-mono text-[11.5px]">{c.worm_object_key}</span></KV>
          </div>
        </Card>
      ))}
    </div>
  )
}

function EventDialog({ seq, onClose }: { seq: number | null; onClose: () => void }) {
  const q = useQuery({
    queryKey: ['audit-event', seq],
    queryFn: () => unwrap(api.GET('/audit/events/{seq}', { params: { path: { seq: seq! } } })),
    enabled: seq != null,
  })
  return (
    <Dialog open={seq != null} onOpenChange={(o) => !o && onClose()} width="max-w-2xl" title={`Audit event #${seq}`}
      description="event_hash = SHA-256( previous hash ‖ canonical JSON below )">
      {q.data ? (
        <div className="space-y-3">
          <div className="rounded-[6px] border border-line p-3">
            <KV label="Summary">{q.data.summary}</KV>
            <KV label="Time">{fmtDateTime(q.data.occurred_at)}</KV>
            <KV label="Outcome">{humanize(q.data.outcome)}{q.data.reason_code ? ` · ${humanize(q.data.reason_code)}` : ''}</KV>
            <KV label="Previous hash"><HashChip value={q.data.prev_hash} /></KV>
            <KV label="Event hash"><HashChip value={q.data.event_hash} /></KV>
            <KV label="Sealed in checkpoint">{q.data.checkpoint_id ? `#${q.data.checkpoint_id}` : 'Not yet (next seal)'}</KV>
          </div>
          <pre className="max-h-72 overflow-auto rounded-[6px] bg-navy-950 p-3 font-mono text-[11.5px] leading-relaxed text-[#cfe3ff]">{JSON.stringify(JSON.parse(q.data.canonical), null, 2)}</pre>
        </div>
      ) : <Skeleton className="h-64" />}
    </Dialog>
  )
}
