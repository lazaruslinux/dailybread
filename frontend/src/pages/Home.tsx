import { AnimatePresence, motion } from 'framer-motion'
import { CalendarClock, CalendarDays, Check, ChevronLeft, ChevronRight, Hourglass, Plus, Rows3, Undo2, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../lib/api'
import { avatarUrl } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { canCheckItem } from '../lib/items'
import { timeGreeting } from '../lib/moods'
import { Avatar } from '../components/Avatar'
import { DayTimeline } from '../components/DayTimeline'
import { Coin } from '../components/BreadIcon'
import { FamilyStrip } from '../components/FamilyStrip'
import { ItemCard, SectionDivider } from '../components/ItemCard'
import { ItemDetail } from '../components/ItemDetail'
import { ItemSheet } from '../components/ItemSheet'
import { TonightCard } from '../components/Meals'
import { VerseCard } from '../components/VerseCard'
import { ShareEventSheet, VillageEventSheet, VillageStrip } from '../components/VillageEvents'
import { FormError } from '../components/ui'

// One toggle in the parent's "show cards for" filter row.
function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${
        active
          ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
          : 'border-fg/10 bg-fg/5 text-fg/55 hover:bg-fg/10'
      }`}
    >
      {children}
    </button>
  )
}

const pad = (n: number) => String(n).padStart(2, '0')

// "Today" / "Yesterday" / "Tomorrow" / "Mon, Jul 6" for approval rows and the
// timeline's day header.
function relativeDay(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  const today = new Date()
  const days = Math.round(
    (new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() - date.getTime()) /
      86_400_000,
  )
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days === -1) return 'Tomorrow'
  return date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

// ISO date arithmetic in local time (new Date('YYYY-MM-DD') would parse UTC).
function shiftDay(iso: string, delta: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const next = new Date(y, m - 1, d + delta)
  return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}`
}

// Kid mode, the parents' side: every check-off in the family still waiting
// on a parent, above the board where it can't be missed. Approve makes the
// kid's mark official; Put back clears it so they can redo the thing.
function WaitingOnYou({
  approvals,
  family,
  onApprove,
  onPutBack,
}: {
  approvals: api.PendingApproval[]
  family: api.FamilyMember[]
  onApprove: (a: api.PendingApproval) => void
  onPutBack: (a: api.PendingApproval) => void
}) {
  if (approvals.length === 0) return null
  return (
    <motion.section
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass mb-5 border border-amber-400/25 p-4"
      data-waiting-on-you
    >
      <span className="mb-3 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-amber-300">
        <Hourglass className="h-3 w-3" strokeWidth={3} /> Waiting on you
      </span>
      <div className="flex flex-col gap-2.5">
        <AnimatePresence>
          {approvals.map((a) => {
            const kid = family.find((m) => m.id === a.user.id) ?? a.user
            return (
              <motion.div
                key={`${a.item_id}-${a.user.id}-${a.date_for}`}
                layout
                exit={{ opacity: 0, x: 24 }}
                className="flex items-center gap-3"
              >
                <Avatar name={kid.display_name} src={avatarUrl(kid)} size="sm" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{a.title}</p>
                  <p className="text-xs text-fg/50">
                    {kid.display_name.split(/\s+/)[0]} · {relativeDay(a.date_for)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onPutBack(a)}
                  className="shrink-0 rounded-full border border-fg/10 bg-fg/5 px-2.5 py-1.5 text-xs font-semibold text-fg/60 transition-colors hover:bg-fg/10"
                >
                  Put back
                </button>
                <button
                  type="button"
                  onClick={() => onApprove(a)}
                  className="flex shrink-0 items-center gap-1 rounded-full border border-emerald-300/40 bg-emerald-400/15 px-2.5 py-1.5 text-xs font-bold text-emerald-300 transition-colors hover:bg-emerald-400/25"
                >
                  <Check className="h-3.5 w-3.5" strokeWidth={3} /> Approve
                </button>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </motion.section>
  )
}

// Which slice of "today" a card belongs to, decided by the live clock. Past due
// is only for one-offs (routines are habits, never overdue); a passed timed
// routine just stays in Now until it's done.
type Slot = 'pastdue' | 'now' | 'coming' | 'anytime'
function todaySlot(item: api.FeedItem, nowHm: string): Slot {
  if (!item.time_of_day && !item.all_day) return 'anytime'
  if (item.all_day) return 'now'
  const end = item.end_time || item.time_of_day! // has a start time here
  if (item.kind !== 'routine' && end < nowHm) return 'pastdue'
  if (item.time_of_day! <= nowHm) return 'now'
  return 'coming'
}


// The day's first hello: a slim strip when today's show-up crumb landed.
// Marked seen the moment it renders, so it greets once per day per device
// whether or not it's dismissed (the award itself is server-side and never
// repeats; login_award_today stays true all day, so showing can't gate on it).
function WelcomeCrumb() {
  const todayKey = `crumb-banner-${api.localDate()}`
  const [show, setShow] = useState(false)
  useEffect(() => {
    if (localStorage.getItem(todayKey)) return
    api
      .getMyCrumbs()
      .then((c) => {
        if (!c.login_award_today) return
        localStorage.setItem(todayKey, '1')
        setShow(true)
      })
      .catch(() => {})
  }, [todayKey])
  if (!show) return null
  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-3 flex items-center gap-2 rounded-xl border border-gold/30 bg-gold/10 px-3 py-2"
      data-welcome-crumb
    >
      <Coin className="h-4 w-4 shrink-0" />
      <span className="min-w-0 flex-1 text-sm font-medium text-fg/80">
        +1 breadcrumb earned · welcome back
      </span>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => setShow(false)}
        className="-m-3.5 shrink-0 rounded-lg p-3.5 text-fg/40 hover:bg-fg/10 hover:text-fg/70"
      >
        <X className="h-4 w-4" strokeWidth={2.5} />
      </button>
    </motion.div>
  )
}

export function Home({
  onOpenProfile,
  onOpenKitchen,
  onOpenCalendar,
}: {
  onOpenProfile: (id: number) => void
  onOpenKitchen: () => void
  onOpenCalendar: () => void
}) {
  const { user } = useAuth()
  const isParent = user?.role === 'parent'
  const isMinor = user?.is_minor ?? false

  const [feed, setFeed] = useState<api.Feed | null>(null)
  const [family, setFamily] = useState<api.FamilyMember[]>([])
  const [familyName, setFamilyName] = useState<string | null>(null)
  // Kid mode: the family's check-offs waiting on a parent. Parents only.
  const [approvals, setApprovals] = useState<api.PendingApproval[]>([])
  // Village events: the invite strip + the RSVP sheets. Parents only — kids
  // never see the strip; a landed copy is just a normal card to them.
  const [vEvents, setVEvents] = useState<api.VillageEvent[]>([])
  const [eventSheet, setEventSheet] = useState<api.VillageEvent | null>(null)
  const [shareSheet, setShareSheet] = useState<api.FeedItem | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sheet, setSheet] = useState<{ open: boolean; item: api.FeedItem | null }>({ open: false, item: null })
  // checkable rides along so the detail sheet knows whether to offer "Mark done".
  const [detail, setDetail] = useState<{ item: api.FeedItem; checkable: boolean } | null>(null)
  const [toast, setToast] = useState<api.FeedItem | null>(null)
  const toastTimer = useRef<number | undefined>(undefined)
  // Re-rendering once a minute keeps the section buckets honest without polling.
  const [clock, setClock] = useState(() => new Date())
  // Parent-only board lens: which members' cards to show. Empty means everyone's.
  const [filter, setFilter] = useState<number[]>([])
  // How today's timed cards are drawn: stacked list, or laid on a day timeline.
  // Always opens on List; Timeline lasts only until the page is left, so the
  // board greets everyone the same way every time.
  const [view, setView] = useState<'list' | 'timeline'>('list')
  // The day the timeline shows. null = today (the live board); any other day
  // is a read-only peek fetched from the calendar endpoint.
  const [timelineDate, setTimelineDate] = useState<string | null>(null)
  const [peekItems, setPeekItems] = useState<api.FeedItem[] | null>(null)
  const pickView = (v: 'list' | 'timeline') => {
    setView(v)
    if (v === 'list') setTimelineDate(null) // the list is always today
  }

  // Fetch the peeked day's cards whenever the timeline leaves today (and
  // refetch after any board refresh, so an edit shows up in the peek too).
  useEffect(() => {
    if (!timelineDate) {
      setPeekItems(null)
      return
    }
    let stale = false
    api
      .getCalendar(timelineDate, timelineDate)
      .then((cal) => {
        if (!stale) setPeekItems(cal.days[0]?.items ?? [])
      })
      .catch(() => {
        if (!stale) setPeekItems([])
      })
    return () => {
      stale = true
    }
  }, [timelineDate, feed])

  const refresh = useCallback(async () => {
    try {
      const [f, fam] = await Promise.all([api.getFeed(), api.getFamily()])
      setFeed(f)
      setFamily(fam)
      setError(null)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load the board.')
    }
    // The header's team name; separate so a hiccup never blanks the board.
    api.getMyFamily().then((fam) => setFamilyName(fam.name)).catch(() => {})
    if (isParent) {
      // Separate so a hiccup here never blanks the board.
      api.getPendingApprovals().then(setApprovals).catch(() => {})
      api.villageEvents().then(setVEvents).catch(() => {})
    }
  }, [isParent])

  useEffect(() => {
    refresh()
    const tick = setInterval(() => setClock(new Date()), 60_000)
    // Coming back to the app (phone unlock, tab focus) refetches the board.
    const onVisible = () => document.visibilityState === 'visible' && refresh()
    document.addEventListener('visibilitychange', onVisible)
    // The daily greeting saves a mood/status over the board; show it right away.
    window.addEventListener('db:profile-changed', refresh)
    return () => {
      clearInterval(tick)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('db:profile-changed', refresh)
      window.clearTimeout(toastTimer.current)
    }
  }, [refresh])

  // Flip one card's completed flag in local state across every bucket. This is
  // the optimistic half of a toggle: the UI answers the tap instantly and the
  // server call catches up (or the flag flips back if it fails).
  const setItemCompleted = useCallback(
    (id: number, completed: boolean) => {
      const patch = (items: api.FeedItem[]) =>
        items.map((it) =>
          it.id === id
            ? {
                ...it,
                completed,
                assignee_completions:
                  it.assignee_completions?.map((c) =>
                    c.user_id === user?.id ? { ...c, completed } : c,
                  ) ?? null,
              }
            : it,
        )
      setFeed((f) =>
        f ? { ...f, overdue: patch(f.overdue), today: patch(f.today), next7: patch(f.next7) } : f,
      )
      setDetail((d) => (d && d.item.id === id ? { ...d, item: { ...d.item, completed } } : d))
    },
    [user],
  )

  // Flip one member's own row on a per-person (routine) card. Used by the
  // detail sheet so a parent can check a routine off on a child's behalf.
  const setAssigneeCompleted = useCallback(
    (id: number, userId: number, completed: boolean) => {
      const patch = (items: api.FeedItem[]) =>
        items.map((it) =>
          it.id === id
            ? {
                ...it,
                completed: userId === user?.id ? completed : it.completed,
                assignee_completions:
                  it.assignee_completions?.map((c) =>
                    // Either way the waiting state is settled: an approval
                    // promoted it, a put-back deleted it.
                    c.user_id === userId ? { ...c, completed, pending: false } : c,
                  ) ?? null,
              }
            : it,
        )
      setFeed((f) =>
        f ? { ...f, overdue: patch(f.overdue), today: patch(f.today), next7: patch(f.next7) } : f,
      )
      setDetail((d) => (d && d.item.id === id ? { ...d, item: patch([d.item])[0] } : d))
    },
    [user],
  )

  // Kid mode's optimistic half: flip the viewer's own WAITING state (their
  // tap that a parent hasn't answered yet) without ever touching completed.
  const setItemPending = useCallback(
    (id: number, pending: boolean) => {
      const patch = (items: api.FeedItem[]) =>
        items.map((it) =>
          it.id === id
            ? {
                ...it,
                pending,
                pending_by: pending ? (user?.id ?? null) : null,
                assignee_completions:
                  it.assignee_completions?.map((c) =>
                    c.user_id === user?.id ? { ...c, pending } : c,
                  ) ?? null,
              }
            : it,
        )
      setFeed((f) =>
        f ? { ...f, overdue: patch(f.overdue), today: patch(f.today), next7: patch(f.next7) } : f,
      )
      setDetail((d) => (d && d.item.id === id ? { ...d, item: patch([d.item])[0] } : d))
    },
    [user],
  )

  function showUndoToast(item: api.FeedItem) {
    window.clearTimeout(toastTimer.current)
    setToast(item)
    toastTimer.current = window.setTimeout(() => setToast(null), 5000)
  }

  // A completion that paid breadcrumbs celebrates in place: the card floats
  // the +n (via the db:crumbs event) and the header's level refreshes.
  function celebrate(itemId: number, res: api.FeedItem) {
    if ((res.crumbs_awarded ?? 0) > 0) {
      window.dispatchEvent(
        new CustomEvent('db:crumbs', { detail: { itemId, amount: res.crumbs_awarded } }),
      )
      window.dispatchEvent(new Event('db:profile-changed'))
    }
  }

  async function toggle(item: api.FeedItem) {
    // Kid mode first: a minor's tap becomes a waiting mark, and tapping the
    // waiting mark again withdraws it. Done stays a parent's call.
    if (item.pending && item.pending_by === user?.id) {
      setItemPending(item.id, false)
      try {
        await api.uncompleteItem(item.id)
        refresh()
      } catch (err) {
        setItemPending(item.id, true)
        setError(err instanceof api.ApiError ? err.message : 'Could not update the card.')
      }
      return
    }
    if (isMinor && !item.completed) {
      setItemPending(item.id, true)
      try {
        await api.completeItem(item.id)
        refresh()
      } catch (err) {
        setItemPending(item.id, false)
        setError(err instanceof api.ApiError ? err.message : 'Could not update the card.')
      }
      return
    }

    const next = !item.completed
    setItemCompleted(item.id, next)
    try {
      // A parent tapping a kid's pending card here approves it; the approval day
      // is always now, so a dated one-off re-dates into today's Done. Harmless on
      // an ordinary complete (the backend uses it only on the approval branch).
      if (next) celebrate(item.id, await api.completeItem(item.id, undefined, undefined, api.localDate()))
      else await api.uncompleteItem(item.id)
      if (next) showUndoToast(item)
      refresh()
    } catch (err) {
      setItemCompleted(item.id, !next)
      // Most likely a 403 on someone else's card; surface it briefly.
      setError(err instanceof api.ApiError ? err.message : 'Could not update the card.')
    }
  }

  // Check a routine off for a specific member (from the detail sheet's
  // per-person list). Parents can do this for anyone; a member for themselves.
  // For a parent this doubles as the approval control: completing over a kid's
  // waiting mark approves it, un-checking puts it back.
  async function toggleFor(item: api.FeedItem, userId: number, done: boolean) {
    if (isMinor && userId === user?.id) {
      // A minor's own row follows kid-mode semantics: tap = waiting mark (or
      // withdrawing one), never a direct Done.
      const mine = item.assignee_completions?.find((c) => c.user_id === userId)
      if (mine?.completed) return // approved: a parent's word, not theirs to undo
      setItemPending(item.id, done)
      try {
        if (done) await api.completeItem(item.id, userId)
        else await api.uncompleteItem(item.id, userId)
        refresh()
      } catch (err) {
        setItemPending(item.id, !done)
        setError(err instanceof api.ApiError ? err.message : 'Could not update the card.')
      }
      return
    }
    if (item.kind !== 'routine' && item.pending && item.pending_by === userId) {
      // A parent answering a one-shot's waiting mark from the detail sheet:
      // approve promotes it to done, put back clears it.
      setItemPending(item.id, false)
      setItemCompleted(item.id, done)
      try {
        // Approving a one-shot from the detail sheet: pass the approval day so a
        // dated one-off lands in Done today (undated/routines ignore it).
        if (done) celebrate(item.id, await api.completeItem(item.id, userId, undefined, api.localDate()))
        else await api.uncompleteItem(item.id, userId)
        refresh()
      } catch (err) {
        setError(err instanceof api.ApiError ? err.message : 'Could not update the card.')
        refresh()
      }
      return
    }
    setAssigneeCompleted(item.id, userId, done)
    try {
      // Completing for another member can promote their pending mark, so carry
      // the approval day (ignored by the backend on a plain complete).
      if (done) celebrate(item.id, await api.completeItem(item.id, userId, undefined, api.localDate()))
      else await api.uncompleteItem(item.id, userId)
      refresh()
    } catch (err) {
      setAssigneeCompleted(item.id, userId, !done)
      setError(err instanceof api.ApiError ? err.message : 'Could not update the card.')
    }
  }

  async function undo() {
    if (!toast) return
    const item = toast
    window.clearTimeout(toastTimer.current)
    setToast(null)
    setItemCompleted(item.id, false)
    try {
      await api.uncompleteItem(item.id)
      refresh()
    } catch (err) {
      setItemCompleted(item.id, true)
      setError(err instanceof api.ApiError ? err.message : 'Could not update the card.')
    }
  }

  async function deleteFromDetail(item: api.FeedItem) {
    try {
      await api.deleteItem(item.id)
      setDetail(null)
      refresh()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not remove the card.')
    }
  }

  const canCheck = (item: api.FeedItem) => canCheckItem(item, user)

  const openEditor = (item: api.FeedItem | null) => {
    setDetail(null)
    setSheet({ open: true, item })
  }

  const cardProps = (item: api.FeedItem) => {
    // Kid mode: once a parent has approved (completed, no waiting mark of
    // their own), the card is settled — a minor gets no checkbox to undo it.
    const lockedForMinor =
      isMinor && item.completed && !(item.pending && item.pending_by === user?.id)
    const checkable = canCheck(item) && !lockedForMinor
    return {
      item,
      canCheck: checkable,
      family,
      viewerId: user?.id,
      viewerIsParent: isParent,
      // The date lives inside the card for anything not dated today, so the
      // past-due and next-7-days lists read without repeated date separators.
      showDate: item.date_for != null && item.date_for !== feed?.date,
      onToggle: checkable ? () => toggle(item) : undefined,
      onOpen: () => setDetail({ item, checkable }),
      onEdit: isParent ? () => openEditor(item) : undefined,
    }
  }

  // Answer an approval row. The row leaves the list optimistically; the
  // refresh brings back the truth (and the card's new state with it).
  async function answerApproval(a: api.PendingApproval, approve: boolean) {
    setApprovals((prev) =>
      prev.filter(
        (p) => !(p.item_id === a.item_id && p.user.id === a.user.id && p.date_for === a.date_for),
      ),
    )
    try {
      if (approve) await api.completeItem(a.item_id, a.user.id, a.date_for, api.localDate())
      else await api.uncompleteItem(a.item_id, a.user.id, a.date_for)
      refresh()
    } catch (err) {
      setApprovals((prev) => [...prev, a])
      setError(err instanceof api.ApiError ? err.message : 'Could not update the card.')
    }
  }

  const toggleFilter = (id: number) =>
    setFilter((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  // The filter is about who a card is FOR, not who can see it: a member matches
  // if they're an assignee, or (when nobody is assigned) the owner.
  const isForMember = (item: api.FeedItem, id: number) =>
    item.assignees.length > 0
      ? item.assignees.some((a) => a.id === id)
      : item.owner_id === id
  const matchesFilter = (item: api.FeedItem) =>
    filter.length === 0 || filter.some((id) => isForMember(item, id))

  const nowHm = `${pad(clock.getHours())}:${pad(clock.getMinutes())}:00`

  const overdue = feed ? feed.overdue.filter(matchesFilter) : []
  const todayCards = feed ? feed.today.filter(matchesFilter) : []
  const next7 = feed ? feed.next7.filter(matchesFilter) : []

  // Completing a card for today (or ahead of time) moves it to the bottom Done
  // section, crossed out but still visible for the day (the "I did it" payoff).
  // Past-due cards are the exception: they weren't done today, so checking one
  // archives it straight to its own day in the calendar instead of lingering
  // here. (The server drops them on refresh; filtering overdue out keeps the
  // optimistic in-between state consistent with that.)
  const done = [...todayCards, ...next7].filter((i) => i.completed)

  // The timeline draws every timed card in place - done ones faded, missed
  // ones right where they were scheduled - so those stay off the Done and
  // Past due lists in that view. Only carry-overs from earlier days (which
  // have no spot on today's grid) and the untimed sections keep their lists.
  const timed = todayCards.filter((i) => i.time_of_day && !i.all_day)
  const allDayOpen = todayCards.filter((i) => i.all_day && !i.completed)
  const timedIds = new Set(timed.map((i) => i.id))
  const doneOffTimeline = done.filter((i) => !timedIds.has(i.id))
  const pastDueOffTimeline = overdue.filter((i) => !i.completed)

  const openToday = todayCards.filter((i) => !i.completed)
  const pastDue = [...overdue.filter((i) => !i.completed), ...openToday.filter((i) => todaySlot(i, nowHm) === 'pastdue')]
  const nowCards = openToday.filter((i) => todaySlot(i, nowHm) === 'now')
  const comingCards = openToday.filter((i) => todaySlot(i, nowHm) === 'coming')
  const anytimeCards = openToday.filter((i) => todaySlot(i, nowHm) === 'anytime')
  const next7Open = next7.filter((i) => !i.completed)

  const todayEmpty =
    pastDue.length === 0 &&
    nowCards.length === 0 &&
    comingCards.length === 0 &&
    anytimeCards.length === 0 &&
    done.length === 0
  const allEmpty = todayEmpty && next7Open.length === 0

  const renderCards = (items: api.FeedItem[]) => (
    <div className="flex flex-col gap-3">
      <AnimatePresence>
        {items.map((item, i) => (
          <ItemCard key={item.id} index={i} {...cardProps(item)} />
        ))}
      </AnimatePresence>
    </div>
  )

  return (
    <div>
      <WelcomeCrumb />

      {/* The home masthead, in reading order: who you are to us (greeting),
          what day it is, whose house this is (team name), then the family. */}
      <h1 className="font-display text-[2.05rem] font-semibold leading-[1.1] tracking-[-0.02em]">
        {timeGreeting()}, {user?.display_name.split(/\s+/)[0] ?? ''}
      </h1>
      <p className="mt-1 text-sm text-fg/50">
        It's{' '}
        {clock.toLocaleDateString(undefined, {
          weekday: 'long',
          month: 'long',
          day: 'numeric',
          year: 'numeric',
        })}
      </p>
      {familyName && (
        <div className="mb-3 mt-4 flex items-center gap-3">
          <span className="h-px flex-1 bg-gradient-to-r from-transparent to-gold/40" />
          <span className="font-team text-2xl font-bold leading-none text-gold">
            {familyName}
          </span>
          <span className="h-px flex-1 bg-gradient-to-l from-transparent to-gold/40" />
        </div>
      )}
      <FamilyStrip members={family} onOpen={onOpenProfile} />

      {isParent && (
        <WaitingOnYou
          approvals={approvals}
          family={family}
          onApprove={(a) => answerApproval(a, true)}
          onPutBack={(a) => answerApproval(a, false)}
        />
      )}

      {isParent && <VillageStrip events={vEvents} onOpen={setEventSheet} />}

      <TonightCard onOpenKitchen={onOpenKitchen} />

      {/* The board's control bar: List/Timeline swap the view in place (enclosed
          segmented pill), Calendar navigates away (free-standing accent pill). */}
      <div className="mb-4 flex items-stretch justify-center gap-2" data-view-toggle>
        <div className="flex gap-1 rounded-full border border-fg/10 bg-fg/5 p-1">
          {(
            [
              { id: 'list', label: 'List', Icon: Rows3 },
              { id: 'timeline', label: 'Timeline', Icon: CalendarClock },
            ] as const
          ).map(({ id, label, Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => pickView(id)}
              aria-pressed={view === id}
              className={`flex items-center gap-1.5 rounded-full px-3.5 py-2 text-sm font-semibold transition-colors ${
                view === id ? 'bg-accent-bright/20 text-fg' : 'text-fg/50 hover:text-fg/80'
              }`}
            >
              <Icon className="h-4 w-4" strokeWidth={2.5} /> {label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onOpenCalendar}
          aria-label="View calendar"
          className="flex items-center gap-1.5 rounded-full border border-accent-bright/40 bg-accent-bright/15 px-3.5 text-sm font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
        >
          <CalendarDays className="h-4 w-4" strokeWidth={2.5} /> Calendar
        </button>
      </div>

      {isParent && family.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-1.5">
          <span className="mr-0.5 text-[11px] font-semibold uppercase tracking-wide text-fg/35">
            Filter
          </span>
          <FilterChip active={filter.length === 0} onClick={() => setFilter([])}>
            All
          </FilterChip>
          {family.map((m) => (
            <FilterChip key={m.id} active={filter.includes(m.id)} onClick={() => toggleFilter(m.id)}>
              {m.id === user?.id ? 'Me' : m.display_name.split(/\s+/)[0]}
            </FilterChip>
          ))}
        </div>
      )}

      <FormError message={error} />

      {feed && filter.length > 0 && allEmpty && (
        <p className="glass p-6 text-center text-sm text-fg/50">
          No cards for the people you picked.
        </p>
      )}

      {feed && filter.length === 0 && todayEmpty && view === 'list' && (
        isParent ? (
          // Empty board is the natural place to start one: tap to open the editor.
          <button
            type="button"
            onClick={() => openEditor(null)}
            className="glass w-full p-6 text-center text-sm text-fg/60 transition-colors hover:text-fg"
          >
            Nothing on the board today.{' '}
            <span className="font-semibold text-accent-bright">Add something?</span>
          </button>
        ) : (
          <p className="glass p-6 text-center text-sm text-fg/50">
            Nothing on the board today. Enjoy it.
          </p>
        )
      )}

      {feed && !todayEmpty && view === 'list' && (
        <>
          {pastDue.length > 0 && (
            <>
              <SectionDivider label="Past due" />
              {renderCards(pastDue)}
            </>
          )}

          {nowCards.length > 0 && (
            <>
              <SectionDivider label="Now" accent />
              {renderCards(nowCards)}
            </>
          )}

          <SectionDivider label="Coming up" />
          {comingCards.length > 0 ? (
            renderCards(comingCards)
          ) : (
            <p className="px-1 text-sm text-fg/40">The rest of your day is empty.</p>
          )}

          {anytimeCards.length > 0 && (
            <>
              <SectionDivider label="Anytime" />
              {renderCards(anytimeCards)}
            </>
          )}

          {done.length > 0 && (
            <>
              <SectionDivider label="Done" />
              {renderCards(done)}
            </>
          )}
        </>
      )}

      {feed && view === 'timeline' && (
        <>
          {!timelineDate && pastDueOffTimeline.length > 0 && (
            <>
              <SectionDivider label="Past due" />
              {renderCards(pastDueOffTimeline)}
            </>
          )}

          {!timelineDate && allDayOpen.length > 0 && (
            <>
              <SectionDivider label="All day" />
              {renderCards(allDayOpen)}
            </>
          )}

          {/* Day header: the divider grew chevrons. Any day but today is a
              read-only peek; the label taps back to today. */}
          <div className="mb-2 mt-6 flex items-center gap-2 py-0.5 first:mt-0" data-timeline-nav>
            <button
              type="button"
              aria-label="Previous day"
              onClick={() => setTimelineDate(shiftDay(timelineDate ?? api.localDate(), -1))}
              className="-m-2.5 rounded-lg p-3.5 text-fg/45 transition-colors hover:bg-fg/10 hover:text-fg"
            >
              <ChevronLeft className="h-4 w-4" strokeWidth={2.5} />
            </button>
            <button
              type="button"
              onClick={() => setTimelineDate(null)}
              disabled={!timelineDate}
              className={`text-[10px] font-bold uppercase tracking-widest ${
                timelineDate ? 'text-fg/70 underline decoration-fg/30 underline-offset-4' : 'text-accent-bright'
              }`}
            >
              {relativeDay(timelineDate ?? feed.date)}
            </button>
            <button
              type="button"
              aria-label="Next day"
              onClick={() => setTimelineDate(shiftDay(timelineDate ?? api.localDate(), 1))}
              className="-m-2.5 rounded-lg p-3.5 text-fg/45 transition-colors hover:bg-fg/10 hover:text-fg"
            >
              <ChevronRight className="h-4 w-4" strokeWidth={2.5} />
            </button>
            <span className="h-px flex-1 bg-gradient-to-r from-accent-bright/70 to-transparent" />
            {timelineDate && (
              <button
                type="button"
                onClick={() => setTimelineDate(null)}
                className="inline-flex min-h-11 items-center rounded-full border border-fg/10 bg-fg/5 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-fg/60 transition-colors hover:bg-fg/10"
              >
                Back to today
              </button>
            )}
          </div>

          {timelineDate ? (
            peekItems === null ? (
              <p className="px-1 text-sm text-fg/40">Loading…</p>
            ) : (
              <>
                {/* Peeked days are for looking: no checkboxes (a toggle would
                    record the wrong date), cards still open their detail. */}
                {(() => {
                  const peekAllDay = peekItems.filter((i) => i.all_day)
                  const peekTimed = peekItems.filter((i) => i.time_of_day && !i.all_day)
                  return (
                    <>
                      {peekAllDay.length > 0 && (
                        <div className="mb-3 flex flex-col gap-3">
                          <AnimatePresence>
                            {peekAllDay.map((item, i) => (
                              <ItemCard
                                key={item.id}
                                index={i}
                                item={item}
                                canCheck={false}
                                family={family}
                                viewerId={user?.id}
                                viewerIsParent={isParent}
                                onOpen={() => setDetail({ item, checkable: false })}
                              />
                            ))}
                          </AnimatePresence>
                        </div>
                      )}
                      {peekTimed.length > 0 ? (
                        <DayTimeline
                          key={timelineDate}
                          items={peekTimed}
                          nowMinutes={clock.getHours() * 60 + clock.getMinutes()}
                          isToday={false}
                          canCheck={() => false}
                          viewerId={user?.id}
                          onToggle={() => {}}
                          onOpen={(item) => setDetail({ item, checkable: false })}
                        />
                      ) : (
                        <p className="px-1 text-sm text-fg/40">
                          Nothing with a time on {relativeDay(timelineDate).toLowerCase()}.
                        </p>
                      )}
                    </>
                  )
                })()}
              </>
            )
          ) : timed.length > 0 ? (
            <DayTimeline
              items={timed}
              nowMinutes={clock.getHours() * 60 + clock.getMinutes()}
              canCheck={canCheck}
              viewerId={user?.id}
              onToggle={toggle}
              onOpen={(item) => setDetail({ item, checkable: canCheck(item) })}
            />
          ) : (
            <p className="px-1 text-sm text-fg/40">Nothing with a time today.</p>
          )}

          {!timelineDate && anytimeCards.length > 0 && (
            <>
              <SectionDivider label="Anytime" />
              {renderCards(anytimeCards)}
            </>
          )}

          {!timelineDate && doneOffTimeline.length > 0 && (
            <>
              <SectionDivider label="Done" />
              {renderCards(doneOffTimeline)}
            </>
          )}
        </>
      )}

      {feed && !(filter.length > 0 && allEmpty) && (
        <>
          <SectionDivider label="Next 7 days" />
          {next7Open.length > 0 ? (
            renderCards(next7Open)
          ) : (
            <p className="px-1 text-sm text-fg/40">Nothing in the next 7 days.</p>
          )}
        </>
      )}

      <VerseCard />

      {isParent && (
        <motion.button
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          whileTap={{ scale: 0.9 }}
          onClick={() => openEditor(null)}
          aria-label="Add to the board"
          className="fixed bottom-24 right-1/2 z-30 flex h-14 w-14 translate-x-[calc(min(50vw,14rem)-2rem)] items-center justify-center rounded-full bg-gradient-to-r from-accent to-accent-strong shadow-xl shadow-accent/30"
        >
          <Plus className="h-6 w-6" strokeWidth={2.5} />
        </motion.button>
      )}

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            className="glass fixed bottom-40 left-1/2 z-30 flex w-[calc(100%-2.5rem)] max-w-sm -translate-x-1/2 items-center gap-3 px-4 py-3"
            data-undo-toast
          >
            <p className="min-w-0 flex-1 truncate text-sm text-fg/85">
              Done: <span className="font-semibold">{toast.title}</span>
            </p>
            <button
              type="button"
              onClick={undo}
              className="flex shrink-0 items-center gap-1 rounded-lg bg-fg/10 px-2.5 py-1.5 text-sm font-semibold text-fg/85 hover:bg-fg/20"
            >
              <Undo2 className="h-3.5 w-3.5" /> Undo
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {detail && (() => {
          // A materialized village-event copy is organizer-managed: no edit,
          // delete, or cancel here — the RSVP is the family's lever. The
          // organizer's own source card matches by item_id instead, so they
          // get the same who's-going picture (their sheet hides RSVP buttons).
          const managed = detail.item.village_event_id != null
          const matchedEvent = managed
            ? vEvents.find((e) => e.my_item_id === detail.item.id) ?? null
            : vEvents.find((e) => e.is_own && e.item_id === detail.item.id) ?? null
          const shareable =
            isParent &&
            !managed &&
            (detail.item.kind === 'appointment' || detail.item.kind === 'activity') &&
            Boolean(detail.item.date_for) &&
            !detail.item.repeat
          return (
            <ItemDetail
              item={detail.item}
              canCheck={detail.checkable}
              family={family}
              me={user}
              onToggle={() => toggle(detail.item)}
              onToggleFor={(userId, done) => toggleFor(detail.item, userId, done)}
              onEdit={isParent && !managed ? () => openEditor(detail.item) : undefined}
              onDelete={isParent && !managed ? () => deleteFromDetail(detail.item) : undefined}
              onCancel={
                isParent &&
                !managed &&
                (detail.item.kind === 'appointment' || detail.item.kind === 'activity')
                  ? async () => {
                      const call = detail.item.cancelled ? api.uncancelItem : api.cancelItem
                      await call(detail.item.id, api.localDate())
                      setDetail(null)
                      refresh()
                    }
                  : undefined
              }
              villageEvent={matchedEvent}
              onChangeRsvp={
                matchedEvent
                  ? () => {
                      setDetail(null)
                      setEventSheet(matchedEvent)
                    }
                  : undefined
              }
              onShareVillage={
                shareable
                  ? () => {
                      const item = detail.item
                      setDetail(null)
                      setShareSheet(item)
                    }
                  : undefined
              }
              onClose={() => setDetail(null)}
            />
          )
        })()}
      </AnimatePresence>

      {eventSheet && (
        <VillageEventSheet
          event={eventSheet}
          family={family}
          onClose={() => setEventSheet(null)}
          onChanged={refresh}
        />
      )}
      {shareSheet && (
        <ShareEventSheet
          item={shareSheet}
          onClose={() => setShareSheet(null)}
          onShared={() => {
            setShareSheet(null)
            refresh()
          }}
        />
      )}

      <AnimatePresence>
        {sheet.open && (
          <ItemSheet
            item={sheet.item}
            family={family}
            onClose={() => setSheet({ open: false, item: null })}
            onSaved={() => {
              setSheet({ open: false, item: null })
              refresh()
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
