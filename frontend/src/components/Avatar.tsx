import { BookOpen } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Mood } from '../lib/api'
import { MOODS, initialsOf } from '../lib/moods'

// Initials circle used everywhere a person appears. When the member has an
// uploaded photo (src), it fills the circle; otherwise the coloured initials
// show. A load error silently falls back to the initials. The optional mood
// badge is a small weather icon pinned to the corner; no mood means no badge,
// and a hidden mood never reaches the client in the first place. The optional
// verseStreak badge mirrors it on the LEFT: a gold book and the streak count.

const SIZES = {
  sm: { circle: 'h-7 w-7 text-[10px]', badge: 'h-3.5 w-3.5 -right-0.5 -bottom-0.5 p-[1px]', streak: '-left-1 -bottom-0.5 h-3.5 px-1 text-[7px]' },
  md: { circle: 'h-11 w-11 text-sm', badge: 'h-5 w-5 -right-1 -bottom-0.5 p-0.5', streak: '-left-1.5 -bottom-0.5 h-5 px-1.5 text-[9px]' },
  lg: { circle: 'h-20 w-20 text-2xl', badge: 'h-7 w-7 right-0 bottom-0 p-1', streak: 'left-0 bottom-0 h-7 px-2 text-xs' },
} as const

export function Avatar({
  name,
  src = null,
  mood = null,
  verseStreak = null,
  size = 'md',
  className = '',
}: {
  name: string
  // Photo URL, or null/undefined to draw generated initials.
  src?: string | null
  mood?: Mood | null
  // Verse-reading streak: > 0 renders the little book badge with the count.
  verseStreak?: number | null
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
          className={`flex items-center justify-center rounded-full bg-gradient-to-br from-avatar-1/80 to-avatar-2/80 font-bold text-white ${s.circle} ${className}`}
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
      {verseStreak != null && verseStreak > 0 && (
        <span
          className={`absolute flex items-center gap-0.5 rounded-full border border-gold/40 bg-[#151b2e] font-bold text-gold ${s.streak}`}
          title={`${verseStreak}-day reading streak`}
        >
          <BookOpen className="h-[1em] w-[1em]" strokeWidth={2.5} />
          x{verseStreak}
        </span>
      )}
    </div>
  )
}
