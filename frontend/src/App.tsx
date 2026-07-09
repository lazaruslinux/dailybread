import { AnimatePresence, motion } from 'framer-motion'
import { CalendarDays, ChevronLeft } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useAuth } from './auth/AuthContext'
import { applyTheme, getTheme } from './lib/theme'
import { timeGreeting } from './lib/moods'
import { DailyGreeting } from './components/Greeting'
import { HealthBadge } from './components/HealthBadge'
import { TabBar, type Tab } from './components/TabBar'
import { Admin } from './pages/Admin'
import { Calendar } from './pages/Calendar'
import { CreateFamily } from './pages/CreateFamily'
import { ForcedPasswordChange } from './pages/Password'
import { Home } from './pages/Home'
import { Kitchen } from './pages/Kitchen'
import { Login } from './pages/Login'
import { Nutrition } from './pages/Nutrition'
import { Profile } from './pages/Profile'
import { Setup } from './pages/Setup'
import { You } from './pages/You'

function todayLabel(): string {
  return new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

// An overlay sits on top of the current tab (a member's profile opened from
// the family strip, or the admin dashboard opened from You). Back returns to
// the tab underneath; switching tabs dismisses it.
type Overlay = { name: 'profile'; id: number } | { name: 'admin' } | { name: 'calendar' } | null

const TAB_TITLE: Record<Tab, string> = {
  home: '', // Home shows the date + greeting instead of a title
  nutrition: 'Nutrition',
  kitchen: 'Kitchen',
  you: 'You',
}

function AppShell() {
  const { user } = useAuth()
  const [tab, setTab] = useState<Tab>('home')
  const [overlay, setOverlay] = useState<Overlay>(null)
  const firstName = user?.display_name.split(/\s+/)[0] ?? ''

  // Kid mode: minors get Home / Kitchen / You — no nutrition area. The server
  // 403s those APIs regardless; this keeps the door out of sight too.
  const isMinor = user?.is_minor ?? false
  const tabs: Tab[] = isMinor ? ['home', 'kitchen', 'you'] : ['home', 'nutrition', 'kitchen', 'you']

  // If the account just became a minor (admin cleared a birthdate mid-session,
  // say), don't leave it stranded on a tab it no longer has.
  useEffect(() => {
    if (isMinor && tab === 'nutrition') setTab('home')
  }, [isMinor, tab])

  // Apply this member's saved theme once we know who they are: the one
  // stored on the account wins (it follows them across devices); the
  // device-local choice is the fallback for accounts that never picked.
  useEffect(() => {
    applyTheme(user?.theme ?? getTheme(user?.id))
  }, [user?.id, user?.theme])

  const switchTab = (next: Tab) => {
    setOverlay(null)
    setTab(next)
  }

  // pb-28 clears the floating tab bar so the last card is never buried.
  return (
    <div className="mx-auto min-h-svh w-full max-w-md px-5 pb-28 pt-8">
      <header className="mb-6">
        <div className="mb-1 flex items-center justify-between gap-3">
          {overlay ? (
            <button
              onClick={() => setOverlay(null)}
              className="-ml-1 flex items-center gap-1 rounded-lg py-1 pr-2 text-sm font-semibold text-fg/60 transition-colors hover:text-fg"
            >
              <ChevronLeft className="h-4 w-4" /> Back
            </button>
          ) : tab === 'home' ? (
            <p className="text-sm text-fg/50">{todayLabel()}</p>
          ) : (
            <p className="text-sm font-semibold text-fg/70">{TAB_TITLE[tab]}</p>
          )}
          <div className="flex items-center gap-2">
            <HealthBadge />
            {tab === 'home' && !overlay && (
              <button
                onClick={() => setOverlay({ name: 'calendar' })}
                aria-label="View calendar"
                className="flex items-center gap-1.5 rounded-full border border-accent-bright/40 bg-accent-bright/15 px-3 py-1.5 text-sm font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
              >
                <CalendarDays className="h-4 w-4" strokeWidth={2.5} /> Calendar
              </button>
            )}
          </div>
        </div>

        {tab === 'home' && !overlay && (
          <h1 className="font-display text-[2.05rem] font-semibold leading-[1.1] tracking-[-0.02em]">
            {timeGreeting()}, {firstName}
          </h1>
        )}
      </header>

      <AnimatePresence mode="wait">
        <motion.div
          key={overlay ? `${overlay.name}-${'id' in overlay ? overlay.id : ''}` : tab}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.18 }}
        >
          {overlay?.name === 'profile' && <Profile userId={overlay.id} />}
          {overlay?.name === 'admin' && <Admin />}
          {overlay?.name === 'calendar' && <Calendar />}
          {!overlay && tab === 'home' && (
            <Home onOpenProfile={(id) => setOverlay({ name: 'profile', id })} onOpenKitchen={() => setTab('kitchen')} />
          )}
          {!overlay && tab === 'nutrition' && !isMinor && <Nutrition />}
          {!overlay && tab === 'kitchen' && <Kitchen />}
          {!overlay && tab === 'you' && <You onOpenAdmin={() => setOverlay({ name: 'admin' })} />}
        </motion.div>
      </AnimatePresence>

      <footer className="mt-10 text-center text-xs text-fg/30">dailybread v0.0.1</footer>

      <DailyGreeting />
      <TabBar active={tab} onChange={switchTab} tabs={tabs} />
    </div>
  )
}

function App() {
  const { screen } = useAuth()

  // Pre-auth screens (setup, login, wizards) default to dark — nobody is
  // signed in yet, so there's no saved preference to honor. AppShell's own
  // effect swaps in the member's real theme the moment they're in.
  useEffect(() => {
    if (screen !== 'app') applyTheme('dark')
  }, [screen])

  if (screen === 'loading') {
    // Splash while /auth/me resolves; keeps the login form from flashing for
    // users who are already signed in.
    return (
      <div className="flex min-h-svh items-center justify-center">
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.5 }}
          className="text-lg font-semibold tracking-tight"
        >
          dailybread
        </motion.p>
      </div>
    )
  }
  if (screen === 'setup') return <Setup />
  if (screen === 'login') return <Login />
  if (screen === 'change-password') return <ForcedPasswordChange />
  if (screen === 'create-family') return <CreateFamily />
  return <AppShell />
}

export default App
