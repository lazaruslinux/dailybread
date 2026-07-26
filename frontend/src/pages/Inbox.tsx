import { useEffect, useRef, useState } from 'react'
import {
  BadgeCheck,
  CalendarCheck,
  CookingPot,
  Dumbbell,
  Home,
  Hourglass,
  Mailbox,
  ShoppingCart,
  Trees,
  UserPlus,
  Users,
  Utensils,
  type LucideIcon,
} from 'lucide-react'
import * as api from '../lib/api'
import { Coin } from '../components/BreadIcon'

// The You tab's Inbox: the history behind the notifications. Rows arrive
// newest first from the server (capped there, so no pagination). Opening the
// page marks everything read on the server, but this visit keeps the unread
// highlights it fetched — you can still see what's new before the flags
// reset on the next visit.

const KIND_ICON: Record<string, { Icon: LucideIcon; tint: string }> = {
  crumb: { Icon: Coin as unknown as LucideIcon, tint: 'text-gold' },
  board: { Icon: CalendarCheck, tint: 'text-fg/60' },
  dinner: { Icon: Utensils, tint: 'text-fg/60' },
  workout: { Icon: Dumbbell, tint: 'text-fg/60' },
  pending: { Icon: Hourglass, tint: 'text-amber-400' },
  approved: { Icon: BadgeCheck, tint: 'text-gold' },
  invite: { Icon: Mailbox, tint: 'text-accent-bright' },
  rsvp: { Icon: Users, tint: 'text-fg/60' },
  village: { Icon: Trees, tint: 'text-accent-bright' },
  grocery: { Icon: ShoppingCart, tint: 'text-fg/60' },
  recipe: { Icon: CookingPot, tint: 'text-fg/60' },
  member: { Icon: UserPlus, tint: 'text-accent-bright' },
  household: { Icon: Home, tint: 'text-accent-bright' },
}

// "Just now" through short dates: enough to place a row without a timestamp
// column. The server sends UTC; Date handles the local shift.
function ago(iso: string): string {
  const then = new Date(iso)
  const mins = Math.floor((Date.now() - then.getTime()) / 60_000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return then.toLocaleDateString(undefined, { weekday: 'long' })
  return then.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// Where a tapped entry leads, by kind: board/village/member news lives on
// Home, workouts on the Health tab, crumb earns in Breadcrumbs & Levels, and
// the Kitchen owns groceries, recipes, and the meal planner (dinner). The
// caller (You) owns the actual navigation.
export function inboxDestination(kind: string): 'home' | 'fitness' | 'crumbs' | 'kitchen' {
  if (kind === 'crumb') return 'crumbs'
  if (kind === 'workout') return 'fitness'
  // Dinner lines move off Home to the Kitchen, where the meal planner lives.
  if (kind === 'grocery' || kind === 'recipe' || kind === 'dinner') return 'kitchen'
  return 'home'
}

export function InboxPage({
  onAllRead,
  onGo,
}: {
  onAllRead?: () => void
  onGo?: (kind: string) => void
}) {
  const [entries, setEntries] = useState<api.InboxEntry[] | null>(null)
  // Two-tap clear: the first tap arms, the second empties. It disarms on blur
  // or after a few seconds so a stray first tap never stays hot.
  const [armed, setArmed] = useState(false)
  const armedTimer = useRef<number | null>(null)

  function disarm() {
    setArmed(false)
    if (armedTimer.current !== null) {
      clearTimeout(armedTimer.current)
      armedTimer.current = null
    }
  }

  async function handleClear() {
    if (!armed) {
      setArmed(true)
      armedTimer.current = window.setTimeout(disarm, 4000)
      return
    }
    disarm()
    try {
      await api.clearInbox()
    } catch {
      // A failed clear just leaves the list as it was.
      return
    }
    setEntries([]) // the empty state takes over
  }

  useEffect(
    () => () => {
      if (armedTimer.current !== null) clearTimeout(armedTimer.current)
    },
    [],
  )

  useEffect(() => {
    let active = true
    api
      .getInbox()
      .then((rows) => {
        if (!active) return
        setEntries(rows)
        // Seen is read: clear the badges now, keep this visit's highlights.
        if (rows.some((r) => !r.read)) {
          api.markInboxRead().then(() => onAllRead?.()).catch(() => {})
        }
      })
      .catch(() => {
        if (active) setEntries([])
      })
    return () => {
      active = false
    }
    // Mount-only: the list is a snapshot of this visit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (entries === null) return null

  if (entries.length === 0) {
    return (
      <div className="glass p-6 text-center">
        <p className="text-sm font-semibold text-fg/70">Nothing yet</p>
        <p className="mt-1 text-xs leading-relaxed text-fg/45">
          Crumbs you earn and family activity will land here.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleClear}
          onBlur={disarm}
          className="min-h-11 rounded-lg px-3 text-sm font-semibold text-fg/55 transition-colors hover:text-fg"
        >
          {armed ? 'Tap again to clear' : 'Clear inbox'}
        </button>
      </div>
      <div className="glass overflow-hidden p-4">
        {/* Hairline dividers, not per-row cards: an inbox is a list. Unread rows
          get a warm accent wash bleeding to the card edges plus a full-contrast
          title, so "new" reads at a glance on both themes. */}
      <div className="flex flex-col divide-y divide-fg/10">
        {entries.map((entry) => {
          const { Icon, tint } = KIND_ICON[entry.kind] ?? KIND_ICON.board
          return (
            <button
              key={entry.id}
              type="button"
              onClick={() => onGo?.(entry.kind)}
              className={`-mx-4 flex w-[calc(100%+2rem)] items-center gap-3 px-5 py-3 text-left transition-colors hover:bg-fg/5 active:bg-fg/10 ${
                entry.read ? '' : 'bg-accent-bright/10'
              }`}
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-fg/10">
                <Icon className={`h-4.5 w-4.5 ${tint}`} strokeWidth={2} />
              </span>
              <span className="min-w-0 flex-1">
                <span
                  className={`block text-sm font-semibold ${
                    entry.read ? 'text-fg/85' : 'text-fg'
                  }`}
                >
                  {entry.title}
                </span>
                {entry.body && (
                  <span className="block text-xs leading-snug text-fg/45">{entry.body}</span>
                )}
              </span>
              <span className="flex shrink-0 flex-col items-end gap-1">
                <span className="text-xs text-fg/40">{ago(entry.created_at)}</span>
                {!entry.read && <span className="h-2 w-2 rounded-full bg-rose-400" />}
              </span>
            </button>
          )
        })}
        </div>
      </div>
    </div>
  )
}
