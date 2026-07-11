import { AnimatePresence } from 'framer-motion'
import { BookOpen, KeyRound, LogOut, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import * as api from '../lib/api'
import { updateMyProfile } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { JournalCard } from '../components/JournalCard'
import { NotificationsCard } from '../components/Notifications'
import { VillagesCard } from '../components/Villages'
import { getTheme, setTheme, THEMES, type Theme } from '../lib/theme'
import { ChangePasswordSheet } from './Password'
import { Profile } from './Profile'

// Little preview swatch per theme so the choice reads at a glance.
const SWATCH: Record<Theme, string> = {
  light: 'bg-[linear-gradient(135deg,#f7f4ee,#b45309)]',
  dark: 'bg-[linear-gradient(135deg,#3bb977,#08090a)]',
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
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold text-fg/90">{t.label}</span>
              <span className="block truncate text-[11px] text-fg/45">{t.hint}</span>
            </span>
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

// Daily verse check-offs: enable the reading streak, and optionally show the
// streak number (never the reading history) to village members.
function VersePrefsCard() {
  const [verses, setVerses] = useState<api.Verses | null>(null)

  useEffect(() => {
    api.getVerses().then(setVerses).catch(() => {})
  }, [])

  async function save(patch: { enabled?: boolean; share?: boolean }) {
    try {
      setVerses(await api.setVerseSettings(patch))
    } catch {
      // The switch stays put; the next tap tries again.
    }
  }

  if (!verses) return null
  return (
    <div className="glass p-4">
      <span className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-fg/50">
        <BookOpen className="h-3.5 w-3.5 text-gold/80" /> Daily verses
      </span>
      <p className="mb-3 text-sm text-fg/55">
        Check off the day's three verses as you read them and build a streak. The little book
        by your avatar shows the family how many days you've kept it going.
      </p>
      <div className="flex flex-col gap-2">
        <PrefSwitch
          label="Check off daily verses"
          checked={verses.enabled}
          onToggle={() => void save({ enabled: !verses.enabled })}
        />
        {verses.enabled && (
          <PrefSwitch
            label="Show my streak to villages"
            checked={verses.share}
            onToggle={() => void save({ share: !verses.share })}
          />
        )}
      </div>
    </div>
  )
}

// The You tab: your own profile (bio + mood) plus account-level actions that
// used to crowd the header. Admin entry lives here now.
export function You({ onOpenAdmin }: { onOpenAdmin: () => void }) {
  const { user, logout } = useAuth()
  const [changingPassword, setChangingPassword] = useState(false)
  if (!user) return null

  return (
    <div className="flex flex-col gap-4">
      <Profile userId={user.id} />

      <JournalCard />

      <ThemePicker userId={user.id} stored={user.theme} />

      <VersePrefsCard />

      <NotificationsCard />

      <VillagesCard />

      <div className="flex flex-col gap-2">
        <button
          onClick={() => setChangingPassword(true)}
          className="glass flex items-center gap-3 p-4 text-left font-semibold text-fg/80 transition-colors hover:text-fg"
        >
          <KeyRound className="h-4 w-4 text-fg/55" /> Change password
        </button>
        {user.is_admin && (
          <button
            onClick={onOpenAdmin}
            className="glass flex items-center gap-3 p-4 text-left font-semibold text-fg/80 transition-colors hover:text-fg"
          >
            <Users className="h-4 w-4 text-fg/55" /> Family members
          </button>
        )}
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

      {/* Thomas Nelson's gratis quotation policy requires this notice in any
          work that quotes the NKJV (the daily verse card). */}
      <p className="px-3 pt-1 text-center text-[10px] leading-relaxed text-fg/30">
        Scripture taken from the New King James Version&reg;. Copyright &copy; 1982 by Thomas
        Nelson. Used by permission. All rights reserved.
      </p>
    </div>
  )
}
