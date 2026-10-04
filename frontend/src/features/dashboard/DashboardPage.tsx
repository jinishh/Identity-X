import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'
import { api, unwrap } from '@/api/client'
import { CaseStatusBadge, KpiCard, Stamp, Timeline } from '@/components/domain'
import { EyeOff } from '@/components/icons'
import { Card, CardHeader, EmptyState, ErrorState, Skeleton } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { CASE_STATUS_LABEL, DOC_TYPE_LABEL, ROLE_LABEL, fmtDate, fmtDateTime, fmtRelative } from '@/lib/format'

const today = new Intl.DateTimeFormat('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Kolkata' })

export function DashboardPage() {
  const { me } = useAuth()
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['dashboard'], queryFn: () => unwrap(api.GET('/dashboard/summary')) })
  const d = q.data
  const showCases = !['AUDITOR', 'ADMIN', 'SUPER_ADMIN'].includes(me!.role)
  const chainOk = d?.integrity.last_chain_check?.status !== 'BROKEN'

  return (
    <>
      <div className="mb-7 border-b border-line pb-5">
        <div className="smallcaps text-muted">{today.format(new Date())}</div>
        <h1 className="serif mt-1 text-[32px] leading-[1.1] font-semibold tracking-[-0.01em]">{me!.unit_name}</h1>
        <p className="mt-1.5 text-[14.5px] text-ink-2">
          {ROLE_LABEL[me!.role]} · {me!.full_name}, {me!.rank}
        </p>
      </div>

      {q.error && <ErrorState error={q.error} className="mb-5" />}

      {/* figures, ruled like the summary line of a register */}
      <Card className="grid grid-cols-2 divide-line max-md:divide-y md:grid-cols-4 md:divide-x">
        {d ? d.kpis.map((k) => <KpiCard key={k.key} kpi={k} />)
          : Array.from({ length: 4 }, (_, i) => <div key={i} className="p-5"><Skeleton className="h-14" /></div>)}
      </Card>

      <div className="mt-8 grid gap-8 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <div className="space-y-8">
          {showCases && (
            <section>
              <div className="mb-2 flex items-baseline justify-between">
                <h2 className="serif text-[20px] font-semibold">{me!.role === 'SUPERVISOR' ? 'Open cases at your station' : 'Your open cases'}</h2>
                <Link to="/cases" className="text-[13.5px] text-brand underline decoration-brand/30 underline-offset-[3px] hover:decoration-brand">every case →</Link>
              </div>
              {!d ? <Skeleton className="h-64" /> : d.my_cases.length === 0 ? <Card><EmptyState title="Nothing assigned to you" body="Cases appear here once you are added as an IO, supervisor, prosecutor or expert." /></Card> : (
                <Card className="overflow-hidden">
                  <div className="overflow-x-auto"><table className="ledger w-full min-w-[680px] text-[13.5px]">
                    <thead><tr className="text-left">
                      <th className="px-5 pt-3 pb-1.5">Case</th>
                      <th className="px-3 pt-3 pb-1.5">Stage</th>
                      <th className="px-3 pt-3 pb-1.5 text-right">Files</th>
                      <th className="px-5 pt-3 pb-1.5 text-right">Next</th>
                    </tr></thead>
                    <tbody>
                      {d.my_cases.map((c) => (
                        <tr key={c.id} onClick={() => nav(`/cases/${c.id}`)} className="cursor-pointer transition-colors hover:bg-[#fffdf8]">
                          <td className="px-5 py-3">
                            <div className="flex items-center gap-1.5 font-mono text-[12.5px] text-brand">
                              {c.case_number}
                              {c.is_victim_protected && <EyeOff weight="bold" className="size-3.5 text-s-victim" aria-label="victim protected" />}
                            </div>
                            <div className="mt-0.5 text-ink">{c.title}</div>
                          </td>
                          <td className="px-3 py-3"><CaseStatusBadge status={c.status} /></td>
                          <td className="px-3 py-3 text-right text-ink-2">{c.document_count}</td>
                          <td className="px-5 py-3 text-right text-[13px] whitespace-nowrap">
                            {c.next_hearing_date
                              ? <span className="font-medium text-warn">hearing {fmtDate(c.next_hearing_date)}</span>
                              : <span className="text-muted">touched {fmtRelative(c.updated_at)}</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table></div>
                </Card>
              )}
            </section>
          )}

          {d && (
            <section className="grid gap-8 md:grid-cols-2">
              <div>
                <h2 className="serif mb-3 text-[18px] font-semibold">Documents held, by kind</h2>
                <Tally rows={d.documents_by_type.slice(0, 8).map((x) => [DOC_TYPE_LABEL[x.key] ?? x.key, x.count])} />
              </div>
              <div>
                <h2 className="serif mb-3 text-[18px] font-semibold">Cases, by stage</h2>
                <Tally rows={[...d.cases_by_status].sort((a, b) => b.count - a.count).map((x) => [CASE_STATUS_LABEL[x.key] ?? x.key, x.count])} />
              </div>
            </section>
          )}
        </div>

        <aside className="space-y-6">
          {d && (
            <div className="flex items-start gap-4 rounded-[6px] border border-line bg-surface px-5 py-4">
              <div className="pt-1">
                {chainOk ? <Stamp size="sm" rotate={-6}>Intact</Stamp> : <Stamp tone="red" size="sm" rotate={-6}>Broken</Stamp>}
              </div>
              <div className="min-w-0 text-[13.5px]">
                <p className="text-ink">
                  <span className="serif text-[18px] font-semibold">{d.integrity.versions_verified.toLocaleString('en-IN')}</span>
                  <span className="text-muted"> of {d.integrity.versions_total.toLocaleString('en-IN')} files re-verified</span>
                </p>
                <p className="mt-0.5 text-muted">
                  {d.integrity.last_chain_check
                    ? <>Last full ledger check {fmtDateTime(d.integrity.last_chain_check.at)} — {d.integrity.last_chain_check.events_checked} entries.</>
                    : 'The ledger has not been checked yet.'}
                </p>
              </div>
            </div>
          )}
          <Card>
            <CardHeader title="Latest in the ledger" subtitle={me!.role === 'AUDITOR' ? 'Everything, everywhere' : 'On cases you can see'} />
            <div className="max-h-[560px] overflow-y-auto px-5 py-4">
              {d ? (d.recent_activity.length ? <Timeline events={d.recent_activity} showCase /> : <p className="text-muted">Nothing yet.</p>) : <Skeleton className="h-48" />}
            </div>
          </Card>
        </aside>
      </div>
    </>
  )
}

/** A hand-totted tally: label, dotted leader, count, and a hairline proportional rule. */
function Tally({ rows }: { rows: [string, number][] }) {
  const max = Math.max(1, ...rows.map((r) => r[1]))
  return (
    <ul className="space-y-2">
      {rows.map(([label, n]) => (
        <li key={label} className="text-[13.5px]">
          <div className="flex items-baseline gap-2">
            <span className="text-ink-2">{label}</span>
            <span className="mb-1 flex-1 border-b border-dotted border-line-strong" />
            <span className="font-medium text-ink">{n}</span>
          </div>
          <div className="mt-1 h-[3px] bg-sunken"><div className="h-full bg-navy-600/70" style={{ width: `${(n / max) * 100}%` }} /></div>
        </li>
      ))}
    </ul>
  )
}
