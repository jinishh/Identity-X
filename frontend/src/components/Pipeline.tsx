import { Check, Circle, Loader2, Minus, X } from '@/components/icons'
import type { Schemas } from '@/api/client'
import { cn } from '@/lib/cn'
import { fmtDateTime, shortHash } from '@/lib/format'

export const STEP_LABEL: Record<string, [string, string]> = {
  RECEIVE: ['Received', 'Bytes streamed to an isolated staging area'],
  HASH_MATCH: ['Fingerprint matched', 'SHA-256 from your browser equals the server’s'],
  VALIDATE: ['File validated', 'Type checked by file signature, size and extension'],
  MALWARE_SCAN: ['Malware scan', 'Known-signature scan before anything is stored'],
  ENCRYPT: ['Encrypted', 'AES-256-GCM with a fresh key for this file'],
  STORE_WORM: ['Stored write-once', 'Cannot be overwritten or deleted'],
  SIGN_MANIFEST: ['Manifest signed', 'Ed25519 signature over the canonical manifest'],
  AUDIT_ANCHOR: ['Anchored in audit chain', 'Manifest hash sealed into the ledger'],
  OCR: ['Text extracted', 'Makes the document searchable'],
  EXTRACT_ENTITIES: ['Entities & PII detected', 'Sections, vehicles, phones, Aadhaar, victim identifiers'],
  REDACT: ['Auto-redaction', 'Redacted copy for victim-protected records'],
  INDEX: ['Indexed for search', 'Full-text index, access-aware'],
  EMBED: ['Semantic embedding', 'Roadmap'],
}

function detailLine(s: Schemas['ProcessingStep']): string | null {
  const d = (s.detail ?? {}) as Record<string, unknown>
  switch (s.step) {
    case 'RECEIVE': return d.bytes ? `${Number(d.bytes).toLocaleString('en-IN')} bytes · ${d.filename}` : null
    case 'HASH_MATCH': return d.sha256 ? `SHA-256 ${shortHash(String(d.sha256), 10)}` : null
    case 'VALIDATE': return d.detected_mime ? String(d.detected_mime) : null
    case 'MALWARE_SCAN': return d.result ? `${d.result}${d.signature ? ` · ${d.signature}` : ''} · ${d.note ?? d.engine}` : null
    case 'ENCRYPT': return d.key ? String(d.key) : null
    case 'STORE_WORM': return d.retain_until ? `Retained until ${fmtDateTime(String(d.retain_until)).replace(/,.*$/, '')}` : null
    case 'SIGN_MANIFEST': return d.kid ? `${d.kid} · manifest ${shortHash(String(d.manifest_sha256), 8)}` : null
    case 'AUDIT_ANCHOR': return d.audit_seq ? `Audit event #${d.audit_seq} · ${shortHash(String(d.event_hash), 8)}` : null
    case 'OCR': return d.pages ? `${d.pages} page(s) · ${d.method}` : d.reason ? `${d.reason} — ${d.note}` : null
    case 'EXTRACT_ENTITIES': {
      const f = (d.found ?? {}) as Record<string, number>
      const parts = Object.entries(f).map(([k, v]) => `${v} ${k.toLowerCase().replace(/_/g, ' ')}`)
      return parts.length ? parts.join(' · ') : s.status === 'DONE' ? 'Nothing sensitive found' : null
    }
    case 'REDACT': return d.spans != null ? `${d.spans} span(s) blacked out` : d.reason ? String(d.reason) : null
    case 'INDEX': return d.pages_indexed != null ? `${d.pages_indexed} page(s) · ${d.engine}` : null
    case 'EMBED': return d.reason ? String(d.reason) : null
  }
  return null
}

const ICON = {
  DONE: <Check className="size-3.5" />, RUNNING: <Loader2 className="size-3.5 animate-spin" />,
  FAILED: <X className="size-3.5" />, SKIPPED: <Minus className="size-3.5" />, PENDING: <Circle className="size-2" />,
}
const RING = {
  DONE: 'bg-ok text-white', RUNNING: 'bg-brand text-white', FAILED: 'bg-bad text-white',
  SKIPPED: 'bg-sunken text-muted ring-1 ring-line', PENDING: 'bg-surface text-faint ring-1 ring-line',
}

export function PipelineSteps({ steps }: { steps: Schemas['ProcessingStep'][] }) {
  const groups = [
    { title: 'Must pass', hint: 'or the file is refused', items: steps.filter((s) => s.critical) },
    { title: 'Helps you find it later', hint: 'best effort', items: steps.filter((s) => !s.critical) },
  ]
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {groups.map((g) => (
        <div key={g.title}>
          <div className="mb-3 flex items-baseline justify-between border-b border-ink-2 pb-1">
            <span className="serif text-[15px] font-semibold">{g.title}</span>
            <span className="serif text-[13px] text-muted italic">{g.hint}</span>
          </div>
          <ol className="space-y-0">
            {g.items.map((s, i) => {
              const [label, desc] = STEP_LABEL[s.step] ?? [s.step, '']
              const line = detailLine(s)
              const ms = s.started_at && s.finished_at ? new Date(s.finished_at).getTime() - new Date(s.started_at).getTime() : null
              const st = s.status as keyof typeof ICON
              return (
                <li key={s.step} className="relative flex gap-3 pb-3.5">
                  {i < g.items.length - 1 && <span className={cn('absolute top-7 bottom-0 left-[11px] w-px', st === 'DONE' ? 'bg-ok/40' : 'bg-line')} />}
                  <span className={cn('relative z-[1] mt-0.5 flex size-[23px] shrink-0 items-center justify-center rounded-full transition-colors duration-300', RING[st])}>{ICON[st]}</span>
                  <div className={cn('min-w-0 flex-1', st === 'PENDING' && 'opacity-50')}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className={cn('text-[13.5px] font-medium', st === 'FAILED' && 'text-bad')}>{label}</span>
                      {ms != null && st !== 'PENDING' && st !== 'RUNNING' && st !== 'SKIPPED' && (
                        <span className="font-mono text-[11px] text-faint">{ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`}</span>
                      )}
                    </div>
                    <div className="text-[12px] text-muted">{line && st !== 'PENDING' ? <span key={line} className="inline-block animate-step-in font-mono text-[11.5px] text-ink-2">{line}</span> : desc}</div>
                  </div>
                </li>
              )
            })}
          </ol>
        </div>
      ))}
    </div>
  )
}
