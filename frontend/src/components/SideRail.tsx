import { useAuth } from '../auth/AuthContext'
import { avatarUrl } from '../lib/api'
import { Avatar } from './Avatar'
import { LoafMark } from './BreadIcon'
import { TABS, type Tab } from './TabBar'

// The persistent left rail: navigation for every viewport where the bottom tab
// bar steps aside — desktop widths, and a landscape phone, where a bottom bar
// would eat a third of the height. One markup takes both shapes and CSS picks:
// labelled with the wordmark on top (>=900px), or a slim column of icons whose
// labels are hidden (landscape phone). Same tab set and same unread dot as the
// bar it replaces, so nothing is reachable on one shape and not the other.
export function SideRail({
  active,
  onChange,
  tabs,
  dot,
}: {
  active: Tab
  onChange: (tab: Tab) => void
  tabs?: Tab[]
  dot?: Tab
}) {
  const { user } = useAuth()
  const visible = tabs ? TABS.filter(({ id }) => tabs.includes(id)) : TABS

  return (
    <nav className="db-rail" aria-label="Main">
      {/* Hidden on the slim shape, where the header keeps the brand instead. */}
      <div className="db-railmark">
        <LoafMark className="h-8 w-8 flex-none text-gold" />
        <span className="font-display text-[19px] font-semibold tracking-[-0.02em]">
          daily
          <span className="bg-gradient-to-r from-accent-bright to-accent-strong bg-clip-text text-transparent">
            bread
          </span>
        </span>
      </div>

      {visible.map(({ id, label, Icon }) => {
        const isActive = id === active
        return (
          <button
            key={id}
            onClick={() => onChange(id)}
            aria-label={label}
            aria-current={isActive ? 'page' : undefined}
            className="db-navitem transition-colors"
          >
            <span className="relative flex-none">
              <Icon
                className={`h-[19px] w-[19px] ${isActive ? 'text-accent-bright' : ''}`}
                strokeWidth={2}
              />
              {dot === id && (
                <span className="absolute -top-0.5 -right-1 h-2 w-2 rounded-full bg-rose-400" />
              )}
            </span>
            <span className="db-navlabel">{label}</span>
          </button>
        )
      })}

      {/* Your face and name in the same visual language as the nav items above,
          so it has to BE a nav item: as a plain div it read as "click me for my
          account" and answered nothing. You is where the account lives, which
          is exactly where it goes. No aria-current here — the You item above
          already carries the one current-page marker. */}
      {user && visible.some(({ id }) => id === 'you') && (
        // aria-label, not the visible text: on the slim landscape rail the
        // label is hidden and the avatar renders alt="", which would leave this
        // a focusable button with no accessible name at all.
        <button
          type="button"
          onClick={() => onChange('you')}
          aria-label={user.display_name}
          className="db-railfoot"
        >
          <Avatar name={user.display_name} src={avatarUrl(user)} size="sm" />
          <span className="db-navlabel truncate">{user.display_name}</span>
        </button>
      )}
    </nav>
  )
}
