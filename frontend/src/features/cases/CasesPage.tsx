import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { EyeOff, FolderPlus, Search } from '@/components/icons'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { api, unwrap } from '@/api/client'
import { CaseStatusBadge, UserChip } from '@/components/domain'
import { Button, Card, EmptyState, ErrorState, Input, PageHeader, Select, Skeleton } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { CAPACITY_LABEL, CASE_STATUS_LABEL, CATEGORY_LABEL, fmtDate, fmtRelative } from '@/lib/format'

export function CasesPage() {
  const { me } = useAuth()
  const nav = useNavigate()
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') ?? '')
  const status = params.get('status') ?? ''
  const category = params.get('category') ?? ''
  const mine = params.get('mine') === 'true'

  const query = useQuery({
    queryKey: ['cases', { q: params.get('q'), status, category, mine }],
    queryFn: () => unwrap(api.GET('/cases', {
      params: { query: { q: params.get('q') || undefined, status: (status || undefined) as never, category: (category || undefined) as never, mine, page_size: 100 } },
    })),
    placeholderData: keepPreviousData,
  })
  const set = (k: string, v: string) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p) }

  return (
    <>
      <PageHeader title="Cases" subtitle={me!.role === 'AUDITOR' ? 'All cases (metadata only)' : 'Cases you are assigned to or supervise'}
        actions={['INVESTIGATOR', 'SUPERVISOR'].includes(me!.role) && (
          <Button onClick={() => nav('/cases/new')}><FolderPlus className="size-4" />Register case</Button>
        )} />

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <form className="relative min-w-64 flex-1" onSubmit={(e) => { e.preventDefault(); set('q', q.trim()) }}>
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} onBlur={() => set('q', q.trim())} placeholder="Case number, FIR or title" className="pl-9" />
          </form>
          <Select value={status} onChange={(e) => set('status', e.target.value)} className="w-48">
            <option value="">All statuses</option>
            {Object.entries(CASE_STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <Select value={category} onChange={(e) => set('category', e.target.value)} className="w-52">
            <option value="">All categories</option>
            {Object.entries(CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          {me!.role !== 'AUDITOR' && (
            <label className="flex items-center gap-2 px-2 text-[13px] text-ink-2">
              <input type="checkbox" checked={mine} onChange={(e) => set('mine', e.target.checked ? 'true' : '')} className="accent-brand" />
              Only mine
            </label>
          )}
        </div>
        {query.error ? <div className="p-4"><ErrorState error={query.error} /></div>
          : !query.data ? <div className="space-y-2 p-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-11" />)}</div>
            : query.data.items.length === 0 ? <EmptyState title="No cases match" body="Try clearing the filters." />
              : (
                <div className="overflow-x-auto"><table className="ledger w-full min-w-[680px] text-[13.5px]">
                  <thead>
                    <tr className="text-left">
                      <th className="px-4 py-2.5 font-medium">Case</th>
                      <th className="px-3 py-2.5 font-medium">Category</th>
                      <th className="px-3 py-2.5 font-medium">Lead IO</th>
                      <th className="px-3 py-2.5 font-medium">Docs</th>
                      <th className="px-3 py-2.5 font-medium">Your role</th>
                      <th className="px-3 py-2.5 font-medium">Status</th>
                      <th className="px-4 py-2.5 text-right font-medium">Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {query.data.items.map((c) => (
                      <tr key={c.id} onClick={() => nav(`/cases/${c.id}`)} className="cursor-pointer transition-colors hover:bg-[#fffdf8]">
                        <td className="px-4 py-3">
                          <Link to={`/cases/${c.id}`} className="flex items-center gap-1.5 font-mono text-[12.5px] font-medium text-brand hover:underline" onClick={(e) => e.stopPropagation()}>
                            {c.case_number}{c.is_victim_protected && <EyeOff className="size-3.5 text-s-victim" />}
                          </Link>
                          <div className="mt-0.5 max-w-md truncate text-ink">{c.title}</div>
                          <div className="text-[12px] text-muted">FIR {c.fir_number} · {fmtDate(c.fir_date)} · {c.unit_name}</div>
                        </td>
                        <td className="px-3 py-3 text-ink-2">{CATEGORY_LABEL[c.category]}</td>
                        <td className="px-3 py-3"><UserChip user={c.lead_io} /></td>
                        <td className="px-3 py-3 tabular-nums">{c.document_count}</td>
                        <td className="px-3 py-3 text-ink-2">{c.my_capacity ? CAPACITY_LABEL[c.my_capacity] : <span className="text-faint">—</span>}</td>
                        <td className="px-3 py-3"><CaseStatusBadge status={c.status} /></td>
                        <td className="px-4 py-3 text-right text-muted">{fmtRelative(c.updated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table></div>
              )}
      </Card>
    </>
  )
}
