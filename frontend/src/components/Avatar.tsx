import type { Mood } from '../lib/api'
import { MOODS, initialsOf } from '../lib/moods'

// Initials circle used everywhere a person appears. The optional mood badge
// is a small weather icon pinned to the corner; no mood means no badge, and
// a hidden mood never reaches the client in the first place.

const SIZES = {
  sm: { circle: 'h-7 w-7 text-[10px]', badge: 'h-3.5 w-3.5 -right-0.5 -bottom-0.5 p-[1px]' },
  md: { circle: 'h-11 w-11 text-sm', badge: 'h-5 w-5 -right-1 -bottom-0.5 p-0.5' },
  lg: { circle: 'h-20 w-20 text-2xl', badge: 'h-7 w-7 right-0 bottom-0 p-1' },
} as const

export function Avatar({
  name,
  mood = null,
  size = 'md',
}: {
  name: string
  mood?: Mood | null
  size?: keyof typeof SIZES
}) {
  const s = SIZES[size]
  const meta = mood ? MOODS[mood.level] : null

  return (
    <div className="relative inline-block shrink-0">
      <div
        className={`flex items-center justify-center rounded-full bg-gradient-to-br from-indigo-400/60 to-violet-500/60 font-bold ${s.circle}`}
      >
        {initialsOf(name)}
      </div>
      {meta && (
        <span
          className={`absolute flex items-center justify-center rounded-full border border-white/20 bg-[#151b2e] ${s.badge}`}
          title={meta.label}
        >
          <meta.Icon className={`h-full w-full ${meta.tint}`} strokeWidth={2.5} />
        </span>
      )}
    </div>
  )
}
