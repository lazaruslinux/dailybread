import { useState, type FormEvent } from 'react'
import { ApiError, setVerseSettings } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { AuthShell, Brand, Button, Field, FormError } from '../components/ui'
import { VERSES_OPTIN_KEY, WelcomeTour } from '../components/WelcomeTour'

// Shown to a fresh new-household account: they are signed in but have no family
// yet. Naming their household founds it and makes them its parent + admin, and
// from there they add their own members. This is the far side of the "Invite
// to dailybread" action in the server admin's dashboard.
export function CreateFamily() {
  const { user, createFamily, logout } = useAuth()
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [touring, setTouring] = useState(
    () => sessionStorage.getItem('db-invite-tour') === '1',
  )

  const firstName = user?.display_name.split(/\s+/)[0] ?? ''

  if (touring) {
    return (
      <WelcomeTour
        firstName={firstName}
        context="signup"
        onDone={() => {
          sessionStorage.removeItem('db-invite-tour')
          setTouring(false)
        }}
      />
    )
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await createFamily(name)
      // The tour's verses opt-in couldn't save until a family existed; apply
      // it now. A miss is harmless — the You page has the same switch.
      if (sessionStorage.getItem(VERSES_OPTIN_KEY) === '1') {
        sessionStorage.removeItem(VERSES_OPTIN_KEY)
        setVerseSettings({ enabled: true }).catch(() => {})
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  return (
    <AuthShell>
      <Brand subtitle={`Welcome, ${firstName}. Let's set up your household.`} />
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <div>
          <Field
            label="Family name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="The Breakfast Club"
            maxLength={80}
            autoFocus
            required
          />
          <p className="mt-1.5 text-xs leading-relaxed text-fg/40">
            Lots of families share a last name. A fun, custom name keeps yours recognizable
            when villages link families together. You can change it later.
          </p>
        </div>
        <FormError message={error} />
        <Button type="submit" disabled={busy || !name.trim()} className="mt-1">
          {busy ? 'Creating' : 'Create our family'}
        </Button>
        <p className="text-center text-xs leading-relaxed text-fg/40">
          You'll be the head of this household. Add the rest of your family from the admin
          dashboard once you're in.
        </p>
        <button
          type="button"
          onClick={logout}
          className="text-center text-xs font-semibold text-fg/40 transition-colors hover:text-fg/70"
        >
          Sign out
        </button>
      </form>
    </AuthShell>
  )
}
