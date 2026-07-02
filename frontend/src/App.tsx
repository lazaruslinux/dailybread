import { AnimatePresence, motion } from 'framer-motion'
import { ChevronLeft, LogOut, Users } from 'lucide-react'
import { useState } from 'react'
import { useAuth } from './auth/AuthContext'
import { HealthBadge } from './components/HealthBadge'
import { Admin } from './pages/Admin'
import { Home } from './pages/Home'
import { Login } from './pages/Login'
import { Profile } from './pages/Profile'
import { Setup } from './pages/Setup'

function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

function todayLabel(): string {
  return new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

type View = { name: 'home' } | { name: 'admin' } | { name: 'profile'; id: number }

function AppShell() {
  const { user, logout } = useAuth()
  const [view, setView] = useState<View>({ name: 'home' })
  const firstName = user?.display_name.split(/\s+/)[0] ?? ''
  const atHome = view.name === 'home'

  return (
    <div className="mx-auto min-h-svh w-full max-w-md px-5 py-8">
      <header className="mb-6">
        {/* Top row: date / back button on the left, controls on the right.
            The greeting gets its own full-width line below so long names
            never fight the buttons for space. */}
        <div className="mb-1 flex items-center justify-between gap-3">
          {atHome ? (
            <p className="text-sm text-white/50">{todayLabel()}</p>
          ) : (
            <button
              onClick={() => setView({ name: 'home' })}
              className="-ml-1 flex items-center gap-1 rounded-lg py-1 pr-2 text-sm font-semibold text-white/60 transition-colors hover:text-white"
            >
              <ChevronLeft className="h-4 w-4" /> Home
            </button>
          )}

          <div className="flex shrink-0 items-center gap-2">
            <HealthBadge />
            {user?.is_admin && (
              <button
                onClick={() => setView(view.name === 'admin' ? { name: 'home' } : { name: 'admin' })}
                aria-label="Admin dashboard"
                className={`glass rounded-full p-2 transition-colors ${
                  view.name === 'admin' ? 'text-indigo-300' : 'text-white/60 hover:text-white'
                }`}
              >
                <Users className="h-4 w-4" />
              </button>
            )}
            <button
              onClick={logout}
              aria-label="Sign out"
              className="glass rounded-full p-2 text-white/60 transition-colors hover:text-white"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>

        {atHome && (
          <h1 className="text-3xl font-bold tracking-tight">
            {greeting()}, {firstName}
          </h1>
        )}
      </header>

      <AnimatePresence mode="wait">
        <motion.div
          key={view.name === 'profile' ? `profile-${view.id}` : view.name}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.18 }}
        >
          {view.name === 'home' && (
            <Home onOpenProfile={(id) => setView({ name: 'profile', id })} />
          )}
          {view.name === 'admin' && <Admin />}
          {view.name === 'profile' && <Profile userId={view.id} />}
        </motion.div>
      </AnimatePresence>

      <footer className="mt-10 text-center text-xs text-white/30">dailybread v0.0.1</footer>
    </div>
  )
}

function App() {
  const { screen } = useAuth()

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
  return <AppShell />
}

export default App
