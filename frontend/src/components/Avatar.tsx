import { useEffect, useState } from 'react'
import type { MoodLevel } from '../lib/api'
import { initialsOf, MOODS } from '../lib/moods'

// Initials circle used everywhere a person appears. When the member has an
// uploaded photo (src), it fills the circle; otherwise the coloured initials
// show. A load error silently falls back to the initials. The one mark an
// avatar wears is the mood dot (bottom right): the day's weather at a
// glance, in the mood's own color — details live behind a tap, so the photo
// stays a photo.

const SIZES = {
  sm: { circle: 'h-7 w-7 text-[10px]', dot: 'h-2 w-2 right-0 bottom-0' },
  md: { circle: 'h-11 w-11 text-sm', dot: 'h-3 w-3 right-0 bottom-0' },
  lg: { circle: 'h-20 w-20 text-2xl', dot: 'h-4.5 w-4.5 right-1 bottom-1' },
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
  // Today's mood: renders the little colored dot on the corner.
  mood?: MoodLevel | null
  size?: keyof typeof SIZES
  // Extra classes on the circle, e.g. a ring when avatars overlap.
  className?: string
}) {
  const s = SIZES[size]

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
          className={`flex items-center justify-center rounded-full bg-gradient-to-br from-avatar-1/80 to-avatar-2/80 font-bold text-white ${s.circle} ${className}`}
        >
          {initialsOf(name)}
        </div>
      )}
      {mood && (
        <span
          className={`absolute rounded-full ring-2 ring-[var(--bg-base)] ${s.dot} ${MOODS[mood].dot}`}
          title={`Mood · ${MOODS[mood].label}`}
        />
      )}
    </div>
  )
}
