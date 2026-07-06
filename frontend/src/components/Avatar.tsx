import { useEffect, useState } from 'react'
import type { Mood } from '../lib/api'
import { MOODS, initialsOf } from '../lib/moods'

// Initials circle used everywhere a person appears. When the member has an
// uploaded photo (src), it fills the circle; otherwise the coloured initials
// show. A load error silently falls back to the initials. The optional mood
// badge is a small weather icon pinned to the corner; no mood means no badge,
// and a hidden mood never reaches the client in the first place.

const SIZES = {
  sm: { circle: 'h-7 w-7 text-[10px]', badge: 'h-3.5 w-3.5 -right-0.5 -bottom-0.5 p-[1px]' },
  md: { circle: 'h-11 w-11 text-sm', badge: 'h-5 w-5 -right-1 -bottom-0.5 p-0.5' },
  lg: { circle: 'h-20 w-20 text-2xl', badge: 'h-7 w-7 right-0 bottom-0 p-1' },
} as const

export function Avatar({
  name,
  src = null,
  mood = null,
  size = 'md',
  className = '',
}: {
  name: string
  // Photo URL, or null/undefined to draw generated initials.
  src?: string | null
  mood?: Mood | null
  size?: keyof typeof SIZES
  // Extra classes on the circle, e.g. a ring when avatars overlap.
  className?: string
}) {
  const s = SIZES[size]
  const meta = mood ? MOODS[mood.level] : null

  // Reset the error flag whenever the source changes so a new upload retries.
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [src])
  const showPhoto = src && !failed

  return (
    <div className="relative inline-block shrink-0">
      {showPhoto ? (
        <img
          src={src}
          alt=""
          onError={() => setFailed(true)}
          className={`rounded-full object-cover ${s.circle} ${className}`}
        />
      ) : (
        <div
          className={`flex items-center justify-center rounded-full bg-gradient-to-br from-accent-bright/60 to-accent-strong/60 font-bold text-white ${s.circle} ${className}`}
        >
          {initialsOf(name)}
        </div>
      )}
      {meta && (
        <span
          className={`absolute flex items-center justify-center rounded-full border border-fg/20 bg-[#151b2e] ${s.badge}`}
          title={meta.label}
        >
          <meta.Icon className={`h-full w-full ${meta.tint}`} strokeWidth={2.5} />
        </span>
      )}
    </div>
  )
}
