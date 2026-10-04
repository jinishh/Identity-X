import { useMutation, useQuery } from '@tanstack/react-query'
import { EyeOff } from '@/components/icons'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { ApiProblem, api, unwrap } from '@/api/client'
import { Button, Card, Field, Input, PageHeader, Select, Textarea } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { CATEGORY_LABEL } from '@/lib/format'

export function NewCasePage() {
  const { me } = useAuth()
  const nav = useNavigate()
  const units = useQuery({ queryKey: ['units'], queryFn: () => unwrap(api.GET('/units')) })
  const stations = units.data?.filter((u) => u.type === 'POLICE_STATION') ?? []
  const [f, setF] = useState({
    fir_number: '', fir_date: new Date().toISOString().slice(0, 10), unit_id: me!.unit_id,
    title: '', category: 'CRIME_AGAINST_WOMEN', sections: '', description: '', lead_io_id: '',
  })
  const ios = useQuery({
    queryKey: ['directory', 'INVESTIGATOR'],
    queryFn: () => unwrap(api.GET('/directory', { params: { query: { q: 'NV', role: 'INVESTIGATOR' } } })),
    enabled: me!.role === 'SUPERVISOR',
  })
  const create = useMutation({
    mutationFn: () => unwrap(api.POST('/cases', {
      body: {
        fir_number: f.fir_number, fir_date: f.fir_date, unit_id: f.unit_id, title: f.title,
        category: f.category as never, offence_sections: f.sections.split(',').map((s) => s.trim()).filter(Boolean),
        description: f.description || undefined, lead_io_id: f.lead_io_id || undefined,
      },
    })),
    onSuccess: (c) => { toast.success(`Registered ${c.case_number}`); nav(`/cases/${c.id}`) },
  })
  const err = create.error as ApiProblem | null
  const errFor = (k: string) => err?.errors?.find((e) => e.field === k)?.message
  const victim = f.category.startsWith('CRIME_AGAINST')

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader eyebrow="Cases" title="Register a case" subtitle="Creates the case workspace. Documents are added afterwards." />
      <Card className="p-5">
        <form className="grid grid-cols-2 gap-4" onSubmit={(e) => { e.preventDefault(); create.mutate() }}>
          <Field label="FIR number" hint="Format 0142/2026" error={errFor('fir_number')}>
            <Input value={f.fir_number} onChange={(e) => setF({ ...f, fir_number: e.target.value })} placeholder="0157/2026" className="font-mono" />
          </Field>
          <Field label="FIR date"><Input type="date" value={f.fir_date} onChange={(e) => setF({ ...f, fir_date: e.target.value })} /></Field>
          <Field label="Police station" className="col-span-2">
            <Select value={f.unit_id} onChange={(e) => setF({ ...f, unit_id: e.target.value })}>
              {stations.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
          <Field label="Short title" hint="Never include the victim's name." className="col-span-2" error={errFor('title')}>
            <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Chain snatching near railway over-bridge" />
          </Field>
          <Field label="Category">
            <Select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
              {Object.entries(CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </Field>
          <Field label="Offence sections" hint="Comma separated, e.g. BNS 74, BNS 78">
            <Input value={f.sections} onChange={(e) => setF({ ...f, sections: e.target.value })} />
          </Field>
          {me!.role === 'SUPERVISOR' && (
            <Field label="Lead investigating officer" className="col-span-2">
              <Select value={f.lead_io_id} onChange={(e) => setF({ ...f, lead_io_id: e.target.value })}>
                <option value="">Choose…</option>
                {ios.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name} · {u.service_id}</option>)}
              </Select>
            </Field>
          )}
          <Field label="Brief facts (optional)" className="col-span-2">
            <Textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </Field>
          {victim && (
            <div className="col-span-2 flex items-start gap-2 border-l-[3px] border-s-victim bg-s-victim-bg/70 px-3 py-2.5 text-[13.5px] text-ink-2">
              <EyeOff className="mt-0.5 size-4 shrink-0 text-s-victim" />
              This case will be <strong className="font-semibold">victim-protected</strong> (BNS §72): documents default to the highest
              sensitivity and are auto-redacted for anyone who doesn't need the victim's identity.
            </div>
          )}
          {err && !err.errors && <p className="col-span-2 text-[13px] text-bad">{err.detail ?? err.message}</p>}
          <div className="col-span-2 flex justify-end gap-2 border-t border-line pt-4">
            <Button type="button" variant="secondary" onClick={() => nav(-1)}>Cancel</Button>
            <Button type="submit" loading={create.isPending} disabled={!f.fir_number || f.title.length < 5 || !f.sections}>Register case</Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
