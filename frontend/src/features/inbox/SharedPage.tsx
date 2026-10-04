import { useQuery } from '@tanstack/react-query'
import { Clock } from '@/components/icons'
import { useNavigate } from 'react-router'
import { api, unwrap } from '@/api/client'
import { Badge, Card, EmptyState, PageHeader, Skeleton } from '@/components/ui'
import { fmtRelative, humanize } from '@/lib/format'

export function SharedPage() {
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['shared-with-me'], queryFn: () => unwrap(api.GET('/shared-with-me')) })
  return (
    <>
      <PageHeader title="Shared with me" subtitle="Documents from other cases you have been given time-limited access to." />
      {!q.data ? <Skeleton className="h-48" /> : q.data.length === 0 ? <Card><EmptyState title="Nothing shared with you right now" /></Card> : (
        <Card>
          <ul className="divide-y divide-line">
            {q.data.map((s) => (
              <li key={s.id}>
                <button onClick={() => nav(`/documents/${s.document_id}`)} className="flex w-full items-center gap-4 px-4 py-3 text-left hover:bg-[#fffdf8]">
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{s.document_title}</div>
                    <div className="text-[12px] text-muted"><span className="font-mono">{s.case_number}</span> · shared by {s.created_by?.full_name}, approved by {s.approved_by?.full_name}</div>
                  </div>
                  <Badge tone="brand">{humanize(s.scope)}</Badge>
                  <span className="flex items-center gap-1 text-[12px] text-warn"><Clock className="size-3.5" />expires {fmtRelative(s.expires_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  )
}

