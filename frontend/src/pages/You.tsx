import { AnimatePresence } from 'framer-motion'
import {
  Bell,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  HeartPulse,
  Inbox,
  KeyRound,
  LogOut,
  Map,
  Palette,
  Trees,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import * as api from '../lib/api'
import { updateMyProfile } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { JournalCard } from '../components/JournalCard'
import { NotificationsCard } from '../components/Notifications'
import { VillagesCard } from '../components/Villages'
import { getTheme, setTheme, THEMES, type Theme } from '../lib/theme'
import { Coin } from '../components/BreadIcon'
import { HealthSettings } from '../components/Health'
import { WelcomeTour } from '../components/WelcomeTour'
import { ChangePasswordSheet } from './Password'
import { BreadcrumbsPage } from './Breadcrumbs'
import { InboxPage, inboxDestination } from './Inbox'
import { Profile } from './Profile'

// Little preview swatch per theme so the choice reads at a glance.
const SWATCH: Record<Theme, string> = {
  light: 'bg-[linear-gradient(135deg,#f4f1ea,#b45309)]',
  dark: 'bg-[linear-gradient(135deg,#eab04e,#0f0c08)]',
}

function ThemePicker({ userId, stored }: { userId: number; stored: Theme | null }) {
  // The account's stored choice wins (it followed them here); the device's
  // localStorage is the fallback for accounts that never picked one.
  const [theme, setThemeState] = useState<Theme>(() => stored ?? getTheme(userId))
  function pick(t: Theme) {
    setThemeState(t)
    setTheme(userId, t)
    // Also stored on the account, so the choice follows this member onto any
    // device at their next sign-in. Fire-and-forget: the local switch already
    // happened, and a failed save just means device-only for now.
    updateMyProfile({ theme: t }).catch(() => {})
  }
  return (
    <div className="glass p-3.5">
      <span className="db-micro mb-3 block">
        Appearance
      </span>
      <div className="grid grid-cols-2 gap-2">
        {THEMES.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => pick(t.id)}
            aria-pressed={theme === t.id}
            className={`flex items-center gap-2.5 rounded-xl border p-2.5 text-left transition-colors ${
              theme === t.id
                ? 'border-accent-bright/60 bg-accent-bright/15'
                : 'border-fg/10 bg-fg/5 hover:bg-fg/10'
            }`}
          >
            <span className={`h-8 w-8 shrink-0 rounded-full border border-fg/15 ${SWATCH[t.id]}`} />
            <span className="min-w-0 truncate text-sm font-semibold text-fg/90">{t.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

// One switch row, ItemSheet-style, for the preference cards below.
function PrefSwitch({
  label,
  checked,
  onToggle,
}: {
  label: string
  checked: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onToggle}
      className="flex w-full items-center justify-between gap-3 rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left"
    >
      <span className="text-sm font-semibold text-fg/85">{label}</span>
      <span className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${checked ? 'bg-accent' : 'bg-fg/15'}`}>
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-fg transition-all ${checked ? 'left-[1.125rem]' : 'left-0.5'}`} />
      </span>
    </button>
  )
}

// The daily-verses opt-in: receiving the day's three verses at all, with the
// check-offs and reading streak as part of the package. Off by default for
// new accounts, so this card doubles as the gentle nudge to try it. Village
// sharing lives with the other village toggles, under Villages.
function VersePrefsCard() {
  const [verses, setVerses] = useState<api.Verses | null>(null)

  useEffect(() => {
    api.getVerses().then(setVerses).catch(() => {})
  }, [])

  async function save(enabled: boolean) {
    try {
      setVerses(await api.setVerseSettings({ enabled }))
    } catch {
      // The switch stays put; the next tap tries again.
    }
  }

  if (!verses) return null
  return (
    <div className="glass p-3.5">
      <span className="db-micro mb-1 flex items-center gap-1.5">
        <BookOpen className="h-3.5 w-3.5 text-gold/80" /> Daily Bread
      </span>
      <p className="mb-3 text-sm text-fg/55">
        Three comforting verses from scripture waiting quietly at the bottom of your schedule
        to read each day. Every family gets a different 3 each day, and reading streaks earn
        breadcrumbs.
      </p>
      <PrefSwitch
        label="Opt-in to daily Bible verses"
        checked={verses.enabled}
        onToggle={() => void save(!verses.enabled)}
      />
      {/* Thomas Nelson's gratis quotation policy requires this notice in any
          work that quotes the NKJV (the daily verse card). */}
      <p className="mt-4 text-center text-[10px] leading-relaxed text-fg/30">
        Scripture taken from the New King James Version&reg;. Copyright &copy; 1982 by Thomas
        Nelson. Used by permission. All rights reserved.
      </p>
    </div>
  )
}

// The settings that moved one level down: set-and-forget things open as
// subpages, so the daily ritual (profile, mood, status, journal) stays one
// scroll at the top level.
type SubPage = 'inbox' | 'crumbs' | 'notifications' | 'appearance' | 'health' | 'verses' | 'villages'

const SUB_META: Record<SubPage, { label: string; hint: string }> = {
  inbox: { label: 'Inbox', hint: 'Crumbs you earned and family activity' },
  crumbs: { label: 'Breadcrumbs & Levels', hint: 'How the family earns and levels up' },
  notifications: { label: 'Notifications', hint: 'What rings this device' },
  appearance: { label: 'Appearance', hint: 'Light and dark' },
  health: { label: 'Health profile', hint: 'Your body, calorie plan, and weigh-ins' },
  verses: { label: 'Daily Bread', hint: 'Manage daily scripture settings' },
  villages: { label: 'Villages', hint: 'Linked families and what they see' },
}

function SettingsRow({
  Icon,
  page,
  onOpen,
  iconClass = 'text-fg/55',
  badge = 0,
}: {
  Icon: LucideIcon
  page: SubPage
  onOpen: (page: SubPage) => void
  iconClass?: string
  badge?: number
}) {
  return (
    <button
      onClick={() => onOpen(page)}
      className="db-setrow transition-colors hover:bg-fg/5"
    >
      <Icon className={`h-[19px] w-[19px] shrink-0 ${iconClass}`} />
      <span className="min-w-0 flex-1">
        <span className="block text-fg/80">{SUB_META[page].label}</span>
        <span className="block truncate text-xs font-medium text-fg/40">{SUB_META[page].hint}</span>
      </span>
      {badge > 0 && (
        // Solid, not the tinted-chip pattern: the count must read at a glance
        // on both themes, and rose-on-rose washes out in light mode.
        <span className="shrink-0 rounded-full bg-rose-500/90 px-2 py-0.5 text-xs font-bold text-white">
          {badge}
        </span>
      )}
      <ChevronRight className="h-4 w-4 shrink-0 text-fg/30" />
    </button>
  )
}

// One of the plain action rows that close the You page. Same 52px rhythm as
// SettingsRow, no hint line and no destination page behind it.
function ActionRow({
  Icon,
  iconClass = 'text-fg/55',
  onClick,
  children,
}: {
  Icon: LucideIcon
  iconClass?: string
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button onClick={onClick} className="db-setrow text-fg/80 transition-colors hover:bg-fg/5">
      <Icon className={`h-[19px] w-[19px] shrink-0 ${iconClass}`} />
      {children}
    </button>
  )
}

// The You tab: your own profile (bio + mood) and daily journal up top, then
// the settings list. Admin entry lives here too.
export function You({
  onOpenAdmin,
  inboxUnread = 0,
  onInboxRead,
  onGoTo,
  reselect = 0,
}: {
  onOpenAdmin: () => void
  inboxUnread?: number
  onInboxRead?: () => void
  // Inbox rows navigate: board/village news to Home, workouts to Health,
  // groceries/recipes/dinner to the Kitchen.
  onGoTo?: (tab: 'home' | 'fitness' | 'kitchen') => void
  // Bumps each time the You tab is tapped while already active; a change means
  // "return to the root", so we close any open subpage (scroll restores).
  reselect?: number
}) {
  const { user, logout } = useAuth()
  const [changingPassword, setChangingPassword] = useState(false)
  const [sub, setSub] = useState<SubPage | null>(null)
  const [touring, setTouring] = useState(false)
  // The window is the only scroller, so opening a subpage would otherwise
  // inherit the list's scroll position. Remember where the list was, open the
  // subpage at the top, and restore the list's position on the way back.
  const savedScroll = useRef<number | null>(null)

  function openSub(page: SubPage) {
    savedScroll.current = window.scrollY
    setSub(page)
    window.scrollTo(0, 0)
  }

  function closeSub() {
    setSub(null)
  }

  useLayoutEffect(() => {
    // Only the transition back to the list restores; a fresh open leaves the
    // ref null, and a sub-to-sub jump keeps the list position for later.
    if (sub === null && savedScroll.current !== null) {
      window.scrollTo(0, savedScroll.current)
      savedScroll.current = null
    }
  }, [sub])

  // Tapping the active You tab (reselect bumps) returns to the root. Skip the
  // initial mount so a first render never force-closes a subpage that an Inbox
  // deep-link may have just opened.
  const firstReselect = useRef(true)
  useEffect(() => {
    if (firstReselect.current) {
      firstReselect.current = false
      return
    }
    closeSub()
  }, [reselect])

  if (!user) return null

  if (touring) {
    // Fixed overlay: the replay button sits low on the page, so an inline
    // render would open the tour below the fold. This centers it in the
    // viewport wherever you were scrolled.
    return (
      <div className="fixed inset-0 z-40 overflow-y-auto bg-[var(--bg-base)]">
        <WelcomeTour
          firstName={user.display_name.split(/\s+/)[0]}
          context="replay"
          onDone={() => setTouring(false)}
        />
      </div>
    )
  }

  if (sub !== null) {
    return (
      <div className="flex flex-col gap-3">
        <button
          onClick={closeSub}
          className="-my-2 -ml-2.5 flex min-h-11 items-center gap-1 self-start rounded-lg pl-2.5 pr-3 text-base font-semibold text-fg/60 transition-colors hover:text-fg"
        >
          <ChevronLeft className="h-5 w-5" /> You
        </button>
        <h2 className="-mt-1.5 text-lg font-bold tracking-tight">{SUB_META[sub].label}</h2>
        {sub === 'inbox' && (
          <InboxPage
            onAllRead={onInboxRead}
            onGo={(kind) => {
              const dest = inboxDestination(kind)
              if (dest === 'crumbs') setSub('crumbs')
              else onGoTo?.(dest)
            }}
          />
        )}
        {sub === 'crumbs' && <BreadcrumbsPage />}
        {sub === 'notifications' && <NotificationsCard />}
        {sub === 'appearance' && <ThemePicker userId={user.id} stored={user.theme} />}
        {sub === 'health' && <HealthSettings />}
        {sub === 'verses' && <VersePrefsCard />}
        {sub === 'villages' && <VillagesCard />}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <Profile userId={user.id} onOpenCrumbs={() => openSub('crumbs')} />

      <JournalCard />

      {/* One card per group of rows, not a card per row: the settings list
          reads as a list. */}
      <div className="glass db-pad overflow-hidden">
        <SettingsRow Icon={Inbox} page="inbox" onOpen={openSub} badge={inboxUnread} />
        <SettingsRow Icon={Coin as unknown as LucideIcon} page="crumbs" onOpen={openSub} />
        {/* Minors get no notifications (the server sends them none, so the
            page would be empty), no health area, and no village roster; the
            API 403s the latter two anyway. */}
        {!user.is_minor && <SettingsRow Icon={Bell} page="notifications" onOpen={openSub} />}
        <SettingsRow Icon={Palette} page="appearance" onOpen={openSub} />
        {!user.is_minor && (
          <SettingsRow Icon={HeartPulse} page="health" onOpen={openSub} iconClass="text-red-400" />
        )}
        <SettingsRow Icon={BookOpen} page="verses" onOpen={openSub} />
        {!user.is_minor && <SettingsRow Icon={Trees} page="villages" onOpen={openSub} />}
      </div>

      <div className="glass db-pad overflow-hidden">
        {user.is_admin && (
          <ActionRow Icon={Users} onClick={onOpenAdmin}>
            Family members
          </ActionRow>
        )}
        <ActionRow Icon={Map} onClick={() => setTouring(true)}>
          Repeat welcome tutorial
        </ActionRow>
        <ActionRow Icon={KeyRound} onClick={() => setChangingPassword(true)}>
          Change password
        </ActionRow>
        <ActionRow Icon={LogOut} iconClass="text-danger" onClick={logout}>
          Sign out
        </ActionRow>
      </div>

      <AnimatePresence>
        {changingPassword && <ChangePasswordSheet onClose={() => setChangingPassword(false)} />}
      </AnimatePresence>
    </div>
  )
}
