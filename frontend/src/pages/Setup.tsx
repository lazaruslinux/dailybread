import { useState, type FormEvent } from 'react'
import { ApiError } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { AuthShell, Brand, Button, Field, FormError } from '../components/ui'

// First-run wizard, Jellyfin-style: shown only while the install has zero
// users. Creates the owner account, which is always a parent and an admin.
export function Setup() {
  const { bootstrap } = useAuth()
  const [displayName, setDisplayName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    // Client-side checks mirror the backend rules so people get instant
    // feedback. The backend still enforces everything; this is just UX.
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }

    setBusy(true)
    try {
      await bootstrap(username, displayName, password)
    } catch (err) {
      // 403 here means someone else initialized the install between page
      // load and submit; anything else is a validation or server problem.
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  return (
    <AuthShell>
      <Brand subtitle="Welcome. Set up the family account to get started." />
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field
          label="Your name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="What the family calls you"
          autoComplete="name"
          autoFocus
          required
        />
        <Field
          label="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="For signing in"
          autoComplete="username"
          autoCapitalize="none"
          minLength={3}
          required
        />
        <Field
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 8 characters"
          autoComplete="new-password"
          minLength={8}
          required
        />
        <Field
          label="Confirm password"
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          autoComplete="new-password"
          required
        />
        <FormError message={error} />
        <Button type="submit" disabled={busy} className="mt-1">
          {busy ? 'Creating account' : 'Create admin account'}
        </Button>
        <p className="text-center text-xs leading-relaxed text-white/40">
          This becomes the owner account. You can add the rest of the family from the admin
          dashboard afterward.
        </p>
      </form>
    </AuthShell>
  )
}
