import { Lock } from '@/components/icons'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import { Spinner } from '@/components/ui'

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

function watermarkUrl(text: string) {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;')
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='520' height='220'><text x='0' y='140' transform='rotate(-24 260 110)' font-family='IBM Plex Sans, sans-serif' font-size='15' fill='rgba(47,74,138,0.16)'>${esc}</text></svg>`
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`
}

/** Renders pages to canvas (no native viewer toolbar → no silent download), with a tiled
 *  watermark naming the viewer. Downloads go through the audited download action instead. */
export function SecureViewer({ url, mime, watermark, redacted }: { url: string; mime: string; watermark: string; redacted?: boolean }) {
  const [pages, setPages] = useState(0)
  const [width, setWidth] = useState(720)
  const wm = useMemo(() => watermarkUrl(watermark), [watermark])
  const file = useMemo(() => ({ url }), [url])
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(() => setWidth(Math.min(el.clientWidth - 32, 900)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  return (
    <div ref={box} className="relative bg-[#e4ddcd] p-4">
      {redacted && (
        <div className="sticky top-14 z-10 mb-3 flex items-center gap-2 rounded-[4px] bg-s-victim px-3 py-2 text-[12.5px] font-medium text-white shadow">
          <Lock className="size-3.5" />Redacted copy — victim identity removed (BNS §72)
        </div>
      )}
      {mime === 'application/pdf' ? (
        <Document file={file} onLoadSuccess={(p) => setPages(p.numPages)}
          loading={<div className="grid h-96 place-items-center"><Spinner className="size-6" /></div>}
          error={<p className="p-6 text-center text-bad">Could not render this PDF.</p>}>
          {Array.from({ length: pages }, (_, i) => (
            <div key={i} className="relative mx-auto mb-4 w-fit shadow-card">
              <Page pageNumber={i + 1} width={width} renderTextLayer={false} renderAnnotationLayer={false} />
              <div className="pointer-events-none absolute inset-0" style={{ backgroundImage: wm }} />
            </div>
          ))}
        </Document>
      ) : (
        <div className="relative mx-auto w-fit shadow-card">
          <img src={url} alt="Evidence" className="block max-w-full" style={{ width }} draggable={false} onContextMenu={(e) => e.preventDefault()} />
          <div className="pointer-events-none absolute inset-0" style={{ backgroundImage: wm }} />
        </div>
      )}
      <p className="mt-1 text-center text-[11.5px] text-muted">Watermarked to: {watermark}</p>
    </div>
  )
}
