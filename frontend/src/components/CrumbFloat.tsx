import { motion } from 'framer-motion'
import { BreadIcon } from './BreadIcon'

// The little "+n" that drifts up when breadcrumbs land — a warm nod, not a
// damage number. Mount it with a fresh key per award inside a relatively
// positioned parent; it rises, fades, and is gone. The amount always comes
// from the server's crumbs_awarded, never a client guess.
export function CrumbFloat({ amount }: { amount: number }) {
  if (amount <= 0) return null
  return (
    <motion.span
      initial={{ opacity: 0, y: 4, scale: 0.9 }}
      animate={{ opacity: [0, 1, 1, 0], y: -26, scale: 1 }}
      transition={{ duration: 1.4, times: [0, 0.15, 0.7, 1], ease: 'easeOut' }}
      className="pointer-events-none absolute -top-2 right-0 z-10 flex items-center gap-0.5 rounded-full border border-gold/40 bg-[var(--bg-base)] px-1.5 py-0.5 text-[11px] font-bold text-gold shadow-sm"
      aria-hidden
    >
      <BreadIcon className="h-3 w-3" strokeWidth={2.5} />
      +{amount}
    </motion.span>
  )
}
