import { BookOpen } from 'lucide-react'
import { useEffect, useState } from 'react'
import { initialsOf } from '../lib/moods'

// Initials circle used everywhere a person appears. When the member has an
// uploaded photo (src), it fills the circle; otherwise the coloured initials
// show. A load error silently falls back to the initials. The one badge an
// avatar wears is the verse streak (gold book + count, bottom right); moods
// live on profiles and the village mini profile, so the photo stays a photo.

const SIZES = {
  sm: { circle: 'h-7 w-7 text-[10px]', streak: '-right-1 -bottom-0.5 h-3.5 px-1 text-[7px]' },
  md: { circle: 'h-11 w-11 text-sm', streak: '-right-1.5 -bottom-0.5 h-5 px-1.5 text-[9px]' },
  lg: { circle: 'h-20 w-20 text-2xl', streak: 'right-0 bottom-0 h-7 px-2 text-xs' },
} as const

export function Avatar({
  name,
  src = null,
  verseStreak = null,
  size = 'md',
  className = '',
}: {
  name: string
  // Photo URL, or null/undefined to draw generated initials.
  src?: string | null
  // Verse-reading streak: > 0 renders the little book badge with the count.
  verseStreak?: number | null
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
