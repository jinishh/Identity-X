import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRightLeft, Check, FileSignature, Lock, Share2, X } from '@/components/icons'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { api, unwrap, type Schemas } from '@/api/client'
import { Badge, Button, Card, Dialog, EmptyState, ErrorState, Field, PageHeader, Skeleton, Tab, TabList, Tabs, Textarea } from '@/components/ui'
import { fmtDate, fmtRelative, humanize } from '@/lib/format'

const ICON = { SHARE: Share2, CUSTODY_TRANSFER: ArrowRightLeft, REVIEW: FileSignature, LEGAL_HOLD_RELEASE: Lock, MEMBERSHIP: Share2 }

function describe(r: Schemas['Request']) {
  const p = r.payload as Record<string, unknown> & { grantee?: Schemas['UserSummary']; to?: Schemas['UserSummary']; from?: Schemas['UserSummary'] }
  switch (r.type) {
    case 'SHARE': return <>Share <strong>{r.document_title}</strong> with <strong>{p.grantee?.full_name}</strong> as <Badge tone="brand">{humanize(String(p.scope))}</Badge> until {fmtDate(String(p.expires_at))}</>
    case 'CUSTODY_TRANSFER': return <>Take custody of <strong>{r.document_title}</strong> from <strong>{p.from?.full_name}</strong></>
    case 'REVIEW': return <>Review <strong>{r.document_title}</strong> (v{String(p.version_no)})</>
    case 'LEGAL_HOLD_RELEASE': return <>Release legal hold on <strong>{r.document_title}</strong></>
    default: return humanize(r.type)
  }
}

export function InboxPage() {
  const qc = useQueryClient()
  const [box, setBox] = useState<'inbox' | 'outbox'>('inbox')
  const q = useQuery({ queryKey: ['requests', box], queryFn: () => unwrap(api.GET('/requests', { params: { query: { box, page_size: 100 } } })) })
  const [rejecting, setRejecting] = useState<Schemas['Request'] | null>(null)
  const [note, setNote] = useState('')
  const decide = useMutation({
    mutationFn: ({ r, decision, note }: { r: Schemas['Request']; decision: 'APPROVE' | 'REJECT'; note?: string }) =>
      unwrap(api.POST('/requests/{requestId}/decision', { params: { path: { requestId: r.id } }, body: { decision, note } })),
    onSuccess: (r) => {
      toast.success(r.status === 'APPROVED' ? (r.type === 'SHARE' ? 'Approved — access granted until expiry' : r.type === 'CUSTODY_TRANSFER' ? 'Custody accepted' : 'Approved') : 'Rejected')
      setRejecting(null); setNote('')
      qc.invalidateQueries({ queryKey: ['requests'] })
    },
  })
  const items = q.data?.items ?? []
  const pending = items.filter((r) => r.status === 'PENDING')
  const done = items.filter((r) => r.status !== 'PENDING')

  return (
    <>
      <PageHeader title="Approvals" subtitle="Shares, custody transfers and reviews that need a second officer." />
      <Tabs value={box} onValueChange={(v) => setBox(v as never)}>
        <TabList className="mb-4"><Tab value="inbox">Waiting for me</Tab><Tab value="outbox">Requested by me</Tab></TabList>
      </Tabs>
      {q.error && <ErrorState error={q.error} />}
      {!q.data ? <Skeleton className="h-64" /> : items.length === 0 ? <Card><EmptyState title="Nothing here" body="Requests will appear here." /></Card> : (
        <div className="space-y-6">
          {[['Pending', pending], ['Decided', done]].map(([label, list]) => (list as Schemas['Request'][]).length > 0 && (
            <section key={label as string}>
              <h2 className="mb-2 smallcaps text-muted">{label as string}</h2>
              <div className="space-y-2">
                {(list as Schemas['Request'][]).map((r) => {
                  const Icon = ICON[r.type as keyof typeof ICON] ?? Share2
                  return (
                    <Card key={r.id} className="flex flex-wrap items-center gap-4 px-4 py-3.5">
                      <div className="flex size-9 shrink-0 items-center justify-center rounded-[5px] bg-navy-50 text-brand"><Icon className="size-4" /></div>
                      <div className="min-w-0 flex-1">
                        <p className="text-[13.5px]">{describe(r)}</p>
                        <p className="mt-0.5 text-[12.5px] text-ink-2">“{r.reason}”</p>
                        <div className="mt-1 flex flex-wrap items-center gap-x-3 text-[12px] text-muted">
                          <Link to={`/cases/${r.case_id}`} className="font-mono text-brand hover:underline">{r.case_number}</Link>
                          <span>requested by {r.requested_by.full_name} · {fmtRelative(r.created_at)}</span>
                          {r.decided_by && <span>· {humanize(r.status)} by {r.decided_by.full_name}{r.decision_note ? ` — “${r.decision_note}”` : ''}</span>}
                        </div>
                      </div>
                      {r.status === 'PENDING' && r.can_decide ? (
                        <div className="flex gap-2">
                          <Button variant="secondary" onClick={() => setRejecting(r)}><X className="size-4" />Reject</Button>
                          <Button variant="success" loading={decide.isPending && decide.variables?.r.id === r.id} onClick={() => decide.mutate({ r, decision: 'APPROVE' })}>
                            <Check className="size-4" />{r.type === 'CUSTODY_TRANSFER' ? 'Accept custody' : 'Approve'}
                          </Button>
                        </div>
                      ) : (
                        <Badge tone={r.status === 'APPROVED' ? 'ok' : r.status === 'REJECTED' ? 'bad' : r.status === 'PENDING' ? 'warn' : 'neutral'}>
                          {r.status === 'PENDING' && box === 'outbox' ? 'Awaiting decision' : humanize(r.status)}
                        </Badge>
                      )}
                    </Card>
                  )
                })}
              </div>
            </section>
          ))}
        </div>
      )}
      {decide.error && <ErrorState error={decide.error} className="mt-4" />}
      <Dialog open={!!rejecting} onOpenChange={(o) => !o && setRejecting(null)} title="Reject request" description="The requester will see your reason."
        footer={<><Button variant="secondary" onClick={() => setRejecting(null)}>Cancel</Button><Button variant="danger" disabled={note.trim().length < 3} loading={decide.isPending} onClick={() => decide.mutate({ r: rejecting!, decision: 'REJECT', note })}>Reject</Button></>}>
        <Field label="Reason"><Textarea autoFocus value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </Dialog>
    </>
  )
}

