import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import * as api from '../lib/api'

// One place owns "who is logged in". Everything else reads it via useAuth().
//
// screen decides what the app shows:
//   'loading'       -> splash while we ask the backend who we are
//   'setup'         -> brand-new install, show the create-admin wizard
//   'login'         -> no session, show the sign-in form
//   'create-family' -> signed in but no family yet (a fresh new-household
//                      account): show the create-your-family wizard
//   'change-password' -> signed in with a password an admin generated: they
//                      must pick their own before anything else
//   'app'           -> signed in and in a family, show the real app

type Screen = 'loading' | 'setup' | 'login' | 'create-family' | 'change-password' | 'app'

// A signed-in user lands on the app if they have a family, or on the
// create-family wizard if they are a fresh new-household account. A pending
// forced password change trumps both (the backend refuses all else anyway).
const screenForUser = (user: api.User): Screen =>
  user.must_change_password
    ? 'change-password'
    : user.family_id === null
      ? 'create-family'
      : 'app'

interface AuthState {
  screen: Screen
  user: api.User | null
  login: (username: string, password: string) => Promise<void>
  bootstrap: (username: string, displayName: string, password: string) => Promise<void>
  createFamily: (name: string) => Promise<void>
  changePassword: (current: string, next: string) => Promise<void>
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
        setScreen(screenForUser(me))
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
    setScreen(screenForUser(me))
  }, [])

  const bootstrap = useCallback(
    async (username: string, displayName: string, password: string) => {
      const me = await api.bootstrap(username, displayName, password)
      setUser(me)
      setScreen(screenForUser(me))
    },
    [],
  )

  // A fresh new-household account names its family; the backend promotes them
  // to parent + admin of it. Re-fetch so we pick up the new family_id/role.
  const createFamily = useCallback(async (name: string) => {
    await api.createFamily(name)
    const me = await api.getMe()
    setUser(me)
    setScreen(screenForUser(me))
  }, [])

  // Used by the Preferences sheet and by the forced-change screen after an
  // admin reset; the backend re-issues this session's cookie, so no re-login.
  const changePassword = useCallback(async (current: string, next: string) => {
    const me = await api.changePassword(current, next)
    setUser(me)
    setScreen(screenForUser(me))
  }, [])

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
    <AuthContext.Provider
      value={{ screen, user, login, bootstrap, createFamily, changePassword, logout }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
