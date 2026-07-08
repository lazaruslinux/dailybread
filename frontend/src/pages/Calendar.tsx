import { AnimatePresence } from 'framer-motion'
import { Check, ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Avatar } from '../components/Avatar'
import { ItemDetail } from '../components/ItemDetail'
import { KIND_STYLE, SectionDivider } from '../components/ItemCard'
import { ItemSheet } from '../components/ItemSheet'
import { FormError } from '../components/ui'
import { canCheckItem } from '../lib/items'
import { formatTime } from '../lib/moods'

const DOW = ['S', 'M', 'T', 'W', 'T', 'F', 'S']

function toISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function midnight(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}
function addDays(d: Date, n: number): Date {
  const x = midnight(d)
  x.setDate(x.getDate() + n)
  return x
}
// Sunday that starts the week containing d. The grid is laid out Sunday-first
// (US calendar convention, S M T W T F S); routine weekday masks are date-based,
// so the week's display start is purely a layout choice and doesn't touch them.
function weekStartOf(d: Date): Date {
  const x = midnight(d)
  x.setDate(x.getDate() - x.getDay()) // getDay(): Sunday == 0
  return x
}
function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}
function endOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0)
}
function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1)
}

function fortnightLabel(start: Date, end: Date): string {
  const sM = start.toLocaleDateString(undefined, { month: 'short' })
  const eM = end.toLocaleDateString(undefined, { month: 'short' })
  const range =
    start.getMonth() === end.getMonth()
      ? `${sM} ${start.getDate()} – ${end.getDate()}`
      : `${sM} ${start.getDate()} – ${eM} ${end.getDate()}`
  return `${range}, ${end.getFullYear()}`
}

function fullDay(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

// Fold the overview's flat day-tagged card list into consecutive-day groups,
// preserving order, so each day renders once with its cards beneath it.
function groupByDay(entries: { date: string; item: api.FeedItem }[]) {
  const groups: { date: string; items: api.FeedItem[] }[] = []
  for (const { date, item } of entries) {
    let g = groups[groups.length - 1]
    if (!g || g.date !== date) {
      g = { date, items: [] }
      groups.push(g)
    }
    g.items.push(item)
  }
  return groups
}

// Short day header for the overview groups: "Today" for today, else "Mon, Jul 7".
function dayHeading(iso: string, todayISO: string): string {
  if (iso === todayISO) return 'Today'
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

// One scheduled card in the day's agenda. When the viewer can act on it, a
// left circle checks it off on that day — past and present days for anything,
// any day for a task (reminders can be finished early; the check lands on
// today). Otherwise it's read-only, with a quiet check when already done.
function AgendaRow({
  item,
  family,
  checkable,
  onToggle,
  onOpen,
}: {
  item: api.FeedItem
  family: api.FamilyMember[]
  checkable: boolean
  onToggle?: () => void
  onOpen?: () => void
}) {
  const { Icon, tint, label } = KIND_STYLE[item.kind]
  const when = item.all_day ? 'All day' : formatTime(item.time_of_day)
  const until = item.all_day ? null : formatTime(item.end_time)
  const people = item.assignees
    .map((a) => family.find((m) => m.id === a.id))
    .filter((m): m is api.FamilyMember => Boolean(m))
  return (
    <div onClick={onOpen} className="glass flex cursor-pointer items-center gap-3 p-3">
      {checkable && onToggle ? (
        <button
          type="button"
          aria-label={item.completed ? `Mark ${item.title} not done` : `Mark ${item.title} done`}
          onClick={(e) => {
            e.stopPropagation()
            onToggle()
          }}
          className="-m-1 shrink-0 p-1"
          data-check
        >
          <span
            className={`flex h-6 w-6 items-center justify-center rounded-full border-2 transition-colors ${
              item.completed ? 'border-emerald-300/70 bg-emerald-400/25' : 'border-fg/30 bg-fg/5'
            }`}
          >
            {item.completed && <Check className="h-3.5 w-3.5 text-emerald-300" strokeWidth={3} />}
          </span>
        </button>
      ) : null}
      {/* Untimed cards skip the time column entirely — a blank fixed-width
          box would push the title far from its checkbox. */}
      {when != null && (
        <div className="w-14 shrink-0 text-right text-[11px] font-semibold leading-tight text-fg/55">
          {when}
          {until && <span className="block text-fg/40">– {until}</span>}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <span className={`flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide ${tint}`}>
          <Icon className="h-3 w-3" strokeWidth={2.5} /> {label}
        </span>
        <p className={`truncate font-semibold ${item.completed ? 'text-fg/50 line-through decoration-fg/30' : 'text-fg/90'}`}>
          {item.title}
        </p>
      </div>
      {people.length > 0 && (
        <div className="flex -space-x-2">
          {people.slice(0, 3).map((m) => (
            <Avatar key={m.id} name={m.display_name} src={api.avatarUrl(m)} size="sm" className="ring-2 ring-[var(--bg-base)]" />
          ))}
        </div>
      )}
      {!checkable && item.completed && <Check className="h-4 w-4 shrink-0 text-emerald-400" strokeWidth={3} />}
    </div>
  )
}

// One day in the grid. Shared by the two-week and month layouts; month passes
// dimmed=true for days that spill in from the neighbouring month.
function DayCell({
  day,
  count,
  isToday,
  isSelected,
  dimmed,
  onSelect,
}: {
  day: Date
  count: number
  isToday: boolean
  isSelected: boolean
  dimmed: boolean
  onSelect: () => void
}) {
  return (
    <button
      onClick={onSelect}
      aria-pressed={isSelected}
      className={`flex flex-col items-center gap-1 rounded-xl py-1.5 transition-colors ${
        isSelected ? 'bg-accent-bright/20 ring-1 ring-accent-bright/50' : 'hover:bg-fg/5'
      } ${dimmed ? 'opacity-35' : ''}`}
    >
      <span
        className={`flex h-7 w-7 items-center justify-center rounded-full text-sm font-semibold ${
          isToday ? 'bg-accent text-white' : 'text-fg/85'
        }`}
      >
        {day.getDate()}
      </span>
      <span className={`h-1.5 w-1.5 rounded-full ${count > 0 ? 'bg-accent-bright' : 'bg-transparent'}`} />
    </button>
  )
}

type Mode = 'fortnight' | 'month'

// How many cards the whole-period overview shows before offering "Load more".
const PERIOD_PAGE = 20

export function Calendar() {
  const { user } = useAuth()
  const isParent = user?.role === 'parent'
  const todayISO = api.localDate()
  const [mode, setMode] = useState<Mode>('fortnight')
  // Fortnight is anchored on the week's Sunday; month on the 1st of the month.
  const [fortnightStart, setFortnightStart] = useState(() => weekStartOf(new Date()))
  const [monthAnchor, setMonthAnchor] = useState(() => startOfMonth(new Date()))
  // No day selected = the whole-period overview (every scheduled one-off across
  // the view). Selecting a day narrows to just that day, routines included.
  const [selected, setSelected] = useState<string | null>(null)
  const [cal, setCal] = useState<api.Calendar | null>(null)
  const [family, setFamily] = useState<api.FamilyMember[]>([])
  const [error, setError] = useState<string | null>(null)
  // The card whose detail sheet is open, and the day it was opened on (so a
  // routine is marked on the right occurrence). Plus the add/edit sheet.
  const [detail, setDetail] = useState<{ item: api.FeedItem; day: string } | null>(null)
  const [sheet, setSheet] = useState<{ item: api.FeedItem | null; date: string } | null>(null)
  // The overview shows this many cards before "Load more" (a busy month would
  // otherwise be a wall of rows).
  const [shown, setShown] = useState(PERIOD_PAGE)

  // The days the grid draws, as full weeks. Two weeks for the fortnight; for a
  // month, the whole weeks that the month touches (so it starts on a Monday and
  // ends on a Sunday, with neighbouring days dimmed).
  const gridDays = useMemo(() => {
    const days: Date[] = []
    if (mode === 'fortnight') {
      for (let i = 0; i < 14; i++) days.push(addDays(fortnightStart, i))
    } else {
      const gStart = weekStartOf(startOfMonth(monthAnchor))
      const gEnd = addDays(weekStartOf(endOfMonth(monthAnchor)), 6)
      for (let d = gStart; d <= gEnd; d = addDays(d, 1)) days.push(d)
    }
    return days
  }, [mode, fortnightStart, monthAnchor])

  const rangeStart = gridDays[0]
  const rangeEnd = gridDays[gridDays.length - 1]

  const refresh = useCallback(async () => {
    try {
      const [c, fam] = await Promise.all([
        api.getCalendar(toISO(rangeStart), toISO(rangeEnd)),
        api.getFamily(),
      ])
      setCal(c)
      setFamily(fam)
      setError(null)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load the calendar.')
    }
  }, [rangeStart, rangeEnd])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Reset paging when the view changes under it.
  const rangeStartISO = toISO(rangeStart)
  useEffect(() => setShown(PERIOD_PAGE), [mode, rangeStartISO])

  const countFor = (iso: string) => cal?.days.find((d) => d.date === iso)?.items.length ?? 0
  const selectedItems = selected ? cal?.days.find((d) => d.date === selected)?.items ?? [] : []

  // The whole-period overview: every scheduled card across the view, in date
  // order, each tagged with its day — routines included, so a habit doesn't
  // seem to vanish when you zoom out from a single day to the whole period.
  // Open cards come first; completed ones settle into a "Completed" section at
  // the bottom of the whole period (matching the single-day agenda), so a
  // fortnight that starts in the past doesn't lead with days of finished cards.
  const overview = useMemo(() => {
    const out: { date: string; item: api.FeedItem }[] = []
    for (const d of cal?.days ?? [])
      for (const it of d.items) out.push({ date: d.date, item: it })
    return [...out.filter((e) => !e.item.completed), ...out.filter((e) => e.item.completed)]
  }, [cal])
  const overviewShown = overview.slice(0, shown)
  const overviewOpen = groupByDay(overviewShown.filter((e) => !e.item.completed))
  const overviewDone = groupByDay(overviewShown.filter((e) => e.item.completed))

  // You can only mark days that have already happened (or today) — nothing is
  // "done" in the future. Tasks are the exception: they're reminders, and the
  // board already lets you finish one ahead of its due day, so the calendar
  // offers the same (the check is recorded on today, its actual day).
  const markable = (dayISO: string) => dayISO <= todayISO
  const canMarkOn = (item: api.FeedItem, dayISO: string) =>
    (markable(dayISO) || item.kind === 'task') && canCheckItem(item, user)
  // What day a completion is recorded on: the tapped day, except that a task
  // checked ahead of time is done *today* (the server refuses future dates).
  const markDay = (dayISO: string) => (dayISO > todayISO ? todayISO : dayISO)

  // Patch a card's completion in the calendar and in an open detail sheet.
  function patch(dayISO: string, id: number, fn: (it: api.FeedItem) => api.FeedItem) {
    setCal((c) =>
      c
        ? {
            ...c,
            days: c.days.map((d) =>
              d.date === dayISO ? { ...d, items: d.items.map((it) => (it.id === id ? fn(it) : it)) } : d,
            ),
          }
        : c,
    )
    setDetail((dt) => (dt && dt.item.id === id && dt.day === dayISO ? { ...dt, item: fn(dt.item) } : dt))
  }

  // Flip a shared/own completion on the given day, optimistically, then
  // reconcile. The completion is recorded on THAT day (accurate history).
  async function toggle(item: api.FeedItem, dayISO: string) {
    const done = !item.completed
    patch(dayISO, item.id, (it) => ({ ...it, completed: done }))
    try {
      if (done) await api.completeItem(item.id, undefined, markDay(dayISO))
      else await api.uncompleteItem(item.id, undefined, markDay(dayISO))
      refresh()
    } catch (err) {
      patch(dayISO, item.id, (it) => ({ ...it, completed: !done }))
      setError(err instanceof api.ApiError ? err.message : 'Could not update the card.')
    }
  }

  // Flip one member's own row on a per-person (routine) card, for that day.
  async function toggleFor(item: api.FeedItem, userId: number, done: boolean, dayISO: string) {
    const set = (value: boolean) => (it: api.FeedItem): api.FeedItem => ({
      ...it,
      completed: userId === user?.id ? value : it.completed,
      assignee_completions:
        it.assignee_completions?.map((c) => (c.user_id === userId ? { ...c, completed: value } : c)) ?? null,
    })
    patch(dayISO, item.id, set(done))
    try {
      if (done) await api.completeItem(item.id, userId, dayISO)
      else await api.uncompleteItem(item.id, userId, dayISO)
      refresh()
    } catch (err) {
      patch(dayISO, item.id, set(!done))
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

  // A day's cards split into what's still to do (top) and what's done (a
  // "Completed" section at the bottom), so a checked-off card settles out of
  // the way instead of sitting up top.
  const openItems = selectedItems.filter((i) => !i.completed)
  const doneItems = selectedItems.filter((i) => i.completed)

  const renderRow = (item: api.FeedItem, dayISO: string) => {
    const canMark = canMarkOn(item, dayISO)
    return (
      <AgendaRow
        key={`${item.id}-${dayISO}`}
        item={item}
        family={family}
        checkable={canMark}
        onToggle={canMark ? () => toggle(item, dayISO) : undefined}
        onOpen={() => setDetail({ item, day: dayISO })}
      />
    )
  }

  const weeks = useMemo(() => {
    const rows: Date[][] = []
    for (let i = 0; i < gridDays.length; i += 7) rows.push(gridDays.slice(i, i + 7))
    return rows
  }, [gridDays])

  const label =
    mode === 'fortnight'
      ? fortnightLabel(fortnightStart, addDays(fortnightStart, 13))
      : monthAnchor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })

  const page = (dir: -1 | 1) => {
    if (mode === 'fortnight') setFortnightStart((s) => addDays(s, dir * 14))
    else setMonthAnchor((m) => addMonths(m, dir))
  }

  const goToday = () => {
    setFortnightStart(weekStartOf(new Date()))
    setMonthAnchor(startOfMonth(new Date()))
    setSelected(todayISO)
  }

  // Is the grid already showing the period that contains today?
  const onCurrent =
    mode === 'fortnight'
      ? toISO(rangeStart) <= todayISO && todayISO <= toISO(rangeEnd)
      : monthAnchor.getMonth() === new Date().getMonth() &&
        monthAnchor.getFullYear() === new Date().getFullYear()

  return (
    <div className="flex flex-col gap-4">
      <div className="glass p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex rounded-full border border-fg/10 bg-fg/5 p-0.5 text-xs font-semibold">
            {(['fortnight', 'month'] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                aria-pressed={mode === m}
                className={`rounded-full px-3 py-1 transition-colors ${
                  mode === m ? 'bg-accent-bright/25 text-fg' : 'text-fg/55 hover:text-fg'
                }`}
              >
                {m === 'fortnight' ? '2 weeks' : 'Month'}
              </button>
            ))}
          </div>
          {!onCurrent && (
            <button
              onClick={goToday}
              className="rounded-full bg-fg/10 px-3 py-1 text-xs font-semibold text-fg/70 hover:bg-fg/15"
            >
              Today
            </button>
          )}
        </div>

        <div className="mb-2 flex items-center justify-between">
          <button
            onClick={() => page(-1)}
            aria-label={mode === 'fortnight' ? 'Previous two weeks' : 'Previous month'}
            className="rounded-lg p-1.5 text-fg/60 transition-colors hover:bg-fg/10 hover:text-fg"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <span className="font-display text-lg font-semibold tracking-[-0.01em]">{label}</span>
          <button
            onClick={() => page(1)}
            aria-label={mode === 'fortnight' ? 'Next two weeks' : 'Next month'}
            className="rounded-lg p-1.5 text-fg/60 transition-colors hover:bg-fg/10 hover:text-fg"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>

        <div className="mb-1 grid grid-cols-7">
          {DOW.map((lbl, i) => (
            <span key={i} className="text-center text-[10px] font-semibold uppercase tracking-wide text-fg/40">
              {lbl}
            </span>
          ))}
        </div>
        <div className="flex flex-col gap-1">
          {weeks.map((week) => (
            <div key={toISO(week[0])} className="grid grid-cols-7 gap-1">
              {week.map((day) => {
                const iso = toISO(day)
                return (
                  <DayCell
                    key={iso}
                    day={day}
                    count={countFor(iso)}
                    isToday={iso === todayISO}
                    isSelected={iso === selected}
                    dimmed={mode === 'month' && day.getMonth() !== monthAnchor.getMonth()}
                    onSelect={() => setSelected((s) => (s === iso ? null : iso))}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>

      <FormError message={error} />

      {selected ? (
        // ONE DAY: the selected day's cards, routines included, with its own Add.
        <div>
          <div className="mb-2 flex items-center justify-between pl-1">
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-fg/40">
                {fullDay(selected)}
              </p>
              <button
                onClick={() => setSelected(null)}
                className="mt-0.5 text-[11px] font-semibold text-accent-bright hover:underline"
              >
                Show the whole {mode === 'fortnight' ? 'two weeks' : 'month'}
              </button>
            </div>
            {isParent && (
              <button
                onClick={() => setSheet({ item: null, date: selected })}
                className="flex items-center gap-1 rounded-full border border-accent-bright/40 bg-accent-bright/15 px-2.5 py-1 text-xs font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
              >
                <Plus className="h-3.5 w-3.5" strokeWidth={2.5} /> Add
              </button>
            )}
          </div>
          {selectedItems.length === 0 ? (
            <p className="glass p-6 text-center text-sm text-fg/50">Nothing scheduled.</p>
          ) : (
            <div className="flex flex-col gap-2.5">
              {openItems.length > 0 ? (
                openItems.map((item) => renderRow(item, selected))
              ) : (
                <p className="glass p-6 text-center text-sm text-fg/55">All done for this day.</p>
              )}
              {doneItems.length > 0 && (
                <>
                  <SectionDivider label="Completed" />
                  {doneItems.map((item) => renderRow(item, selected))}
                </>
              )}
            </div>
          )}
        </div>
      ) : (
        // WHOLE PERIOD: every scheduled one-off across the view, grouped by day.
        <div>
          <p className="mb-2 pl-1 text-xs font-semibold uppercase tracking-widest text-fg/40">
            Scheduled · tap a day to focus
          </p>
          {overview.length === 0 ? (
            <p className="glass p-6 text-center text-sm text-fg/50">Nothing scheduled in this period.</p>
          ) : (
            <div className="flex flex-col gap-4">
              {overviewOpen.map((g) => (
                <div key={g.date}>
                  <p className="mb-1.5 pl-1 text-[11px] font-semibold text-fg/45">{dayHeading(g.date, todayISO)}</p>
                  <div className="flex flex-col gap-2.5">
                    {g.items.map((item) => renderRow(item, g.date))}
                  </div>
                </div>
              ))}
              {overviewOpen.length === 0 && (
                <p className="glass p-6 text-center text-sm text-fg/55">All done in this period.</p>
              )}
              {overviewDone.length > 0 && (
                <>
                  <SectionDivider label="Completed" />
                  {overviewDone.map((g) => (
                    <div key={`done-${g.date}`}>
                      <p className="mb-1.5 pl-1 text-[11px] font-semibold text-fg/45">{dayHeading(g.date, todayISO)}</p>
                      <div className="flex flex-col gap-2.5">
                        {g.items.map((item) => renderRow(item, g.date))}
                      </div>
                    </div>
                  ))}
                </>
              )}
              {overview.length > shown && (
                <button
                  onClick={() => setShown((n) => n + PERIOD_PAGE)}
                  className="glass py-2.5 text-center text-sm font-semibold text-fg/70 transition-colors hover:text-fg"
                >
                  Load more ({overview.length - shown} more)
                </button>
              )}
            </div>
          )}
        </div>
      )}

      <AnimatePresence>
        {detail &&
          (() => {
            const dayMarkable = markable(detail.day)
            const canMark = canMarkOn(detail.item, detail.day)
            return (
              <ItemDetail
                item={detail.item}
                canCheck={canMark}
                family={family}
                me={user}
                onToggle={() => toggle(detail.item, detail.day)}
                onToggleFor={
                  dayMarkable ? (userId, done) => toggleFor(detail.item, userId, done, detail.day) : undefined
                }
                onEdit={
                  isParent
                    ? () => {
                        setSheet({ item: detail.item, date: detail.item.date_for ?? detail.day })
                        setDetail(null)
                      }
                    : undefined
                }
                onDelete={isParent ? () => deleteFromDetail(detail.item) : undefined}
                onClose={() => setDetail(null)}
              />
            )
          })()}
      </AnimatePresence>

      <AnimatePresence>
        {sheet && (
          <ItemSheet
            item={sheet.item}
            family={family}
            defaultDate={sheet.date}
            defaultKind="appointment"
            onClose={() => setSheet(null)}
            onSaved={() => {
              setSheet(null)
              setDetail(null)
              refresh()
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
