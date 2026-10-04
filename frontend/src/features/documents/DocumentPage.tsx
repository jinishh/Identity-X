import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Download, Eye, EyeOff, FileSignature, History, Lock, ScrollText, Share2, ShieldCheck,
  Stamp, Tags,
} from '@/components/icons'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'
import { api, unwrap, type Schemas } from '@/api/client'
import { Badge, Button, Card, Dialog, ErrorState, Field, Skeleton, Tab, TabList, TabPanel, Tabs, Textarea } from '@/components/ui'
import { ProcessingBadge, SensitivityBadge } from '@/components/domain'
import { DOC_TYPE_LABEL, fmtDateTime } from '@/lib/format'
import { useObligations } from '@/lib/obligations'
import { CertificatesPanel, CustodyPanel, EntitiesPanel, IntegrityPanel, SharingPanel, VersionsPanel } from './panels'
import { SecureViewer } from './Viewer'

type Grant = Schemas['ContentAccessGrant']

export function DocumentPage() {
  const { docId = '' } = useParams()
  const qc = useQueryClient()
  const { withObligations } = useObligations()
  const doc = useQuery({ queryKey: ['doc', docId], queryFn: () => unwrap(api.GET('/documents/{documentId}', { params: { path: { documentId: docId } } })) })
  const versions = useQuery({ queryKey: ['versions', docId], queryFn: () => unwrap(api.GET('/documents/{documentId}/versions', { params: { path: { documentId: docId } } })) })
  const [versionId, setVersionId] = useState<string | null>(null)
  const [grant, setGrant] = useState<Grant | null>(null)
  const [opening, setOpening] = useState(false)
  const [tab, setTab] = useState('integrity')

  const d = doc.data
  const current = versions.data?.find((v) => v.id === (versionId ?? d?.current_version?.id)) ?? null
  const access = d?.access
  const needsPurpose = access?.view === 'ORIGINAL' && access.obligations.includes('PURPOSE')

  const open = async (variant: 'ORIGINAL' | 'REDACTED' = 'ORIGINAL') => {
    if (!current) return
    setOpening(true)
    try {
      const g = await withObligations((purpose) => unwrap(api.POST('/versions/{versionId}/access', {
        params: { path: { versionId: current.id } }, body: { variant, disposition: 'inline', purpose },
      })))
      if (g) { setGrant(g); qc.invalidateQueries({ queryKey: ['doc-timeline', docId] }) }
    } catch (e) { toast.error((e as Error).message) } finally { setOpening(false) }
  }

  // auto-open when no obligation stands in the way
  useEffect(() => {
    setGrant(null)
    if (!d || !current || current.processing_status !== 'READY') return
    if (d.access.view === 'REDACTED') open('REDACTED')
    else if (d.access.view === 'ORIGINAL' && !d.access.obligations.includes('PURPOSE')) open('ORIGINAL')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d?.id, current?.id])

  const download = async () => {
    if (!current) return
    try {
      const g = await withObligations((purpose) => unwrap(api.POST('/versions/{versionId}/access', {
        params: { path: { versionId: current.id } }, body: { variant: 'ORIGINAL', disposition: 'attachment', purpose },
      })))
      if (g) {
        const a = document.createElement('a'); a.href = g.url; a.click()
        toast.success('Download recorded in the audit ledger')
        qc.invalidateQueries({ queryKey: ['doc-timeline', docId] })
      }
    } catch (e) { toast.error((e as Error).message) }
  }

  if (doc.error) return <ErrorState error={doc.error} />
  if (!d || !versions.data) return <div className="space-y-3"><Skeleton className="h-20" /><Skeleton className="h-[600px]" /></div>
  const can = (a: string) => d.access.actions.includes(a)
  const isCurrent = current?.id === d.current_version?.id

  return (
    <>
      <Link to={`/cases/${d.case_id}`} className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink"><ArrowLeft className="size-3.5" />{d.case_number}</Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-[13px]">
            <span className="font-mono text-muted">{d.doc_number}</span>
            <span className="text-faint">·</span><span className="text-ink-2">{DOC_TYPE_LABEL[d.doc_type]}</span>
            <SensitivityBadge value={d.sensitivity} />
            <ProcessingBadge status={current?.processing_status} verification={current?.last_verification?.overall} />
            {d.retention_state === 'LEGAL_HOLD' && <Badge tone="lock"><Lock className="size-3" />Legal hold</Badge>}
            {d.status === 'WITHDRAWN' && <Badge tone="bad">Withdrawn</Badge>}
          </div>
          <h1 className="serif mt-1 text-[30px] leading-[1.12] font-semibold tracking-[-0.01em]">{d.title}</h1>
          <div className="mt-1 text-[13px] text-muted">
            Viewing <strong className="text-ink">v{current?.version_no}</strong>{!isCurrent && ' (earlier version)'} · uploaded {fmtDateTime(current?.uploaded_at)} by {current?.uploaded_by.full_name}
            {(d.access.via ?? []).length > 0 && <> · access via {(d.access.via ?? []).map((v) => v.toLowerCase()).join(', ')}</>}
          </div>
        </div>
        <HeaderActions d={d} versionId={current?.id} onDownload={download} canDownload={can('document:download')} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(380px,1fr)]">
        <Card className="overflow-hidden">
          {grant ? (
            <SecureViewer key={grant.url} url={grant.url} mime={grant.variant === 'REDACTED' ? 'application/pdf' : current!.detected_mime}
              watermark={grant.watermark} redacted={grant.variant === 'REDACTED'} />
          ) : (
            <div className="flex min-h-[520px] flex-col items-center justify-center bg-[#e4ddcd] px-6 text-center">
              {current?.processing_status !== 'READY' ? (
                <><ProcessingBadge status={current?.processing_status} /><p className="mt-3 text-muted">This version is not available for viewing.</p></>
              ) : access?.view === 'NONE' ? (
                <><div className="mb-3 rounded-[6px] bg-surface p-3 text-muted shadow-card"><EyeOff className="size-6" /></div>
                  <p className="font-medium">Metadata only</p>
                  <p className="mt-1 max-w-sm text-[13px] text-muted">Your role can see that this record exists and verify its integrity, but not its contents.</p></>
              ) : needsPurpose ? (
                <><div className="mb-3 rounded-[6px] bg-surface p-3 text-s-victim shadow-card">{d.sensitivity === 'VICTIM_PROTECTED' ? <EyeOff className="size-6" /> : <Lock className="size-6" />}</div>
                  <p className="font-medium">{d.sensitivity === 'VICTIM_PROTECTED' ? 'Victim-protected original' : 'Restricted record'}</p>
                  <p className="mt-1 max-w-sm text-[13px] text-muted">Opening the original requires a stated purpose. It will be recorded in the audit ledger{d.sensitivity === 'VICTIM_PROTECTED' ? ' and the supervisor will be notified' : ''}.</p>
                  <div className="mt-4 flex gap-2">
                    <Button loading={opening} onClick={() => open('ORIGINAL')}><Eye className="size-4" />View original</Button>
                    {d.sensitivity === 'VICTIM_PROTECTED' && <Button variant="secondary" onClick={() => open('REDACTED')}>View redacted copy</Button>}
                  </div></>
              ) : (
                <Button loading={opening} onClick={() => open()}><Eye className="size-4" />Open document</Button>
              )}
            </div>
          )}
        </Card>

        <Card className="self-start">
          <Tabs value={tab} onValueChange={setTab}>
            <TabList className="grid grid-cols-6 gap-0 px-1">
              {([['integrity', ShieldCheck, 'Integrity'], ['versions', History, 'Versions'], ['custody', ScrollText, 'Custody'],
                ['sharing', Share2, 'Sharing'], ['certs', Stamp, '§63 cert'], ['entities', Tags, 'Entities']] as const).map(([v, Icon, label]) => (
                <Tab key={v} value={v}><span className="flex w-full flex-col items-center gap-0.5 text-[11.5px]"><Icon className="size-4" />{label}</span></Tab>
              ))}
            </TabList>
            <div className="p-4">
              <TabPanel value="integrity">{current && <IntegrityPanel version={current} doc={d} />}</TabPanel>
              <TabPanel value="versions"><VersionsPanel doc={d} versions={versions.data} selected={current?.id} onSelect={setVersionId} /></TabPanel>
              <TabPanel value="custody"><CustodyPanel doc={d} /></TabPanel>
              <TabPanel value="sharing"><SharingPanel doc={d} /></TabPanel>
              <TabPanel value="certs">{current && <CertificatesPanel doc={d} version={current} />}</TabPanel>
              <TabPanel value="entities">{current && <EntitiesPanel version={current} />}</TabPanel>
            </div>
          </Tabs>
        </Card>
      </div>
    </>
  )
}

function HeaderActions({ d, versionId, onDownload, canDownload }: { d: Schemas['Document']; versionId?: string; onDownload: () => void; canDownload: boolean }) {
  const qc = useQueryClient()
  const can = (a: string) => d.access.actions.includes(a)
  const [dialog, setDialog] = useState<null | 'hold' | 'withdraw' | 'review'>(null)
  const [text, setText] = useState('')
  const refresh = () => { qc.invalidateQueries({ queryKey: ['doc', d.id] }); qc.invalidateQueries({ queryKey: ['doc-timeline', d.id] }) }
  const m = useMutation({
    mutationFn: async () => {
      const p = { params: { path: { documentId: d.id } } }
      if (dialog === 'hold') return unwrap(api.POST('/documents/{documentId}/legal-hold', { ...p, body: { reason: text } }))
      if (dialog === 'withdraw') return unwrap(api.POST('/documents/{documentId}/withdraw', { ...p, body: { reason: text } }))
      return unwrap(api.POST('/versions/{versionId}/review', { params: { path: { versionId: versionId! } }, body: { note: text } }))
    },
    onSuccess: () => { toast.success(dialog === 'review' ? 'Submitted for supervisor review' : 'Done — recorded in the audit ledger'); setDialog(null); setText(''); refresh() },
  })
  const titles = { hold: 'Place on legal hold', withdraw: 'Withdraw document', review: 'Submit for review' }
  return (
    <div className="flex flex-wrap gap-2">
      {can('document:review_submit') && <Button variant="secondary" onClick={() => setDialog('review')}><FileSignature className="size-4" />Submit for review</Button>}
      {can('document:legal_hold_set') && <Button variant="secondary" onClick={() => setDialog('hold')}><Lock className="size-4" />Legal hold</Button>}
      {can('document:withdraw') && <Button variant="ghost" onClick={() => setDialog('withdraw')}>Withdraw</Button>}
      {canDownload && <Button onClick={onDownload}><Download className="size-4" />Download original</Button>}
      <Dialog open={!!dialog} onOpenChange={(o) => !o && setDialog(null)} title={dialog ? titles[dialog] : ''}
        description={dialog === 'withdraw' ? 'Withdrawn documents are hidden from the case file but never deleted.' : dialog === 'hold' ? 'Prevents withdrawal or lowering of protection until released by a second officer.' : 'Your supervisor will approve or return it.'}
        footer={<><Button variant="secondary" onClick={() => setDialog(null)}>Cancel</Button>
          <Button variant={dialog === 'withdraw' ? 'danger' : 'primary'} loading={m.isPending} disabled={dialog !== 'review' && text.trim().length < 10} onClick={() => m.mutate()}>Confirm</Button></>}>
        <Field label={dialog === 'review' ? 'Note (optional)' : 'Reason'}><Textarea value={text} onChange={(e) => setText(e.target.value)} /></Field>
        {m.error && <ErrorState error={m.error} className="mt-3" />}
      </Dialog>
    </div>
  )
}

