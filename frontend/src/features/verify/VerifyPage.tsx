import { useMutation, useQuery } from '@tanstack/react-query'
import { FileSearch, Fingerprint, Laptop } from '@/components/icons'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { api, unwrap } from '@/api/client'
import { Stamp } from '@/components/domain'
import { Logo } from '@/components/Logo'
import { Button, Card, ErrorState, Input, KV, Skeleton } from '@/components/ui'
import { cn } from '@/lib/cn'
import { DOC_TYPE_LABEL, fmtBytes, fmtDateTime } from '@/lib/format'
import { sha256File } from '@/lib/hash'

/** Public page for courts, defence and any verifier. No login. The file is hashed locally. */
export function VerifyPage() {
  const { code } = useParams()
  const nav = useNavigate()
  const [entry, setEntry] = useState('')
  const [drag, setDrag] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [hash, setHash] = useState<string | null>(null)

  const cert = useQuery({
    queryKey: ['public-cert', code],
    queryFn: () => unwrap(api.GET('/public/certificates/{code}', { params: { path: { code: code! } } })),
    enabled: !!code, retry: false,
  })
  const check = useMutation({
    mutationFn: (sha256: string) => unwrap(api.POST('/public/verify/{code}', { params: { path: { code: code! } }, body: { sha256 } })),
  })
  const pick = async (f: File) => {
    setFile(f); setHash(null); check.reset()
    const h = await sha256File(f)
    setHash(h); check.mutate(h)
  }
  const r = check.data

  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-6 py-4">
          <Logo className="size-8" />
          <div className="leading-tight"><div className="serif text-[18px] font-semibold">Case-File Vault</div><div className="text-[12.5px] text-muted">Public verification — for courts, defence counsel and anyone holding a copy</div></div>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-8">
        {!code ? (
          <Card className="p-6">
            <h1 className="serif text-[26px] font-semibold">Verify a certified document</h1>
            <p className="mt-1 text-muted">Enter the 12-character verification code printed on the §63 certificate, or scan its QR code.</p>
            <form className="mt-5 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (entry.trim()) nav(`/verify/${entry.trim().toUpperCase()}`) }}>
              <Input value={entry} onChange={(e) => setEntry(e.target.value.toUpperCase())} placeholder="K7Q2M4XZ9BRA" className="h-11 font-mono text-[15px] tracking-widest" maxLength={12} />
              <Button type="submit" size="lg">Look up</Button>
            </form>
          </Card>
        ) : cert.error ? <ErrorState error={cert.error} /> : !cert.data ? <Skeleton className="h-96" /> : (
          <div className="space-y-5">
            <Card className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="smallcaps text-muted">Certificate under BSA 2023, §63</div>
                  <h1 className="mt-0.5 font-mono text-lg font-semibold">{cert.data.cert_number}</h1>
                </div>
                {cert.data.status === 'ISSUED'
                  ? <Stamp rotate={4}>Issued</Stamp>
                  : <Stamp tone="red" rotate={4}>Revoked</Stamp>}
              </div>
              <div className="mt-4 grid gap-x-8 sm:grid-cols-2">
                <KV label="Case number" mono>{cert.data.case_number}</KV>
                <KV label="Document type">{DOC_TYPE_LABEL[cert.data.doc_type]}</KV>
                <KV label="Version">v{cert.data.version_no}</KV>
                <KV label="Size">{fmtBytes(cert.data.size_bytes)}</KV>
                <KV label="Issued">{fmtDateTime(cert.data.issued_at)}</KV>
                <KV label="Issuing unit">{cert.data.issuing_unit}</KV>
              </div>
              <div className="mt-3 rounded-[6px] bg-canvas p-3">
                <div className="text-[12px] text-muted">Certified SHA-256</div>
                <div className="font-mono text-[12.5px] break-all">{cert.data.sha256}</div>
              </div>
            </Card>

            <Card className="p-5">
              <h2 className="serif flex items-center gap-2 text-[20px] font-semibold"><FileSearch className="size-5 text-brand" />Check your copy</h2>
              <p className="mt-1 flex items-center gap-1.5 text-[13px] text-muted"><Laptop className="size-4" />Your file stays on this device. Only its fingerprint is compared.</p>
              <div onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
                onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) pick(f) }}
                className={cn('mt-4 rounded-[6px] border-2 border-dashed px-4 py-8 text-center transition-colors', drag ? 'border-brand bg-navy-50' : 'border-line-strong')}>
                <Fingerprint className="mx-auto mb-2 size-7 text-brand" />
                <p className="font-medium">{file ? file.name : 'Drop the file you received'}</p>
                <label className="mt-2 inline-block cursor-pointer text-[13px] text-brand hover:underline">
                  or choose a file<input type="file" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) pick(f); e.target.value = '' }} />
                </label>
              </div>
              {hash && <p className="mt-3 font-mono text-[11.5px] break-all text-muted">Your copy: {hash}</p>}
              {r && (
                <div className={cn('mt-5 flex items-center gap-6 border-y px-2 py-6', r.result === 'MATCH' ? 'border-ok-line' : 'border-bad-line')}>
                  <Stamp key={r.checked_at} size="lg" animate tone={r.result === 'MATCH' ? 'green' : 'red'} rotate={r.result === 'MATCH' ? -6 : 4}>{r.result}</Stamp>
                  <div>
                    <p className="serif text-[17px] text-ink">{r.result === 'MATCH'
                      ? 'This copy is byte-for-byte identical to the certified record.'
                      : 'This copy differs from the certified record. Even a single changed byte produces a different fingerprint.'}</p>
                    {r.certificate_status === 'REVOKED' && <p className="mt-1 text-[13px] font-medium text-bad">Note: this certificate has been revoked.</p>}
                  </div>
                </div>
              )}
              {check.error && <ErrorState error={check.error} className="mt-4" />}
            </Card>
            <p className="text-center text-[12px] text-muted">A matching fingerprint shows the bytes are unchanged. It does not by itself establish authorship or admissibility.</p>
          </div>
        )}
      </main>
    </div>
  )
}
