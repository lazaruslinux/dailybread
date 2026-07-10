import { useEffect, useRef, useState } from 'react'
import { Button } from './ui'
import { Sheet } from './Recipes'

// Manual avatar framing: pinch (or wheel) to zoom, drag to position, with a
// circle mask previewing exactly what the round Avatar will show. Exports the
// framed square as a 512px JPEG for the regular upload path; the server's own
// center-crop then has nothing left to do.
//
// The math lives in one transform: the image is laid out at natural size with
// transform-origin 0 0, so the visible rect is (tx, ty, natW*s, natH*s) in
// viewport pixels and the export source rect is just (-tx/s, -ty/s, V/s, V/s).

const V = 288 // the square viewport, CSS px (18rem, fits a 390px phone sheet)
const MAX_ZOOM = 8

type Transform = { s: number; tx: number; ty: number }

export function AvatarCrop({
  file,
  busy,
  onCancel,
  onSave,
}: {
  file: File
  busy: boolean
  onCancel: () => void
  onSave: (blob: Blob) => void
}) {
  const imgRef = useRef<HTMLImageElement>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [nat, setNat] = useState<{ w: number; h: number } | null>(null)
  const [t, setT] = useState<Transform | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Live pointers by id; two of them make a pinch. Refs, not state — gesture
  // math must read the latest positions inside move events.
  const pointers = useRef(new Map<number, { x: number; y: number }>())

  // The object URL is made AND revoked inside the effect: StrictMode runs
  // mount effects twice, and a revoke in cleanup would kill a URL created in
  // a state initializer before the image ever loads.
  useEffect(() => {
    const u = URL.createObjectURL(file)
    setUrl(u)
    return () => URL.revokeObjectURL(u)
  }, [file])

  const minScale = nat ? V / Math.min(nat.w, nat.h) : 1

  // Zoom and pan always end inside these bounds, so the export rect can never
  // leave the photo: clamp on every update, not at save time.
  function clamp(next: Transform): Transform {
    if (!nat) return next
    const s = Math.min(Math.max(next.s, minScale), minScale * MAX_ZOOM)
    const tx = Math.min(0, Math.max(V - nat.w * s, next.tx))
    const ty = Math.min(0, Math.max(V - nat.h * s, next.ty))
    return { s, tx, ty }
  }

  function onLoad() {
    const img = imgRef.current
    if (!img) return
    const w = img.naturalWidth
    const h = img.naturalHeight
    if (!w || !h) {
      setError("That file doesn't look like a photo.")
      return
    }
    setNat({ w, h })
    const s = V / Math.min(w, h)
    setT({ s, tx: (V - w * s) / 2, ty: (V - h * s) / 2 })
  }

  // Zoom about a viewport point so whatever sits under the fingers/cursor
  // stays put while the rest of the photo grows around it.
  function zoomAt(t0: Transform, px: number, py: number, factor: number): Transform {
    const s = Math.min(Math.max(t0.s * factor, minScale), minScale * MAX_ZOOM)
    const real = s / t0.s
    return clamp({ s, tx: px - (px - t0.tx) * real, ty: py - (py - t0.ty) * real })
  }

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    e.currentTarget.setPointerCapture(e.pointerId)
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const prev = pointers.current.get(e.pointerId)
    if (!prev || !t) return
    const now = { x: e.clientX, y: e.clientY }
    const pts = pointers.current
    if (pts.size === 2) {
      const [a, b] = Array.from(pts.entries())
      const other = a[0] === e.pointerId ? b[1] : a[1]
      const before = Math.hypot(prev.x - other.x, prev.y - other.y)
      const after = Math.hypot(now.x - other.x, now.y - other.y)
      const rect = e.currentTarget.getBoundingClientRect()
      const mid = { x: (now.x + other.x) / 2 - rect.left, y: (now.y + other.y) / 2 - rect.top }
      setT((cur) => (cur && before > 0 ? zoomAt(cur, mid.x, mid.y, after / before) : cur))
    } else if (pts.size === 1) {
      setT((cur) => (cur ? clamp({ ...cur, tx: cur.tx + now.x - prev.x, ty: cur.ty + now.y - prev.y }) : cur))
    }
    pts.set(e.pointerId, now)
  }

  function onPointerEnd(e: React.PointerEvent<HTMLDivElement>) {
    pointers.current.delete(e.pointerId)
  }

  function onWheel(e: React.WheelEvent<HTMLDivElement>) {
    if (!t) return
    const rect = e.currentTarget.getBoundingClientRect()
    setT(zoomAt(t, e.clientX - rect.left, e.clientY - rect.top, e.deltaY < 0 ? 1.1 : 1 / 1.1))
  }

  function save() {
    const img = imgRef.current
    if (!img || !t) return
    const canvas = document.createElement('canvas')
    canvas.width = 512
    canvas.height = 512
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(img, -t.tx / t.s, -t.ty / t.s, V / t.s, V / t.s, 0, 0, 512, 512)
    // JPEG, not WebP: Safari's toBlob only reliably speaks JPEG/PNG, and the
    // server re-encodes to WebP anyway.
    canvas.toBlob(
      (blob) => {
        if (blob) onSave(blob)
        else setError('Could not prepare that photo.')
      },
      'image/jpeg',
      0.9,
    )
  }

  return (
    <Sheet onClose={onCancel}>
      <div data-avatar-crop>
        <h2 className="mb-1 text-lg font-bold leading-snug">Frame your photo</h2>
        <p className="mb-4 text-sm text-fg/50">Pinch to zoom, drag to position. The circle is what everyone sees.</p>

        <div className="flex justify-center">
          <div
            className="relative overflow-hidden rounded-2xl bg-black/40"
            style={{ width: V, height: V, touchAction: 'none' }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerEnd}
            onPointerCancel={onPointerEnd}
            onWheel={onWheel}
          >
            {url && (
            <img
              ref={imgRef}
              src={url}
              alt=""
              draggable={false}
              onLoad={onLoad}
              onError={() => setError("That file doesn't look like a photo.")}
              className="max-w-none select-none"
              style={
                t && nat
                  ? {
                      width: nat.w,
                      height: nat.h,
                      transform: `translate(${t.tx}px, ${t.ty}px) scale(${t.s})`,
                      transformOrigin: '0 0',
                    }
                  : { visibility: 'hidden' }
              }
            />
            )}
            <div className="pointer-events-none absolute inset-0 rounded-full border-2 border-white/80 shadow-[0_0_0_9999px_rgba(0,0,0,0.45)]" />
          </div>
        </div>

        {error && <p className="mt-3 text-center text-sm text-danger">{error}</p>}

        <div className="mt-5 flex flex-col gap-2">
          <Button type="button" onClick={save} disabled={busy || !t} className="w-full">
            {busy ? 'Uploading…' : 'Use this photo'}
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel} disabled={busy} className="w-full">
            Cancel
          </Button>
        </div>
      </div>
    </Sheet>
  )
}
