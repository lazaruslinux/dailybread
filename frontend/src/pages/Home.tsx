import { AnimatePresence, motion } from 'framer-motion'
import { Plus, Undo2 } from 'lucide-react'
import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { FamilyStrip } from '../components/FamilyStrip'
import { ItemCard, NowDivider } from '../components/ItemCard'
import { ItemDetail } from '../components/ItemDetail'
import { ItemSheet } from '../components/ItemSheet'
import { VerseCard } from '../components/VerseCard'
import { FormError } from '../components/ui'

// Where does the "Now" line sit? After the last timed card that's already
// passed. Returns -1 when it shouldn't render (nothing timed yet to compare).
function nowIndex(items: api.FeedItem[], clock: Date): number {
  const nowHm = `${String(clock.getHours()).padStart(2, '0')}:${String(clock.getMinutes()).padStart(2, '0')}:00`
  let idx = -1
  items.forEach((item, i) => {
    if (item.time_of_day && item.time_of_day <= nowHm) idx = i
  })
  return idx
}

function SectionLabel({ children }: { children: string }) {
  return (
    <p className="mb-2 mt-6 text-xs font-semibold uppercase tracking-widest text-white/40">
      {children}
    </p>
  )
}

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
          ? 'border-indigo-400/60 bg-indigo-400/20 text-white'
          : 'border-white/10 bg-white/5 text-white/55 hover:bg-white/10'
      }`}
    >
      {children}
    </button>
  )
}

function upcomingLabel(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
}

export function Home({ onOpenProfile }: { onOpenProfile: (id: number) => void }) {
  const { user } = useAuth()
  const isParent = user?.role === 'parent'

  const [feed, setFeed] = useState<api.Feed | null>(null)
  const [family, setFamily] = useState<api.FamilyMember[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sheet, setSheet] = useState<{ open: boolean; item: api.FeedItem | null }>({ open: false, item: null })
  // checkable rides along so an upcoming card's sheet never offers "Mark
  // done" (completions only apply to today's date).
  const [detail, setDetail] = useState<{ item: api.FeedItem; checkable: boolean } | null>(null)
  const [toast, setToast] = useState<api.FeedItem | null>(null)
  const toastTimer = useRef<number | undefined>(undefined)
  // Re-rendering once a minute keeps the Now line honest without any polling.
  const [clock, setClock] = useState(() => new Date())
  // Parent-only board lens: which members' cards to show. Empty means show
  // everyone's. Whole-family cards always show, since they're everyone's.
  const [filter, setFilter] = useState<number[]>([])

  const refresh = useCallback(async () => {
    try {
      const [f, fam] = await Promise.all([api.getFeed(), api.getFamily()])
      setFeed(f)
      setFamily(fam)
      setError(null)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load the board.')
    }
  }, [])

  useEffect(() => {
    refresh()
    const tick = setInterval(() => setClock(new Date()), 60_000)
    // Coming back to the app (phone unlock, tab focus) refetches the board.
    const onVisible = () => document.visibilityState === 'visible' && refresh()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(tick)
      document.removeEventListener('visibilitychange', onVisible)
      window.clearTimeout(toastTimer.current)
    }
  }, [refresh])

  // Flip one card's completed flag in local state. This is the optimistic
  // half of a toggle: the UI answers the tap instantly and the server call
  // catches up (or the flag flips back if it fails).
  const setItemCompleted = useCallback(
    (id: number, completed: boolean) => {
      // Also flip the current member's own row on a routine, so their avatar
      // badge answers the tap instantly alongside the left circle.
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
      setFeed((f) => (f ? { ...f, today: patch(f.today), anytime: patch(f.anytime) } : f))
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
                    c.user_id === userId ? { ...c, completed } : c,
                  ) ?? null,
              }
            : it,
        )
      setFeed((f) => (f ? { ...f, today: patch(f.today), anytime: patch(f.anytime) } : f))
      setDetail((d) => (d && d.item.id === id ? { ...d, item: patch([d.item])[0] } : d))
    },
    [user],
  )

  function showUndoToast(item: api.FeedItem) {
    window.clearTimeout(toastTimer.current)
    setToast(item)
    toastTimer.current = window.setTimeout(() => setToast(null), 5000)
  }

  async function toggle(item: api.FeedItem) {
    const next = !item.completed
    setItemCompleted(item.id, next)
    try {
      if (next) await api.completeItem(item.id)
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
  async function toggleFor(item: api.FeedItem, userId: number, done: boolean) {
    setAssigneeCompleted(item.id, userId, done)
    try {
      if (done) await api.completeItem(item.id, userId)
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

  function canCheck(item: api.FeedItem): boolean {
    if (!user) return false
    // Routines are per-person: only a participant checks their own. Other kinds
    // can be checked by anyone involved (owner or assignee), plus either parent
    // on a family-board card, so co-parents share the household's chores.
    if (item.kind === 'routine')
      return item.assignee_completions?.some((c) => c.user_id === user.id) ?? false
    if (item.owner_id === user.id || item.assignees.some((a) => a.id === user.id)) return true
    return user.role === 'parent' && item.visibility === 'family'
  }

  const openEditor = (item: api.FeedItem | null) => {
    setDetail(null)
    setSheet({ open: true, item })
  }

  // A timed appointment/activity past its end (and not done) is overdue; a task
  // past its due time gets a softer nudge. Only today's dated cards, never
  // routines or all-day. Recomputes on the minute via the clock re-render.
  function pastFlag(item: api.FeedItem): 'overdue' | 'due' | null {
    if (item.completed || item.all_day || !feed || item.date_for !== feed.date) return null
    const endHm = item.end_time || item.time_of_day
    if (!endHm) return null
    const nowHm = `${String(clock.getHours()).padStart(2, '0')}:${String(clock.getMinutes()).padStart(2, '0')}:00`
    if (endHm >= nowHm) return null
    if (item.kind === 'appointment' || item.kind === 'activity') return 'overdue'
    return item.kind === 'task' ? 'due' : null
  }

  const cardProps = (item: api.FeedItem, checkable: boolean) => ({
    item,
    canCheck: checkable,
    family,
    flag: pastFlag(item),
    onToggle: checkable ? () => toggle(item) : undefined,
    onOpen: () => setDetail({ item, checkable }),
    onEdit: isParent ? () => openEditor(item) : undefined,
  })

  const toggleFilter = (id: number) =>
    setFilter((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  // The filter is about who a card is FOR, not who can see it: a member matches
  // if they're an assignee, or (when nobody is assigned) the owner. Being on the
  // family board no longer forces a card to show under every member's filter.
  const isForMember = (item: api.FeedItem, id: number) =>
    item.assignees.length > 0
      ? item.assignees.some((a) => a.id === id)
      : item.owner_id === id
  const matchesFilter = (item: api.FeedItem) =>
    filter.length === 0 || filter.some((id) => isForMember(item, id))

  const today = feed ? feed.today.filter(matchesFilter) : []
  const anytime = feed ? feed.anytime.filter(matchesFilter) : []
  const upcoming = feed ? feed.upcoming.filter(matchesFilter) : []
  const divider = nowIndex(today, clock)

  return (
    <div>
      <FamilyStrip members={family} onOpen={onOpenProfile} />

      {isParent && family.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-1.5">
          <span className="mr-0.5 text-[11px] font-semibold uppercase tracking-wide text-white/35">
            Show
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

      {feed && today.length === 0 && anytime.length === 0 && (
        <p className="glass p-6 text-center text-sm text-white/50">
          {filter.length > 0
            ? 'No cards for the people you picked.'
            : 'Nothing on the board today. Enjoy it.'}
        </p>
      )}

      <div className="flex flex-col gap-3">
        <AnimatePresence>
          {today.map((item, i) => (
            <Fragment key={item.id}>
              <ItemCard index={i} {...cardProps(item, canCheck(item))} />
              {i === divider && <NowDivider />}
            </Fragment>
          ))}
        </AnimatePresence>
      </div>

      {anytime.length > 0 && (
        <>
          <SectionLabel>Anytime</SectionLabel>
          <div className="flex flex-col gap-3">
            <AnimatePresence>
              {anytime.map((item, i) => (
                <ItemCard key={item.id} index={i} {...cardProps(item, canCheck(item))} />
              ))}
            </AnimatePresence>
          </div>
        </>
      )}

      {upcoming.length > 0 && (
        <>
          <SectionLabel>Coming up</SectionLabel>
          <div className="flex flex-col gap-3">
            {upcoming.map((item, i) => (
              <div key={item.id}>
                <p className="mb-1 pl-1 text-[11px] font-medium text-white/35">
                  {item.date_for ? upcomingLabel(item.date_for) : ''}
                </p>
                <ItemCard index={i} {...cardProps(item, false)} />
              </div>
            ))}
          </div>
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
          className="fixed bottom-24 right-1/2 z-30 flex h-14 w-14 translate-x-[calc(min(50vw,14rem)-2rem)] items-center justify-center rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 shadow-xl shadow-indigo-500/30"
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
            <p className="min-w-0 flex-1 truncate text-sm text-white/85">
              Done: <span className="font-semibold">{toast.title}</span>
            </p>
            <button
              type="button"
              onClick={undo}
              className="flex shrink-0 items-center gap-1 rounded-lg bg-white/10 px-2.5 py-1.5 text-sm font-semibold text-white/85 hover:bg-white/20"
            >
              <Undo2 className="h-3.5 w-3.5" /> Undo
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {detail && (
          <ItemDetail
            item={detail.item}
            canCheck={detail.checkable}
            family={family}
            me={user}
            onToggle={() => toggle(detail.item)}
            onToggleFor={(userId, done) => toggleFor(detail.item, userId, done)}
            onEdit={isParent ? () => openEditor(detail.item) : undefined}
            onDelete={isParent ? () => deleteFromDetail(detail.item) : undefined}
            onClose={() => setDetail(null)}
          />
        )}
      </AnimatePresence>

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
