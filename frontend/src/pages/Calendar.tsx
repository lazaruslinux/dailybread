import { AnimatePresence } from 'framer-motion'
import { Check, ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Avatar } from '../components/Avatar'
import { KIND_STYLE } from '../components/ItemCard'
import { ItemSheet } from '../components/ItemSheet'
import { FormError } from '../components/ui'
import { canCheckItem } from '../lib/items'
import { formatTime } from '../lib/moods'

const DOW = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']

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
// Monday that starts the week containing d (matches the routine day masks, 0=Mon).
function mondayOf(d: Date): Date {
  const x = midnight(d)
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7))
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

// One scheduled card in the day's agenda. When the viewer can act on it and the
// day isn't in the future, a left circle checks it off ON THAT DAY, so a missed
// item is marked on the day it actually was. Otherwise it's read-only, with a
// quiet check when it's already done.
function AgendaRow({
  item,
  family,
  checkable,
  onToggle,
}: {
  item: api.FeedItem
  family: api.FamilyMember[]
  checkable: boolean
  onToggle?: () => void
}) {
  const { Icon, tint, label } = KIND_STYLE[item.kind]
  const when = item.all_day ? 'All day' : formatTime(item.time_of_day)
  const people = item.assignees
    .map((a) => family.find((m) => m.id === a.id))
    .filter((m): m is api.FamilyMember => Boolean(m))
  return (
    <div className="glass flex items-center gap-3 p-3">
      {checkable && onToggle ? (
        <button
          type="button"
          aria-label={item.completed ? `Mark ${item.title} not done` : `Mark ${item.title} done`}
          onClick={onToggle}
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
      <div className="w-14 shrink-0 text-right text-[11px] font-semibold leading-tight text-fg/55">
        {when ?? ''}
      </div>
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

export function Calendar() {
  const { user } = useAuth()
  const isParent = user?.role === 'parent'
  const todayISO = api.localDate()
  const [mode, setMode] = useState<Mode>('fortnight')
  const [adding, setAdding] = useState(false)
  // Fortnight is anchored on a Monday; month on the 1st of the shown month.
  const [fortnightStart, setFortnightStart] = useState(() => mondayOf(new Date()))
  const [monthAnchor, setMonthAnchor] = useState(() => startOfMonth(new Date()))
  const [selected, setSelected] = useState(todayISO)
  const [cal, setCal] = useState<api.Calendar | null>(null)
  const [family, setFamily] = useState<api.FamilyMember[]>([])
  const [error, setError] = useState<string | null>(null)

  // The days the grid draws, as full weeks. Two weeks for the fortnight; for a
  // month, the whole weeks that the month touches (so it starts on a Monday and
  // ends on a Sunday, with neighbouring days dimmed).
  const gridDays = useMemo(() => {
    const days: Date[] = []
    if (mode === 'fortnight') {
      for (let i = 0; i < 14; i++) days.push(addDays(fortnightStart, i))
    } else {
      const gStart = mondayOf(startOfMonth(monthAnchor))
      const gEnd = addDays(mondayOf(endOfMonth(monthAnchor)), 6)
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

  const countFor = (iso: string) => cal?.days.find((d) => d.date === iso)?.items.length ?? 0
  const selectedItems = cal?.days.find((d) => d.date === selected)?.items ?? []
  // You can only mark days that have already happened (or today) — nothing is
  // "done" in the future.
  const dayIsMarkable = selected <= todayISO

  // Flip a card's completed state on the day being viewed, optimistically, then
  // reconcile with the server. The completion is recorded on THAT day.
  function setDone(dayISO: string, id: number, done: boolean) {
    setCal((c) =>
      c
        ? {
            ...c,
            days: c.days.map((d) =>
              d.date === dayISO
                ? { ...d, items: d.items.map((it) => (it.id === id ? { ...it, completed: done } : it)) }
                : d,
            ),
          }
        : c,
    )
  }
  async function toggle(item: api.FeedItem, dayISO: string) {
    const done = !item.completed
    setDone(dayISO, item.id, done)
    try {
      if (done) await api.completeItem(item.id, undefined, dayISO)
      else await api.uncompleteItem(item.id, undefined, dayISO)
      refresh()
    } catch (err) {
      setDone(dayISO, item.id, !done)
      setError(err instanceof api.ApiError ? err.message : 'Could not update the card.')
    }
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
    setFortnightStart(mondayOf(new Date()))
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
          {DOW.map((lbl) => (
            <span key={lbl} className="text-center text-[10px] font-semibold uppercase tracking-wide text-fg/40">
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
                    onSelect={() => setSelected(iso)}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>

      <FormError message={error} />

      <div>
        <div className="mb-2 flex items-center justify-between pl-1">
          <p className="text-xs font-semibold uppercase tracking-widest text-fg/40">
            {fullDay(selected)}
          </p>
          {isParent && (
            <button
              onClick={() => setAdding(true)}
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
            {selectedItems.map((item) => {
              const checkable = dayIsMarkable && canCheckItem(item, user)
              return (
                <AgendaRow
                  key={`${item.id}-${selected}`}
                  item={item}
                  family={family}
                  checkable={checkable}
                  onToggle={checkable ? () => toggle(item, selected) : undefined}
                />
              )
            })}
          </div>
        )}
      </div>

      <AnimatePresence>
        {adding && (
          <ItemSheet
            item={null}
            family={family}
            defaultDate={selected}
            defaultKind="appointment"
            onClose={() => setAdding(false)}
            onSaved={() => {
              setAdding(false)
              refresh()
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
