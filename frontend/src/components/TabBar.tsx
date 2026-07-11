import { motion } from 'framer-motion'
import { CircleUser, HeartPulse, House, ShoppingBasket, Utensils, type LucideIcon } from 'lucide-react'

export type Tab = 'home' | 'nutrition' | 'fitness' | 'kitchen' | 'you'

// Kitchen rides beside Home (his flow: the kitchen sits next to the living
// room); Fitness keeps the center seat.
const TABS: { id: Tab; label: string; Icon: LucideIcon }[] = [
  { id: 'home', label: 'Home', Icon: House },
  { id: 'kitchen', label: 'Kitchen', Icon: ShoppingBasket },
  { id: 'fitness', label: 'Fitness', Icon: HeartPulse },
  { id: 'nutrition', label: 'Nutrition', Icon: Utensils },
  { id: 'you', label: 'You', Icon: CircleUser },
]

// Floating bottom navigation. Thumb-reachable, always visible, one tap to
// anywhere. The pb-safe padding keeps it above the iPhone home indicator.
// `tabs` narrows the set for accounts that don't get every area (kid mode).
export function TabBar({
  active,
  onChange,
  tabs,
}: {
  active: Tab
  onChange: (tab: Tab) => void
  tabs?: Tab[]
}) {
  const visible = tabs ? TABS.filter(({ id }) => tabs.includes(id)) : TABS
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-30 pb-[env(safe-area-inset-bottom)]"
    >
      <div className="mx-auto mb-3 flex w-full max-w-md justify-center px-5">
        <div className="glass flex w-full items-stretch justify-around p-1.5">
          {visible.map(({ id, label, Icon }) => {
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
