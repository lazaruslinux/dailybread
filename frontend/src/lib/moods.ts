import { Cloud, CloudLightning, CloudRain, CloudSun, Sun, type LucideIcon } from 'lucide-react'
import type { MoodLevel } from './api'

// Moods render as weather, not smiley faces: a five-step scale from sun to
// storm. Clean line icons, one accent color per level, plain labels.

export interface MoodMeta {
  label: string
  Icon: LucideIcon
  tint: string // icon color
  chip: string // background for badges/buttons
}

export const MOODS: Record<MoodLevel, MoodMeta> = {
  sunny: { label: 'Great', Icon: Sun, tint: 'text-gold', chip: 'bg-gold/20' },
  partly: { label: 'Good', Icon: CloudSun, tint: 'text-gold', chip: 'bg-gold/15' },
  cloudy: { label: 'Okay', Icon: Cloud, tint: 'text-slate-300', chip: 'bg-slate-400/20' },
  rainy: { label: 'Low', Icon: CloudRain, tint: 'text-sky-300', chip: 'bg-sky-400/20' },
  stormy: { label: 'Rough', Icon: CloudLightning, tint: 'text-violet-300', chip: 'bg-violet-400/20' },
}

export const MOOD_ORDER: MoodLevel[] = ['sunny', 'partly', 'cloudy', 'rainy', 'stormy']

export function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
}

// Time-of-day hello, shared by the Home header and the daily greeting sheet.
export function timeGreeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

// "07:00:00" -> "7:00 AM"
export function formatTime(t: string | null): string | null {
  if (!t) return null
  const [h, m] = t.split(':').map(Number)
  const suffix = h < 12 ? 'AM' : 'PM'
  const hour = h % 12 === 0 ? 12 : h % 12
  return `${hour}:${String(m).padStart(2, '0')} ${suffix}`
}

// The full slot: "3:00 – 4:30 PM", or "11:30 AM – 1:00 PM" across noon. The
// start drops its AM/PM when the end shares it, so short slots stay short.
export function formatTimeRange(start: string | null, end: string | null): string | null {
  const from = formatTime(start)
  if (!from) return null
  const to = formatTime(end)
  if (!to) return from
  const sameHalf = from.slice(-2) === to.slice(-2)
  return `${sameHalf ? from.slice(0, -3) : from} – ${to}`
}
