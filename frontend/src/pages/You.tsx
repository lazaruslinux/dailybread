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
import { useEffect, useState } from 'react'
import * as api from '../lib/api'
import { updateMyProfile } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { JournalCard } from '../components/JournalCard'
import { NotificationsCard } from '../components/Notifications'
import { VillagesCard } from '../components/Villages'
import { getTheme, setTheme, THEMES, type Theme } from '../lib/theme'
import { BreadIcon } from '../components/BreadIcon'
import { HealthSettings } from '../components/Health'
import { WelcomeTour } from '../components/WelcomeTour'
import { ChangePasswordSheet } from './Password'
import { BreadcrumbsPage } from './Breadcrumbs'
import { InboxPage } from './Inbox'
import { Profile } from './Profile'

// Little preview swatch per theme so the choice reads at a glance.
const SWATCH: Record<Theme, string> = {
  light: 'bg-[linear-gradient(135deg,#f7f4ee,#b45309)]',
  dark: 'bg-[linear-gradient(135deg,#eab04e,#0b0906)]',
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
    <div className="glass p-4">
      <span className="mb-3 block text-xs font-semibold uppercase tracking-wide text-fg/50">
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
    <div className="glass p-4">
      <span className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-fg/50">
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
      className="glass flex items-center gap-3 p-4 text-left transition-colors hover:bg-fg/5"
    >
      <Icon className={`h-4 w-4 shrink-0 ${iconClass}`} />
      <span className="min-w-0 flex-1">
        <span className="block font-semibold text-fg/80">{SUB_META[page].label}</span>
        <span className="block truncate text-xs text-fg/40">{SUB_META[page].hint}</span>
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

// The You tab: your own profile (bio + mood) and daily journal up top, then
// the settings list. Admin entry lives here too.
export function You({
  onOpenAdmin,
  inboxUnread = 0,
  onInboxRead,
}: {
  onOpenAdmin: () => void
  inboxUnread?: number
  onInboxRead?: () => void
}) {
  const { user, logout } = useAuth()
  const [changingPassword, setChangingPassword] = useState(false)
  const [sub, setSub] = useState<SubPage | null>(null)
  const [touring, setTouring] = useState(false)
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
      <div className="flex flex-col gap-4">
        <button
          onClick={() => setSub(null)}
          className="flex items-center gap-1 self-start rounded-lg py-1 pr-2 text-sm font-semibold text-fg/60 transition-colors hover:text-fg"
        >
          <ChevronLeft className="h-4 w-4" /> You
        </button>
        <h2 className="-mt-2 text-xl font-bold tracking-tight">{SUB_META[sub].label}</h2>
        {sub === 'inbox' && <InboxPage onAllRead={onInboxRead} />}
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
    <div className="flex flex-col gap-4">
      <Profile userId={user.id} onOpenCrumbs={() => setSub('crumbs')} />

      <JournalCard />

      <div className="flex flex-col gap-2">
        <SettingsRow Icon={Inbox} page="inbox" onOpen={setSub} badge={inboxUnread} />
        <SettingsRow Icon={BreadIcon as unknown as LucideIcon} page="crumbs" onOpen={setSub} />
        {/* Minors get no notifications (the server sends them none, so the
            page would be empty), no health area, and no village roster; the
            API 403s the latter two anyway. */}
        {!user.is_minor && <SettingsRow Icon={Bell} page="notifications" onOpen={setSub} />}
        <SettingsRow Icon={Palette} page="appearance" onOpen={setSub} />
        {!user.is_minor && (
          <SettingsRow Icon={HeartPulse} page="health" onOpen={setSub} iconClass="text-red-400" />
        )}
        <SettingsRow Icon={BookOpen} page="verses" onOpen={setSub} />
        {!user.is_minor && <SettingsRow Icon={Trees} page="villages" onOpen={setSub} />}
      </div>

      <div className="flex flex-col gap-2">
        {user.is_admin && (
          <button
            onClick={onOpenAdmin}
            className="glass flex items-center gap-3 p-4 text-left font-semibold text-fg/80 transition-colors hover:text-fg"
          >
            <Users className="h-4 w-4 text-fg/55" /> Family members
          </button>
        )}
        <button
          onClick={() => setTouring(true)}
          className="glass flex items-center gap-3 p-4 text-left font-semibold text-fg/80 transition-colors hover:text-fg"
        >
          <Map className="h-4 w-4 text-fg/55" /> Repeat welcome tutorial
        </button>
        <button
          onClick={() => setChangingPassword(true)}
          className="glass flex items-center gap-3 p-4 text-left font-semibold text-fg/80 transition-colors hover:text-fg"
        >
          <KeyRound className="h-4 w-4 text-fg/55" /> Change password
        </button>
        <button
          onClick={logout}
          className="glass flex items-center gap-3 p-4 text-left font-semibold text-fg/80 transition-colors hover:text-fg"
        >
          <LogOut className="text-danger h-4 w-4" /> Sign out
        </button>
      </div>

      <AnimatePresence>
        {changingPassword && <ChangePasswordSheet onClose={() => setChangingPassword(false)} />}
      </AnimatePresence>
    </div>
  )
}
