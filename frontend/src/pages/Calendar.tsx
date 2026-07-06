import { Check, ChevronLeft, ChevronRight } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import * as api from '../lib/api'
import { Avatar } from '../components/Avatar'
import { KIND_STYLE } from '../components/ItemCard'
import { FormError } from '../components/ui'
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

function monthLabel(start: Date, end: Date): string {
  const opts: Intl.DateTimeFormatOptions = { month: 'long' }
  const sameMonth = start.getMonth() === end.getMonth()
  const sameYear = start.getFullYear() === end.getFullYear()
  if (sameMonth) return `${start.toLocaleDateString(undefined, opts)} ${start.getFullYear()}`
  const a = start.toLocaleDateString(undefined, { month: 'short' })
  const b = end.toLocaleDateString(undefined, { month: 'short' })
  return sameYear
    ? `${a} – ${b} ${end.getFullYear()}`
    : `${a} ${start.getFullYear()} – ${b} ${end.getFullYear()}`
}

function fullDay(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

// One scheduled card in the day's agenda: read-only (tapping into detail/edit is
// a later slice). Time on the left, kind + title in the middle, who it's for on
// the right, a check when it's already done.
function AgendaRow({ item, family }: { item: api.FeedItem; family: api.FamilyMember[] }) {
  const { Icon, tint, label } = KIND_STYLE[item.kind]
  const when = item.all_day ? 'All day' : formatTime(item.time_of_day)
  const people = item.assignees
    .map((a) => family.find((m) => m.id === a.id))
    .filter((m): m is api.FamilyMember => Boolean(m))
  return (
    <div className="glass flex items-center gap-3 p-3">
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
      {item.completed && (
        <Check className="h-4 w-4 shrink-0 text-emerald-400" strokeWidth={3} />
      )}
    </div>
  )
}

export function Calendar() {
  const todayISO = api.localDate()
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()))
  const [selected, setSelected] = useState(todayISO)
  const [cal, setCal] = useState<api.Calendar | null>(null)
  const [family, setFamily] = useState<api.FamilyMember[]>([])
  const [error, setError] = useState<string | null>(null)

  const weekEnd = useMemo(() => addDays(weekStart, 6), [weekStart])

  const refresh = useCallback(async () => {
    try {
      const [c, fam] = await Promise.all([
        api.getCalendar(toISO(weekStart), toISO(weekEnd)),
        api.getFamily(),
      ])
      setCal(c)
      setFamily(fam)
      setError(null)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load the calendar.')
    }
  }, [weekStart, weekEnd])

  useEffect(() => {
    refresh()
  }, [refresh])

  const countFor = (iso: string) => cal?.days.find((d) => d.date === iso)?.items.length ?? 0
  const selectedItems = cal?.days.find((d) => d.date === selected)?.items ?? []

  const goToday = () => {
    setWeekStart(mondayOf(new Date()))
    setSelected(todayISO)
  }
  const shiftWeek = (weeks: number) => {
    const next = addDays(weekStart, weeks * 7)
    setWeekStart(next)
    // Keep the selection on the same weekday in the new week.
    const dow = DOW.findIndex((_, i) => toISO(addDays(weekStart, i)) === selected)
    setSelected(toISO(addDays(next, dow >= 0 ? dow : 0)))
  }

  const onCurrentWeek = toISO(weekStart) === toISO(mondayOf(new Date()))

  return (
    <div className="flex flex-col gap-4">
      <div className="glass p-4">
        <div className="mb-3 flex items-center justify-between">
          <button
            onClick={() => shiftWeek(-1)}
            aria-label="Previous week"
            className="rounded-lg p-1.5 text-fg/60 transition-colors hover:bg-fg/10 hover:text-fg"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <span className="font-display text-lg font-semibold tracking-[-0.01em]">
            {monthLabel(weekStart, weekEnd)}
          </span>
          <button
            onClick={() => shiftWeek(1)}
            aria-label="Next week"
            className="rounded-lg p-1.5 text-fg/60 transition-colors hover:bg-fg/10 hover:text-fg"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>

        <div className="grid grid-cols-7 gap-1">
          {DOW.map((lbl, i) => {
            const day = addDays(weekStart, i)
            const iso = toISO(day)
            const isToday = iso === todayISO
            const isSelected = iso === selected
            const count = countFor(iso)
            return (
              <button
                key={iso}
                onClick={() => setSelected(iso)}
                aria-pressed={isSelected}
                className={`flex flex-col items-center gap-1 rounded-xl border py-2 transition-colors ${
                  isSelected
                    ? 'border-accent-bright/60 bg-accent-bright/20'
                    : 'border-transparent hover:bg-fg/5'
                }`}
              >
                <span className="text-[10px] font-semibold uppercase tracking-wide text-fg/45">
                  {lbl}
                </span>
                <span
                  className={`flex h-7 w-7 items-center justify-center rounded-full text-sm font-semibold ${
                    isToday ? 'bg-accent text-white' : 'text-fg/85'
                  }`}
                >
                  {day.getDate()}
                </span>
                <span
                  className={`h-1.5 w-1.5 rounded-full ${count > 0 ? 'bg-accent-bright' : 'bg-transparent'}`}
                />
              </button>
            )
          })}
        </div>

        {!onCurrentWeek && (
          <div className="mt-3 flex justify-center">
            <button
              onClick={goToday}
              className="rounded-full bg-fg/10 px-3 py-1 text-xs font-semibold text-fg/70 hover:bg-fg/15"
            >
              Today
            </button>
          </div>
        )}
      </div>

      <FormError message={error} />

      <div>
        <p className="mb-2 pl-1 text-xs font-semibold uppercase tracking-widest text-fg/40">
          {fullDay(selected)}
        </p>
        {selectedItems.length === 0 ? (
          <p className="glass p-6 text-center text-sm text-fg/50">Nothing scheduled.</p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {selectedItems.map((item) => (
              <AgendaRow key={`${item.id}-${selected}`} item={item} family={family} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
