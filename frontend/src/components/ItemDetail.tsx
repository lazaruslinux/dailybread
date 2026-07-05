import { motion } from 'framer-motion'
import { Check, Flame, Pencil, Trash2, Undo2, X } from 'lucide-react'
import { useState } from 'react'
import type { FamilyMember, FeedItem, Repeat, User } from '../lib/api'
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
  if (r.type === 'weekly') {
    const isEveryDay = r.days.length === 7
    const isWeekdays = r.days.length === 5 && [0, 1, 2, 3, 4].every((d) => r.days.includes(d))
    const base = isEveryDay
      ? 'Every day'
      : isWeekdays
        ? 'Weekdays'
        : r.days.map((d) => DAY_FULL[d]).join(', ')
    return r.interval > 1 ? `${base}, every ${r.interval} weeks` : base
  }
  const base = `The ${ordinal(r.month_day ?? 1)} of the month`
  return r.interval > 1 ? `${base}, every ${r.interval} months` : base
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
  onClose,
}: {
  item: FeedItem
  canCheck: boolean
  family?: FamilyMember[]
  me?: User | null
  onToggle?: () => void
  onToggleFor?: (userId: number, done: boolean) => void
  onEdit?: () => void
  onDelete?: () => Promise<void>
  onClose: () => void
}) {
  const { Icon, tint, label } = KIND_STYLE[item.kind]
  const isRoutine = item.kind === 'routine'
  const whenLabel = item.all_day
    ? 'All day'
    : item.time_of_day
      ? item.end_time
        ? `${formatTime(item.time_of_day)} – ${formatTime(item.end_time)}`
        : formatTime(item.time_of_day)
      : null
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)

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
        data-item-detail
      >
        <div className="mb-4 flex items-center justify-between">
          <span className={`flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide ${tint}`}>
            <Icon className="h-3.5 w-3.5" strokeWidth={2.5} />
            {label}
          </span>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-white/50 hover:bg-white/10 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <h2 className={`text-xl font-bold ${item.completed ? 'text-white/60 line-through decoration-white/30' : ''}`}>
          {item.title}
        </h2>
        {item.notes && <p className="mt-2 text-sm leading-relaxed text-white/70">{item.notes}</p>}

        <div className="mt-4 flex flex-col gap-2 text-sm text-white/70">
          <div className="flex items-start gap-2">
            <span className="w-12 shrink-0 pt-1 text-xs font-semibold uppercase tracking-wide text-white/40">For</span>
            {item.assignees.length === 0 ? (
              <span className="pt-0.5">You</span>
            ) : (
              <span className="flex flex-wrap gap-x-3 gap-y-1.5">
                {item.assignees.map((a) => (
                  <span key={a.id} className="flex items-center gap-1.5">
                    <Avatar name={a.display_name} size="sm" />
                    {a.display_name}
                  </span>
                ))}
              </span>
            )}
          </div>
          {item.visibility === 'family' && (
            <div className="flex items-center gap-2">
              <span className="w-12 shrink-0 text-xs font-semibold uppercase tracking-wide text-white/40">
                Shown
              </span>
              On the family board
            </div>
          )}
          {item.repeat && (
            <div className="flex items-center gap-2">
              <span className="w-12 shrink-0 text-xs font-semibold uppercase tracking-wide text-white/40">
                Repeats
              </span>
              {describeRepeat(item.repeat)}
            </div>
          )}
          {whenLabel && (
            <div className="flex items-center gap-2">
              <span className="w-12 shrink-0 text-xs font-semibold uppercase tracking-wide text-white/40">Time</span>
              {whenLabel}
            </div>
          )}
          {item.date_for && (
            <div className="flex items-center gap-2">
              <span className="w-12 text-xs font-semibold uppercase tracking-wide text-white/40">
                {item.kind === 'task' ? 'Due' : 'Date'}
              </span>
              {formatDate(item.date_for)}
            </div>
          )}
        </div>

        {isRoutine && item.assignee_completions && (
          <div className="mt-6">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-white/40">
              Who's done
            </span>
            <div className="flex flex-col gap-2">
              {item.assignee_completions.map((ac) => {
                const member = family?.find((m) => m.id === ac.user_id)
                // You can toggle your own; a parent can toggle anyone's.
                const canToggle = Boolean(me) && (me!.id === ac.user_id || me!.role === 'parent')
                return (
                  <button
                    key={ac.user_id}
                    type="button"
                    disabled={!canToggle}
                    onClick={() => onToggleFor?.(ac.user_id, !ac.completed)}
                    className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-left transition-colors enabled:hover:bg-white/10 disabled:opacity-70"
                  >
                    <span
                      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 ${
                        ac.completed
                          ? 'border-emerald-300/70 bg-emerald-400/25'
                          : 'border-white/30 bg-white/5'
                      }`}
                    >
                      {ac.completed && <Check className="h-3.5 w-3.5 text-emerald-300" strokeWidth={3} />}
                    </span>
                    <Avatar name={member?.display_name ?? '?'} size="sm" />
                    <span className="flex-1 truncate font-semibold text-white/90">
                      {member?.display_name ?? 'Member'}
                    </span>
                    {ac.streak >= 3 && (
                      <span className="flex items-center gap-0.5 rounded-full bg-orange-400/20 px-1.5 py-px text-[10px] font-bold text-orange-300">
                        <Flame className="h-3 w-3" /> {ac.streak}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        <div className="mt-6 flex flex-col gap-2.5">
          {!isRoutine && canCheck && onToggle && (
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
                  <Check className="h-4 w-4" /> Mark done
                </>
              )}
            </Button>
          )}
          {onEdit && (
            <Button type="button" variant="ghost" onClick={onEdit} className="flex items-center justify-center gap-1.5">
              <Pencil className="h-4 w-4" /> Edit card
            </Button>
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
