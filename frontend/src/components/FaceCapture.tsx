import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/cn'
import { BlinkCapture, loadFaceModels, readFrame, type FaceProof } from '@/lib/face'
import { Button } from './ui'

const PROMPT = {
  starting: 'Starting the camera…',
  models: 'Loading the face model (first time only)…',
  look: 'Look straight at the camera',
  blink: 'Now blink once',
  hold: 'Good — hold still',
  done: 'Got it',
  noface: 'Move into the frame, in good light',
}

/** Webcam with an oval guide. Calls onProof once a blink and steady frames are captured. */
export function FaceCapture({ onProof, busy, className }: { onProof: (p: FaceProof) => void; busy?: boolean; className?: string }) {
  const video = useRef<HTMLVideoElement>(null)
  const [stage, setStage] = useState<keyof typeof PROMPT>('starting')
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let stream: MediaStream | null = null
    let stopped = false
    const capture = new BlinkCapture()
    ;(async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' }, audio: false })
        if (stopped) return
        video.current!.srcObject = stream
        await video.current!.play()
        setStage('models')
        await loadFaceModels()
        setStage('look')
        while (!stopped) {
          const f = await readFrame(video.current!)
          if (stopped) break
          if (!f) { setStage('noface'); await new Promise((r) => setTimeout(r, 120)); continue }
          const proof = capture.push(f)
          setStage(capture.phase())
          if (proof) { onProof(proof); break }
          await new Promise((r) => setTimeout(r, 60))
        }
      } catch (e) {
        const name = (e as Error).name
        setError(name === 'NotAllowedError' ? 'Camera permission was refused. Allow it in the browser and try again.'
          : name === 'NotFoundError' ? 'No camera found on this device.' : `Camera unavailable: ${(e as Error).message}`)
      }
    })()
    return () => { stopped = true; stream?.getTracks().forEach((t) => t.stop()) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt])

  return (
    <div className={cn('flex flex-col items-center', className)}>
      <div className="relative aspect-[4/3] w-full max-w-[340px] overflow-hidden rounded-[6px] bg-navy-950">
        <video ref={video} muted playsInline className="h-full w-full -scale-x-100 object-cover" />
        <svg viewBox="0 0 400 300" className="pointer-events-none absolute inset-0 h-full w-full">
          <defs><mask id="oval"><rect width="400" height="300" fill="white" /><ellipse cx="200" cy="145" rx="88" ry="112" fill="black" /></mask></defs>
          <rect width="400" height="300" fill="rgb(18 26 44 / 0.55)" mask="url(#oval)" />
          <ellipse cx="200" cy="145" rx="88" ry="112" fill="none" strokeWidth="3"
            className={cn('transition-colors', stage === 'done' || stage === 'hold' ? 'stroke-[#7fd19b]' : stage === 'blink' ? 'stroke-[#e9c46a]' : 'stroke-white/70')} />
        </svg>
        {error && <div className="absolute inset-0 grid place-items-center bg-navy-950/90 p-5 text-center text-[13.5px] text-[#efe9dc]">{error}</div>}
      </div>
      <p className={cn('serif mt-3 text-[17px]', stage === 'blink' && 'font-semibold text-warn')}>{error ? 'Camera problem' : busy ? 'Checking…' : PROMPT[stage]}</p>
      <p className="mt-0.5 text-[12.5px] text-muted">Only a numeric face template leaves this device — never a picture.</p>
      {error && <Button variant="secondary" size="sm" className="mt-3" onClick={() => { setError(null); setStage('starting'); setAttempt((a) => a + 1) }}>Try again</Button>}
    </div>
  )
}
