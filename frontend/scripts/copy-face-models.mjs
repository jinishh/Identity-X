// Copies the three face-api networks the app uses into public/models (kept out of git).
import { copyFileSync, mkdirSync } from 'node:fs'
const src = 'node_modules/@vladmandic/face-api/model/'
const dst = 'public/models/'
mkdirSync(dst, { recursive: true })
for (const m of ['tiny_face_detector_model', 'face_landmark_68_model', 'face_recognition_model'])
  for (const ext of ['.bin', '-weights_manifest.json']) copyFileSync(src + m + ext, dst + m + ext)
console.log('face models copied to public/models')
