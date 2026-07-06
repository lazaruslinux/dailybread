import { motion } from 'framer-motion'
import { Activity, CalendarClock, Check, Circle, Flame, Pencil, Repeat, type LucideIcon } from 'lucide-react'
import type { FamilyMember, FeedItem, ItemKind } from '../lib/api'
import { formatTime } from '../lib/moods'
import { Avatar } from './Avatar'

export const KIND_STYLE: Record<ItemKind, { Icon: LucideIcon; tint: string; label: string }> = {
  routine: { Icon: Repeat, tint: 'text-sky-300', label: 'Routine' },
  task: { Icon: Circle, tint: 'text-gold', label: 'Task' },
  activity: { Icon: Activity, tint: 'text-emerald-300', label: 'Activity' },
  appointment: { Icon: CalendarClock, tint: 'text-accent-strong', label: 'Appointment' },
}

// A face with a small check badge when that person has done their own bit.
// Used for routines, which are completed per person.
function ParticipantAvatar({ name, done }: { name: string; done: boolean }) {
  return (
    <span className="relative">
      <Avatar name={name} size="sm" className={`ring-2 ring-black/40 ${done ? '' : 'opacity-45'}`} />
      {done && (
        <span className="absolute -bottom-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-emerald-400 ring-2 ring-black/40">
          <Check className="h-2.5 w-2.5 text-black" strokeWidth={4} />
        </span>
      )}
    </span>
  )
}

// One card on the board. The circle on the left is the only thing that
// completes a card; tapping anywhere else opens the detail sheet, so a
// stray tap can never silently change state. Completed cards stay in place
// but visibly settle: dimmed, circle filled with a check.
export function ItemCard({
  item,
  index,
  canCheck,
  family,
  flag,
  onToggle,
  onOpen,
  onEdit,
}: {
  item: FeedItem
  index: number
  canCheck: boolean
  family?: FamilyMember[]
  flag?: 'overdue' | 'due' | null
  onToggle?: () => void
  onOpen?: () => void
  onEdit?: () => void
}) {
  const { Icon, tint, label } = KIND_STYLE[item.kind]
  const timeLabel = item.all_day ? 'All day' : formatTime(item.time_of_day)
  const showCheckbox = canCheck && onToggle

  // Routines are per-person: show each participant's own check. Suppressed
  // when it's the viewer's own solo routine (their left circle already says
  // it), but shown for a solo routine the viewer only watches (awareness).
  const perPerson =
    item.kind === 'routine' && item.assignee_completions && item.assignee_completions.length >= 1
      ? item.assignee_completions.map((c) => ({
          user: family?.find((m) => m.id === c.user_id),
          completed: c.completed,
        }))
      : null
  const showPerPerson = perPerson !== null && (perPerson.length > 1 || !showCheckbox)
  const doneCount = perPerson?.filter((p) => p.completed).length ?? 0

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: item.completed ? 0.55 : 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ delay: index * 0.05, type: 'spring', stiffness: 300, damping: 26 }}
      whileTap={{ scale: 0.97 }}
      onClick={onOpen}
      className="glass flex cursor-pointer touch-pan-y select-none items-center gap-3 p-4"
    >
      {showCheckbox ? (
        // Generous tap target around a modest circle; stops propagation so
        // checking off never also opens the detail sheet underneath.
        <button
          type="button"
          aria-label={item.completed ? `Mark ${item.title} not done` : `Mark ${item.title} done`}
          onClick={(e) => {
            e.stopPropagation()
            onToggle()
          }}
          className="-m-2 shrink-0 p-2"
          data-check
        >
          <span
            className={`flex h-7 w-7 items-center justify-center rounded-full border-2 transition-colors ${
              item.completed
                ? 'border-emerald-300/70 bg-emerald-400/25'
                : 'border-fg/30 bg-fg/5'
            }`}
          >
            {item.completed && <Check className="h-4 w-4 text-emerald-300" strokeWidth={3} />}
          </span>
        </button>
      ) : (
        <div
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${
            item.completed ? 'bg-emerald-400/25' : 'bg-fg/15'
          }`}
        >
          {item.completed ? (
            <Check className="h-5 w-5 text-emerald-300" strokeWidth={2.5} />
          ) : (
            <Icon className={`h-5 w-5 ${tint}`} strokeWidth={2} />
          )}
        </div>
      )}

      <div className="min-w-0 flex-1">
        <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wide text-fg/50">
          <span className={`flex items-center gap-1 ${showCheckbox ? tint : ''}`}>
            {showCheckbox && <Icon className="h-3 w-3" strokeWidth={2.5} />}
            {label}
          </span>
          {flag === 'overdue' && (
            <span className="rounded-full bg-rose-500/20 px-1.5 py-px text-[10px] font-bold normal-case text-rose-300">
              Overdue
            </span>
          )}
          {flag === 'due' && (
            <span className="rounded-full bg-gold/20 px-1.5 py-px text-[10px] font-bold normal-case text-gold">
              Due
            </span>
          )}
          {perPerson && perPerson.length > 1 && (
            <span className="font-bold normal-case text-fg/40">
              {doneCount}/{perPerson.length}
            </span>
          )}
        </span>
        <p className={`truncate font-semibold ${item.completed ? 'text-fg/60 line-through decoration-fg/30' : 'text-fg'}`}>
          {item.title}
        </p>
        {item.notes && <p className="truncate text-sm text-fg/60">{item.notes}</p>}
      </div>

      <div className="flex shrink-0 flex-col items-end gap-1.5">
        {timeLabel && (
          <span className={`text-xs font-medium ${flag === 'overdue' ? 'text-rose-300' : 'text-fg/50'}`}>
            {timeLabel}
          </span>
        )}
        {showPerPerson && perPerson ? (
          // Per-person routine: each face carries its own check state.
          <div className="flex -space-x-2">
            {perPerson.slice(0, 3).map((p, i) => (
              <ParticipantAvatar key={i} name={p.user?.display_name ?? '?'} done={p.completed} />
            ))}
            {perPerson.length > 3 && (
              <span className="z-10 flex h-7 w-7 items-center justify-center rounded-full bg-fg/15 text-[10px] font-bold ring-2 ring-black/40">
                +{perPerson.length - 3}
              </span>
            )}
          </div>
        ) : (
          item.assignees.length > 0 && (
            // Overlapping cluster; the ring separates faces. Cap at three, then
            // a +N so a card for several people never overflows the row.
            <div className="flex -space-x-2">
              {item.assignees.slice(0, 3).map((a) => (
                <Avatar key={a.id} name={a.display_name} size="sm" className="ring-2 ring-black/40" />
              ))}
              {item.assignees.length > 3 && (
                <span className="z-10 flex h-7 w-7 items-center justify-center rounded-full bg-fg/15 text-[10px] font-bold ring-2 ring-black/40">
                  +{item.assignees.length - 3}
                </span>
              )}
            </div>
          )
        )}
        {(item.streak ?? 0) >= 3 && (
          <span className="flex items-center gap-0.5 text-[10px] font-bold text-orange-300">
            <Flame className="h-3 w-3" /> {item.streak}
          </span>
        )}
      </div>

      {onEdit && (
        // Shortcut straight into the editor for parents; the detail sheet
        // has Edit too. Propagation stops so it never opens the sheet.
        <button
          type="button"
          aria-label={`Edit ${item.title}`}
          onClick={(e) => {
            e.stopPropagation()
            onEdit()
          }}
          className="-my-2 -mr-2 shrink-0 rounded-xl p-2.5 text-fg/35 transition-colors hover:bg-fg/10 hover:text-fg/70 active:bg-fg/15"
        >
          <Pencil className="h-4 w-4" strokeWidth={2} />
        </button>
      )}
    </motion.div>
  )
}

// The thin "you are here" line between what's passed and what's next.
export function NowDivider() {
  return (
    <motion.div
      layout
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex items-center gap-2 py-0.5"
    >
      <span className="text-[10px] font-bold uppercase tracking-widest text-accent-bright">Now</span>
      <span className="h-px flex-1 bg-gradient-to-r from-accent-bright/70 to-transparent" />
    </motion.div>
  )
}
