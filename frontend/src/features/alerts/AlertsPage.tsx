import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertOctagon, AlertTriangle, Check, Info, ShieldAlert } from '@/components/icons'
import { useState } from 'react'
import { Link } from 'react-router'
import { api, unwrap, type Schemas } from '@/api/client'
import { Badge, Button, Card, Dialog, EmptyState, Field, PageHeader, Skeleton, Tab, TabList, Tabs, Textarea } from '@/components/ui'
import { cn } from '@/lib/cn'
import { fmtDateTime, fmtRelative, humanize } from '@/lib/format'

const SEV = {
  CRITICAL: { icon: AlertOctagon, cls: 'bg-bad text-white', tone: 'bad' as const },
  HIGH: { icon: ShieldAlert, cls: 'bg-bad-bg text-bad ring-1 ring-bad-line', tone: 'bad' as const },
  MEDIUM: { icon: AlertTriangle, cls: 'bg-warn-bg text-warn ring-1 ring-warn-line', tone: 'warn' as const },
  LOW: { icon: AlertTriangle, cls: 'bg-sunken text-ink-2 ring-1 ring-line', tone: 'neutral' as const },
  INFO: { icon: Info, cls: 'bg-navy-50 text-brand ring-1 ring-navy-100', tone: 'brand' as const },
}

export function AlertsPage() {
  const qc = useQueryClient()
  const [status, setStatus] = useState('open')
  const q = useQuery({ queryKey: ['alerts', 'list'], queryFn: () => unwrap(api.GET('/alerts', { params: { query: { page_size: 100 } } })), refetchInterval: 10_000 })
  const [resolving, setResolving] = useState<Schemas['Alert'] | null>(null)
  const [note, setNote] = useState('')
  const refresh = () => qc.invalidateQueries({ queryKey: ['alerts'] })
  const ack = useMutation({ mutationFn: (id: string) => unwrap(api.POST('/alerts/{alertId}/acknowledge', { params: { path: { alertId: id } } })), onSuccess: refresh })
  const resolve = useMutation({
    mutationFn: () => unwrap(api.POST('/alerts/{alertId}/resolve', { params: { path: { alertId: resolving!.id } }, body: { note } })),
    onSuccess: () => { setResolving(null); setNote(''); refresh() },
  })
  const items = (q.data?.items ?? []).filter((a) => (status === 'open' ? a.status !== 'RESOLVED' : a.status === 'RESOLVED'))

  return (
    <>
      <PageHeader title="Security alerts" subtitle="Raised automatically by integrity checks, malware scanning, access patterns and victim-record access." />
      <Tabs value={status} onValueChange={setStatus}><TabList className="mb-4"><Tab value="open">Open</Tab><Tab value="resolved">Resolved</Tab></TabList></Tabs>
      {!q.data ? <Skeleton className="h-64" /> : items.length === 0 ? <Card><EmptyState title={status === 'open' ? 'No open alerts' : 'Nothing resolved yet'} /></Card> : (
        <div className="space-y-2">
          {items.map((a) => {
            const s = SEV[a.severity as keyof typeof SEV] ?? SEV.INFO
            return (
              <Card key={a.id} className="flex items-start gap-4 px-4 py-3.5 animate-fade-in">
                <span className={cn('mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-[5px]', s.cls)}><s.icon className="size-4" /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{a.title}</span>
                    <Badge tone={s.tone}>{humanize(a.severity)}</Badge>
                    <span className="text-[12px] text-muted">{humanize(a.type)}</span>
                  </div>
                  <p className="mt-0.5 text-[13.5px] text-ink-2">{a.message}</p>
                  <div className="mt-1 flex flex-wrap gap-x-3 text-[12px] text-muted">
                    <span title={fmtDateTime(a.created_at)}>{fmtRelative(a.created_at)}</span>
                    {a.case_number && <Link to={`/cases/${a.case_id}`} className="font-mono text-brand hover:underline">{a.case_number}</Link>}
                    {a.document_id && <Link to={`/documents/${a.document_id}`} className="text-brand hover:underline">Open document</Link>}
                    {a.actor && <span>{a.actor.full_name} · {a.actor.service_id}</span>}
                    {a.acknowledged_by && <span>Acknowledged by {a.acknowledged_by.full_name}</span>}
                    {a.resolution_note && <span>Resolved: “{a.resolution_note}”</span>}
                  </div>
                </div>
                {a.status !== 'RESOLVED' && (
                  <div className="flex shrink-0 gap-2">
                    {a.status === 'OPEN' && <Button size="sm" variant="secondary" onClick={() => ack.mutate(a.id)}>Acknowledge</Button>}
                    <Button size="sm" onClick={() => setResolving(a)}><Check className="size-3.5" />Resolve</Button>
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}
      <Dialog open={!!resolving} onOpenChange={(o) => !o && setResolving(null)} title="Resolve alert" description={resolving?.title}
        footer={<><Button variant="secondary" onClick={() => setResolving(null)}>Cancel</Button><Button disabled={note.trim().length < 5} loading={resolve.isPending} onClick={() => resolve.mutate()}>Resolve</Button></>}>
        <Field label="What was found / done"><Textarea autoFocus value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </Dialog>
    </>
  )
}
