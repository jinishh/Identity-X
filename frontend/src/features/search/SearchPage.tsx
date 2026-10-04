import { useQuery } from '@tanstack/react-query'
import { EyeOff, FileText, Search, Sparkles } from '@/components/icons'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { api, unwrap, type Schemas } from '@/api/client'
import { SensitivityBadge } from '@/components/domain'
import { Badge, Button, Card, EmptyState, ErrorState, Input, PageHeader, Skeleton, Tip } from '@/components/ui'
import { cn } from '@/lib/cn'
import { DOC_TYPE_LABEL } from '@/lib/format'

function Snippet({ hit }: { hit: Schemas['SearchHit'] }) {
  if (!hit.snippet) return null
  const parts: React.ReactNode[] = []
  let at = 0
  for (const h of hit.highlights ?? []) {
    parts.push(hit.snippet.slice(at, h.start))
    parts.push(<mark key={h.start} className="rounded bg-[#fde68a] px-0.5 text-ink">{hit.snippet.slice(h.start, h.end)}</mark>)
    at = h.end
  }
  parts.push(hit.snippet.slice(at))
  return <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">{parts}</p>
}

export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const mode = (params.get('mode') ?? 'keyword') as 'keyword' | 'fuzzy' | 'semantic'
  const [text, setText] = useState(q)
  const res = useQuery({
    queryKey: ['search', q, mode],
    queryFn: () => unwrap(api.GET('/search', { params: { query: { q, mode, page_size: 50 } } })),
    enabled: q.length >= 2,
  })

  return (
    <>
      <PageHeader title="Search" subtitle="Across case numbers, titles and the text inside documents — only what you are allowed to see." />
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setParams({ q: text.trim(), mode }) }}>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
          <Input autoFocus value={text} onChange={(e) => setText(e.target.value)} className="h-11 pl-9 text-[15px]" placeholder='Try "white SUV near bus stand"' />
        </div>
        <div className="flex rounded-[4px] border border-line-strong bg-surface p-0.5">
          {(['keyword', 'fuzzy', 'semantic'] as const).map((m) => {
            const btn = (
              <button key={m} type="button" disabled={m === 'semantic'} onClick={() => setParams({ q, mode: m })}
                className={cn('rounded px-3 text-[13px] font-medium capitalize transition-colors disabled:opacity-40',
                  mode === m ? 'bg-navy-800 text-white' : 'text-ink-2 hover:bg-sunken')}>
                {m === 'semantic' && <Sparkles className="mr-1 inline size-3.5" />}{m}
              </button>
            )
            return m === 'semantic' ? <Tip key={m} content="Semantic search (pgvector) is on the roadmap">{btn}</Tip> : btn
          })}
        </div>
        <Button type="submit" size="lg">Search</Button>
      </form>

      <div className="mt-5">
        {res.error && <ErrorState error={res.error} />}
        {!q ? <Card><EmptyState icon={<Search className="size-5" />} title="Search the vault" body="Scanned FIRs and statements are indexed page by page. Victim-protected records only ever return redacted snippets to people who can't see the original." /></Card>
          : res.isLoading ? <Skeleton className="h-64" />
            : res.data && (
              <>
                <p className="mb-3 text-[13px] text-muted">{res.data.total} result{res.data.total === 1 ? '' : 's'} · {res.data.took_ms} ms</p>
                {res.data.items.length === 0 ? <Card><EmptyState title="No matches" body="Try fuzzy mode or fewer words." /></Card> : (
                  <div className="space-y-2">
                    {res.data.items.map((h) => (
                      <Card key={h.document.id} className="px-4 py-3.5 transition-shadow hover:shadow-pop">
                        <Link to={`/documents/${h.document.id}`} className="block">
                          <div className="flex flex-wrap items-center gap-2">
                            <FileText className="size-4 text-brand" />
                            <span className="font-medium text-ink hover:underline">{h.document.title}</span>
                            <SensitivityBadge value={h.document.sensitivity} withTip={false} />
                            {h.redacted && <Badge tone="victim"><EyeOff className="size-3" />Redacted snippet</Badge>}
                            <span className="ml-auto text-[12px] text-muted">{h.match_type === 'METADATA' ? 'Title / number match' : `Page ${h.page_no}`}</span>
                          </div>
                          <div className="mt-0.5 text-[12px] text-muted"><span className="font-mono">{h.document.case_number}</span> · {DOC_TYPE_LABEL[h.document.doc_type]} · <span className="font-mono">{h.document.doc_number}</span></div>
                          <Snippet hit={h} />
                        </Link>
                      </Card>
                    ))}
                  </div>
                )}
              </>
            )}
      </div>
    </>
  )
}
