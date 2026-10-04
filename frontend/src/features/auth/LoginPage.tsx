import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'
import { ApiProblem, api, unwrap, type Schemas } from '@/api/client'
import { Avatar, Stamp } from '@/components/domain'
import { FaceCapture } from '@/components/FaceCapture'
import { ArrowLeft, Fingerprint, KeyRound } from '@/components/icons'
import { Logo } from '@/components/Logo'
import { OtpInput } from '@/components/OtpInput'
import { Button, Field, Input } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/cn'
import type { FaceProof } from '@/lib/face'

/** The paper file this system replaces — manila cover, typed entries, red tape, a stamp. */
function CaseFileCover() {
  const rows: [string, string][] = [
    ['Police Station', 'Shantinagar'],
    ['FIR No.', '0142 / 2026'],
    ['Date', '14-08-2026'],
    ['Under Section', 'BNS 74, 78, 351(2)'],
    ['I.O.', 'SI Anjali Verma'],
  ]
  return (
    <div className="relative mx-auto w-[min(420px,100%)] -rotate-[1.5deg]">
      {/* the sheets peeking out behind the cover */}
      <div className="absolute inset-x-3 -top-2 h-full rotate-[2.5deg] rounded-[3px] bg-[#f4efe2] shadow-[0_1px_2px_rgb(60_45_20/0.15)]" />
      <div className="absolute inset-x-1 -top-1 h-full -rotate-[1deg] rounded-[3px] bg-[#faf6ec] shadow-[0_1px_2px_rgb(60_45_20/0.15)]" />
      <div className="relative rounded-[3px] bg-[#d6c294] px-8 pt-7 pb-14 shadow-[0_24px_40px_-20px_rgb(40_30_10/0.55),0_2px_4px_rgb(40_30_10/0.2)]"
        style={{ backgroundImage: 'radial-gradient(ellipse at 20% 10%, rgb(255 250 230 / 0.35), transparent 60%), radial-gradient(ellipse at 90% 100%, rgb(120 90 40 / 0.18), transparent 55%)' }}>
        <div className="text-center">
          <div className="serif text-[12px] font-semibold tracking-[0.3em] text-[#5b4a28]">NAVAGARH STATE POLICE</div>
          <div className="serif mt-1 text-[26px] font-bold tracking-[0.12em] text-[#3d311a]">CASE FILE</div>
        </div>
        <dl className="mt-6 space-y-2.5">
          {rows.map(([k, v]) => (
            <div key={k} className="flex items-baseline gap-2 text-[13px]">
              <dt className="serif shrink-0 text-[#5b4a28]">{k}</dt>
              <dd className="flex-1 border-b border-dashed border-[#8c7647] pb-0.5 font-mono text-[13.5px] text-[#1f2a44]">{v}</dd>
            </div>
          ))}
        </dl>
        <div className="absolute top-[46%] right-5">
          <Stamp tone="red" rotate={-11} size="sm" className="bg-[#d6c294]/40 text-[13px]">Confidential</Stamp>
        </div>
      </div>
      {/* lal fita — the red tape round the file, and its knot */}
      <div className="absolute inset-x-[-14px] top-[85%] h-[11px] bg-tape shadow-[0_1px_1px_rgb(0_0_0/0.25)]" style={{ backgroundImage: 'repeating-linear-gradient(90deg, rgb(255 255 255 / 0.06) 0 2px, transparent 2px 5px)' }} />
      <div className="absolute top-[calc(85%-8px)] left-[58%] size-[26px] rotate-12 rounded-[40%] bg-[#8e2a21] shadow-[0_2px_3px_rgb(0_0_0/0.3)]" />
      <div className="absolute top-[calc(85%+12px)] left-[60%] h-14 w-[7px] rotate-[14deg] bg-tape" />
      <div className="absolute top-[calc(85%+12px)] left-[62.5%] h-11 w-[7px] -rotate-[8deg] bg-tape" />
    </div>
  )
}

export function LoginPage() {
  const { me, signIn } = useAuth()
  const nav = useNavigate()
  const from = (useLocation().state as { from?: string } | null)?.from ?? '/'
  const [method, setMethod] = useState<'password' | 'face'>('password')
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState<Schemas['LoginResponse'] | null>(null)
  const [code, setCode] = useState('')
  const [faceKey, setFaceKey] = useState(0)

  const login = useMutation({
    mutationFn: () => unwrap(api.POST('/auth/login', { body: { identifier, password } })),
    onSuccess: (r) => { setPending(r); setCode('') },
  })
  const face = useMutation({
    mutationFn: (proof: FaceProof) => unwrap(api.POST('/auth/login/face', { body: { ...proof, identifier: identifier || null } })),
    onSuccess: (r) => { setPending(r); setCode('') },
  })
  const verify = useMutation({
    mutationFn: (c: string) => unwrap(api.POST('/auth/mfa/verify', { body: { mfa_token: pending!.mfa_token, code: c } })),
    onSuccess: (r) => { signIn(r.access_token, r.user); nav(from, { replace: true }) },
    onError: () => setCode(''),
  })

  if (me) return <Navigate to="/" replace />
  const err = (login.error ?? face.error ?? verify.error) as ApiProblem | null

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden flex-col overflow-hidden border-r border-line px-14 py-10 lg:flex">
        <div className="flex items-center gap-2.5">
          <Logo className="size-8" />
          <span className="serif text-[20px] font-semibold">Case-File Vault</span>
        </div>
        <div className="my-auto py-12"><CaseFileCover /></div>
        <div className="max-w-[46ch]">
          <p className="serif text-[22px] leading-snug text-ink">
            Most case files still travel like this — tied in red tape, carried by hand, signed for in a register.
          </p>
          <p className="mt-3 text-[14.5px] leading-relaxed text-ink-2">
            The vault keeps that register for you, and can prove to a court that nothing in the file has changed since it was received.
          </p>
        </div>
      </section>

      <section className="flex items-center justify-center bg-surface/60 px-6 py-12">
        <div className="w-full max-w-[380px]">
          {!pending ? (
            <div className="animate-fade-in">
              <h1 className="serif text-[28px] font-semibold">Sign in</h1>
              <p className="mt-1 text-[14px] text-muted">With your email or mobile number — or your face, if you’ve registered it. An authenticator code always follows.</p>

              <div className="mt-6 grid grid-cols-2 rounded-[5px] border border-line-strong bg-surface p-0.5 text-[13.5px]">
                {([['password', KeyRound, 'Password'], ['face', Fingerprint, 'Face']] as const).map(([m, Icon, label]) => (
                  <button key={m} type="button" onClick={() => { setMethod(m); login.reset(); face.reset() }}
                    className={cn('flex items-center justify-center gap-1.5 rounded-[4px] py-1.5 font-medium transition-colors',
                      method === m ? 'bg-navy-800 text-white' : 'text-ink-2 hover:bg-sunken')}>
                    <Icon className="size-4" />{label}
                  </button>
                ))}
              </div>

              {method === 'password' ? (
                <form onSubmit={(e) => { e.preventDefault(); login.mutate() }} className="mt-5 space-y-4">
                  <Field label="Email or mobile number">
                    <Input autoFocus value={identifier} onChange={(e) => setIdentifier(e.target.value)}
                      placeholder="name@nvpolice.example or 98100 45001" autoComplete="username" />
                  </Field>
                  <Field label="Password">
                    <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
                  </Field>
                  {err && <ErrorLine err={err} />}
                  <Button type="submit" size="lg" className="w-full" loading={login.isPending} disabled={!identifier || !password}>Continue</Button>
                </form>
              ) : (
                <div className="mt-5">
                  <FaceCapture key={faceKey} busy={face.isPending} onProof={(p) => face.mutate(p)} />
                  {err && <div className="mt-3"><ErrorLine err={err} /></div>}
                  {face.isError && <Button variant="secondary" className="mt-3 w-full" onClick={() => { face.reset(); setFaceKey((k) => k + 1) }}>Try again</Button>}
                  <p className="mt-4 text-[12.5px] text-muted">No face registered yet? Sign in with your password, then add it under Settings.</p>
                </div>
              )}

              <p className="mt-6 text-[13.5px] text-ink-2">First time here? <Link to="/activate" className="text-brand underline decoration-brand/30 underline-offset-[3px] hover:decoration-brand">Activate your account</Link> with the code from your administrator.</p>

            </div>
          ) : (
            <div className="animate-fade-in">
              <button onClick={() => { setPending(null); verify.reset(); face.reset(); setFaceKey((k) => k + 1) }} className="mb-6 flex items-center gap-1 text-[13px] text-muted hover:text-ink">
                <ArrowLeft className="size-4" />Different account
              </button>
              {pending.first_factor === 'FACE' && (
                <div className="mb-5 flex items-center gap-3 border-l-[3px] border-ok bg-ok-bg/70 px-3 py-2.5">
                  <Avatar name={pending.user.full_name} />
                  <div className="text-[13.5px]"><div className="font-medium">Recognised: {pending.user.full_name}</div><div className="text-muted">{pending.user.rank} · {pending.user.unit_name}</div></div>
                </div>
              )}
              <h1 className="serif text-[28px] font-semibold">Authenticator code</h1>
              <p className="mt-1 text-[14px] text-muted">From the app linked to <span className="text-ink">{pending.user.full_name}</span>. It changes every 30 seconds and works once.</p>
              <div className="mt-7">
                <OtpInput value={code} onChange={setCode} onComplete={(c) => verify.mutate(c)} autoFocus invalid={!!verify.error} />
              </div>
              {verify.error && <p className="mt-3 text-[13.5px] text-bad">{(verify.error as ApiProblem).detail ?? 'That code didn’t match'}</p>}
              <Button size="lg" className="mt-6 w-full" loading={verify.isPending} disabled={code.length !== 6} onClick={() => verify.mutate(code)}>Sign in</Button>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

function ErrorLine({ err }: { err: ApiProblem }) {
  return <p className="border-l-[3px] border-bad bg-bad-bg px-3 py-2 text-[13.5px] text-bad">{err.detail ?? err.message}</p>
}
