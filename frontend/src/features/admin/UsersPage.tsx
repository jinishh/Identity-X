import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { ApiProblem, api, unwrap, type Schemas } from '@/api/client'
import { Stamp, UserChip } from '@/components/domain'
import { Check, Copy, Fingerprint, Plus, ShieldCheck, Smartphone } from '@/components/icons'
import { Button, Card, Dialog, ErrorState, Field, Input, PageHeader, Select, Skeleton, Tab, TabList, TabPanel, Tabs, Tip } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/cn'
import { fmtDate, fmtRelative } from '@/lib/format'

type Invitation = Schemas['UserInvitation']

export function UsersPage() {
  const { me } = useAuth()
  const isSuper = me!.role === 'SUPER_ADMIN'
  return (
    <>
      <PageHeader title="Accounts"
        subtitle={isSuper ? 'Everyone in the state, administrators included. You cannot open any case — and neither can they.'
          : `Officers in ${me!.unit_name} and the units under it. Administrators never see case content.`} />
      <div className="mb-6 flex max-w-4xl items-start gap-3 border-l-[3px] border-lock bg-lock-bg/70 px-4 py-3 text-[13.5px] text-ink-2">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-lock" />
        New accounts start as <strong>invited</strong>. The officer activates with a one-time code you hand over in person, chooses their own password and links an authenticator. You never see or set their password.
      </div>
      <Tabs defaultValue="people">
        <TabList className="mb-5"><Tab value="people">People</Tab>{isSuper && <Tab value="units">Units</Tab>}<Tab value="roles">Roles</Tab></TabList>
        <TabPanel value="people"><People isSuper={isSuper} /></TabPanel>
        {isSuper && <TabPanel value="units"><Units /></TabPanel>}
        <TabPanel value="roles"><Roles /></TabPanel>
      </Tabs>
    </>
  )
}

function People({ isSuper }: { isSuper: boolean }) {
  const { me } = useAuth()
  const qc = useQueryClient()
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [invite, setInvite] = useState<Invitation | null>(null)
  const users = useQuery({ queryKey: ['users', q], queryFn: () => unwrap(api.GET('/users', { params: { query: { q: q || undefined, page_size: 100 } } })) })
  const roles = useQuery({ queryKey: ['roles'], queryFn: () => unwrap(api.GET('/roles')) })
  const units = useQuery({ queryKey: ['units'], queryFn: () => unwrap(api.GET('/units')) })
  const blank = { service_id: '', full_name: '', rank: '', role: 'INVESTIGATOR', unit_id: '', email: '', phone: '' }
  const [f, setF] = useState(blank)

  const create = useMutation({
    mutationFn: () => unwrap(api.POST('/users', { body: { ...f, rank: f.rank || undefined, role: f.role as never } })),
    onSuccess: (r) => { setOpen(false); setF(blank); setInvite(r); qc.invalidateQueries({ queryKey: ['users'] }) },
  })
  const reset = useMutation({
    mutationFn: (id: string) => unwrap(api.POST('/users/{userId}/reset-access', { params: { path: { userId: id } } })),
    onSuccess: (r) => { setInvite(r); qc.invalidateQueries({ queryKey: ['users'] }) },
  })
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'ACTIVE' | 'DISABLED' }) =>
      unwrap(api.PATCH('/users/{userId}', { params: { path: { userId: id } }, body: { status } })),
    onSuccess: (u) => { toast(u.status === 'DISABLED' ? `${u.full_name} disabled` : `${u.full_name} re-enabled`); qc.invalidateQueries({ queryKey: ['users'] }) },
    onError: (e) => toast.error((e as ApiProblem).detail ?? (e as Error).message),
  })
  const assignable = (roles.data ?? []).filter((r) => r.code !== 'SUPER_ADMIN' && (isSuper || !r.is_administrative))
  const err = create.error as ApiProblem | null

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, service ID or email" className="max-w-xs" />
        <Button className="ml-auto" onClick={() => { create.reset(); setOpen(true) }}><Plus className="size-4" />New account</Button>
      </div>
      {users.error && <ErrorState error={users.error} />}
      {!users.data ? <Skeleton className="h-96" /> : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto"><table className="ledger w-full min-w-[860px] text-[13.5px]">
            <thead><tr className="text-left">
              <th className="px-5 pt-3 pb-1.5">Person</th><th className="px-3 pt-3 pb-1.5">Role</th><th className="px-3 pt-3 pb-1.5">Contact</th>
              <th className="px-3 pt-3 pb-1.5">Sign-in</th><th className="px-3 pt-3 pb-1.5">Status</th><th className="px-3 pt-3 pb-1.5">Last seen</th><th className="px-5 pt-3 pb-1.5" />
            </tr></thead>
            <tbody>
              {users.data.items.map((u) => (
                <tr key={u.id}>
                  <td className="px-5 py-2.5"><UserChip user={u} sub={`${u.service_id} · ${u.unit_name}`} /></td>
                  <td className="px-3 py-2.5 text-ink-2">{u.role_title}</td>
                  <td className="px-3 py-2.5 text-[12.5px] text-muted"><div>{u.email}</div><div>{u.phone_masked}</div></td>
                  <td className="px-3 py-2.5">
                    <span className="flex items-center gap-2 text-faint">
                      <Tip content={u.mfa_enabled ? 'Authenticator linked' : 'No authenticator yet'}><Smartphone className={cn('size-4', u.mfa_enabled && 'text-ok')} /></Tip>
                      <Tip content={u.face_enrolled ? 'Face sign-in registered' : 'No face sign-in'}><Fingerprint className={cn('size-4', u.face_enrolled && 'text-ok')} /></Tip>
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    {u.status === 'INVITED' ? <Stamp size="xs" rotate={-3}>Invited</Stamp>
                      : u.status === 'DISABLED' ? <Stamp size="xs" tone="red" rotate={-3}>Disabled</Stamp>
                        : <span className="text-[13px] text-ok">Active</span>}
                  </td>
                  <td className="px-3 py-2.5 text-[12.5px] text-muted">{u.last_login_at ? fmtRelative(u.last_login_at) : 'never'}</td>
                  <td className="px-5 py-2.5 text-right whitespace-nowrap">
                    {u.id !== me!.id && u.role !== 'SUPER_ADMIN' && (
                      <>
                        <Button size="sm" variant="ghost" loading={reset.isPending && reset.variables === u.id} onClick={() => reset.mutate(u.id)}>Reset access</Button>
                        {u.status === 'DISABLED'
                          ? <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: u.id, status: 'ACTIVE' })}>Enable</Button>
                          : u.status === 'ACTIVE' && <Button size="sm" variant="ghost" className="text-bad" onClick={() => setStatus.mutate({ id: u.id, status: 'DISABLED' })}>Disable</Button>}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </Card>
      )}

      <Dialog open={open} onOpenChange={setOpen} title="New account" width="max-w-lg" description="The officer will activate it themselves with the code shown next."
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
          <Button loading={create.isPending} disabled={!f.service_id || !f.full_name || !f.unit_id || !f.email || !f.phone} onClick={() => create.mutate()}>Create and get code</Button></>}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Full name" className="col-span-2"><Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
          <Field label="Service ID" hint="e.g. NV-IO-1301"><Input value={f.service_id} onChange={(e) => setF({ ...f, service_id: e.target.value.toUpperCase() })} className="font-mono" /></Field>
          <Field label="Rank"><Input value={f.rank} onChange={(e) => setF({ ...f, rank: e.target.value })} placeholder="Sub-Inspector" /></Field>
          <Field label="Role"><Select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{assignable.map((r) => <option key={r.code} value={r.code}>{r.title}</option>)}</Select></Field>
          <Field label="Unit"><Select value={f.unit_id} onChange={(e) => setF({ ...f, unit_id: e.target.value })}><option value="">Choose…</option>{units.data?.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</Select></Field>
          <Field label="Official email"><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          <Field label="Mobile number"><Input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} placeholder="98100 45031" /></Field>
        </div>
        {err && <p className="mt-3 text-[13.5px] text-bad">{err.status === 403 ? 'You can’t create that role or add people to that unit.' : err.detail ?? err.message}</p>}
      </Dialog>

      <InvitationDialog invite={invite} onClose={() => setInvite(null)} />
    </>
  )
}

function InvitationDialog({ invite, onClose }: { invite: Invitation | null; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  return (
    <Dialog open={!!invite} onOpenChange={(o) => !o && onClose()} title="Activation code" description={invite ? `For ${invite.user.full_name} (${invite.user.service_id})` : ''}
      footer={<Button onClick={onClose}>Done</Button>}>
      {invite && (
        <div className="text-center">
          <div className="inline-flex items-center gap-3 rounded-[4px] border border-dashed border-line-strong bg-[#fffdf8] px-5 py-3">
            <span className="font-mono text-[28px] font-medium tracking-[0.18em]">{invite.activation_code}</span>
            <button onClick={() => { navigator.clipboard?.writeText(invite.activation_code); setCopied(true) }} className="text-muted hover:text-ink" aria-label="Copy">
              {copied ? <Check className="size-4 text-ok" /> : <Copy className="size-4" />}
            </button>
          </div>
          <p className="mt-3 text-[13.5px] text-ink-2">Hand this to the officer in person. It’s shown only now, works once, and expires {fmtDate(invite.activation_expires_at)}.</p>
          <p className="mt-1 text-[12.5px] text-muted">They’ll use it at “Activate your account” with {invite.user.email}.</p>
        </div>
      )}
    </Dialog>
  )
}

function Units() {
  const qc = useQueryClient()
  const units = useQuery({ queryKey: ['units'], queryFn: () => unwrap(api.GET('/units')) })
  const [f, setF] = useState({ code: '', name: '', type: 'POLICE_STATION', parent_id: '' })
  const create = useMutation({
    mutationFn: () => unwrap(api.POST('/units', { body: { ...f, type: f.type as never } })),
    onSuccess: () => { setF({ code: '', name: '', type: 'POLICE_STATION', parent_id: '' }); qc.invalidateQueries({ queryKey: ['units'] }); toast.success('Unit created') },
  })
  const list = units.data ?? []
  const children = (pid: string | null) => list.filter((u) => (u.parent_id ?? null) === pid)
  const Tree = ({ pid, depth }: { pid: string | null; depth: number }) => (
    <>
      {children(pid).map((u) => (
        <div key={u.id}>
          <div className="flex items-baseline gap-2 py-1.5" style={{ paddingLeft: depth * 20 }}>
            <span className="text-faint">{depth ? '└' : ''}</span>
            <span className="font-medium">{u.name}</span>
            <span className="font-mono text-[12px] text-muted">{u.code}</span>
            <span className="text-[12px] text-muted">· {u.type.replace(/_/g, ' ').toLowerCase()}</span>
          </div>
          <Tree pid={u.id} depth={depth + 1} />
        </div>
      ))}
    </>
  )
  return (
    <div className="grid gap-6 md:grid-cols-[1.4fr_1fr]">
      <Card className="px-5 py-4 text-[13.5px]">{units.data ? <Tree pid={null} depth={0} /> : <Skeleton className="h-60" />}</Card>
      <Card className="self-start px-5 py-4">
        <h3 className="serif mb-3 text-[17px] font-semibold">Add a unit</h3>
        <div className="space-y-3">
          <Field label="Name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Kotwali Police Station" /></Field>
          <Field label="Code" hint="e.g. NV-PS-KTW"><Input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} className="font-mono" /></Field>
          <Field label="Type"><Select value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>{['POLICE_STATION', 'DISTRICT_HQ', 'FSL', 'PROSECUTION_OFFICE', 'NCRB_CELL'].map((t) => <option key={t} value={t}>{t.replace(/_/g, ' ').toLowerCase()}</option>)}</Select></Field>
          <Field label="Reports to"><Select value={f.parent_id} onChange={(e) => setF({ ...f, parent_id: e.target.value })}><option value="">Choose…</option>{list.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</Select></Field>
          {create.error && <p className="text-[13px] text-bad">{(create.error as ApiProblem).detail ?? (create.error as Error).message}</p>}
          <Button loading={create.isPending} disabled={!f.name || !f.code || !f.parent_id} onClick={() => create.mutate()}>Create unit</Button>
        </div>
      </Card>
    </div>
  )
}

function Roles() {
  const roles = useQuery({ queryKey: ['roles'], queryFn: () => unwrap(api.GET('/roles')) })
  if (!roles.data) return <Skeleton className="h-80" />
  return (
    <Card className="overflow-hidden">
      <p className="border-b border-line px-5 py-3 text-[13px] text-muted">Read from <span className="font-mono">iam.roles</span> and <span className="font-mono">iam.role_permissions</span>. Case-level access also depends on assignment and document sensitivity.</p>
      <ul className="divide-y divide-line">
        {roles.data.map((r) => (
          <li key={r.code} className="grid gap-2 px-5 py-3 md:grid-cols-[220px_1fr]">
            <div>
              <div className="font-medium">{r.title}</div>
              <div className="font-mono text-[12px] text-muted">{r.code}</div>
              {!r.sees_case_content && <div className="mt-1 text-[12px] text-bad">never sees case content</div>}
            </div>
            <div>
              <p className="text-[13.5px] text-ink-2">{r.description}</p>
              <div className="mt-1.5 flex flex-wrap gap-1">{r.permissions.map((p) => <span key={p} className="rounded-[3px] bg-sunken px-1.5 py-px font-mono text-[11.5px] text-ink-2">{p}</span>)}</div>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  )
}
