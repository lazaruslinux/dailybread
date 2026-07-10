import { Flashlight, X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'

// Full-screen barcode scanner: live camera preview decoded by zxing-wasm
// (loaded lazily, bundled locally), with a type-it-yourself fallback for no
// camera / no permission / plain-http contexts. Reusable anywhere a barcode
// is wanted — the recipe ingredient picker today, the food diary later.
//
// Rendered through a portal and styled in fixed dark colors: it sits over a
// camera feed, so it ignores the app theme on purpose.
export function BarcodeScanner({
  onCode,
  onClose,
}: {
  onCode: (code: string) => void
  onClose: () => void
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [notice, setNotice] = useState<string | null>('Starting the camera…')
  const [manual, setManual] = useState('')
  // Torch support is a camera capability (rear cameras on newer phones);
  // the button only exists when the track reports it.
  const [torch, setTorch] = useState<{ track: MediaStreamTrack; on: boolean } | null>(null)
  // Set once a code is accepted, so a half-decoded second frame can't fire twice.
  const done = useRef(false)

  useEffect(() => {
    let stream: MediaStream | null = null
    let timer: number | undefined
    let cancelled = false

    async function start() {
      let read: (img: ImageData) => Promise<string | null>
      try {
        read = (await import('../lib/scanner')).readCode
      } catch {
        setNotice('The scanner failed to load. Type the number instead.')
        return
      }
      // Camera needs a secure context (HTTPS); anywhere else this API simply
      // isn't there and the manual field below is the way in.
      if (!navigator.mediaDevices?.getUserMedia) {
        setNotice('No camera here — type the numbers under the barcode instead.')
        return
      }
      try {
        // Without a resolution ask the browser picks a low default, and a
        // barcode at arm's length lands on too few pixels to ever decode —
        // the "have to lean right in" complaint. `ideal` degrades gracefully.
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } },
          audio: false,
        })
      } catch {
        setNotice('Camera unavailable or blocked — type the numbers under the barcode instead.')
        return
      }
      if (cancelled) {
        stream.getTracks().forEach((t) => t.stop())
        return
      }
      const video = videoRef.current
      if (!video) return
      video.srcObject = stream
      try {
        await video.play()
      } catch {
        // iOS can refuse an early play(); the loop below still reads frames
        // once metadata arrives.
      }
      setNotice(null)

      const track = stream.getVideoTracks()[0]
      if (track) {
        // Continuous autofocus helps Android Chrome; browsers that don't know
        // the constraint (iOS) reject or ignore it, both fine.
        track
          .applyConstraints({ advanced: [{ focusMode: 'continuous' } as MediaTrackConstraintSet] })
          .catch(() => {})
        const caps = track.getCapabilities?.() as (MediaTrackCapabilities & { torch?: boolean }) | undefined
        if (caps?.torch && !cancelled) setTorch({ track, on: false })
      }

      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d', { willReadFrequently: true })
      if (!ctx) return
      let busy = false
      let tick = 0
      timer = window.setInterval(async () => {
        if (busy || done.current || !video.videoWidth) return
        busy = true
        try {
          // Most ticks decode a centered square crop — full pixel density
          // where the reticle points, far cheaper than the whole 1080p frame,
          // and square so a sideways barcode still fits (zxing rotates).
          // Every 4th tick takes the full frame for codes held off-center.
          const full = ++tick % 4 === 0
          const s = Math.round(0.7 * Math.min(video.videoWidth, video.videoHeight))
          const w = full ? video.videoWidth : s
          const h = full ? video.videoHeight : s
          canvas.width = w
          canvas.height = h
          if (full) ctx.drawImage(video, 0, 0)
          else {
            const sx = Math.round((video.videoWidth - s) / 2)
            const sy = Math.round((video.videoHeight - s) / 2)
            ctx.drawImage(video, sx, sy, s, s, 0, 0, s, s)
          }
          const code = await read(ctx.getImageData(0, 0, w, h))
          if (code && !done.current) {
            done.current = true
            onCode(code)
          }
        } finally {
          busy = false
        }
      }, 150)
    }

    start()
    return () => {
      cancelled = true
      window.clearInterval(timer)
      stream?.getTracks().forEach((t) => t.stop())
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function toggleTorch() {
    if (!torch) return
    const on = !torch.on
    torch.track
      .applyConstraints({ advanced: [{ torch: on } as MediaTrackConstraintSet] })
      .then(() => setTorch({ ...torch, on }))
      .catch(() => {})
  }

  function submitManual(e: FormEvent) {
    e.preventDefault()
    const code = manual.trim()
    if (!/^[0-9]{6,14}$/.test(code) || done.current) return
    done.current = true
    onCode(code)
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex flex-col bg-black" data-barcode-scanner>
      <div className="flex items-center justify-between p-4">
        <span className="text-xs font-semibold uppercase tracking-wide text-white/70">
          Scan a barcode
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close scanner"
          className="rounded-lg p-1.5 text-white/70 hover:text-white"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden">
        <video ref={videoRef} playsInline muted className="h-full w-full object-cover" />
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="h-40 w-72 max-w-[85%] rounded-2xl border-2 border-white/70 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" />
        </div>
        {notice && (
          <p className="absolute inset-x-4 top-4 rounded-xl bg-black/75 p-3 text-center text-sm text-white/90">
            {notice}
          </p>
        )}
        {torch && (
          <button
            type="button"
            onClick={toggleTorch}
            aria-label={torch.on ? 'Turn the flashlight off' : 'Turn the flashlight on'}
            aria-pressed={torch.on}
            className={`absolute bottom-5 left-1/2 -translate-x-1/2 rounded-full border p-3.5 transition-colors ${
              torch.on ? 'border-white bg-white text-black' : 'border-white/40 bg-black/50 text-white'
            }`}
          >
            <Flashlight className="h-5 w-5" />
          </button>
        )}
      </div>

      <form onSubmit={submitManual} className="flex items-center gap-2 p-4">
        <input
          value={manual}
          onChange={(e) => setManual(e.target.value.replace(/\D/g, ''))}
          inputMode="numeric"
          maxLength={14}
          placeholder="Or type the number under the bars"
          className="min-w-0 flex-1 rounded-xl border border-white/20 bg-white/10 px-4 py-2.5 text-white placeholder:text-white/40 focus:outline-none"
          data-barcode-manual
        />
        <button
          type="submit"
          disabled={!/^[0-9]{6,14}$/.test(manual.trim())}
          className="shrink-0 rounded-xl bg-white/15 px-4 py-2.5 font-semibold text-white disabled:opacity-40"
        >
          Use
        </button>
      </form>
    </div>,
    document.body,
  )
}
