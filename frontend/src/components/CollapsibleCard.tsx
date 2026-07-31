import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useAuth } from '../auth/AuthContext'

// A Kitchen-page section that folds, so a page full of lists (recipes, custom
// foods, grocery, and the dinner planner to come) opens compact instead of as
// one long scroll. Open/closed is remembered per user per device. The header
// toggles; an optional action (e.g. "New recipe") sits beside the title as its
// own control, so tapping it doesn't fold the card.
// `flush` is for cards whose content is already .db-row based: the children
// keep the card's full width so the hairlines run edge to edge.
export function CollapsibleCard({
  title,
  summary,
  action,
  storageKey,
  defaultOpen = false,
  flush = false,
  children,
}: {
  title: string
  summary?: string
  action?: ReactNode
  storageKey: string
  defaultOpen?: boolean
  flush?: boolean
  children: ReactNode
}) {
  const { user } = useAuth()
  const key = `db:section:${user?.id ?? 0}:${storageKey}`
  const [open, setOpen] = useState(defaultOpen)

  // Apply the saved preference once we know who's signed in.
  useEffect(() => {
    const saved = localStorage.getItem(key)
    if (saved != null) setOpen(saved === '1')
  }, [key])

  function toggle() {
    setOpen((o) => {
      const next = !o
      localStorage.setItem(key, next ? '1' : '0')
      return next
    })
  }

  return (
    // Closed, the header is the whole card, so it needs its own bottom padding.
    <section className={`glass ${open ? '' : 'pb-2.5'}`}>
      <div className="db-card-h">
        {/* Negative margins keep the header slim while the tap area stays 44px. */}
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          className="-my-2 flex min-h-11 min-w-0 flex-1 items-center gap-2 py-2 text-left"
        >
          <ChevronDown className={`h-3.5 w-3.5 shrink-0 text-fg/40 transition-transform ${open ? '' : '-rotate-90'}`} />
          <h2 className="db-micro truncate">{title}</h2>
          {summary && <span className="db-sum truncate">{summary}</span>}
        </button>
        {action}
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className={flush ? 'db-pad pt-1' : 'px-3.5 pb-3.5 pt-2'}>{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
