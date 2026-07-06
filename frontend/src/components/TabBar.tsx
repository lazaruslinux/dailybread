import { motion } from 'framer-motion'
import { CircleUser, House, ShoppingBasket, Utensils, type LucideIcon } from 'lucide-react'

export type Tab = 'today' | 'food' | 'kitchen' | 'me'

const TABS: { id: Tab; label: string; Icon: LucideIcon }[] = [
  { id: 'today', label: 'Today', Icon: House },
  { id: 'food', label: 'Food', Icon: Utensils },
  { id: 'kitchen', label: 'Kitchen', Icon: ShoppingBasket },
  { id: 'me', label: 'Me', Icon: CircleUser },
]

// Floating bottom navigation. Thumb-reachable, always visible, one tap to
// anywhere. The pb-safe padding keeps it above the iPhone home indicator.
export function TabBar({ active, onChange }: { active: Tab; onChange: (tab: Tab) => void }) {
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-30 pb-[env(safe-area-inset-bottom)]"
    >
      <div className="mx-auto mb-3 flex w-full max-w-md justify-center px-5">
        <div className="glass flex w-full items-stretch justify-around p-1.5">
          {TABS.map(({ id, label, Icon }) => {
            const isActive = id === active
            return (
              <button
                key={id}
                onClick={() => onChange(id)}
                aria-label={label}
                aria-current={isActive ? 'page' : undefined}
                className="relative flex flex-1 flex-col items-center gap-0.5 rounded-xl py-2"
              >
                {isActive && (
                  // One shared highlight that glides between tabs.
                  <motion.span
                    layoutId="tab-highlight"
                    className="absolute inset-0 rounded-xl bg-fg/10"
                    transition={{ type: 'spring', stiffness: 400, damping: 32 }}
                  />
                )}
                <Icon
                  className={`relative h-5 w-5 ${isActive ? 'text-accent-bright' : 'text-fg/45'}`}
                  strokeWidth={2}
                />
                <span
                  className={`relative text-[10px] font-semibold ${
                    isActive ? 'text-fg' : 'text-fg/45'
                  }`}
                >
                  {label}
                </span>
              </button>
            )
          })}
        </div>
      </div>
    </nav>
  )
}
