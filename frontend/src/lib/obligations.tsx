import { useQueryClient } from '@tanstack/react-query'
import { KeyRound, ScrollText } from '@/components/icons'
import { createContext, useContext, useRef, useState, type ReactNode } from 'react'
import { ApiProblem, api, unwrap } from '@/api/client'
import { OtpInput } from '@/components/OtpInput'
import { Button, Dialog, Textarea } from '@/components/ui'
import { cn } from '@/lib/cn'

/**
 * The server answers 428 when an obligation is missing (docs/04-api-contract.md):
 *   PURPOSE_REQUIRED → ask for a purpose, retry with it
 *   STEP_UP_REQUIRED → ask for a fresh TOTP, POST /auth/step-up, retry
 * `withObligations` hides that dance from every caller.
 */
const PRESETS = [
  'Preparing charge-sheet',
  'Court hearing preparation',
  'Supervisory review of investigation',
  'Forensic analysis of exhibit',
  'Responding to court summons',
]

type Ctx = {
  withObligations: <T>(call: (purpose?: string) => Promise<T>) => Promise<T | null>
}
const ObligationCtx = createContext<Ctx>({ withObligations: async () => null })

export function ObligationsProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [purposeOpen, setPurposeOpen] = useState(false)
  const [stepOpen, setStepOpen] = useState(false)
  const [purpose, setPurpose] = useState('')
  const [code, setCode] = useState('')
  const [stepErr, setStepErr] = useState(false)
  const [busy, setBusy] = useState(false)
  const resolver = useRef<(v: string | boolean | null) => void>(() => {})

  const askPurpose = () => new Promise<string | null>((res) => {
    setPurpose(''); setPurposeOpen(true)
    resolver.current = (v) => res(typeof v === 'string' ? v : null)
  })
  const askStepUp = () => new Promise<boolean>((res) => {
    setCode(''); setStepErr(false); setStepOpen(true)
    resolver.current = (v) => res(v === true)
  })

  const withObligations: Ctx['withObligations'] = async (call) => {
    let p: string | undefined
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        return await call(p)
      } catch (e) {
        if (!(e instanceof ApiProblem) || e.status !== 428) throw e
        if (e.code === 'PURPOSE_REQUIRED') {
          const got = await askPurpose()
          if (!got) return null
          p = got
        } else if (e.code === 'STEP_UP_REQUIRED') {
          if (!(await askStepUp())) return null
        } else throw e
      }
    }
    return null
  }

  const submitStepUp = async (c = code) => {
    if (c.length !== 6) return
    setBusy(true)
    try {
      await unwrap(api.POST('/auth/step-up', { body: { code: c } }))
      qc.invalidateQueries({ queryKey: ['me'] })
      setStepOpen(false)
      resolver.current(true)
    } catch {
      setStepErr(true); setCode('')
    } finally { setBusy(false) }
  }

  return (
    <ObligationCtx.Provider value={{ withObligations }}>
      {children}

      <Dialog open={purposeOpen}
        onOpenChange={(o) => { if (!o) { setPurposeOpen(false); resolver.current(null) } }}
        title={<span className="flex items-center gap-2"><ScrollText className="size-4 text-warn" />State the purpose of access</span>}
        description="This record is protected. Your purpose is written to the tamper-evident audit log and shown to supervisors."
        footer={<>
          <Button variant="secondary" onClick={() => { setPurposeOpen(false); resolver.current(null) }}>Cancel</Button>
          <Button disabled={purpose.trim().length < 10}
            onClick={() => { setPurposeOpen(false); resolver.current(purpose.trim()) }}>Continue</Button>
        </>}>
        <div className="mb-3 flex flex-wrap gap-1.5">
          {PRESETS.map((x) => (
            <button key={x} type="button" onClick={() => setPurpose(x)}
              className={cn('rounded-[3px] border px-2.5 py-1 text-[12.5px] transition-colors',
                purpose === x ? 'border-brand bg-navy-50 text-brand' : 'border-line text-ink-2 hover:border-line-strong')}>
              {x}
            </button>
          ))}
        </div>
        <Textarea autoFocus value={purpose} onChange={(e) => setPurpose(e.target.value)}
          placeholder="e.g. Preparing for hearing in Sessions Court on 13 Oct" />
        <p className="mt-1 text-[12px] text-muted">At least 10 characters.</p>
      </Dialog>

      <Dialog open={stepOpen}
        onOpenChange={(o) => { if (!o) { setStepOpen(false); resolver.current(false) } }}
        title={<span className="flex items-center gap-2"><KeyRound className="size-4 text-brand" />Confirm it's you</span>}
        description="Downloading or lowering protection requires re-entering your 2FA code. Valid for 5 minutes."
        footer={<>
          <Button variant="secondary" onClick={() => { setStepOpen(false); resolver.current(false) }}>Cancel</Button>
          <Button loading={busy} disabled={code.length !== 6} onClick={() => submitStepUp()}>Confirm</Button>
        </>}>
        <OtpInput value={code} onChange={(v) => { setCode(v); setStepErr(false) }} onComplete={submitStepUp} autoFocus invalid={stepErr} />
        {stepErr && <p className="mt-2 text-[12px] text-bad">That code didn't match. Try the current one.</p>}
      </Dialog>
    </ObligationCtx.Provider>
  )
}

export const useObligations = () => useContext(ObligationCtx)
