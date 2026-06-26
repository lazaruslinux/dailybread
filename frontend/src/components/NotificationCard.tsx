import { motion } from 'framer-motion'
import { KIND_LABEL, type FeedCard } from '../data/mock'

// One frosted "notification" row. `index` staggers the entrance animation so
// the cards cascade in like iOS notifications.
export function NotificationCard({ card, index }: { card: FeedCard; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay: index * 0.06, type: 'spring', stiffness: 300, damping: 26 }}
      whileTap={{ scale: 0.97 }}
      className="glass flex items-center gap-4 p-4"
    >
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-white/15 text-xl">
        {card.icon}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-white/50">
            {KIND_LABEL[card.kind]}
          </span>
        </div>
        <p className="truncate font-semibold text-white">{card.title}</p>
        <p className="truncate text-sm text-white/60">{card.subtitle}</p>
      </div>

      {card.time && <span className="shrink-0 text-xs font-medium text-white/50">{card.time}</span>}
    </motion.div>
  )
}
