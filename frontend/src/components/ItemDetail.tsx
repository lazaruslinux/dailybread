import { motion } from 'framer-motion'
import { Ban, Check, Flame, Hourglass, MapPin, Pencil, Trash2, Undo2, X } from 'lucide-react'
import { useState } from 'react'
import {
  avatarUrl,
  type FamilyMember,
  type FeedItem,
  type Repeat,
  type User,
  type VillageEvent,
} from '../lib/api'
import { compactDate, mapsUrl, spansDays } from '../lib/items'
import { formatTime } from '../lib/moods'
import { Avatar } from './Avatar'
import { KIND_STYLE } from './ItemCard'
import { Button } from './ui'

function formatDate(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

const DAY_FULL = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return n + (s[(v - 20) % 10] ?? s[v] ?? s[0])
}

// A routine's recurrence in plain words for the detail view.
function describeRepeat(r: Repeat): string {
  let base: string
  if (r.type === 'weekly') {
    const isEveryDay = r.days.length === 7
    const isWeekdays = r.days.length === 5 && [0, 1, 2, 3, 4].every((d) => r.days.includes(d))
    base = isEveryDay
      ? 'Every day'
      : isWeekdays
        ? 'Weekdays'
        : r.days.map((d) => DAY_FULL[d]).join(', ')
    if (r.interval > 1) base = `${base}, every ${r.interval} weeks`
  } else {
    base = `The ${ordinal(r.month_day ?? 1)} of the month`
    if (r.interval > 1) base = `${base}, every ${r.interval} months`
  }
  return r.until ? `${base}, until ${compactDate(r.until)}` : base
}

// Full view of one card: everything the board truncates, plus the actions.
// Tapping the card body opens this; state only changes from explicit buttons
// in here. Delete is two-tap (arm, then confirm) so a slip can't nuke a card.
export function ItemDetail({
  item,
  canCheck,
  family,
  me,
  onToggle,
  onToggleFor,
  onEdit,
  onDelete,
  onCancel,
  onClose,
  villageEvent,
  onChangeRsvp,
  onShareVillage,
}: {
  item: FeedItem
  canCheck: boolean
  family?: FamilyMember[]
  me?: User | null
  onToggle?: () => void
  onToggleFor?: (userId: number, done: boolean) => void
  onEdit?: () => void
  onDelete?: () => Promise<void>
  // Appointments/activities only: call it off (or put it back on) without
  // pretending it was done.
  onCancel?: () => Promise<void>
  onClose: () => void
  // Set when this card is a materialized village-event copy: the matched
  // event carries the organizer and RSVP picture; the card itself is
  // organizer-managed (Home passes no edit/delete/cancel handlers).
  villageEvent?: VillageEvent | null
  onChangeRsvp?: () => void
  // Set when this card could be offered to a village (parent, own dated
  // non-recurring activity). Home decides; this just renders.
  onShareVillage?: () => void
}) {
  const { Icon, tint, label: kindLabel } = KIND_STYLE[item.kind]
  const label = item.cancelled ? `${kindLabel} · Cancelled` : kindLabel
  const isRoutine = item.kind === 'routine'
  const spans = spansDays(item)
  // A span shows only its START time: its end time belongs to the last day,
  // and "9:00 AM – 4:00 PM" beside a date range reads as if both times landed
  // on both days. Same rule the notification text uses.
  const whenLabel = item.all_day
    ? 'All day'
    : item.time_of_day
      ? item.end_time && !spans
        ? `${formatTime(item.time_of_day)} – ${formatTime(item.end_time)}`
        : formatTime(item.time_of_day)
      : null
  const locationHref = item.location ? mapsUrl(item.location) : null
  // Only a task is a to-do list. Appointments, activities and an adult's
  // routines are calendar entries: they pass on their own and nothing here
  // offers to tick them. A routine stays completable, but only by the kid it
  // was set for, and their word is "I'm done!" rather than an adult's
  // bookkeeping.
  const isKid = me?.is_minor ?? false
  const completable = canCheck && !item.cancelled && (item.kind === 'task' || (isRoutine && isKid))
  const doneLabel = isKid ? "I'm done!" : 'Mark done'
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)

  const [cancelBusy, setCancelBusy] = useState(false)

  async function handleCancel() {
    if (!onCancel) return
    setCancelBusy(true)
    try {
      await onCancel()
    } finally {
      setCancelBusy(false)
    }
  }

  async function handleDelete() {
    if (!onDelete) return
    if (!armed) {
      setArmed(true)
      return
    }
    setBusy(true)
    try {
      await onDelete()
    } finally {
      setBusy(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 40 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        className="sheet-card max-h-[90svh] w-full max-w-sm overflow-y-auto p-4"
        role="dialog"
        aria-modal="true"
        data-item-detail
      >
        <div className="mb-3 flex items-center justify-between">
          <span className={`flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide ${tint}`}>
            <Icon className="h-3.5 w-3.5" strokeWidth={2.5} />
            {label}
          </span>
          <button
            onClick={onClose}
            aria-label="Close"
            className="-m-2 rounded-lg p-3.5 text-fg/50 hover:bg-fg/10 hover:text-fg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <h2 className={`font-display text-xl font-semibold tracking-[-0.01em] ${item.completed ? 'text-fg/60 line-through decoration-fg/30' : ''}`}>
          {item.title}
        </h2>
        {item.notes && <p className="mt-2 text-sm leading-relaxed text-fg/70">{item.notes}</p>}

        <div className="mt-3 flex flex-col gap-1.5 text-sm text-fg/70">
          <div className="flex items-start gap-2">
            <span className="db-micro w-12 shrink-0 pt-1">For</span>
            {item.assignees.length === 0 ? (
              <span className="pt-0.5">You</span>
            ) : (
              <span className="flex flex-wrap gap-x-3 gap-y-1.5">
                {item.assignees.map((a) => (
                  <span key={a.id} className="flex items-center gap-1.5">
                    <Avatar name={a.display_name} src={avatarUrl(a)} size="sm" />
                    {a.display_name}
                  </span>
                ))}
              </span>
            )}
          </div>
          {item.visibility === 'family' && (
            <div className="flex items-center gap-2">
              <span className="db-micro w-12 shrink-0">
                Shown
              </span>
              On the family board
            </div>
          )}
          {item.repeat && (
            <div className="flex items-center gap-2">
              <span className="db-micro w-12 shrink-0">
                Repeats
              </span>
              {describeRepeat(item.repeat)}
            </div>
          )}
          {whenLabel && (
            <div className="flex items-center gap-2">
              <span className="db-micro w-12 shrink-0">Time</span>
              {whenLabel}
            </div>
          )}
          {item.date_for && (
            <div className="flex items-center gap-2">
              <span className="db-micro w-12 shrink-0">
                {item.kind === 'task' ? 'Due' : spans ? 'Dates' : 'Date'}
              </span>
              {spans
                ? `${compactDate(item.date_for)} – ${compactDate(item.end_date!)}`
                : formatDate(item.date_for)}
            </div>
          )}
          {item.location && (
            <div className="flex items-center gap-2">
              <span className="db-micro w-12 shrink-0">
                Where
              </span>
              {locationHref ? (
                <a
                  href={locationHref}
                  target="_blank"
                  rel="noopener"
                  className="flex min-h-11 items-center gap-1 py-1 font-semibold text-accent-bright underline decoration-accent-bright/40 underline-offset-2"
                >
                  <MapPin className="h-3.5 w-3.5 shrink-0" /> {item.location}
                </a>
              ) : (
                <span className="flex items-center gap-1 py-1 text-fg/70">
                  <MapPin className="h-3.5 w-3.5 shrink-0" /> {item.location}
                </span>
              )}
            </div>
          )}
          {villageEvent && (
            <div className="flex items-center gap-2">
              <span className="db-micro w-12 shrink-0">
                From
              </span>
              {villageEvent.organizer_family_name} · {villageEvent.village_name}
            </div>
          )}
        </div>

        {villageEvent && onChangeRsvp && (
          <button
            type="button"
            onClick={onChangeRsvp}
            className="mt-3 flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border border-fg/10 bg-fg/5 px-4 py-2.5 text-sm font-semibold text-fg/80 transition-colors hover:bg-fg/10"
          >
            {villageEvent.is_own ? 'View Attendees' : 'View Attendees · Change RSVP'}
          </button>
        )}

        {isRoutine && item.assignee_completions && (
          <div className="mt-6">
            <span className="db-micro mb-1.5 block">
              Who's done
            </span>
            <div className="flex flex-col gap-2">
              {item.assignee_completions.map((ac) => {
                const member = family?.find((m) => m.id === ac.user_id)
                const parentOnPending = ac.pending && me?.role === 'parent'
                // Read-only. Marking a routine is the assigned kid's own act
                // and it happens on the button below; a parent answers a
                // waiting mark with Approve / Put back on the right.
                return (
                  <div
                    key={ac.user_id}
                    className="flex items-center gap-3 rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left"
                  >
                    <span
                      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 ${
                        ac.completed
                          ? 'border-emerald-300/70 bg-emerald-400/25'
                          : ac.pending
                            ? 'border-amber-300/70 bg-amber-400/25'
                            : 'border-fg/30 bg-fg/5'
                      }`}
                    >
                      {ac.completed && <Check className="h-3.5 w-3.5 text-emerald-300" strokeWidth={3} />}
                      {!ac.completed && ac.pending && (
                        <Hourglass className="h-3 w-3 text-amber-300" strokeWidth={2.5} />
                      )}
                    </span>
                    <Avatar name={member?.display_name ?? '?'} src={member ? avatarUrl(member) : null} size="sm" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold text-fg/90">
                        {member?.display_name ?? 'Member'}
                      </span>
                      {ac.pending && !ac.completed && (
                        <span className="block text-xs font-medium text-amber-300/90">
                          Waiting for a parent
                        </span>
                      )}
                    </span>
                    {parentOnPending && onToggleFor ? (
                      // Real buttons now that the row around them is a plain
                      // div: they used to sit inside a disabled button.
                      <span className="flex shrink-0 items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => onToggleFor(ac.user_id, false)}
                          className="db-tap44 rounded-full border border-fg/10 bg-fg/5 px-2 py-1 text-xs font-semibold text-fg/60 hover:bg-fg/10"
                        >
                          Put back
                        </button>
                        <button
                          type="button"
                          onClick={() => onToggleFor(ac.user_id, true)}
                          className="db-tap44 rounded-full border border-emerald-300/40 bg-emerald-400/15 px-2 py-1 text-xs font-bold text-emerald-300 hover:bg-emerald-400/25"
                        >
                          Approve
                        </button>
                      </span>
                    ) : (
                      ac.streak >= 3 && (
                        <span className="flex items-center gap-0.5 rounded-full bg-orange-400/20 px-1.5 py-px text-[10px] font-bold text-orange-300">
                          <Flame className="h-3 w-3" /> {ac.streak}
                        </span>
                      )
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        <div className="mt-6 flex flex-col gap-2.5">
          {/* Kid mode: the kid's own waiting mark gets a withdraw button; a
              parent gets the same Approve / Put back pair as the "Waiting on
              you" list (for a routine that pair sits per person above). */}
          {completable && item.pending && item.pending_by === me?.id && onToggle && (
            <Button
              type="button"
              variant="ghost"
              onClick={onToggle}
              className="flex items-center justify-center gap-1.5"
            >
              <Hourglass className="h-4 w-4 text-amber-300" /> Undo (waiting for a parent)
            </Button>
          )}
          {!isRoutine && item.pending && item.pending_by !== me?.id && me?.role === 'parent' && onToggleFor && (
            <div className="flex gap-2.5">
              <Button
                type="button"
                variant="ghost"
                onClick={() => onToggleFor(item.pending_by!, false)}
                className="flex flex-1 items-center justify-center gap-1.5"
              >
                <Undo2 className="h-4 w-4" /> Put back
              </Button>
              <Button
                type="button"
                onClick={() => onToggleFor(item.pending_by!, true)}
                className="flex flex-1 items-center justify-center gap-1.5"
              >
                <Check className="h-4 w-4" /> Approve
              </Button>
            </div>
          )}
          {completable && !item.pending && onToggle && (
            <Button
              type="button"
              variant={item.completed ? 'ghost' : 'primary'}
              onClick={onToggle}
              className="flex items-center justify-center gap-1.5"
            >
              {item.completed ? (
                <>
                  <Undo2 className="h-4 w-4" /> Mark not done
                </>
              ) : (
                <>
                  <Check className="h-4 w-4" /> {doneLabel}
                </>
              )}
            </Button>
          )}
          {onEdit && !item.cancelled && (
            <Button type="button" variant="ghost" onClick={onEdit} className="flex items-center justify-center gap-1.5">
              <Pencil className="h-4 w-4" /> Edit card
            </Button>
          )}
          {onShareVillage && !item.cancelled && (
            <Button
              type="button"
              variant="ghost"
              onClick={onShareVillage}
              className="flex items-center justify-center gap-1.5"
            >
              Share with the village
            </Button>
          )}
          {onCancel && (
            <button
              type="button"
              disabled={cancelBusy}
              onClick={handleCancel}
              className="flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border border-gold/40 bg-gold/10 px-4 py-2.5 text-sm font-semibold text-gold transition-colors hover:bg-gold/20 disabled:opacity-50"
            >
              <Ban className="h-4 w-4" />
              {cancelBusy
                ? 'Working'
                : item.cancelled
                  ? 'Un-Cancel'
                  : item.kind === 'appointment'
                    ? 'Cancel this appointment'
                    : 'Cancel this activity'}
            </button>
          )}
          {onDelete && (
            <Button
              type="button"
              variant="danger"
              onClick={handleDelete}
              disabled={busy}
              className="flex items-center justify-center gap-1.5"
            >
              <Trash2 className="h-4 w-4" />
              {armed ? 'Tap again to remove' : 'Remove from board'}
            </Button>
          )}
        </div>
      </motion.div>
    </motion.div>
  )
}
