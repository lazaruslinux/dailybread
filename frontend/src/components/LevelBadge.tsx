import type { Tier } from '../lib/api'

// The one badge a person wears beside their name: the level, in a small
// circle whose ring is the tier speaking. Slice through Breadmaster, each
// band of ten levels warms the ring a little — color and material only,
// never particles or shine. It has to read at 11px under a name on the
// strip and at hero size in a profile, in both themes.

export const TIER_META: Record<
  Tier,
  { label: string; ring: string; text: string; gradient?: string }
> = {
  slice: { label: 'Slice', ring: 'border-fg/35 bg-fg/5', text: 'text-fg/75' },
  roll: {
    label: 'Roll',
    ring: 'border-amber-600/70 bg-amber-500/15',
    text: 'text-amber-800 dark:text-amber-300',
  },
  loaf: { label: 'Loaf', ring: 'border-gold/80 bg-gold/15 shadow-[0_0_6px_-2px]', text: 'text-gold' },
  baker: {
    label: 'Baker',
    ring: 'border-gold bg-gold/15 shadow-[0_0_8px_-2px] ring-1 ring-gold/30',
    text: 'text-gold',
  },
  breadmaster: {
    label: 'Breadmaster',
    // The gradient ring is a wrapper trick: the outer circle IS the ring.
    ring: 'border-transparent',
    text: 'text-amber-800 dark:text-amber-200',
    gradient: 'bg-gradient-to-br from-amber-300 via-gold to-orange-600 shadow-[0_0_10px_-2px]',
  },
}

const SIZES = {
  sm: { outer: 'h-5 min-w-5 px-1 text-[10px]', pad: 'p-[1.5px]' },
  md: { outer: 'h-6 min-w-6 px-1 text-[11px]', pad: 'p-[2px]' },
  lg: { outer: 'h-16 min-w-16 px-2 text-2xl', pad: 'p-[3px]' },
} as const

export function tierOf(level: number): Tier {
  const bands: Tier[] = ['slice', 'roll', 'loaf', 'baker', 'breadmaster']
  return bands[Math.min(Math.floor(Math.max(level, 1) / 10), bands.length - 1)]
}

export function LevelBadge({
  level,
  size = 'sm',
  className = '',
}: {
  level: number
  size?: keyof typeof SIZES
  className?: string
}) {
  const tier = tierOf(level)
  const meta = TIER_META[tier]
  const s = SIZES[size]
  const circle = (
    <span
      className={`flex items-center justify-center rounded-full border font-bold tabular-nums ${s.outer} ${meta.ring} ${meta.text} ${meta.gradient ? 'border-0 bg-[var(--bg-base)]' : ''}`}
      title={`Level ${level} · ${meta.label}`}
    >
      {level}
    </span>
  )
  if (!meta.gradient) return <span className={`inline-flex shrink-0 ${className}`}>{circle}</span>
  return (
    <span className={`inline-flex shrink-0 rounded-full ${s.pad} ${meta.gradient} ${className}`}>
      {circle}
    </span>
  )
}
