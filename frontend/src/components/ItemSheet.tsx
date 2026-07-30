import { motion } from 'framer-motion'
import { Check, Repeat as RepeatIcon, Trash2, Users, X } from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import * as api from '../lib/api'
import { compactDate } from '../lib/items'
import { Avatar } from './Avatar'
import { TimeCombo } from './TimeCombo'
import { Button, Field, FormError } from './ui'

function Chip({
  selected,
  onClick,
  children,
}: {
  selected: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`flex min-h-11 items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-sm font-semibold transition-colors ${
        selected
          ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
          : 'border-fg/10 bg-fg/5 text-fg/55 hover:bg-fg/10'
      }`}
    >
      {children}
    </button>
  )
}

// A checkbox row: the whole row is the target, so it clears 44px without a
// tiny native box to aim at.
function CheckRow({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  label: string
  hint?: string
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex min-h-11 w-full items-center gap-3 rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left transition-colors hover:bg-fg/10"
    >
      <span
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border-2 transition-colors ${
          checked ? 'border-accent-bright/70 bg-accent-bright/25' : 'border-fg/30 bg-fg/5'
        }`}
      >
        {checked && <Check className="h-3.5 w-3.5 text-accent-bright" strokeWidth={3} />}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-fg/85">{label}</span>
        {hint && <span className="block text-xs text-fg/45">{hint}</span>}
      </span>
    </button>
  )
}

// Compact box for a 1-2 digit number; deliberately not the full-width .field.
const NUM = 'w-14 rounded-lg border border-fg/15 bg-fg/10 px-1 py-2 text-center text-sm text-fg outline-none focus:border-accent-bright/60'

const KIND_LABEL: Record<api.ItemKind, string> = {
  routine: 'Routine',
  task: 'Task',
  activity: 'Activity',
  appointment: 'Appointment',
}

// His own examples, so the four kinds read as things the family actually does
// rather than four abstractions.
const KIND_HINT: Record<api.ItemKind, string> = {
  routine: 'Repeats on a schedule. Workout, laundry, cleaning, reading.',
  task: 'One-off, with an optional due date. Chores, take out the trash, pick up a package.',
  activity: 'A day out. Visit with grandma. Activities can be shared with the Village.',
  appointment: 'A fixed date and time. Work meetings, doctor visits.',
}

// Weekday labels, 0 = Monday .. 6 = Sunday (matching the backend mask).
const DAY_LABELS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const EVERY_DAY = [0, 1, 2, 3, 4, 5, 6]
const WEEKDAYS = [0, 1, 2, 3, 4]

// ---- recurrence -------------------------------------------------------------

type Pattern = 'daily' | 'weekly' | 'monthly'
type EndMode = 'never' | 'until' | 'count'

// What the recurrence dialog edits. Daily is weekly with all seven days set,
// which is how the backend has always stored it; a count end is resolved into
// a date server-side, so it never comes back and only lives here while the
// card is being written.
interface RepeatDraft {
  pattern: Pattern
  days: number[]
  interval: number
  monthDay: number
  anchor: string
  endMode: EndMode
  until: string
  count: number
}

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return n + (s[(v - 20) % 10] ?? s[v] ?? s[0])
}

function repeatSummary(d: RepeatDraft): string {
  let base: string
  if (d.pattern === 'monthly') {
    base =
      d.interval > 1
        ? `Every ${d.interval} months on the ${ordinal(d.monthDay)}`
        : `Monthly on the ${ordinal(d.monthDay)}`
  } else if (d.pattern === 'daily') {
    base = 'Every day'
  } else {
    // All seven days only reaches here at every-N spacing, and spelling out
    // the whole week beside it reads as noise.
    if (d.days.length === 7) {
      base = d.interval > 1 ? `Every ${d.interval} weeks, every day` : 'Every day'
    } else {
      const on = [...d.days].sort((a, b) => a - b).map((x) => DAY_NAMES[x]).join(', ') || 'no days yet'
      base = d.interval > 1 ? `Every ${d.interval} weeks on ${on}` : `Weekly on ${on}`
    }
  }
  if (d.endMode === 'until' && d.until) return `${base} until ${compactDate(d.until)}`
  if (d.endMode === 'count') return `${base}, ${d.count} times`
  return base
}

function repeatReady(d: RepeatDraft): boolean {
  const patternOk =
    d.pattern === 'monthly' ? d.monthDay >= 1 && d.monthDay <= 31 : d.pattern === 'daily' || d.days.length > 0
  if (!patternOk) return false
  if (d.endMode === 'until') return Boolean(d.until) && (!d.anchor || d.until >= d.anchor)
  if (d.endMode === 'count') return d.count >= 1 && d.count <= 500
  return true
}

function repeatPayload(d: RepeatDraft): api.RepeatInput {
  const shared = {
    // "Every N" only means something on a weekly or monthly pattern; daily is
    // every day by definition.
    interval: d.pattern === 'daily' ? 1 : d.interval,
    anchor: d.anchor || null,
    until: d.endMode === 'until' ? d.until || null : null,
    count: d.endMode === 'count' ? d.count : null,
  }
  return d.pattern === 'monthly'
    ? { type: 'monthly', month_day: d.monthDay, ...shared }
    : { type: 'weekly', days: d.pattern === 'daily' ? EVERY_DAY : d.days, ...shared }
}

// The recurrence dialog, laid out the way his Outlook one is: the pattern on
// top, then the range it runs for. It edits a copy, so backing out leaves the
// card's existing pattern alone.
function RecurrenceSheet({
  draft,
  onCancel,
  onSave,
}: {
  draft: RepeatDraft
  onCancel: () => void
  onSave: (next: RepeatDraft) => void
}) {
  const [d, setD] = useState(draft)
  const set = <K extends keyof RepeatDraft>(key: K, value: RepeatDraft[K]) =>
    setD((prev) => ({ ...prev, [key]: value }))

  function toggleDay(day: number) {
    setD((prev) => ({
      ...prev,
      days: prev.days.includes(day)
        ? prev.days.filter((x) => x !== day)
        : [...prev.days, day].sort((a, b) => a - b),
    }))
  }

  const unit = d.pattern === 'monthly' ? 'months' : 'weeks'

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onCancel()}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 40 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        className="sheet-card max-h-[90svh] w-full max-w-sm overflow-y-auto p-6"
        role="dialog"
        aria-modal="true"
        data-recurrence-sheet
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-display text-xl font-semibold tracking-[-0.01em]">How often</h2>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            className="-m-3 rounded-lg p-3 text-fg/50 hover:bg-fg/10 hover:text-fg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex flex-col gap-4">
          <div>
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              Pattern
            </span>
            <div className="grid grid-cols-3 gap-2">
              {(['daily', 'weekly', 'monthly'] as Pattern[]).map((p) => (
                <Chip key={p} selected={d.pattern === p} onClick={() => set('pattern', p)}>
                  <span className="mx-auto capitalize">{p}</span>
                </Chip>
              ))}
            </div>
          </div>

          {d.pattern !== 'daily' && (
            <label className="flex items-center gap-2 text-sm text-fg/60">
              Every
              <input
                type="number"
                min={1}
                max={d.pattern === 'monthly' ? 12 : 52}
                value={d.interval}
                onChange={(e) => set('interval', Math.max(1, Number(e.target.value) || 1))}
                className={NUM}
              />
              {unit}
            </label>
          )}

          {d.pattern === 'weekly' && (
            <div>
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
                On these days
              </span>
              <div className="flex gap-1">
                {DAY_LABELS.map((label, day) => (
                  <button
                    key={day}
                    type="button"
                    onClick={() => toggleDay(day)}
                    aria-pressed={d.days.includes(day)}
                    aria-label={DAY_NAMES[day]}
                    className={`min-h-11 flex-1 rounded-lg border text-xs font-semibold transition-colors ${
                      d.days.includes(day)
                        ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
                        : 'border-fg/10 bg-fg/5 text-fg/55 hover:bg-fg/10'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => set('days', WEEKDAYS)}
                className="mt-2 min-h-11 text-xs font-semibold text-accent-bright"
              >
                Weekdays only
              </button>
              {d.days.length === 0 && (
                <p className="text-danger text-xs">Pick at least one day.</p>
              )}
            </div>
          )}

          {d.pattern === 'monthly' && (
            <label className="flex items-center gap-2 text-sm text-fg/60">
              On day
              <input
                type="number"
                min={1}
                max={31}
                value={d.monthDay}
                onChange={(e) => set('monthDay', Math.min(31, Math.max(1, Number(e.target.value) || 1)))}
                className={NUM}
              />
              of the month
            </label>
          )}

          <div className="border-t border-fg/10 pt-4">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              How long it runs
            </span>
            <Field
              id="repeat-anchor"
              label="Starts"
              type="date"
              value={d.anchor}
              onChange={(e) => set('anchor', e.target.value)}
              onClear={() => set('anchor', '')}
            />
            <p className="mt-1.5 mb-3 text-xs text-fg/45">
              The day the pattern counts from, so an every-2-weeks card lands on the right weeks.
            </p>
            <div className="flex flex-col gap-2">
              <label className="flex min-h-11 items-center gap-3 rounded-xl border border-fg/10 bg-fg/5 px-3 text-sm font-semibold text-fg/85">
                <input
                  type="radio"
                  name="repeat-end"
                  checked={d.endMode === 'never'}
                  onChange={() => set('endMode', 'never')}
                  className="h-4 w-4 accent-[var(--accent)]"
                />
                No end date
              </label>
              <div className="rounded-xl border border-fg/10 bg-fg/5 px-3 py-2">
                <label className="flex min-h-11 items-center gap-3 text-sm font-semibold text-fg/85">
                  <input
                    type="radio"
                    name="repeat-end"
                    checked={d.endMode === 'until'}
                    onChange={() => set('endMode', 'until')}
                    className="h-4 w-4 accent-[var(--accent)]"
                  />
                  End by
                </label>
                {d.endMode === 'until' && (
                  <div className="pb-1">
                    <Field
                      id="repeat-until"
                      label="Last day"
                      type="date"
                      value={d.until}
                      onChange={(e) => set('until', e.target.value)}
                      onClear={() => set('until', '')}
                    />
                    {d.until && d.anchor && d.until < d.anchor && (
                      <p className="text-danger mt-1 text-xs">
                        The last day is before the pattern starts.
                      </p>
                    )}
                  </div>
                )}
              </div>
              <div className="rounded-xl border border-fg/10 bg-fg/5 px-3 py-2">
                <label className="flex min-h-11 items-center gap-3 text-sm font-semibold text-fg/85">
                  <input
                    type="radio"
                    name="repeat-end"
                    checked={d.endMode === 'count'}
                    onChange={() => set('endMode', 'count')}
                    className="h-4 w-4 accent-[var(--accent)]"
                  />
                  End after
                </label>
                {d.endMode === 'count' && (
                  <label className="flex items-center gap-2 pb-2 text-sm text-fg/60">
                    <input
                      type="number"
                      min={1}
                      max={500}
                      value={d.count}
                      onChange={(e) => set('count', Math.min(500, Math.max(1, Number(e.target.value) || 1)))}
                      className={NUM}
                    />
                    times
                  </label>
                )}
              </div>
            </div>
          </div>

          <div className="flex gap-2.5">
            <Button type="button" variant="ghost" onClick={onCancel} className="flex-1">
              Back
            </Button>
            <Button
              type="button"
              disabled={!repeatReady(d)}
              onClick={() => onSave(d)}
              className="flex-1"
            >
              Save pattern
            </Button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}

// ---- the card form ----------------------------------------------------------

// Bottom sheet for parents to add or edit a card, laid out the way a calendar
// app does it: what it is, what it's called, when it happens, then the details.
// Tap outside or the X to close, primary action at the bottom.
export function ItemSheet({
  item,
  family,
  defaultDate,
  defaultKind,
  onClose,
  onSaved,
}: {
  item: api.FeedItem | null // null = creating
  family: api.FamilyMember[]
  // When creating from a calendar day, seed the date (and a sensible kind) so
  // the new card lands on the day the parent tapped.
  defaultDate?: string
  defaultKind?: api.ItemKind
  onClose: () => void
  onSaved: () => void
}) {
  const creating = item === null
  const [kind, setKind] = useState<api.ItemKind>(item?.kind ?? defaultKind ?? 'routine')
  const [title, setTitle] = useState(item?.title ?? '')
  const [notes, setNotes] = useState(item?.notes ?? '')

  // Two separate axes: who is assigned to DO it (checks it off), and who can
  // SEE it. Cards go on the family board unless this one is marked private.
  const [assignees, setAssignees] = useState<number[]>(item?.assignees?.map((a) => a.id) ?? [])
  const [isPrivate, setIsPrivate] = useState(item?.visibility === 'private')

  // Recurrence: routines always repeat; appointments may (a weekly work
  // meeting). A new routine starts as a plain daily one.
  const [repeats, setRepeats] = useState(Boolean(item?.repeat) && item?.kind === 'appointment')
  const [repeat, setRepeat] = useState<RepeatDraft>(() => ({
    // All seven days is only "Daily" at every-week spacing. A week-on,
    // week-off card also carries all seven days, and the engine honours that
    // interval, so it has to come back as Weekly with its every-N intact:
    // reading it as Daily would quietly flatten it to every single day the
    // next time anyone saved the card.
    pattern: item?.repeat
      ? item.repeat.type === 'monthly'
        ? 'monthly'
        : item.repeat.days.length === 7 && item.repeat.interval === 1
          ? 'daily'
          : 'weekly'
      : 'daily',
    days: item?.repeat?.days ?? EVERY_DAY,
    interval: item?.repeat?.interval ?? 1,
    monthDay: item?.repeat?.month_day ?? 1,
    anchor: item?.repeat?.anchor ?? (creating ? api.localDate() : ''),
    endMode: item?.repeat?.until ? 'until' : 'never',
    until: item?.repeat?.until ?? '',
    count: 10,
  }))
  const [patternOpen, setPatternOpen] = useState(false)
  const [workoutAuto, setWorkoutAuto] = useState(item?.workout_auto_complete ?? false)

  const [time, setTime] = useState(item?.time_of_day?.slice(0, 5) ?? '')
  const [endTime, setEndTime] = useState(item?.end_time?.slice(0, 5) ?? '')
  const [allDay, setAllDay] = useState(item?.all_day ?? false)
  const [date, setDate] = useState(item?.date_for ?? defaultDate ?? '')
  // The end date shadows the start until someone moves it somewhere else; a
  // one-day card is the common case and shouldn't need two dates typed.
  const [endDate, setEndDate] = useState(item?.end_date ?? item?.date_for ?? defaultDate ?? '')
  const [endDateOwn, setEndDateOwn] = useState(Boolean(item?.end_date))
  const [location, setLocation] = useState(item?.location ?? '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Set when the card saved but its village share didn't: the card exists, so
  // the sheet stops being a form and closing has to refresh the board.
  const [savedWithoutShare, setSavedWithoutShare] = useState(false)

  // Villages this family belongs to, so a new activity can be offered to one
  // as it's created instead of needing a second trip through the card.
  const [villages, setVillages] = useState<api.Village[]>([])
  const [shareVillage, setShareVillage] = useState(false)
  const [villageId, setVillageId] = useState<number | null>(null)

  useEffect(() => {
    if (!creating) return
    api
      .listVillages()
      .then((list) => {
        setVillages(list)
        setVillageId(list[0]?.id ?? null)
      })
      .catch(() => setVillages([]))
  }, [creating])

  const allAssigned = family.length > 0 && family.every((m) => assignees.includes(m.id))

  function toggleMember(id: number) {
    setAssignees((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }
  function toggleEveryone() {
    setAssignees(allAssigned ? [] : family.map((m) => m.id))
  }
  function changeDate(next: string) {
    setDate(next)
    if (!endDateOwn) setEndDate(next)
  }
  function changeEndDate(next: string) {
    setEndDate(next)
    setEndDateOwn(Boolean(next) && next !== date)
  }

  const isRoutine = kind === 'routine'
  const isEvent = kind === 'activity' || kind === 'appointment'
  const repeatingAppt = kind === 'appointment' && repeats
  const recurs = isRoutine || repeatingAppt
  // A repeating card lives on its pattern, not on dates, so all-day and spans
  // are off the table for it (the backend refuses both).
  const effectiveAllDay = isEvent && !repeatingAppt && allDay
  const hasEndDate = isEvent && !repeatingAppt && Boolean(endDate)
  // An end date equal to the start is just a one-day card, so it isn't sent.
  const spanEnd = hasEndDate && endDate > date ? endDate : ''

  // "HH:MM" strings compare correctly, and prefixing the day makes an overnight
  // slot compare right too.
  const endsAfterStart =
    Boolean(time) && Boolean(endTime) && `${spanEnd || date}T${endTime}` > `${date}T${time}`
  const spanOk = !hasEndDate || endDate >= date
  const timesOk = effectiveAllDay || endsAfterStart
  const routineTimesOk = !endTime || (Boolean(time) && endTime > time)
  const scheduleReady = isRoutine
    ? repeatReady(repeat) && routineTimesOk
    : kind === 'task'
      ? true
      : repeatingAppt
        ? repeatReady(repeat) && timesOk
        : Boolean(date) && spanOk && timesOk

  // Only an activity can be offered to a village, and only a dated one that
  // isn't a copy of someone else's event.
  const canShare = creating && kind === 'activity' && Boolean(date) && villages.length > 0

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    const payload: api.ItemPayload = {
      kind,
      title,
      notes,
      assignee_ids: assignees,
      visibility: isPrivate ? 'private' : 'family',
      time_of_day: effectiveAllDay ? null : time || null,
      end_time: effectiveAllDay || kind === 'task' ? null : endTime || null,
      all_day: effectiveAllDay,
      date_for: recurs ? null : date || null,
      end_date: spanEnd || null,
      repeat: recurs ? repeatPayload(repeat) : null,
      workout_auto_complete: isRoutine ? workoutAuto : false,
      location: isEvent ? location.trim() || null : null,
    }
    try {
      const saved = creating ? await api.createItem(payload) : await api.updateItem(item.id, payload)
      if (canShare && shareVillage && villageId !== null) {
        try {
          await api.shareEvent(villageId, saved.id)
        } catch (err) {
          // The card itself is on the board. Say what didn't happen rather
          // than rolling anything back, and let the close refresh it in.
          setError(
            `Card added, but sharing failed: ${
              err instanceof api.ApiError ? err.message : 'try sharing it from the card.'
            }`,
          )
          setSavedWithoutShare(true)
          setBusy(false)
          return
        }
      }
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  async function onDelete() {
    if (creating) return
    setBusy(true)
    try {
      await api.deleteItem(item.id)
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  // Once the card is saved, closing has to refresh the board or the new card
  // wouldn't show until the next poll.
  const dismiss = () => (savedWithoutShare ? onSaved() : onClose())

  const assignHint = allAssigned
    ? 'Everyone checks off their own'
    : assignees.length === 0
      ? 'Just you'
      : assignees.length === 1
        ? 'The person you picked checks it off'
        : 'Each person checks off their own'

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && dismiss()}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 40 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        className="sheet-card max-h-[90svh] w-full max-w-sm overflow-y-auto p-6"
        role="dialog"
        aria-modal="true"
        data-item-sheet
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-display text-xl font-semibold tracking-[-0.01em]">
            {creating ? 'Add to the board' : 'Edit card'}
          </h2>
          <button
            onClick={dismiss}
            aria-label="Close"
            className="-m-3 rounded-lg p-3 text-fg/50 hover:bg-fg/10 hover:text-fg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div>
            <label
              htmlFor="item-kind"
              className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50"
            >
              Type
            </label>
            <select
              id="item-kind"
              value={kind}
              disabled={!creating}
              onChange={(e) => setKind(e.target.value as api.ItemKind)}
              className="field disabled:opacity-60"
            >
              {(Object.keys(KIND_LABEL) as api.ItemKind[]).map((k) => (
                <option key={k} value={k}>
                  {KIND_LABEL[k]}
                </option>
              ))}
            </select>
            <p className="mt-1.5 text-xs text-fg/45">{KIND_HINT[kind]}</p>
          </div>

          {/* No autoFocus on Title: on phones it would summon the keyboard
              over the sheet before the person has even seen the form. */}
          <Field label="Title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} required />

          {/* WHEN. Each kind gets only the rows it can actually use. */}
          {isRoutine && (
            <div className="grid grid-cols-2 gap-3">
              <TimeCombo label="Start (optional)" value={time} onChange={setTime} />
              <TimeCombo label="End (optional)" value={endTime} onChange={setEndTime} />
            </div>
          )}
          {isRoutine && !routineTimesOk && (
            <p className="text-danger -mt-2 text-xs">An end time needs a start time before it.</p>
          )}

          {kind === 'task' && (
            <div className="grid grid-cols-2 gap-3">
              <Field
                label="Due date (optional)"
                type="date"
                value={date}
                onChange={(e) => changeDate(e.target.value)}
                onClear={() => changeDate('')}
              />
              <TimeCombo label="Due time (optional)" value={time} onChange={setTime} />
            </div>
          )}

          {isEvent && (
            <div className="flex flex-col gap-3">
              {!repeatingAppt && (
                <CheckRow
                  checked={allDay}
                  onChange={setAllDay}
                  label="All day"
                  hint="No start or end time, just the day (or days)"
                />
              )}
              {repeatingAppt ? (
                <div className="grid grid-cols-2 gap-3">
                  <TimeCombo label="From" value={time} onChange={setTime} required />
                  <TimeCombo label="To" value={endTime} onChange={setEndTime} required />
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div className={allDay ? 'col-span-2' : ''}>
                      <Field
                        label="Starts"
                        type="date"
                        value={date}
                        onChange={(e) => changeDate(e.target.value)}
                        required
                      />
                    </div>
                    {!allDay && <TimeCombo label="From" value={time} onChange={setTime} required />}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className={allDay ? 'col-span-2' : ''}>
                      {/* No onClear here: the X would sit on top of the native
                          calendar-picker icon on desktop and eat its clicks.
                          Setting the date back to the start un-spans the card. */}
                      <Field
                        label="Ends"
                        type="date"
                        value={endDate}
                        onChange={(e) => changeEndDate(e.target.value)}
                      />
                    </div>
                    {!allDay && <TimeCombo label="To" value={endTime} onChange={setEndTime} required />}
                  </div>
                </>
              )}
              {!spanOk && (
                <p className="text-danger text-xs">The end date must be on or after the start.</p>
              )}
              {spanOk && !allDay && Boolean(time) && Boolean(endTime) && !endsAfterStart && (
                <p className="text-danger text-xs">End time must be after the start.</p>
              )}
              {Boolean(spanEnd) && (
                <p className="text-xs text-fg/45">
                  This card sits on the board every day from {compactDate(date)} through{' '}
                  {compactDate(spanEnd)}.
                </p>
              )}
            </div>
          )}

          {/* HOW OFTEN. Routines always repeat, so they show their pattern
              outright; an appointment opts in. */}
          {(isRoutine || kind === 'appointment') && (
            <div>
              {recurs ? (
                <div className="rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5">
                  <span className="block text-xs font-semibold uppercase tracking-wide text-fg/50">
                    Repeats
                  </span>
                  <p className="mt-0.5 text-sm font-semibold text-fg/85">{repeatSummary(repeat)}</p>
                  <div className="mt-1 flex gap-2">
                    <button
                      type="button"
                      onClick={() => setPatternOpen(true)}
                      className="min-h-11 rounded-lg px-1 text-xs font-semibold text-accent-bright"
                    >
                      Change how often
                    </button>
                    {kind === 'appointment' && (
                      <button
                        type="button"
                        onClick={() => setRepeats(false)}
                        className="ml-auto min-h-11 rounded-lg px-1 text-xs font-semibold text-fg/50 hover:text-fg/80"
                      >
                        Turn off
                      </button>
                    )}
                  </div>
                  {!repeatReady(repeat) && (
                    <p className="text-danger text-xs">This pattern still needs a day.</p>
                  )}
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setRepeats(true)
                    // A repeating appointment carries times, never all-day.
                    setAllDay(false)
                    setPatternOpen(true)
                  }}
                  className="flex min-h-11 w-full items-center gap-2 rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-sm font-semibold text-fg/85 transition-colors hover:bg-fg/10"
                >
                  <RepeatIcon className="h-4 w-4 text-fg/45" strokeWidth={2} />
                  Make it recurring
                </button>
              )}
            </div>
          )}

          {isEvent && (
            <Field
              label="Where (optional)"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              onClear={() => setLocation('')}
              maxLength={120}
              placeholder="Riverside Park"
            />
          )}

          <div>
            <label
              htmlFor="item-notes"
              className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50"
            >
              Notes (optional)
            </label>
            <textarea
              id="item-notes"
              rows={3}
              maxLength={1000}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="field resize-y"
              placeholder="Anything the family should know"
            />
          </div>

          <div>
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              Assign to
            </span>
            {/* Who is responsible and checks it off. Empty means just you. This
                is separate from who can see it (the Private checkbox below). */}
            <div className="flex flex-wrap gap-2">
              <Chip selected={allAssigned} onClick={toggleEveryone}>
                <Users className="h-4 w-4" /> Everyone
              </Chip>
              {family.map((m) => (
                // Reflect real membership even when Everyone is on, so tapping a
                // person visibly toggles that one person. (The old !allAssigned
                // guard showed them all unselected, so a tap looked like it
                // selected everyone-but-them.)
                <Chip key={m.id} selected={assignees.includes(m.id)} onClick={() => toggleMember(m.id)}>
                  <Avatar name={m.display_name} src={api.avatarUrl(m)} size="sm" /> {m.display_name}
                </Chip>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-fg/40">{assignHint}</p>
          </div>

          {isRoutine && (
            <div>
              <CheckRow
                checked={workoutAuto}
                onChange={setWorkoutAuto}
                label="A workout checks it off"
                hint="A synced workout marks that member done for the day"
              />
            </div>
          )}

          <CheckRow
            checked={isPrivate}
            onChange={setIsPrivate}
            label="Private"
            hint={
              isPrivate
                ? 'Only you and anyone you assign can see it'
                : 'Leave it off and the whole family sees it on the board'
            }
          />

          {canShare && (
            <div className="flex flex-col gap-2">
              <CheckRow
                checked={shareVillage}
                onChange={setShareVillage}
                label="Share to the Village"
                hint="Their parents get an invite and can RSVP"
              />
              {/* Always shown when sharing, even with one village: where the
                  card is going shouldn't be implicit. */}
              {shareVillage && (
                <select
                  aria-label="Which village"
                  value={villageId ?? ''}
                  onChange={(e) => setVillageId(Number(e.target.value))}
                  className="field"
                >
                  {villages.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          <FormError message={error} />
          {savedWithoutShare ? (
            <Button type="button" onClick={onSaved} className="mt-1">
              Done
            </Button>
          ) : (
            <>
              <Button type="submit" disabled={busy || !title.trim() || !scheduleReady} className="mt-1">
                {busy ? 'Saving' : creating ? 'Add card' : 'Save changes'}
              </Button>
              {!creating && (
                <Button type="button" variant="danger" onClick={onDelete} disabled={busy} className="flex items-center justify-center gap-1.5">
                  <Trash2 className="h-4 w-4" /> Remove from board
                </Button>
              )}
            </>
          )}
        </form>
      </motion.div>

      {patternOpen && (
        <RecurrenceSheet
          draft={repeat}
          onCancel={() => {
            setPatternOpen(false)
            // Backing out of the dialog the "Make it recurring" button just
            // opened leaves the appointment as it was: a one-off.
            if (kind === 'appointment' && !item?.repeat) setRepeats(false)
          }}
          onSave={(next) => {
            setRepeat(next)
            setPatternOpen(false)
          }}
        />
      )}
    </motion.div>
  )
}
