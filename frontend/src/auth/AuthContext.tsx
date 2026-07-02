import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import * as api from '../lib/api'

// One place owns "who is logged in". Everything else reads it via useAuth().
//
// screen decides what the app shows:
//   'loading' -> splash while we ask the backend who we are
//   'setup'   -> brand-new install, show the create-admin wizard
//   'login'   -> no session, show the sign-in form
//   'app'     -> signed in, show the real app

type Screen = 'loading' | 'setup' | 'login' | 'app'

interface AuthState {
  screen: Screen
  user: api.User | null
  login: (username: string, password: string) => Promise<void>
  bootstrap: (username: string, displayName: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [screen, setScreen] = useState<Screen>('loading')
  const [user, setUser] = useState<api.User | null>(null)

  // On page load, try to restore the session from the cookie. A 401 means
  // "nobody is signed in", and then one more question (is the install set up
  // yet?) decides between the login form and the first-run wizard.
  useEffect(() => {
    let active = true
    ;(async () => {
      try {
        const me = await api.getMe()
        if (!active) return
        setUser(me)
        setScreen('app')
      } catch {
        try {
          const { initialized } = await api.getSetup()
          if (!active) return
          setScreen(initialized ? 'login' : 'setup')
        } catch {
          // Backend unreachable; show login rather than a dead end. The form
          // will surface the real error when they try to sign in.
          if (active) setScreen('login')
        }
      }
    })()
    return () => {
      active = false
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const me = await api.login(username, password)
    setUser(me)
    setScreen('app')
  }, [])

  const bootstrap = useCallback(
    async (username: string, displayName: string, password: string) => {
      const me = await api.bootstrap(username, displayName, password)
      setUser(me)
      setScreen('app')
    },
    [],
  )

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      // Even if the request failed, drop local state so the UI locks.
      setUser(null)
      setScreen('login')
    }
  }, [])

  return (
    <AuthContext.Provider value={{ screen, user, login, bootstrap, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
