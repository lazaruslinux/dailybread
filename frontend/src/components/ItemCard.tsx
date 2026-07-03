import { motion } from 'framer-motion'
import { Calendar, Check, Circle, Flame, Pencil, Repeat, type LucideIcon } from 'lucide-react'
import type { FeedItem, ItemKind } from '../lib/api'
import { formatTime } from '../lib/moods'
import { useLongPress } from '../lib/useLongPress'
import { Avatar } from './Avatar'

const KIND_STYLE: Record<ItemKind, { Icon: LucideIcon; tint: string; label: string }> = {
  routine: { Icon: Repeat, tint: 'text-sky-300', label: 'Routine' },
  todo: { Icon: Circle, tint: 'text-amber-300', label: 'To-do' },
  event: { Icon: Calendar, tint: 'text-violet-300', label: 'Schedule' },
}

// One card on the board. Tap toggles done; parents hold to edit. Completed
// cards stay in place but visibly settle: dimmed, icon swapped for a check.
export function ItemCard({
  item,
  index,
  canCheck,
  onToggle,
  onEdit,
}: {
  item: FeedItem
  index: number
  canCheck: boolean
  onToggle?: () => void
  onEdit?: () => void
}) {
  const { Icon, tint, label } = KIND_STYLE[item.kind]
  const time = formatTime(item.time_of_day)
  const press = useLongPress(
    () => onEdit?.(),
    () => canCheck && onToggle?.(),
  )

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: item.completed ? 0.55 : 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ delay: index * 0.05, type: 'spring', stiffness: 300, damping: 26 }}
      whileTap={{ scale: 0.97 }}
      className="glass flex touch-pan-y select-none items-center gap-4 p-4"
      {...press}
    >
      <div
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl transition-colors ${
          item.completed ? 'bg-emerald-400/25' : 'bg-white/15'
        }`}
      >
        {item.completed ? (
          <Check className="h-5 w-5 text-emerald-300" strokeWidth={2.5} />
        ) : (
          <Icon className={`h-5 w-5 ${tint}`} strokeWidth={2} />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wide text-white/50">
          {label}
          {(item.streak ?? 0) >= 3 && (
            <span className="flex items-center gap-0.5 rounded-full bg-orange-400/20 px-1.5 py-px text-[10px] font-bold normal-case text-orange-300">
              <Flame className="h-3 w-3" /> {item.streak}
            </span>
          )}
        </span>
        <p className={`truncate font-semibold ${item.completed ? 'text-white/60 line-through decoration-white/30' : 'text-white'}`}>
          {item.title}
        </p>
        {item.notes && <p className="truncate text-sm text-white/60">{item.notes}</p>}
      </div>

      <div className="flex shrink-0 flex-col items-end gap-1.5">
        {time && <span className="text-xs font-medium text-white/50">{time}</span>}
        {item.assignee && <Avatar name={item.assignee.display_name} size="sm" />}
      </div>

      {onEdit && (
        // Visible way into the editor for parents; long-press still works as a
        // shortcut. Pointer events stop here so a tap never toggles the card.
        <button
          type="button"
          aria-label={`Edit ${item.title}`}
          onPointerDown={(e) => e.stopPropagation()}
          onPointerUp={(e) => e.stopPropagation()}
          onClick={onEdit}
          className="-my-2 -mr-2 shrink-0 rounded-xl p-2.5 text-white/35 transition-colors hover:bg-white/10 hover:text-white/70 active:bg-white/15"
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
      <span className="text-[10px] font-bold uppercase tracking-widest text-indigo-300">Now</span>
      <span className="h-px flex-1 bg-gradient-to-r from-indigo-400/70 to-transparent" />
    </motion.div>
  )
}
