/**
 * Face sign-in, browser side. Runs entirely on this device:
 *   webcam → tiny face detector → 68 landmarks → 128-d face embedding
 * Liveness: we wait for one real blink (eye aspect ratio drops, then recovers) so a printed
 * photo or a still on a phone can't sign in. Only embeddings are sent to the server.
 */
import * as faceapi from '@vladmandic/face-api'

let loading: Promise<void> | null = null
// face-api bundles TensorFlow.js; its exported typings omit the backend helpers.
const tf = faceapi.tf as unknown as { setBackend(b: string): Promise<boolean>; ready(): Promise<void> }

export function loadFaceModels(): Promise<void> {
  loading ??= (async () => {
    try {
      await tf.setBackend('webgl')
    } catch {
      await tf.setBackend('cpu')
    }
    await tf.ready()
    await Promise.all([
      faceapi.nets.tinyFaceDetector.loadFromUri('/models'),
      faceapi.nets.faceLandmark68Net.loadFromUri('/models'),
      faceapi.nets.faceRecognitionNet.loadFromUri('/models'),
    ])
  })()
  return loading
}

type Pt = { x: number; y: number }
const d = (a: Pt, b: Pt) => Math.hypot(a.x - b.x, a.y - b.y)

/** Eye aspect ratio (Soukupová & Čech): ~0.3 open, under ~0.2 closed. */
function ear(eye: Pt[]) {
  return (d(eye[1], eye[5]) + d(eye[2], eye[4])) / (2 * d(eye[0], eye[3]))
}

export type FaceFrame = { descriptor: number[]; ear: number; score: number; box: { x: number; y: number; width: number; height: number } }

const options = new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 })

export async function readFrame(video: HTMLVideoElement): Promise<FaceFrame | null> {
  const r = await faceapi.detectSingleFace(video, options).withFaceLandmarks().withFaceDescriptor()
  if (!r) return null
  const lm = r.landmarks
  return {
    descriptor: Array.from(r.descriptor),
    ear: (ear(lm.getLeftEye()) + ear(lm.getRightEye())) / 2,
    score: r.detection.score,
    box: r.detection.box,
  }
}

export type FaceProof = { samples: number[][]; liveness: { blink: boolean; score: number } }

/**
 * Blink-gated capture. Feed frames in; it reports the phase and, once a blink has been seen
 * and a few steady open-eye frames collected, returns the proof.
 */
export class BlinkCapture {
  private openEar: number[] = []
  private before: FaceFrame[] = []
  private after: FaceFrame[] = []
  private closed = false
  blinked = false

  phase(): 'look' | 'blink' | 'hold' | 'done' {
    if (this.after.length >= 3) return 'done'
    if (this.blinked) return 'hold'
    if (this.openEar.length >= 4) return 'blink'
    return 'look'
  }

  push(f: FaceFrame): FaceProof | null {
    const baseline = this.openEar.length ? this.openEar.reduce((a, b) => a + b) / this.openEar.length : 0.3
    const isClosed = f.ear < Math.min(0.22, baseline * 0.72)
    const isOpen = f.ear > Math.max(0.24, baseline * 0.85)

    if (!this.blinked) {
      if (isOpen && !this.closed) {
        this.openEar = [...this.openEar.slice(-9), f.ear]
        this.before = [...this.before.slice(-1), f]
      }
      if (isClosed && this.openEar.length >= 4) this.closed = true
      if (this.closed && isOpen) this.blinked = true
      return null
    }
    if (isOpen && f.score > 0.6) this.after.push(f)
    if (this.after.length < 3) return null
    const frames = [...this.before, ...this.after]
    return {
      samples: frames.map((x) => x.descriptor),
      liveness: { blink: true, score: frames.reduce((a, x) => a + x.score, 0) / frames.length },
    }
  }
}
