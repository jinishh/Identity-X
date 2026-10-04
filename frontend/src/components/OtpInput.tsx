import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/cn'

/** One real input drawn as six boxes: survives fast typing, paste and OTP autofill. */
export function OtpInput({ value, onChange, onComplete, autoFocus, invalid }: {
  value: string; onChange: (v: string) => void; onComplete?: (v: string) => void
  autoFocus?: boolean; invalid?: boolean
}) {
  const ref = useRef<HTMLInputElement>(null)
  const [focused, setFocused] = useState(false)
  useEffect(() => { if (autoFocus) ref.current?.focus() }, [autoFocus])

  return (
    <div className="relative w-fit" onClick={() => ref.current?.focus()}>
      <input ref={ref} value={value} inputMode="numeric" autoComplete="one-time-code" aria-label="One-time code"
        maxLength={6} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
        onChange={(e) => {
          const v = e.target.value.replace(/\D/g, '').slice(0, 6)
          onChange(v)
          if (v.length === 6) onComplete?.(v)
        }}
        className="absolute inset-0 z-10 h-full w-full cursor-text opacity-0" />
      <div className="flex gap-2" aria-hidden>
        {Array.from({ length: 6 }, (_, i) => {
          const active = focused && (i === value.length || (value.length === 6 && i === 5))
          return (
            <div key={i} className={cn('flex h-12 w-10 items-center justify-center rounded-md border bg-surface font-mono text-lg font-medium shadow-sm transition-colors',
              invalid ? 'border-bad' : active ? 'border-brand ring-2 ring-brand/15' : 'border-line-strong')}>
              {value[i] ?? (active ? <span className="h-5 w-px animate-pulse bg-ink" /> : '')}
            </div>
          )
        })}
      </div>
    </div>
  )
}
