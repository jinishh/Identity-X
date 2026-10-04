import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useLocation } from 'react-router'
import { toast } from 'sonner'
import { ApiProblem, api, unwrap } from '@/api/client'
import { Stamp } from '@/components/domain'
import { FaceCapture } from '@/components/FaceCapture'
import { Fingerprint, KeyRound, Laptop, Smartphone } from '@/components/icons'
import { Button, Card, Dialog, ErrorState, Field, Input, KV, PageHeader, Skeleton } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { ROLE_LABEL, fmtDateTime, fmtRelative } from '@/lib/format'
import type { FaceProof } from '@/lib/face'
import { useObligations } from '@/lib/obligations'

function device(ua?: string | null) {
  if (!ua) return 'Unknown device'
  const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : /python|httpx/i.test(ua) ? 'Script' : 'Browser'
  const os = /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS' : /Windows/.test(ua) ? 'Windows' : /Mac OS/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : ''
  return `${browser}${os ? ` on ${os}` : ''}`
}

export function SettingsPage() {
  const { me } = useAuth()
  const qc = useQueryClient()
  const welcome = (useLocation().state as { welcome?: boolean } | null)?.welcome
  const { withObligations } = useObligations()
  const sec = useQuery({ queryKey: ['my-security'], queryFn: () => unwrap(api.GET('/me/security')) })
  const [faceOpen, setFaceOpen] = useState(false)
  const [faceKey, setFaceKey] = useState(0)
  const [pwOpen, setPwOpen] = useState(false)
  const [pw, setPw] = useState({ current: '', next: '' })
  const refresh = () => { qc.invalidateQueries({ queryKey: ['my-security'] }); qc.invalidateQueries({ queryKey: ['me'] }) }

  const enrol = useMutation({
    mutationFn: (proof: FaceProof) => withObligations(() => unwrap(api.POST('/me/face', { body: proof }))),
    onSuccess: (r) => { if (r) { setFaceOpen(false); refresh(); toast.success('Face sign-in is ready. Next time, choose “Face” on the sign-in page.') } },
  })
  const remove = useMutation({
    mutationFn: () => unwrap(api.POST('/me/face/remove')),
    onSuccess: () => { refresh(); toast('Face sign-in removed') },
  })
  const changePw = useMutation({
    mutationFn: () => unwrap(api.POST('/me/password', { body: { current_password: pw.current, new_password: pw.next } })),
    onSuccess: () => { setPwOpen(false); setPw({ current: '', next: '' }); toast.success('Password changed') },
  })
  const endSession = useMutation({
    mutationFn: (id: string) => unwrap(api.POST('/me/sessions/{sessionId}/revoke', { params: { path: { sessionId: id } } })),
    onSuccess: refresh,
  })

  const s = sec.data
  return (
    <div className="max-w-4xl">
      <PageHeader title="Settings" subtitle="How you sign in, and where you are signed in right now." />
      {welcome && (
        <div className="mb-6 flex items-center gap-4 border-l-[3px] border-ok bg-ok-bg/70 px-4 py-3 animate-pop-in">
          <Stamp tone="green" rotate={-4}>Active</Stamp>
          <p className="text-[14px] text-ink-2">Your account is active. If you like, register your face below — then you can sign in without typing a password (the authenticator code is still asked for).</p>
        </div>
      )}
      {sec.error && <ErrorState error={sec.error} />}

      <div className="grid gap-6 md:grid-cols-[1fr_1.2fr]">
        <Card className="self-start px-5 py-4">
          <h2 className="serif mb-2 text-[18px] font-semibold">Account</h2>
          <KV label="Name">{me!.full_name}</KV>
          <KV label="Service ID" mono>{me!.service_id}</KV>
          <KV label="Role">{ROLE_LABEL[me!.role]}</KV>
          <KV label="Unit">{me!.unit_name}</KV>
          <KV label="Email">{s?.email ?? '—'}</KV>
          <KV label="Mobile">{s?.phone_masked ?? '—'}</KV>
          <p className="mt-3 text-[12.5px] text-muted">Name, role and unit are managed by your administrator.</p>
        </Card>

        <Card>
          <div className="border-b border-line px-5 pt-4 pb-3"><h2 className="serif text-[18px] font-semibold">How you sign in</h2></div>
          {!s ? <Skeleton className="m-5 h-40" /> : (
            <ul className="divide-y divide-line">
              <li className="flex items-start gap-4 px-5 py-4">
                <KeyRound className="mt-0.5 size-5 text-ink-2" />
                <div className="min-w-0 flex-1">
                  <div className="font-medium">Password</div>
                  <div className="text-[13px] text-muted">With your email or mobile number.</div>
                </div>
                <Button size="sm" variant="secondary" onClick={() => setPwOpen(true)}>Change</Button>
              </li>
              <li className="flex items-start gap-4 px-5 py-4">
                <Smartphone className="mt-0.5 size-5 text-ink-2" />
                <div className="min-w-0 flex-1">
                  <div className="font-medium">Authenticator app <span className="ml-1 text-[12px] font-normal text-muted">— always required</span></div>
                  <div className="text-[13px] text-muted">{s.authenticator.linked_at ? `Linked ${fmtDateTime(s.authenticator.linked_at)}` : 'Not linked'}. A lost phone is reset by your administrator.</div>
                </div>
              </li>
              <li className="flex items-start gap-4 px-5 py-4">
                <Fingerprint className="mt-0.5 size-5 text-ink-2" />
                <div className="min-w-0 flex-1">
                  <div className="font-medium">Face</div>
                  <div className="text-[13px] text-muted">
                    {s.face
                      ? <>Registered {fmtDateTime(s.face.enrolled_at)} · {s.face.samples} frames · blink checked. Replaces the password, never the authenticator.</>
                      : 'Sign in by looking at the camera instead of typing your password. Stored as an encrypted numeric template — no photo is kept.'}
                  </div>
                </div>
                {s.face
                  ? <div className="flex gap-2"><Button size="sm" variant="secondary" onClick={() => { setFaceKey((k) => k + 1); setFaceOpen(true) }}>Re-register</Button><Button size="sm" variant="ghost" loading={remove.isPending} onClick={() => remove.mutate()}>Remove</Button></div>
                  : <Button size="sm" onClick={() => { setFaceKey((k) => k + 1); setFaceOpen(true) }}>Register my face</Button>}
              </li>
            </ul>
          )}
        </Card>
      </div>

      <Card className="mt-6">
        <div className="border-b border-line px-5 pt-4 pb-3"><h2 className="serif text-[18px] font-semibold">Where you’re signed in</h2></div>
        {!s ? <Skeleton className="m-5 h-24" /> : (
          <ul className="divide-y divide-line">
            {s.sessions.map((x) => (
              <li key={x.id} className="flex items-center gap-4 px-5 py-3">
                <Laptop className="size-5 text-ink-2" />
                <div className="min-w-0 flex-1 text-[13.5px]">
                  <div className="font-medium">{device(x.user_agent)} {x.current && <span className="ml-1 text-[12px] font-normal text-ok">· this one</span>}</div>
                  <div className="text-[12.5px] text-muted">Signed in with {x.first_factor === 'FACE' ? 'face' : x.first_factor === 'ACTIVATION' ? 'activation' : 'password'} + authenticator · {fmtDateTime(x.created_at)} · active {fmtRelative(x.last_seen_at ?? x.created_at)}{x.ip ? ` · ${x.ip}` : ''}</div>
                </div>
                {!x.current && <Button size="sm" variant="ghost" loading={endSession.isPending && endSession.variables === x.id} onClick={() => endSession.mutate(x.id)}>Sign out</Button>}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Dialog open={faceOpen} onOpenChange={setFaceOpen} title="Register your face" width="max-w-[420px]"
        description="Face the camera in good light, then blink once when asked. You’ll be asked for your authenticator code to confirm.">
        <FaceCapture key={faceKey} busy={enrol.isPending} onProof={(p) => enrol.mutate(p)} />
        {enrol.error && (
          <div className="mt-3">
            <ErrorState error={enrol.error} />
            <Button size="sm" variant="secondary" className="mt-2" onClick={() => { enrol.reset(); setFaceKey((k) => k + 1) }}>Try again</Button>
          </div>
        )}
      </Dialog>

      <Dialog open={pwOpen} onOpenChange={setPwOpen} title="Change password"
        footer={<><Button variant="secondary" onClick={() => setPwOpen(false)}>Cancel</Button><Button loading={changePw.isPending} disabled={!pw.current || pw.next.length < 12} onClick={() => changePw.mutate()}>Change</Button></>}>
        <div className="space-y-3">
          <Field label="Current password"><Input type="password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} autoComplete="current-password" /></Field>
          <Field label="New password" hint="12+ characters, letters, numbers and a symbol."><Input type="password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} autoComplete="new-password" /></Field>
          {changePw.error && <p className="text-[13px] text-bad">{(changePw.error as ApiProblem).detail ?? (changePw.error as Error).message}</p>}
        </div>
      </Dialog>
    </div>
  )
}
