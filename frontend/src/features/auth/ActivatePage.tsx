import { useMutation } from '@tanstack/react-query'
import { QRCodeSVG } from 'qrcode.react'
import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { ApiProblem, api, unwrap } from '@/api/client'
import { Check } from '@/components/icons'
import { Logo } from '@/components/Logo'
import { OtpInput } from '@/components/OtpInput'
import { Button, Field, Input } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/cn'

const RULES: [string, (p: string) => boolean][] = [
  ['12 characters or more', (p) => p.length >= 12],
  ['letters and numbers', (p) => /[A-Za-z]/.test(p) && /\d/.test(p)],
  ['at least one symbol', (p) => /[^A-Za-z0-9]/.test(p)],
]

/** First sign-in for an account an administrator created: code → password → authenticator. */
export function ActivatePage() {
  const nav = useNavigate()
  const { signIn } = useAuth()
  const prefill = (useLocation().state ?? {}) as { identifier?: string; code?: string }
  const [identifier, setIdentifier] = useState(prefill.identifier ?? '')
  const [codeIn, setCodeIn] = useState(prefill.code ?? '')
  const [password, setPassword] = useState('')
  const [otp, setOtp] = useState('')

  const start = useMutation({ mutationFn: () => unwrap(api.POST('/auth/activate', { body: { identifier, activation_code: codeIn } })) })
  const setPw = useMutation({
    mutationFn: () => unwrap(api.POST('/auth/activate/password', { body: { activation_token: start.data!.activation_token, password } })),
  })
  const confirm = useMutation({
    mutationFn: (c: string) => unwrap(api.POST('/auth/activate/confirm', { body: { activation_token: start.data!.activation_token, code: c } })),
    onSuccess: (r) => { signIn(r.access_token, r.user); nav('/settings', { replace: true, state: { welcome: true } }) },
    onError: () => setOtp(''),
  })
  const step = setPw.data ? 3 : start.data ? 2 : 1
  const err = (start.error ?? setPw.error ?? confirm.error) as ApiProblem | null

  return (
    <div className="min-h-dvh px-6 py-10">
      <div className="mx-auto max-w-[460px]">
        <Link to="/login" className="flex items-center gap-2.5"><Logo className="size-7" /><span className="serif text-[18px] font-semibold">Case-File Vault</span></Link>
        <h1 className="serif mt-10 text-[30px] leading-tight font-semibold">Activate your account</h1>
        <p className="mt-1.5 text-[14.5px] text-ink-2">Your administrator created the account and gave you a one-time code. Three short steps and you’re in.</p>

        <ol className="mt-8 space-y-0">
          {['Prove it’s you', 'Choose a password', 'Link your authenticator'].map((label, i) => {
            const n = i + 1
            const done = step > n
            const current = step === n
            return (
              <li key={label} className={cn('relative border-l-2 pb-7 pl-6 last:pb-0', done ? 'border-ok' : 'border-line')}>
                <span className={cn('absolute -left-[13px] top-0 flex size-6 items-center justify-center rounded-full text-[12px] font-semibold',
                  done ? 'bg-ok text-white' : current ? 'bg-brand text-white' : 'bg-sunken text-muted')}>
                  {done ? <Check className="size-3.5" /> : n}
                </span>
                <h2 className={cn('serif text-[18px] font-semibold', !current && !done && 'text-muted')}>{label}</h2>

                {current && n === 1 && (
                  <form className="mt-3 space-y-3 animate-fade-in" onSubmit={(e) => { e.preventDefault(); start.mutate() }}>
                    <Field label="Email or mobile number your admin registered"><Input autoFocus value={identifier} onChange={(e) => setIdentifier(e.target.value)} /></Field>
                    <Field label="Activation code" hint="Looks like ABCD-1234. It works once and expires in 7 days.">
                      <Input value={codeIn} onChange={(e) => setCodeIn(e.target.value.toUpperCase())} className="font-mono tracking-[0.2em]" placeholder="XXXX-XXXX" />
                    </Field>
                    <Button type="submit" loading={start.isPending} disabled={!identifier || codeIn.length < 6}>Continue</Button>
                  </form>
                )}
                {done && n === 1 && start.data && <p className="mt-1 text-[13.5px] text-muted">{start.data.user.full_name} · {start.data.user.rank} · {start.data.user.unit_name}</p>}

                {current && n === 2 && (
                  <form className="mt-3 space-y-3 animate-fade-in" onSubmit={(e) => { e.preventDefault(); setPw.mutate() }}>
                    <Field label="New password"><Input autoFocus type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" /></Field>
                    <ul className="space-y-1 text-[13px]">
                      {RULES.map(([rule, ok]) => (
                        <li key={rule} className={cn('flex items-center gap-2', ok(password) ? 'text-ok' : 'text-muted')}>
                          <span className={cn('size-1.5 rounded-full', ok(password) ? 'bg-ok' : 'bg-faint')} />{rule}
                        </li>
                      ))}
                    </ul>
                    <Button type="submit" loading={setPw.isPending} disabled={!RULES.every(([, ok]) => ok(password))}>Set password</Button>
                  </form>
                )}

                {current && n === 3 && setPw.data && start.data && (
                  <div className="mt-3 animate-fade-in">
                    <p className="text-[13.5px] text-ink-2">Scan this with Google Authenticator, Microsoft Authenticator or any TOTP app, then type the 6-digit code it shows.</p>
                    <div className="mt-4 flex items-start gap-4">
                      <div className="rounded-[4px] border border-line bg-white p-2"><QRCodeSVG value={setPw.data.otpauth_uri} size={132} /></div>
                      <div className="min-w-0 text-[12.5px] text-muted">
                        Can’t scan? Enter this key by hand:
                        <div className="mt-1 font-mono text-[12.5px] break-all text-ink">{setPw.data.secret.match(/.{1,4}/g)?.join(' ')}</div>
                      </div>
                    </div>
                    <div className="mt-5"><OtpInput value={otp} onChange={setOtp} onComplete={(c) => confirm.mutate(c)} autoFocus invalid={!!confirm.error} /></div>
                    <Button className="mt-4" loading={confirm.isPending} disabled={otp.length !== 6} onClick={() => confirm.mutate(otp)}>Activate and sign in</Button>
                  </div>
                )}
              </li>
            )
          })}
        </ol>
        {err && <p className="mt-6 border-l-[3px] border-bad bg-bad-bg px-3 py-2 text-[13.5px] text-bad">{err.detail ?? err.message}</p>}
      </div>
    </div>
  )
}
