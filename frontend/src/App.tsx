import { AnimatePresence, motion } from 'framer-motion'
import { ChevronLeft } from 'lucide-react'
import { Suspense, lazy, useEffect, useState } from 'react'
import { useAuth } from './auth/AuthContext'
import { useInboxUnread } from './hooks/useInboxUnread'
import { applyTheme, getTheme } from './lib/theme'
import { resyncPushSubscription } from './lib/push'
import { BreadIcon } from './components/BreadIcon'
import { DailyGreeting } from './components/Greeting'
import { HealthBadge } from './components/HealthBadge'
import { TabBar, type Tab } from './components/TabBar'
// Home stays in the main bundle - it's the first paint after login. Every
// other page loads on demand as its own chunk; the service worker precaches
// them all, so a tab's first open reads the chunk from local cache (no
// network wait), and pages nobody visits never cost parse time on a phone.
import { Home } from './pages/Home'

// A deploy can strand a phone mid-session: the page still runs the old index
// while the auto-updating service worker swaps in the new precache, so the
// next unvisited tab asks for a chunk hash that no longer exists anywhere.
// Without this, that failed import unmounts React to a white screen (and a
// home-screen PWA has no reload button). One forced reload fetches the new
// index with a matching chunk set; the session flag stops a reload loop when
// a chunk is missing for some other reason.
const RELOADED_KEY = 'db_chunk_reloaded'
function withReload<T>(load: Promise<T>): Promise<T> {
  return load.then(
    (m) => {
      sessionStorage.removeItem(RELOADED_KEY)
      return m
    },
    (err) => {
      if (!sessionStorage.getItem(RELOADED_KEY)) {
        sessionStorage.setItem(RELOADED_KEY, '1')
        location.reload()
        return new Promise<never>(() => {}) // the page is going away
      }
      throw err
    }
  )
}
const Admin = lazy(() => withReload(import('./pages/Admin').then((m) => ({ default: m.Admin }))))
const Calendar = lazy(() =>
  withReload(import('./pages/Calendar').then((m) => ({ default: m.Calendar })))
)
const CreateFamily = lazy(() =>
  withReload(import('./pages/CreateFamily').then((m) => ({ default: m.CreateFamily })))
)
const ForcedPasswordChange = lazy(() =>
  withReload(import('./pages/Password').then((m) => ({ default: m.ForcedPasswordChange })))
)
const Kitchen = lazy(() =>
  withReload(import('./pages/Kitchen').then((m) => ({ default: m.Kitchen })))
)
const Login = lazy(() => withReload(import('./pages/Login').then((m) => ({ default: m.Login }))))
const Nutrition = lazy(() =>
  withReload(import('./pages/Nutrition').then((m) => ({ default: m.Nutrition })))
)
const Fitness = lazy(() =>
  withReload(import('./pages/Fitness').then((m) => ({ default: m.Fitness })))
)
const Profile = lazy(() =>
  withReload(import('./pages/Profile').then((m) => ({ default: m.Profile })))
)
const Setup = lazy(() => withReload(import('./pages/Setup').then((m) => ({ default: m.Setup }))))
const You = lazy(() => withReload(import('./pages/You').then((m) => ({ default: m.You }))))

// An overlay sits on top of the current tab (a member's profile opened from
// the family strip, or the admin dashboard opened from You). Back returns to
// the tab underneath; switching tabs dismisses it.
type Overlay = { name: 'profile'; id: number } | { name: 'admin' } | { name: 'calendar' } | null

const TAB_TITLE: Record<Tab, string> = {
  home: '', // Home shows the brand row instead of a title
  nutrition: 'Nutrition',
  fitness: 'Health',
  kitchen: 'Kitchen',
  you: 'You',
}

function AppShell() {
  const { user } = useAuth()
  const [tab, setTab] = useState<Tab>('home')
  const [overlay, setOverlay] = useState<Overlay>(null)
  // One poller owns the unread count; the tab-bar dot and the You row badge
  // read the same number, and opening the Inbox zeroes both at once.
  const { count: inboxUnread, zero: zeroInbox } = useInboxUnread()
  // Kid mode: minors get Home / Kitchen / You — no nutrition or fitness area.
  // The server 403s those APIs regardless; this keeps the door out of sight too.
  const isMinor = user?.is_minor ?? false
  const tabs: Tab[] = isMinor
    ? ['home', 'kitchen', 'you']
    : ['home', 'nutrition', 'fitness', 'kitchen', 'you']

  // If the account just became a minor (admin cleared a birthdate mid-session,
  // say), don't leave it stranded on a tab it no longer has.
  useEffect(() => {
    if (isMinor && (tab === 'nutrition' || tab === 'fitness')) setTab('home')
  }, [isMinor, tab])

  // Apply this member's saved theme once we know who they are: the one
  // stored on the account wins (it follows them across devices); the
  // device-local choice is the fallback for accounts that never picked.
  useEffect(() => {
    applyTheme(user?.theme ?? getTheme(user?.id))
  }, [user?.id, user?.theme])

  // Heal a silently-dropped push subscription on app open (never prompts).
  // Adults only: minors get no pushes at all, so there's nothing to re-bind.
  useEffect(() => {
    if (user && !user.is_minor) void resyncPushSubscription()
  }, [user?.id])

  const switchTab = (next: Tab) => {
    setOverlay(null)
    setTab(next)
  }

  // Flex column: the sticky tab bar rides at the end of the flow (mt-auto
  // keeps it at the screen bottom even when a page is short), so content no
  // longer needs bottom padding to clear a fixed bar.
  return (
    <div className="mx-auto flex min-h-svh w-full max-w-md flex-col px-5 pt-8">
      <header className="mb-6">
        {tab === 'home' && !overlay ? (
          // Home wears the brand: loaf + lettering centered, the health badge
          // kept reachable at the row's edge. The greeting lives in Home now.
          <div className="relative flex items-center justify-center py-0.5">
            <span className="flex items-center gap-2 font-display text-xl font-semibold tracking-[-0.02em]">
              <BreadIcon className="h-6 w-6 text-gold" strokeWidth={2.2} />
              <span>
                daily
                <span className="bg-gradient-to-r from-accent-bright to-accent-strong bg-clip-text text-transparent">
                  bread
                </span>
              </span>
            </span>
            <div className="absolute right-0">
              <HealthBadge />
            </div>
          </div>
        ) : (
          <div className="mb-1 flex items-center justify-between gap-3">
            {overlay ? (
              <button
                onClick={() => setOverlay(null)}
                className="-ml-1 flex items-center gap-1 rounded-lg py-1 pr-2 text-sm font-semibold text-fg/60 transition-colors hover:text-fg"
              >
                <ChevronLeft className="h-4 w-4" /> Back
              </button>
            ) : (
              <p className="text-sm font-semibold text-fg/70">{TAB_TITLE[tab]}</p>
            )}
            <HealthBadge />
          </div>
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
          {/* The null fallback is deliberate: chunks come from the service
              worker cache in a few ms, so a spinner would only flash. */}
          <Suspense fallback={null}>
            {overlay?.name === 'profile' && <Profile userId={overlay.id} />}
            {overlay?.name === 'admin' && (
              <Admin onOpenProfile={(id) => setOverlay({ name: 'profile', id })} />
            )}
            {overlay?.name === 'calendar' && <Calendar />}
            {!overlay && tab === 'home' && (
              <Home
                onOpenProfile={(id) => setOverlay({ name: 'profile', id })}
                onOpenKitchen={() => setTab('kitchen')}
                onOpenCalendar={() => setOverlay({ name: 'calendar' })}
              />
            )}
            {!overlay && tab === 'nutrition' && !isMinor && <Nutrition />}
            {!overlay && tab === 'fitness' && !isMinor && <Fitness />}
            {!overlay && tab === 'kitchen' && <Kitchen />}
            {!overlay && tab === 'you' && (
              <You
                onOpenAdmin={() => setOverlay({ name: 'admin' })}
                inboxUnread={inboxUnread}
                onInboxRead={zeroInbox}
                onGoTo={switchTab}
              />
            )}
          </Suspense>
        </motion.div>
      </AnimatePresence>

      <footer className="mt-10 text-center text-xs text-fg/30">dailybread v0.0.1</footer>

      <DailyGreeting />
      <TabBar
        active={tab}
        onChange={switchTab}
        tabs={tabs}
        dot={inboxUnread > 0 ? 'you' : undefined}
      />
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
  // Pre-auth screens are lazy chunks too; nothing to show while one streams
  // in (a few ms from cache), so the fallback stays blank like the splash.
  if (screen === 'setup')
    return (
      <Suspense fallback={null}>
        <Setup />
      </Suspense>
    )
  if (screen === 'login')
    return (
      <Suspense fallback={null}>
        <Login />
      </Suspense>
    )
  if (screen === 'change-password')
    return (
      <Suspense fallback={null}>
        <ForcedPasswordChange />
      </Suspense>
    )
  if (screen === 'create-family')
    return (
      <Suspense fallback={null}>
        <CreateFamily />
      </Suspense>
    )
  return <AppShell />
}

export default App
