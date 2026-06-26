import { motion } from 'framer-motion'
import { Calendar, Circle, Repeat, type LucideIcon } from 'lucide-react'
import { KIND_LABEL, type CardKind, type FeedCard } from '../data/mock'

// Each card type gets a clean line icon and an accent tint for its tile.
const KIND_STYLE: Record<CardKind, { Icon: LucideIcon; tint: string }> = {
  routine: { Icon: Repeat, tint: 'text-sky-300' },
  todo: { Icon: Circle, tint: 'text-amber-300' },
  event: { Icon: Calendar, tint: 'text-violet-300' },
}

// One frosted "notification" row. `index` staggers the entrance animation so
// the cards cascade in like iOS notifications.
export function NotificationCard({ card, index }: { card: FeedCard; index: number }) {
  const { Icon, tint } = KIND_STYLE[card.kind]

  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay: index * 0.06, type: 'spring', stiffness: 300, damping: 26 }}
      whileTap={{ scale: 0.97 }}
      className="glass flex items-center gap-4 p-4"
    >
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-white/15">
        <Icon className={`h-5 w-5 ${tint}`} strokeWidth={2} />
      </div>

      <div className="min-w-0 flex-1">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-white/50">
          {KIND_LABEL[card.kind]}
        </span>
        <p className="truncate font-semibold text-white">{card.title}</p>
        <p className="truncate text-sm text-white/60">{card.subtitle}</p>
      </div>

      {card.time && <span className="shrink-0 text-xs font-medium text-white/50">{card.time}</span>}
    </motion.div>
  )
}
