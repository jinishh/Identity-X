import { useState, type CSSProperties, type ReactNode } from 'react'
import { Link } from 'react-router'
import type { Schemas } from '@/api/client'
import {
  ArrowRightLeft, Ban, BadgeCheck, Check, Copy, Download, Eye, EyeOff, FilePlus2, FileSignature,
  FolderPlus, Gavel, KeyRound, Link2, Lock, LogIn, LogOut, type LucideIcon, Search, Share2,
  ShieldAlert, ShieldCheck, ShieldX, Stamp as StampIcon, UserMinus, UserPlus, Users,
} from '@/components/icons'
import { cn } from '@/lib/cn'
import { CASE_STATUS_LABEL, fmtDateTime, fmtRelative, humanize, shortHash } from '@/lib/format'
import { Tip } from './ui'

// ───────────── Rubber stamp ─────────────
const STAMP_TONE = {
  violet: 'text-stamp border-stamp',
  green: 'text-ok border-ok',
  red: 'text-bad border-bad',
}

/** A rubber-stamp mark: double rule, spaced capitals, set slightly off-square. */
export function Stamp({ children, tone = 'violet', rotate = -4, size = 'sm', animate, className }: {
  children: ReactNode; tone?: keyof typeof STAMP_TONE; rotate?: number; size?: 'xs' | 'sm' | 'lg'
  animate?: boolean; className?: string
}) {
  return (
    <span style={{ '--stamp-rot': `${rotate}deg`, transform: `rotate(${rotate}deg)` } as CSSProperties}
      className={cn('inline-block border-double font-semibold uppercase opacity-[0.88] select-none',
        'stamp-ink',
        size === 'xs' && 'rounded-[3px] border-[3px] px-1 text-[9.5px] leading-[1.35] tracking-[0.14em]',
        size === 'sm' && 'rounded-[3px] border-[3px] px-1.5 py-px text-[11px] tracking-[0.16em]',
        size === 'lg' && 'rounded-[5px] border-[5px] px-4 py-1 text-[26px] leading-tight tracking-[0.18em]',
        animate && 'animate-stamp',
        STAMP_TONE[tone], className)}>
      {children}
    </span>
  )
}

// ───────────── Sensitivity: the coloured band on a file cover ─────────────
const SENS: Record<string, { label: string; bar: string; text: string; tip: string }> = {
  INTERNAL: { label: 'Internal', bar: 'bg-s-internal', text: 'text-ink-2', tip: 'Any member of the case may view and download.' },
  CONFIDENTIAL: { label: 'Confidential', bar: 'bg-s-confidential', text: 'text-s-confidential', tip: 'Members view. Downloading needs the lead IO, supervisor or prosecutor — with a reason.' },
  RESTRICTED: { label: 'Restricted', bar: 'bg-s-restricted', text: 'text-s-restricted', tip: 'Originals only for the lead IO, supervisor and prosecutor, with a reason. Download also needs 2FA again.' },
  VICTIM_PROTECTED: { label: 'Victim protected', bar: 'bg-s-victim', text: 'text-s-victim', tip: 'BNS §72. Originals only for the lead IO, supervisor and prosecutor, with a reason. Everyone else gets a redacted copy.' },
}

export function SensitivityBadge({ value, withTip = true }: { value: string; withTip?: boolean }) {
  const s = SENS[value] ?? SENS.INTERNAL
  const el = (
    <span className="inline-flex items-stretch overflow-hidden rounded-[2px] border border-line-strong/70 bg-[#fffdf8] text-[12.5px] whitespace-nowrap">
      <span className={cn('w-[5px]', s.bar)} />
      <span className={cn('px-1.5 py-px font-semibold [font-variant-caps:all-small-caps] tracking-[0.05em]', s.text)}>{s.label}</span>
    </span>
  )
  return withTip ? <Tip content={s.tip}>{el}</Tip> : el
}

// ───────────── Case status: plain words with a marker, as written in a register ─────────────
const STATUS_DOT: Record<string, string> = {
  REGISTERED: 'bg-faint', UNDER_INVESTIGATION: 'bg-brand', CHARGESHEET_FILED: 'bg-saffron',
  FINAL_REPORT_FILED: 'bg-faint', UNDER_TRIAL: 'bg-saffron', DISPOSED: 'bg-ok', CLOSED: 'bg-ink-2',
}
export function CaseStatusBadge({ status }: { status: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] whitespace-nowrap text-ink-2">
      <span className={cn('size-[7px] rotate-45', STATUS_DOT[status] ?? 'bg-faint')} />
      {CASE_STATUS_LABEL[status] ?? humanize(status)}
    </span>
  )
}

// ───────────── Integrity / processing ─────────────
export function ProcessingBadge({ status, verification }: { status?: string; verification?: string | null }) {
  if (status === 'QUARANTINED') return <Stamp tone="red" size="xs" rotate={-2}>Quarantined</Stamp>
  if (status === 'FAILED') return <Stamp tone="red" size="xs" rotate={-2}>Failed</Stamp>
  if (status && status !== 'READY') return <span className="inline-flex items-center gap-1.5 text-[12.5px] text-warn"><span className="size-1.5 animate-pulse rounded-full bg-warn" />Sealing…</span>
  if (verification === 'FAILED') return <Stamp tone="red" size="xs" rotate={-2}>Tampered</Stamp>
  return <Stamp size="xs" rotate={-3}>Sealed</Stamp>
}

// ───────────── Hash ─────────────
export function HashChip({ value, label, long, className }: { value?: string | null; label?: string; long?: boolean; className?: string }) {
  const [copied, setCopied] = useState(false)
  if (!value) return <span className="text-faint">—</span>
  return (
    <Tip content={<span className="font-mono break-all">{copied ? 'Copied' : value}</span>}>
      <button type="button"
        onClick={(e) => { e.stopPropagation(); navigator.clipboard?.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1200) }}
        className={cn('group inline-flex items-center gap-1 rounded-[3px] bg-sunken/80 px-1.5 py-px font-mono text-[12px] text-ink-2 hover:bg-line hover:text-ink', className)}>
        {label && <span className="font-sans text-[11.5px] text-muted">{label}</span>}
        {long ? value : shortHash(value, 8)}
        {copied ? <Check className="size-3 text-ok" /> : <Copy className="size-3 opacity-0 transition-opacity group-hover:opacity-60" />}
      </button>
    </Tip>
  )
}

// ───────────── People: square ID-badge initials ─────────────
export function initials(name?: string) {
  return (name ?? '?').replace(/^Dr\.\s*/, '').split(' ').map((p) => p[0]).slice(0, 2).join('')
}

const AVATAR_TINTS = ['bg-[#dfe4ec] text-[#2d3d5f]', 'bg-[#e8e0cf] text-[#5a4a2a]', 'bg-[#e0e7dc] text-[#34503a]', 'bg-[#ebdfe3] text-[#6a3450]', 'bg-[#e4e1ec] text-[#463c72]']

export function Avatar({ name, size = 'md', tone = 'paper' }: { name?: string; size?: 'sm' | 'md' | 'lg'; tone?: 'paper' | 'dark' }) {
  const tint = AVATAR_TINTS[[...(name ?? '')].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR_TINTS.length]
  return (
    <span className={cn('inline-flex shrink-0 items-center justify-center rounded-[4px] font-semibold tracking-wide',
      size === 'sm' ? 'size-6 text-[10px]' : size === 'lg' ? 'size-10 text-[13px]' : 'size-8 text-[11px]',
      tone === 'paper' ? tint : 'bg-[#f1ede4]/12 text-[#efe9dc] ring-1 ring-[#f1ede4]/20')}>
      {initials(name)}
    </span>
  )
}

export function UserChip({ user, sub }: { user?: Schemas['UserSummary'] | null; sub?: ReactNode }) {
  if (!user) return <span className="text-muted italic">system</span>
  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <Avatar name={user.full_name} size="sm" />
      <span className="min-w-0 leading-tight">
        <span className="block truncate text-[13.5px] font-medium text-ink">{user.full_name}</span>
        <span className="block truncate text-[12px] text-muted">{sub ?? `${user.rank ?? ''} · ${user.service_id}`}</span>
      </span>
    </span>
  )
}

// ───────────── A figure in the register (no box, no coloured strip) ─────────────
export function KpiCard({ kpi }: { kpi: Schemas['Kpi'] }) {
  const tone = { neutral: 'text-ink', good: 'text-ok', warn: 'text-warn', bad: 'text-bad' }[kpi.tone ?? 'neutral']
  const body = (
    <div className="group h-full px-5 py-4">
      <div className={cn('serif text-[34px] leading-none font-semibold tabular-nums', tone)}>
        {kpi.value.toLocaleString('en-IN')}
      </div>
      <div className="mt-2 text-[13.5px] font-medium text-ink-2 group-hover:text-ink">
        {kpi.label}{kpi.href && <span className="ml-1 text-faint transition-colors group-hover:text-brand">→</span>}
      </div>
      {kpi.hint && <div className="mt-0.5 text-[12.5px] text-muted">{kpi.hint}</div>}
    </div>
  )
  return kpi.href ? <Link to={kpi.href} className="block transition-colors hover:bg-[#fffdf8]">{body}</Link> : body
}

// ───────────── Audit events ─────────────
const ACTION_ICON: Record<string, LucideIcon> = {
  AUTH_LOGIN_SUCCEEDED: LogIn, AUTH_LOGOUT: LogOut, AUTH_STEP_UP: KeyRound, AUTH_LOGIN_FAILED: ShieldAlert,
  AUTH_MFA_FAILED: ShieldAlert, CASE_CREATED: FolderPlus, CASE_STATUS_CHANGED: Gavel,
  CASE_MEMBER_ADDED: UserPlus, CASE_MEMBER_REMOVED: UserMinus, DOCUMENT_UPLOADED: FilePlus2,
  VERSION_CREATED: Lock, VERSION_READY: ShieldCheck, VERSION_QUARANTINED: ShieldX,
  HASH_MISMATCH_ON_UPLOAD: ShieldX, DOCUMENT_VIEWED: Eye, REDACTED_VIEWED: EyeOff,
  DOCUMENT_DOWNLOADED: Download, SHARE_GRANTED: Share2, SHARE_REVOKED: Link2,
  REQUEST_CREATED: Users, REQUEST_APPROVED: Check, REQUEST_REJECTED: Ban,
  CUSTODY_TRANSFERRED: ArrowRightLeft, CERTIFICATE_ISSUED: StampIcon, PUBLIC_VERIFICATION: BadgeCheck,
  INTEGRITY_VERIFIED: ShieldCheck, INTEGRITY_FAILED: ShieldX, CHAIN_VERIFIED: ShieldCheck,
  CHAIN_BROKEN: ShieldX, CHECKPOINT_CREATED: Lock, ACCESS_DENIED: Ban, SEARCH_PERFORMED: Search,
  REVIEW_SUBMITTED: FileSignature, REVIEW_APPROVED: Check, REVIEW_RETURNED: Ban,
  REDACTION_CREATED: EyeOff,
}

export function eventTone(e: Schemas['AuditEvent']): 'ok' | 'bad' | 'warn' | 'lock' | 'neutral' {
  if (e.outcome === 'DENIED' || e.outcome === 'FAILED') return 'bad'
  if (['VERSION_CREATED', 'CHECKPOINT_CREATED', 'CUSTODY_TRANSFERRED'].includes(e.action)) return 'lock'
  if (['INTEGRITY_VERIFIED', 'CHAIN_VERIFIED', 'VERSION_READY', 'SHARE_GRANTED', 'REQUEST_APPROVED', 'REVIEW_APPROVED', 'CERTIFICATE_ISSUED'].includes(e.action)) return 'ok'
  if (['DOCUMENT_VIEWED', 'DOCUMENT_DOWNLOADED'].includes(e.action) && e.purpose) return 'warn'
  return 'neutral'
}

const MARK: Record<string, string> = {
  ok: 'text-ok', bad: 'text-bad', warn: 'text-warn', lock: 'text-lock', neutral: 'text-muted',
}

/** One line of the register: time on the left, what happened, who, and its link in the chain. */
export function TimelineItem({ e, showCase }: { e: Schemas['AuditEvent']; last?: boolean; showCase?: boolean }) {
  const Icon = ACTION_ICON[e.action] ?? Check
  const tone = eventTone(e)
  return (
    <li className="grid grid-cols-[18px_1fr] gap-x-3 border-t border-line py-3 first:border-t-0 first:pt-0">
      <Icon weight={tone === 'neutral' ? 'regular' : 'bold'} className={cn('mt-[3px] size-[17px]', MARK[tone])} />
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <p className={cn('text-[13.5px] text-ink', tone === 'bad' && 'text-bad')}>{e.summary}</p>
          <Tip content={fmtDateTime(e.occurred_at)}>
            <span className="shrink-0 text-[12px] text-muted tabular-nums">{fmtRelative(e.occurred_at)}</span>
          </Tip>
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] text-muted">
          <span>{e.actor ? `${e.actor.full_name}, ${e.actor.service_id}` : 'system'}</span>
          {showCase && e.case_number && <span className="font-mono text-[12px]">{e.case_number}</span>}
          {e.reason_code && <span className="text-bad">— {humanize(e.reason_code).toLowerCase()}</span>}
          <HashChip value={e.event_hash} label={`#${e.seq}`} />
        </div>
        {e.purpose && <p className="serif mt-1 text-[13.5px] text-ink-2 italic">“{e.purpose}”</p>}
      </div>
    </li>
  )
}

export function Timeline({ events, showCase }: { events: Schemas['AuditEvent'][]; showCase?: boolean }) {
  return (
    <ol className="animate-fade-in">
      {events.map((e) => <TimelineItem key={e.seq} e={e} showCase={showCase} />)}
    </ol>
  )
}
