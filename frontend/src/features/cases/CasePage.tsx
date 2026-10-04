import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CalendarClock, EyeOff, FileText, Gavel, ShieldBan, Upload, UserPlus, Users } from '@/components/icons'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { ApiProblem, api, unwrap, type Schemas } from '@/api/client'
import { CaseStatusBadge, ProcessingBadge, SensitivityBadge, Timeline, UserChip } from '@/components/domain'
import { Badge, Button, Card, Dialog, EmptyState, ErrorState, Field, Input, Select, Skeleton, Tab, TabList, TabPanel, Tabs, Textarea } from '@/components/ui'
import { CAPACITY_LABEL, CASE_STATUS_LABEL, CATEGORY_LABEL, DENY_TEXT, DOC_TYPE_LABEL, fmtDate, fmtRelative } from '@/lib/format'

const NEXT: Record<string, string[]> = {
  REGISTERED: ['UNDER_INVESTIGATION'], UNDER_INVESTIGATION: ['CHARGESHEET_FILED', 'FINAL_REPORT_FILED'],
  CHARGESHEET_FILED: ['UNDER_TRIAL'], FINAL_REPORT_FILED: ['CLOSED'], UNDER_TRIAL: ['DISPOSED'], DISPOSED: ['CLOSED'],
}

export function CasePage() {
  const { caseId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'documents'
  const c = useQuery({ queryKey: ['case', caseId], queryFn: () => unwrap(api.GET('/cases/{caseId}', { params: { path: { caseId } } })) })

  if (c.error) return <DeniedCase error={c.error} />
  if (!c.data) return <div className="space-y-3"><Skeleton className="h-24" /><Skeleton className="h-96" /></div>
  const k = c.data
  const can = (p: string) => k.my_permissions.includes(p)

  return (
    <>
      <Link to="/cases" className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink"><ArrowLeft className="size-3.5" />Cases</Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[13px] font-medium text-brand">{k.case_number}</span>
            <CaseStatusBadge status={k.status} />
            {k.is_victim_protected && <Badge tone="victim"><EyeOff className="size-3" />Victim protected</Badge>}
          </div>
          <h1 className="serif mt-1 text-[30px] leading-[1.12] font-semibold tracking-[-0.01em]">{k.title}</h1>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-muted">
            <span>FIR {k.fir_number} · {fmtDate(k.fir_date)}</span>
            <span>{k.unit_name}</span>
            <span>{CATEGORY_LABEL[k.category]}</span>
            <span>{k.offence_sections.join(', ')}</span>
            {k.next_hearing_date && <span className="flex items-center gap-1 text-warn"><CalendarClock className="size-3.5" />Hearing {fmtDate(k.next_hearing_date)} · {k.court_name}</span>}
          </div>
        </div>
        <div className="flex gap-2">
          {can('case:change_status') && NEXT[k.status] && <StatusButton c={k} />}
          {can('document:upload') && (
            <Link to={`/cases/${k.id}/upload`}><Button><Upload className="size-4" />Upload document</Button></Link>
          )}
        </div>
      </div>

      {k.is_victim_protected && (
        <div className="mb-6 flex max-w-4xl items-start gap-3 border-l-[3px] border-s-victim bg-s-victim-bg/70 px-4 py-3 text-[13.5px]">
          <EyeOff className="mt-0.5 size-4 shrink-0 text-s-victim" />
          <div>
            <span className="font-semibold text-s-victim">Victim identity protected under BNS §72.</span>{' '}
            <span className="text-ink-2">The victim is referred to as <strong>{k.victim_pseudonym}</strong>. Originals are restricted to the lead IO, supervisor and prosecutor and every view needs a stated purpose; other members see auto-redacted copies.</span>
          </div>
        </div>
      )}

      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })}>
        <TabList className="mb-4">
          <Tab value="documents"><FileText className="size-4" />Documents <span className="text-faint">{k.document_count}</span></Tab>
          <Tab value="members"><Users className="size-4" />People</Tab>
          <Tab value="timeline"><Gavel className="size-4" />Chain of custody</Tab>
        </TabList>
        <TabPanel value="documents"><DocumentsTab caseId={k.id} canUpload={can('document:upload')} /></TabPanel>
        <TabPanel value="members"><MembersTab c={k} /></TabPanel>
        <TabPanel value="timeline"><TimelineTab caseId={k.id} /></TabPanel>
      </Tabs>
    </>
  )
}

function DeniedCase({ error }: { error: unknown }) {
  const p = error instanceof ApiProblem ? error : null
  if (p?.status !== 403) return <ErrorState error={error} />
  return (
    <div className="mx-auto mt-10 max-w-lg animate-pop-in">
      <Card className="overflow-hidden border-bad-line">
        <div className="bg-bad-bg px-6 py-6 text-center">
          <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-[5px] bg-white text-bad ring-1 ring-bad-line"><ShieldBan className="size-6" /></div>
          <h1 className="text-lg font-semibold text-bad">Access denied</h1>
          <p className="mt-1 text-[13.5px] text-ink-2">{DENY_TEXT[p.denyReason ?? ''] ?? p.detail}</p>
        </div>
        <div className="space-y-2 px-6 py-4 text-[13px] text-ink-2">
          <p>This attempt has been written to the tamper-evident audit ledger and is visible to the case supervisor and the audit cell.</p>
          <p className="text-muted">If you need this case for an emergency, contact the supervising officer. (Break-glass access is on the roadmap.)</p>
        </div>
        <div className="flex justify-end border-t border-line px-6 py-3"><Link to="/cases"><Button variant="secondary">Back to my cases</Button></Link></div>
      </Card>
    </div>
  )
}

function StatusButton({ c }: { c: Schemas['Case'] }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [to, setTo] = useState(NEXT[c.status][0])
  const [note, setNote] = useState('')
  const m = useMutation({
    mutationFn: () => unwrap(api.POST('/cases/{caseId}/status', { params: { path: { caseId: c.id } }, body: { status: to as never, note } })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['case', c.id] }); setOpen(false); toast.success('Status updated') },
  })
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}><Gavel className="size-4" />Change status</Button>
      <Dialog open={open} onOpenChange={setOpen} title="Change case status" description={`Currently: ${CASE_STATUS_LABEL[c.status]}`}
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={m.isPending} disabled={note.length < 5} onClick={() => m.mutate()}>Update</Button></>}>
        <div className="space-y-3">
          <Field label="New status"><Select value={to} onChange={(e) => setTo(e.target.value)}>{NEXT[c.status].map((s) => <option key={s} value={s}>{CASE_STATUS_LABEL[s]}</option>)}</Select></Field>
          <Field label="Note"><Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reason for the change" /></Field>
          {m.error && <ErrorState error={m.error} />}
        </div>
      </Dialog>
    </>
  )
}

function DocumentsTab({ caseId, canUpload }: { caseId: string; canUpload: boolean }) {
  const nav = useNavigate()
  const q = useQuery({
    queryKey: ['case-docs', caseId],
    queryFn: () => unwrap(api.GET('/cases/{caseId}/documents', { params: { path: { caseId }, query: { page_size: 100 } } })),
    refetchInterval: (query) => query.state.data?.items.some((d) => d.current_version?.processing_status !== 'READY' && d.current_version?.processing_status !== 'QUARANTINED') ? 1500 : false,
  })
  if (q.error) return <ErrorState error={q.error} />
  if (!q.data) return <Skeleton className="h-80" />
  if (!q.data.items.length) return (
    <Card><EmptyState title="No documents yet" body="Upload the FIR to start the case file."
      action={canUpload && <Link to={`/cases/${caseId}/upload`}><Button><Upload className="size-4" />Upload document</Button></Link>} /></Card>
  )
  return (
    <Card>
      <div className="overflow-x-auto"><table className="ledger w-full min-w-[680px] text-[13.5px]">
        <thead>
          <tr className="text-left">
            <th className="px-4 py-2.5 font-medium">Document</th>
            <th className="px-3 py-2.5 font-medium">Sensitivity</th>
            <th className="px-3 py-2.5 font-medium">Version</th>
            <th className="px-3 py-2.5 font-medium">Custodian</th>
            <th className="px-3 py-2.5 font-medium">Integrity</th>
            <th className="px-4 py-2.5 text-right font-medium">Updated</th>
          </tr>
        </thead>
        <tbody>
          {q.data.items.map((d) => (
            <tr key={d.id} onClick={() => nav(`/documents/${d.id}`)} className="cursor-pointer transition-colors hover:bg-[#fffdf8]">
              <td className="px-4 py-3">
                <div className="flex items-center gap-2.5">
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-[4px] bg-navy-50 text-brand"><FileText className="size-4" /></div>
                  <div className="min-w-0">
                    <div className="truncate font-medium text-ink">{d.title}</div>
                    <div className="text-[12px] text-muted"><span className="font-mono">{d.doc_number}</span> · {DOC_TYPE_LABEL[d.doc_type]}</div>
                  </div>
                </div>
              </td>
              <td className="px-3 py-3"><SensitivityBadge value={d.sensitivity} /></td>
              <td className="px-3 py-3 tabular-nums">v{d.current_version?.version_no ?? 1}{d.version_count > 1 && <span className="text-muted"> of {d.version_count}</span>}</td>
              <td className="px-3 py-3"><UserChip user={d.custodian} /></td>
              <td className="px-3 py-3"><ProcessingBadge status={d.current_version?.processing_status} />{d.retention_state === 'LEGAL_HOLD' && <Badge tone="lock" className="ml-1">Legal hold</Badge>}</td>
              <td className="px-4 py-3 text-right text-muted">{fmtRelative(d.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table></div>
    </Card>
  )
}

function MembersTab({ c }: { c: Schemas['Case'] }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['members', c.id], queryFn: () => unwrap(api.GET('/cases/{caseId}/members', { params: { path: { caseId: c.id } } })) })
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [pick, setPick] = useState<Schemas['UserSummary'] | null>(null)
  const [cap, setCap] = useState('CO_IO')
  const dir = useQuery({
    queryKey: ['directory', search],
    queryFn: () => unwrap(api.GET('/directory', { params: { query: { q: search } } })),
    enabled: search.length >= 2,
  })
  const add = useMutation({
    mutationFn: () => unwrap(api.POST('/cases/{caseId}/members', { params: { path: { caseId: c.id } }, body: { user_id: pick!.id, capacity: cap as never } })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['members', c.id] }); setOpen(false); setPick(null); setSearch(''); toast.success('Member added') },
  })
  const capFor = (role: string) => ({ INVESTIGATOR: 'CO_IO', PROSECUTOR: 'PROSECUTOR', FORENSIC_EXPERT: 'FORENSIC', SUPERVISOR: 'SUPERVISOR' } as Record<string, string>)[role]

  return (
    <Card>
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div className="text-[13px] text-muted">Access to this case comes from these assignments. Supervisors of the station are included automatically.</div>
        {c.my_permissions.includes('case:manage_members') && <Button size="sm" variant="secondary" onClick={() => setOpen(true)}><UserPlus className="size-4" />Add person</Button>}
      </div>
      {!q.data ? <Skeleton className="m-4 h-40" /> : (
        <ul className="divide-y divide-line">
          {q.data.map((m) => (
            <li key={m.id} className="flex items-center justify-between gap-3 px-4 py-3">
              <UserChip user={m.user} sub={`${m.user.rank ?? ''} · ${m.user.unit_name}`} />
              <div className="flex items-center gap-2 text-[12px] text-muted">
                {m.expires_at && <span>until {fmtDate(m.expires_at)}</span>}
                <Badge tone={m.capacity === 'LEAD_IO' ? 'brand' : 'neutral'}>{CAPACITY_LABEL[m.capacity]}</Badge>
                {m.implicit && <Badge tone="lock">By jurisdiction</Badge>}
              </div>
            </li>
          ))}
        </ul>
      )}
      <Dialog open={open} onOpenChange={setOpen} title="Add a person to this case"
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button disabled={!pick} loading={add.isPending} onClick={() => add.mutate()}>Add</Button></>}>
        <div className="space-y-3">
          <Field label="Find officer, prosecutor or forensic expert">
            <Input autoFocus value={search} onChange={(e) => { setSearch(e.target.value); setPick(null) }} placeholder="Name or service ID" />
          </Field>
          {search.length >= 2 && !pick && (
            <ul className="max-h-48 overflow-y-auto rounded-[4px] border border-line">
              {dir.data?.map((u) => (
                <li key={u.id}><button type="button" onClick={() => { setPick(u); setCap(capFor(u.role) ?? 'CO_IO') }} className="w-full px-3 py-2 text-left hover:bg-[#fffdf8]"><UserChip user={u} /></button></li>
              ))}
            </ul>
          )}
          {pick && <div className="rounded-[4px] border border-line px-3 py-2"><UserChip user={pick} /></div>}
          <Field label="Capacity"><Select value={cap} onChange={(e) => setCap(e.target.value)}>{['CO_IO', 'FORENSIC', 'PROSECUTOR', 'SUPERVISOR'].map((x) => <option key={x} value={x}>{CAPACITY_LABEL[x]}</option>)}</Select></Field>
          {add.error && <ErrorState error={add.error} />}
        </div>
      </Dialog>
    </Card>
  )
}

function TimelineTab({ caseId }: { caseId: string }) {
  const q = useQuery({ queryKey: ['case-timeline', caseId], queryFn: () => unwrap(api.GET('/cases/{caseId}/timeline', { params: { path: { caseId }, query: { page_size: 100 } } })) })
  if (q.error) return <ErrorState error={q.error} />
  return (
    <Card className="px-5 pt-5">
      <p className="mb-4 text-[13px] text-muted">Every action on this case, newest first. Each entry is a link in the hash chain — hover a hash to see it.</p>
      {q.data ? <Timeline events={q.data.items} /> : <Skeleton className="mb-5 h-64" />}
    </Card>
  )
}
