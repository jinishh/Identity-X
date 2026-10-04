import { cva, type VariantProps } from 'class-variance-authority'
import { Dialog as D, Tabs as T, Tooltip as Tt } from 'radix-ui'
import {
  forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode,
  type SelectHTMLAttributes, type TextareaHTMLAttributes,
} from 'react'
import { ApiProblem } from '@/api/client'
import { AlertTriangle, Inbox, Loader2, X } from '@/components/icons'
import { cn } from '@/lib/cn'
import { DENY_TEXT } from '@/lib/format'

// ───────────── Button ─────────────
const button = cva(
  'inline-flex items-center justify-center gap-1.5 rounded-[4px] font-medium whitespace-nowrap ' +
    'transition-[background-color,border-color,color,box-shadow,transform] duration-150 ' +
    'active:translate-y-px disabled:pointer-events-none disabled:opacity-45 select-none',
  {
    variants: {
      variant: {
        primary: 'bg-brand text-[#f6f3ea] shadow-[inset_0_-1px_0_rgb(0_0_0/0.25)] hover:bg-brand-hover',
        secondary: 'bg-surface text-ink border border-line-strong hover:border-ink-2/40 hover:bg-[#fffdf8]',
        ghost: 'text-ink-2 hover:bg-sunken hover:text-ink',
        link: 'h-auto! px-0! text-brand underline decoration-brand/30 underline-offset-[3px] hover:decoration-brand',
        danger: 'bg-bad text-[#fbf3ef] shadow-[inset_0_-1px_0_rgb(0_0_0/0.25)] hover:bg-[#8c2c23]',
        success: 'bg-ok text-[#f1f6ee] shadow-[inset_0_-1px_0_rgb(0_0_0/0.25)] hover:bg-[#245733]',
      },
      size: { sm: 'h-7 px-2.5 text-[13px]', md: 'h-9 px-3.5 text-[13.5px]', lg: 'h-11 px-5 text-[15px]', icon: 'h-8 w-8' },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof button> & { loading?: boolean }

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, children, disabled, ...props }, ref) => (
    <button ref={ref} className={cn(button({ variant, size }), className)} disabled={disabled || loading} {...props}>
      {loading && <Loader2 className="size-4 animate-spin" />}
      {children}
    </button>
  ),
)

// ───────────── Surfaces: a sheet of paper, not a floating card ─────────────
export function Card({ className, children, ...p }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('rounded-[6px] border border-line bg-surface shadow-card', className)} {...p}>
      {children}
    </div>
  )
}

export function CardHeader({ title, subtitle, actions, className }: {
  title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; className?: string
}) {
  return (
    <div className={cn('flex items-end justify-between gap-3 border-b border-line px-5 pt-4 pb-3', className)}>
      <div className="min-w-0">
        <h3 className="serif text-[17px] leading-snug font-semibold">{title}</h3>
        {subtitle && <p className="mt-0.5 text-[13px] text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions, eyebrow }: {
  title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode
}) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-line pb-5">
      <div className="min-w-0 max-w-3xl">
        {eyebrow && <div className="smallcaps mb-1 text-muted">{eyebrow}</div>}
        <h1 className="serif text-[30px] leading-[1.1] font-semibold tracking-[-0.01em]">{title}</h1>
        {subtitle && <p className="mt-2 max-w-[62ch] text-[14.5px] text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

// ───────────── Tag (square-cut, like a label on a file) ─────────────
const badge = cva('inline-flex items-center gap-1 rounded-[3px] border px-1.5 py-px text-[12px] font-medium whitespace-nowrap', {
  variants: {
    tone: {
      neutral: 'border-line-strong/70 bg-sunken text-ink-2',
      ok: 'border-ok-line bg-ok-bg text-ok',
      warn: 'border-warn-line bg-warn-bg text-warn',
      bad: 'border-bad-line bg-bad-bg text-bad',
      lock: 'border-lock-line bg-lock-bg text-lock',
      brand: 'border-navy-100 bg-navy-50 text-brand',
      victim: 'border-[#e3c4d4] bg-s-victim-bg text-s-victim',
    },
  },
  defaultVariants: { tone: 'neutral' },
})

export function Badge({ tone, className, children }: VariantProps<typeof badge> & { className?: string; children: ReactNode }) {
  return <span className={cn(badge({ tone }), className)}>{children}</span>
}

// ───────────── Form controls ─────────────
const control =
  'w-full rounded-[4px] border border-line-strong bg-[#fffdf9] px-3 text-[14px] text-ink ' +
  'placeholder:text-faint transition-colors focus:border-brand focus:outline-none focus:ring-[3px] focus:ring-brand/12 ' +
  'disabled:bg-sunken disabled:text-muted'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...p }, ref) => <input ref={ref} className={cn(control, 'h-9', className)} {...p} />,
)
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...p }, ref) => <textarea ref={ref} className={cn(control, 'min-h-20 py-2 leading-relaxed', className)} {...p} />,
)
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...p }, ref) => (
    <select ref={ref} className={cn(control, 'h-9 appearance-none bg-[length:14px] bg-[right_10px_center] bg-no-repeat pr-8', className)}
      style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%236e6a60' stroke-width='2.2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")" }}
      {...p}>
      {children}
    </select>
  ),
)

export function Field({ label, hint, error, children, className }: {
  label: ReactNode; hint?: ReactNode; error?: string; children: ReactNode; className?: string
}) {
  return (
    <label className={cn('block', className)}>
      <span className="mb-1.5 block text-[13px] font-medium text-ink-2">{label}</span>
      {children}
      {error ? <span className="mt-1 block text-[12.5px] text-bad">{error}</span>
        : hint && <span className="mt-1 block text-[12.5px] text-muted">{hint}</span>}
    </label>
  )
}

// ───────────── Feedback ─────────────
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-[4px] bg-sunken', className)} />
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn('size-4 animate-spin text-muted', className)} />
}

export function EmptyState({ title, body, icon, action }: { title: string; body?: ReactNode; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start px-6 py-10">
      <div className="mb-3 text-faint">{icon ?? <Inbox className="size-6" />}</div>
      <p className="serif text-[17px] font-semibold">{title}</p>
      {body && <p className="mt-1 max-w-md text-[13.5px] text-muted">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, className }: { error: unknown; className?: string }) {
  const p = error instanceof ApiProblem ? error : null
  const denied = p?.status === 403
  return (
    <div className={cn('flex items-start gap-3 border-l-[3px] px-4 py-3',
      denied ? 'border-bad bg-bad-bg' : 'border-warn bg-warn-bg', className)}>
      <AlertTriangle className={cn('mt-0.5 size-4 shrink-0', denied ? 'text-bad' : 'text-warn')} />
      <div className="text-[13.5px]">
        <p className="font-semibold">{denied ? 'Not allowed' : p?.message ?? 'That didn’t work'}</p>
        <p className="text-ink-2">
          {denied ? (DENY_TEXT[p?.denyReason ?? ''] ?? p?.detail) : p?.detail ?? (error as Error)?.message}
        </p>
        {denied && <p className="mt-1 text-[12.5px] text-muted">The attempt is now part of the audit ledger.</p>}
      </div>
    </div>
  )
}

// ───────────── Dialog ─────────────
export function Dialog({ open, onOpenChange, title, description, children, footer, width = 'max-w-md' }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: ReactNode; description?: ReactNode
  children?: ReactNode; footer?: ReactNode; width?: string
}) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-50 bg-[#1d1a14]/35 data-[state=open]:animate-fade-in" />
        <D.Content className={cn('fixed top-1/2 left-1/2 z-50 w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 rounded-[6px] border border-line-strong bg-surface shadow-pop data-[state=open]:animate-pop-in', width)}>
          <div className="flex items-start justify-between gap-4 px-6 pt-5">
            <div>
              <D.Title className="serif text-[19px] leading-snug font-semibold">{title}</D.Title>
              {description && <D.Description className="mt-1 text-[13.5px] text-muted">{description}</D.Description>}
            </div>
            <D.Close className="-mr-1 rounded-[4px] p-1 text-muted hover:bg-sunken hover:text-ink" aria-label="Close">
              <X className="size-4" />
            </D.Close>
          </div>
          {children && <div className="px-6 pt-4">{children}</div>}
          {footer && <div className="mt-6 flex justify-end gap-2 border-t border-line bg-sunken/50 px-6 py-3 rounded-b-[6px]">{footer}</div>}
          {!footer && <div className="h-6" />}
        </D.Content>
      </D.Portal>
    </D.Root>
  )
}

// ───────────── Tabs ─────────────
export const Tabs = T.Root
export function TabList({ children, className }: { children: ReactNode; className?: string }) {
  return <T.List className={cn('flex gap-5 border-b border-line', className)}>{children}</T.List>
}
export function Tab({ value, children }: { value: string; children: ReactNode }) {
  return (
    <T.Trigger value={value}
      className="relative -mb-px flex items-center gap-1.5 border-b-2 border-transparent py-2 text-[13.5px] font-medium text-muted transition-colors hover:text-ink data-[state=active]:border-ink data-[state=active]:text-ink">
      {children}
    </T.Trigger>
  )
}
export const TabPanel = T.Content

// ───────────── Tooltip ─────────────
export function Tip({ content, children, side = 'top' }: { content: ReactNode; children: ReactNode; side?: 'top' | 'bottom' | 'left' | 'right' }) {
  return (
    <Tt.Root delayDuration={300}>
      <Tt.Trigger asChild>{children}</Tt.Trigger>
      <Tt.Portal>
        <Tt.Content side={side} sideOffset={6}
          className="z-[60] max-w-xs rounded-[4px] bg-navy-950 px-2.5 py-1.5 text-[12.5px] leading-snug text-[#efe9dc] shadow-pop data-[state=delayed-open]:animate-fade-in">
          {content}
        </Tt.Content>
      </Tt.Portal>
    </Tt.Root>
  )
}
export const TipProvider = Tt.Provider

// ───────────── Key/value with a dotted leader, like a printed form ─────────────
export function KV({ label, children, mono }: { label: ReactNode; children: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline gap-2 py-1.5 text-[13.5px]">
      <span className="shrink-0 text-muted">{label}</span>
      <span className="mb-1 min-w-4 flex-1 border-b border-dotted border-line-strong" />
      <span className={cn('min-w-0 text-right text-ink', mono && 'font-mono text-[12.5px]')}>{children}</span>
    </div>
  )
}
