import { motion } from 'framer-motion'
import { Trash2, Users, X } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import * as api from '../lib/api'
import { Avatar } from './Avatar'
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
      className={`flex items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-sm font-semibold transition-colors ${
        selected
          ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
          : 'border-fg/10 bg-fg/5 text-fg/55 hover:bg-fg/10'
      }`}
    >
      {children}
    </button>
  )
}

// Compact box for a 1-2 digit number; deliberately not the full-width .field.
const NUM = 'w-12 rounded-lg border border-fg/15 bg-fg/10 px-1 py-1 text-center text-sm text-fg outline-none focus:border-accent-bright/60'

const KIND_LABEL: Record<api.ItemKind, string> = {
  routine: 'Routine',
  task: 'Task',
  activity: 'Activity',
  appointment: 'Appointment',
}

const KIND_HINT: Record<api.ItemKind, string> = {
  routine: 'Repeats on a schedule you choose',
  task: 'One-off, with an optional due date',
  activity: 'A time block on a set day',
  appointment: 'A fixed date and time',
}

// Weekday labels, 0 = Monday .. 6 = Sunday (matching the backend mask).
const DAY_LABELS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
const EVERY_DAY = [0, 1, 2, 3, 4, 5, 6]
const WEEKDAYS = [0, 1, 2, 3, 4]

// Bottom sheet for parents to add or edit a card. Same pattern as the admin
// member sheet: tap outside or the X to close, primary action at the bottom.
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

  // Two separate axes: who is assigned to DO it (checks it off), and whether
  // it's shown on the whole family's board (visibility). A card is private to
  // the owner + assignees until the family-board switch is on.
  const [assignees, setAssignees] = useState<number[]>(item?.assignees?.map((a) => a.id) ?? [])
  const [familyBoard, setFamilyBoard] = useState(item?.visibility === 'family')

  // Recurrence: routines always repeat; appointments may (a weekly work
  // meeting). A new routine starts as a plain daily one.
  const [repeats, setRepeats] = useState(Boolean(item?.repeat) && item?.kind === 'appointment')
  const [workoutAuto, setWorkoutAuto] = useState(item?.workout_auto_complete ?? false)
  const [repeatType, setRepeatType] = useState<api.RepeatType>(item?.repeat?.type ?? 'weekly')
  const [days, setDays] = useState<number[]>(item?.repeat?.days ?? EVERY_DAY)
  const [interval, setInterval] = useState(item?.repeat?.interval ?? 1)
  const [monthDay, setMonthDay] = useState(item?.repeat?.month_day ?? 1)

  const [time, setTime] = useState(item?.time_of_day?.slice(0, 5) ?? '')
  const [endTime, setEndTime] = useState(item?.end_time?.slice(0, 5) ?? '')
  const [allDay, setAllDay] = useState(item?.all_day ?? false)
  const [date, setDate] = useState(item?.date_for ?? defaultDate ?? '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const allAssigned = family.length > 0 && family.every((m) => assignees.includes(m.id))

  function toggleMember(id: number) {
    setAssignees((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }
  function toggleEveryone() {
    setAssignees(allAssigned ? [] : family.map((m) => m.id))
  }
  function toggleDay(d: number) {
    setDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort((a, b) => a - b)))
  }

  const isRoutine = kind === 'routine'
  const isEvent = kind === 'activity' || kind === 'appointment'
  const repeatingAppt = kind === 'appointment' && repeats
  const recurs = isRoutine || repeatingAppt
  const allDayAppt = kind === 'appointment' && allDay && !repeatingAppt
  const weeklyReady = !recurs || repeatType !== 'weekly' || days.length > 0
  // "HH:MM" strings compare correctly, so end > start is a plain comparison.
  const timesOk = allDayAppt || (Boolean(time) && Boolean(endTime) && endTime > time)
  const scheduleReady = isRoutine
    ? weeklyReady
    : kind === 'task'
      ? true
      : repeatingAppt
        ? weeklyReady && timesOk
        : Boolean(date) && timesOk

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    const repeat: api.RepeatInput | null = recurs
      ? repeatType === 'weekly'
        ? { type: 'weekly', days, interval }
        : { type: 'monthly', month_day: monthDay, interval }
      : null
    const payload: api.ItemPayload = {
      kind,
      title,
      notes,
      assignee_ids: assignees,
      visibility: familyBoard ? 'family' : 'private',
      time_of_day: allDayAppt ? null : time || null,
      end_time: isEvent && !allDayAppt ? endTime || null : null,
      all_day: kind === 'appointment' && !repeatingAppt ? allDay : false,
      date_for: recurs ? null : date || null,
      repeat,
      workout_auto_complete: isRoutine ? workoutAuto : false,
    }
    try {
      if (creating) await api.createItem(payload)
      else await api.updateItem(item.id, payload)
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
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 40 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        className="glass max-h-[90svh] w-full max-w-sm overflow-y-auto p-6"
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-display text-xl font-semibold tracking-[-0.01em]">
            {creating ? 'Add to the board' : 'Edit card'}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div>
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              Type
            </span>
            <div className="grid grid-cols-2 gap-2">
              {(Object.keys(KIND_LABEL) as api.ItemKind[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setKind(k)}
                  disabled={!creating}
                  className={`rounded-xl border px-2 py-2 text-sm font-semibold transition-colors disabled:opacity-60 ${
                    kind === k
                      ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
                      : 'border-fg/10 bg-fg/5 text-fg/55 hover:bg-fg/10'
                  }`}
                >
                  {KIND_LABEL[k]}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-fg/40">{KIND_HINT[kind]}</p>
          </div>

          {/* No autoFocus on Title: on phones it would summon the keyboard
              over the sheet before the person has even seen the form. */}
          <Field label="Title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} required />
          <Field label="Notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={300} />

          {kind === 'appointment' && (
            <button
              type="button"
              role="switch"
              aria-checked={repeats}
              onClick={() => setRepeats((v) => !v)}
              className="flex w-full items-center justify-between rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left"
            >
              <span className="text-sm font-semibold text-fg/85">Repeats</span>
              <span className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${repeats ? 'bg-accent' : 'bg-fg/15'}`}>
                <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-fg transition-all ${repeats ? 'left-[1.125rem]' : 'left-0.5'}`} />
              </span>
            </button>
          )}

          {recurs && (
            <div>
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
                Repeats
              </span>
              <div className="mb-2 grid grid-cols-2 gap-2">
                <Chip selected={repeatType === 'weekly'} onClick={() => setRepeatType('weekly')}>
                  <span className="mx-auto">Weekly</span>
                </Chip>
                <Chip selected={repeatType === 'monthly'} onClick={() => setRepeatType('monthly')}>
                  <span className="mx-auto">Monthly</span>
                </Chip>
              </div>

              {repeatType === 'weekly' ? (
                <>
                  <div className="flex gap-1">
                    {DAY_LABELS.map((label, d) => (
                      <button
                        key={d}
                        type="button"
                        onClick={() => toggleDay(d)}
                        aria-pressed={days.includes(d)}
                        className={`flex-1 rounded-lg border py-1.5 text-xs font-semibold transition-colors ${
                          days.includes(d)
                            ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
                            : 'border-fg/10 bg-fg/5 text-fg/55 hover:bg-fg/10'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setDays(EVERY_DAY)}
                      className="text-xs font-semibold text-accent-bright hover:text-accent-bright"
                    >
                      Daily
                    </button>
                    <span className="text-fg/20">·</span>
                    <button
                      type="button"
                      onClick={() => setDays(WEEKDAYS)}
                      className="text-xs font-semibold text-accent-bright hover:text-accent-bright"
                    >
                      Weekdays
                    </button>
                    <label className="ml-auto flex items-center gap-1.5 text-xs text-fg/50">
                      every
                      <input
                        type="number"
                        min={1}
                        max={52}
                        value={interval}
                        onChange={(e) => setInterval(Math.max(1, Number(e.target.value) || 1))}
                        className={NUM}
                      />
                      wk
                    </label>
                  </div>
                </>
              ) : (
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-1.5 text-xs text-fg/50">
                    Day
                    <input
                      type="number"
                      min={1}
                      max={31}
                      value={monthDay}
                      onChange={(e) => setMonthDay(Math.min(31, Math.max(1, Number(e.target.value) || 1)))}
                      className={NUM}
                    />
                  </label>
                  <label className="ml-auto flex items-center gap-1.5 text-xs text-fg/50">
                    every
                    <input
                      type="number"
                      min={1}
                      max={12}
                      value={interval}
                      onChange={(e) => setInterval(Math.max(1, Number(e.target.value) || 1))}
                      className={NUM}
                    />
                    mo
                  </label>
                </div>
              )}
              {!weeklyReady && <p className="text-danger mt-1.5 text-xs">Pick at least one day.</p>}
            </div>
          )}

          {isRoutine && (
            <div>
              <button
                type="button"
                role="switch"
                aria-checked={workoutAuto}
                onClick={() => setWorkoutAuto((v) => !v)}
                className="flex w-full items-center justify-between rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left"
              >
                <span className="text-sm font-semibold text-fg/85">A workout checks it off</span>
                <span className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${workoutAuto ? 'bg-accent' : 'bg-fg/15'}`}>
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-fg transition-all ${workoutAuto ? 'left-[1.125rem]' : 'left-0.5'}`} />
                </span>
              </button>
              {workoutAuto && (
                <p className="mt-1.5 px-1 text-xs text-fg/45">
                  When someone's watch syncs a workout, their check on this routine is marked
                  done for that day.
                </p>
              )}
            </div>
          )}

          <div>
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              Assign to
            </span>
            {/* Who is responsible and checks it off. Empty means just you. This
                is separate from who can see it (the family-board switch below). */}
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

          <div>
            <button
              type="button"
              role="switch"
              aria-checked={familyBoard}
              onClick={() => setFamilyBoard((v) => !v)}
              className="flex w-full items-center justify-between rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left"
            >
              <span className="text-sm font-semibold text-fg/85">Show on the family board</span>
              <span className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${familyBoard ? 'bg-accent' : 'bg-fg/15'}`}>
                <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-fg transition-all ${familyBoard ? 'left-[1.125rem]' : 'left-0.5'}`} />
              </span>
            </button>
            <p className="mt-1.5 text-xs text-fg/40">
              {familyBoard
                ? 'Everyone can see it and hide it if they like; only assigned people check it off'
                : 'Only you and anyone you assign can see it'}
            </p>
          </div>

          {isRoutine ? (
            <Field
              label="Time (optional)"
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              onClear={() => setTime('')}
            />
          ) : kind === 'task' ? (
            <div className="grid grid-cols-2 gap-3">
              <Field label="Due date (optional)" type="date" value={date} onChange={(e) => setDate(e.target.value)} onClear={() => setDate('')} />
              <Field label="Due time (optional)" type="time" value={time} onChange={(e) => setTime(e.target.value)} onClear={() => setTime('')} />
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {!repeatingAppt && (
                <Field label="Date" type="date" value={date} onChange={(e) => setDate(e.target.value)} onClear={() => setDate('')} required />
              )}
              {kind === 'appointment' && !repeatingAppt && (
                <button
                  type="button"
                  role="switch"
                  aria-checked={allDay}
                  onClick={() => setAllDay((v) => !v)}
                  className="flex w-full items-center justify-between rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left"
                >
                  <span className="text-sm font-semibold text-fg/85">All day</span>
                  <span className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${allDay ? 'bg-accent' : 'bg-fg/15'}`}>
                    <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-fg transition-all ${allDay ? 'left-[1.125rem]' : 'left-0.5'}`} />
                  </span>
                </button>
              )}
              {!allDayAppt && (
                <div className="grid grid-cols-2 gap-3">
                  <Field label="From" type="time" value={time} onChange={(e) => setTime(e.target.value)} onClear={() => setTime('')} required />
                  <Field label="To" type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} onClear={() => setEndTime('')} required />
                </div>
              )}
              {!allDayAppt && Boolean(time) && Boolean(endTime) && endTime <= time && (
                <p className="text-danger text-xs">End time must be after the start.</p>
              )}
            </div>
          )}

          <FormError message={error} />
          <Button type="submit" disabled={busy || !title.trim() || !scheduleReady} className="mt-1">
            {busy ? 'Saving' : creating ? 'Add card' : 'Save changes'}
          </Button>
          {!creating && (
            <Button type="button" variant="danger" onClick={onDelete} disabled={busy} className="flex items-center justify-center gap-1.5">
              <Trash2 className="h-4 w-4" /> Remove from board
            </Button>
          )}
        </form>
      </motion.div>
    </motion.div>
  )
}
