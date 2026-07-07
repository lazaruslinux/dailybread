import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useAuth } from '../auth/AuthContext'

// A Kitchen-page section that folds, so a page full of lists (recipes, custom
// foods, grocery, and the dinner planner to come) opens compact instead of as
// one long scroll. Open/closed is remembered per user per device. The header
// toggles; an optional action (e.g. "New recipe") sits beside the title as its
// own control, so tapping it doesn't fold the card.
export function CollapsibleCard({
  title,
  summary,
  action,
  storageKey,
  defaultOpen = false,
  children,
}: {
  title: string
  summary?: string
  action?: ReactNode
  storageKey: string
  defaultOpen?: boolean
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
    <section className="glass p-5">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <ChevronDown className={`h-4 w-4 shrink-0 text-fg/40 transition-transform ${open ? '' : '-rotate-90'}`} />
          <h2 className="font-bold">{title}</h2>
          {summary && <span className="truncate text-xs text-fg/45">{summary}</span>}
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
            <div className="pt-4">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
