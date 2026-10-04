import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, FileLock2, FlaskConical, HardDrive, Link2Off, RotateCcw } from '@/components/icons'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { api, unwrap, type Schemas } from '@/api/client'
import { Badge, Button, Card, Dialog, ErrorState, Field, Input, PageHeader, Select } from '@/components/ui'
import { cn } from '@/lib/cn'

const SCENARIOS = [
  { id: 'T2_OVERWRITE_STORED_OBJECT', icon: FileLock2, title: 'Overwrite stored evidence', who: 'Attacker with app access',
    body: 'Tries to replace the encrypted file of a sealed version.', expect: 'Refused by write-once storage.', target: 'version', next: null },
  { id: 'T5_REPLACE_CIPHERTEXT', icon: HardDrive, title: 'Edit the encrypted file on disk', who: 'Attacker with server root',
    body: 'Bypasses the lock and flips bytes inside the stored ciphertext.', expect: 'Document verification fails (ciphertext hash + GCM tag).', target: 'version', next: 'Open the document → Integrity → Verify' },
  { id: 'T3_EDIT_AUDIT_ROW', icon: Database, title: 'Edit one audit event', who: 'Database administrator',
    body: 'Disables the append-only trigger and quietly edits a past event (e.g. changes a purpose of access).', expect: 'Chain verification breaks at that event.', target: 'seq', next: 'Audit ledger → Verify entire chain' },
  { id: 'T4_REWRITE_AUDIT_CHAIN', icon: Link2Off, title: 'Rewrite the whole chain', who: 'Sophisticated insider',
    body: 'Edits an event and recomputes every later hash so all links look valid.', expect: 'Caught by the sealed checkpoint stored outside the database.', target: 'seq', next: 'Audit ledger → Verify entire chain' },
] as const

export function DemoPage() {
  const qc = useQueryClient()
  const [active, setActive] = useState<(typeof SCENARIOS)[number] | null>(null)
  const [versionId, setVersionId] = useState('')
  const [seq, setSeq] = useState('')
  const [results, setResults] = useState<Record<string, Schemas['DemoTamperResult']>>({})
  const [confirmReset, setConfirmReset] = useState(false)

  const targets = useQuery({ queryKey: ['demo-targets'], queryFn: () => unwrap(api.GET('/demo/targets')) })
  const health = useQuery({ queryKey: ['health'], queryFn: () => unwrap(api.GET('/health')) })

  const run = useMutation({
    mutationFn: () => unwrap(api.POST('/demo/tamper', { body: { scenario: active!.id as never, version_id: versionId || undefined, seq: seq ? Number(seq) : undefined } })),
    onSuccess: (r) => { setResults({ ...results, [r.scenario]: r }); setActive(null); toast(r.executed ? 'Tamper executed — now go and catch it' : 'Blocked', { description: r.message }) },
  })
  const reset = useMutation({
    mutationFn: () => unwrap(api.POST('/demo/reset')),
    onSuccess: () => { setConfirmReset(false); setResults({}); qc.clear(); toast.success('Demo data restored. Please sign in again.'); setTimeout(() => location.assign('/login'), 800) },
  })

  return (
    <>
      <PageHeader eyebrow="Demo mode only" title="Tamper lab" subtitle="Play the attacker. Each attack is caught by a different layer — then show it being caught."
        actions={<Button variant="secondary" onClick={() => setConfirmReset(true)}><RotateCcw className="size-4" />Reset demo data</Button>} />
      <div className="mb-5 flex flex-wrap gap-2 text-[12.5px]">
        {health.data && Object.entries(health.data.components).map(([k, v]) => (
          <Badge key={k} tone={v === 'ok' ? 'ok' : v === 'disabled' ? 'neutral' : 'warn'}>{k.replace(/_/g, ' ')}: {v}</Badge>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {SCENARIOS.map((s) => {
          const res = results[s.id]
          return (
            <Card key={s.id} className="flex flex-col p-5">
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-[6px] bg-bad-bg text-bad"><s.icon className="size-5" /></span>
                <div>
                  <div className="text-[12px] font-medium text-muted">{s.id.slice(0, 2)} · {s.who}</div>
                  <h3 className="font-semibold">{s.title}</h3>
                </div>
              </div>
              <p className="mt-3 text-[13.5px] text-ink-2">{s.body}</p>
              <p className="mt-1 text-[13px] text-ok">Expected defence: {s.expect}</p>
              {res && (
                <div className={cn('mt-3 rounded-[4px] px-3 py-2 text-[13px]', res.executed ? 'bg-warn-bg text-ink-2' : 'bg-ok-bg text-ok')}>
                  {res.message}
                  {s.next && res.executed && <div className="mt-1 font-medium">Next: {s.next.includes('Audit') ? <Link to="/audit" className="text-brand underline">{s.next}</Link> : s.next}</div>}
                </div>
              )}
              <div className="mt-auto pt-4"><Button variant="danger" onClick={() => { setActive(s); setSeq(String(targets.data?.suggested_seq ?? '')) }}><FlaskConical className="size-4" />Run attack</Button></div>
            </Card>
          )
        })}
      </div>

      <Dialog open={!!active} onOpenChange={(o) => !o && setActive(null)} title={active?.title ?? ''} description={active?.body}
        footer={<><Button variant="secondary" onClick={() => setActive(null)}>Cancel</Button><Button variant="danger" loading={run.isPending} disabled={active?.target === 'version' ? !versionId : !seq} onClick={() => run.mutate()}>Execute</Button></>}>
        {active?.target === 'version' ? (
          <Field label="Target document (hero case)">
            <Select value={versionId} onChange={(e) => setVersionId(e.target.value)}>
              <option value="">Choose…</option>
              {targets.data?.versions.map((v) => <option key={v.version_id} value={v.version_id}>{v.title}</option>)}
            </Select>
          </Field>
        ) : (
          <Field label="Audit event number (seq)" hint={targets.data ? `Suggested: a purpose-of-access event already sealed in a checkpoint (sealed up to #${targets.data.sealed_upto}, head #${targets.data.head_seq}).` : undefined}>
            <Input type="number" value={seq} onChange={(e) => setSeq(e.target.value)} />
          </Field>
        )}
        {run.error && <ErrorState error={run.error} className="mt-3" />}
      </Dialog>
      <Dialog open={confirmReset} onOpenChange={setConfirmReset} title="Reset demo data?" description="Wipes everything and rebuilds the fictional seed world (about 25 seconds). Everyone is signed out."
        footer={<><Button variant="secondary" onClick={() => setConfirmReset(false)}>Cancel</Button><Button variant="danger" loading={reset.isPending} onClick={() => reset.mutate()}>Reset</Button></>} />
    </>
  )
}
