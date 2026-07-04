import { motion } from 'framer-motion'
import { Check, Pencil, Trash2, Undo2, X } from 'lucide-react'
import { useState } from 'react'
import type { FeedItem } from '../lib/api'
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

// Full view of one card: everything the board truncates, plus the actions.
// Tapping the card body opens this; state only changes from explicit buttons
// in here. Delete is two-tap (arm, then confirm) so a slip can't nuke a card.
export function ItemDetail({
  item,
  canCheck,
  onToggle,
  onEdit,
  onDelete,
  onClose,
}: {
  item: FeedItem
  canCheck: boolean
  onToggle?: () => void
  onEdit?: () => void
  onDelete?: () => Promise<void>
  onClose: () => void
}) {
  const { Icon, tint, label } = KIND_STYLE[item.kind]
  const time = formatTime(item.time_of_day)
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
          <div className="flex items-center gap-2">
            <span className="w-12 text-xs font-semibold uppercase tracking-wide text-white/40">For</span>
            {item.assignee ? (
              <span className="flex items-center gap-1.5">
                <Avatar name={item.assignee.display_name} size="sm" />
                {item.assignee.display_name}
              </span>
            ) : (
              'Everyone'
            )}
          </div>
          {time && (
            <div className="flex items-center gap-2">
              <span className="w-12 text-xs font-semibold uppercase tracking-wide text-white/40">Time</span>
              {time}
            </div>
          )}
          {item.date_for && (
            <div className="flex items-center gap-2">
              <span className="w-12 text-xs font-semibold uppercase tracking-wide text-white/40">Date</span>
              {formatDate(item.date_for)}
            </div>
          )}
        </div>

        <div className="mt-6 flex flex-col gap-2.5">
          {canCheck && onToggle && (
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
