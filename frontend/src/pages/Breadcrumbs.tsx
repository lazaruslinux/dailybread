import { useEffect, useState } from 'react'
import { BookOpen, CalendarCheck, Dumbbell, Lock, Sparkles, Sun } from 'lucide-react'
import * as api from '../lib/api'
import { BreadIcon } from '../components/BreadIcon'
import { LevelBadge, TIER_META, tierOf } from '../components/LevelBadge'

// The one place the economy explains itself: how crumbs are earned, what
// levels cost, and what the tier ladder looks like. Static words, live
// numbers for your own progress up top.

const EARNS = [
  {
    Icon: Sun,
    label: 'Show up',
    amount: '+1',
    detail: 'Open dailybread once a day',
  },
  {
    Icon: BookOpen,
    label: 'Read the daily verses',
    amount: '+3',
    detail: 'All three of the day, once a day',
  },
  {
    Icon: Dumbbell,
    label: 'Finish a workout',
    amount: '+3',
    detail: '15 minutes or more, synced from your watch, once a day',
  },
  {
    Icon: Lock,
    label: 'Lock in your calories',
    amount: '+2',
    detail: "Log your day's food, then lock it in on the Nutrition tab",
  },
  {
    Icon: CalendarCheck,
    label: 'Kid tasks',
    amount: '+1',
    detail: 'Kids earn when a parent approves a check-off, up to 3 a day',
  },
  {
    Icon: Sparkles,
    label: 'Streak bonuses',
    amount: '+5 to +50',
    detail: 'Reading streaks pay extra at 7, 30, and 100 days',
  },
]

const LADDER = [5, 15, 25, 35, 45]

export function BreadcrumbsPage() {
  const [me, setMe] = useState<api.Crumbs | null>(null)
  useEffect(() => {
    api.getMyCrumbs().then(setMe).catch(() => {})
  }, [])

  return (
    <div className="flex flex-col gap-4">
      {me && (
        <div className="glass flex flex-col items-center gap-2 p-5 text-center">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-fg/55">Level</span>
            <LevelBadge level={me.level} size="md" />
            <span className={`text-sm font-bold ${TIER_META[me.tier].text}`}>
              {TIER_META[me.tier].label}
            </span>
          </div>
          <div className="h-1.5 w-full max-w-64 overflow-hidden rounded-full bg-fg/10">
            <div
              className="h-full rounded-full bg-gold/70"
              style={{ width: `${Math.min((me.level_progress / me.next_level_cost) * 100, 100)}%` }}
            />
          </div>
          <p className="flex items-center gap-1 text-xs text-fg/45">
            <BreadIcon className="h-3.5 w-3.5 text-gold" strokeWidth={2.5} /> {me.total} earned ·{' '}
            {me.next_level_cost - me.level_progress} to level {me.level + 1}
          </p>
        </div>
      )}

      <div className="glass p-4">
        <span className="mb-3 block text-xs font-semibold uppercase tracking-wide text-fg/50">
          How to earn
        </span>
        <div className="flex flex-col gap-1">
          {EARNS.map((earn) => (
            <div key={earn.label} className="flex items-center gap-3 rounded-xl px-1.5 py-2">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-fg/10">
                <earn.Icon className="h-4.5 w-4.5 text-gold" strokeWidth={2} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-fg/85">{earn.label}</span>
                <span className="block text-xs leading-snug text-fg/45">{earn.detail}</span>
              </span>
              <span className="flex shrink-0 items-center gap-1 text-sm font-bold text-gold">
                <BreadIcon className="h-3.5 w-3.5" strokeWidth={2.5} />
                {earn.amount}
              </span>
            </div>
          ))}
        </div>
        <p className="mt-2 px-1.5 text-xs leading-relaxed text-fg/40">
          Crumbs add up into levels. Each level costs a little more than the last, and nothing
          here ever needs to be bought back: the number only grows.
        </p>
      </div>

      <div className="glass p-4">
        <span className="mb-3 block text-xs font-semibold uppercase tracking-wide text-fg/50">
          The tier ladder
        </span>
        <div className="flex flex-col gap-2">
          {LADDER.map((level) => {
            const tier = tierOf(level)
            return (
              <div key={tier} className="flex items-center gap-3 rounded-xl px-1.5 py-1.5">
                <LevelBadge level={level} size="md" />
                <span className={`text-sm font-bold ${TIER_META[tier].text}`}>
                  {TIER_META[tier].label}
                </span>
                <span className="ml-auto text-xs text-fg/40">
                  {tier === 'breadmaster'
                    ? 'level 40 and beyond'
                    : `levels ${Math.floor(level / 10) * 10 || 1} to ${Math.floor(level / 10) * 10 + 9}`}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
