import { useState, type FormEvent } from 'react'
import { checkInvite, ApiError } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { AuthShell, Brand, Button, Field, FormError } from '../components/ui'

// The sign-in screen, plus the far side of "Invite to dailybread": someone
// holding an invite code enters it here, is greeted by name, picks their own
// password, and lands in the create-your-family wizard.
export function Login() {
  const { login, redeemInvite } = useAuth()
  const [view, setView] = useState<'login' | 'code' | 'password'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [invitee, setInvitee] = useState<{ display_name: string } | null>(null)
  const [newUsername, setNewUsername] = useState('')
  const [newDisplayName, setNewDisplayName] = useState('')
  const [newBirthdate, setNewBirthdate] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function switchTo(next: 'login' | 'code' | 'password') {
    setError(null)
    setBusy(false)
    setView(next)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(username, password)
    } catch {
      // Deliberately generic, mirroring the backend: never hint at whether
      // the username or the password was the wrong half.
      setError('Invalid username or password.')
      setBusy(false)
    }
  }

  async function onCheckCode(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const found = await checkInvite(code)
      setInvitee(found)
      setNewDisplayName(found.display_name)
      switchTo('password')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  async function onRedeem(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (newUsername.trim().length < 3) {
      setError('Username must be at least 3 characters.')
      return
    }
    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (newPassword !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    try {
      await redeemInvite(code, newUsername.trim(), newDisplayName.trim(), newPassword, newBirthdate || null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  if (view === 'code') {
    return (
      <AuthShell>
        <Brand subtitle="Enter the invite code you were given" />
        <form onSubmit={onCheckCode} className="flex flex-col gap-4">
          <Field
            label="Invite code"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="ABCD-EFGH"
            autoComplete="off"
            autoFocus
            required
          />
          <FormError message={error} />
          <Button type="submit" disabled={busy || !code.trim()} className="mt-1">
            {busy ? 'Checking' : 'Continue'}
          </Button>
          <button
            type="button"
            onClick={() => switchTo('login')}
            className="text-center text-xs font-semibold text-fg/40 transition-colors hover:text-fg/70"
          >
            Back to sign in
          </button>
        </form>
      </AuthShell>
    )
  }

  if (view === 'password' && invitee) {
    const firstName = invitee.display_name.split(/\s+/)[0]
    return (
      <AuthShell>
        <Brand subtitle={`Welcome, ${firstName}. Make this account yours.`} />
        <form onSubmit={onRedeem} noValidate className="flex flex-col gap-4">
          <Field
            label="Your name"
            value={newDisplayName}
            onChange={(e) => setNewDisplayName(e.target.value)}
            maxLength={100}
            autoComplete="name"
            required
          />
          <Field
            label="Username"
            value={newUsername}
            onChange={(e) => setNewUsername(e.target.value)}
            placeholder="For signing in"
            autoComplete="username"
            autoCapitalize="none"
            autoFocus
            required
          />
          <div>
            <Field
              label="Birthdate"
              type="date"
              value={newBirthdate}
              onChange={(e) => setNewBirthdate(e.target.value)}
              onClear={() => setNewBirthdate('')}
            />
            <p className="mt-1.5 text-xs leading-relaxed text-fg/40">
              Optional. Used for your calorie targets; you can add it in Nutrition later.
            </p>
          </div>
          <Field
            label="Password"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="At least 8 characters"
            autoComplete="new-password"
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
            {busy ? 'Creating account' : 'Create my account'}
          </Button>
          <button
            type="button"
            onClick={() => switchTo('code')}
            className="text-center text-xs font-semibold text-fg/40 transition-colors hover:text-fg/70"
          >
            Back
          </button>
        </form>
      </AuthShell>
    )
  }

  return (
    <AuthShell>
      <Brand subtitle="Sign in to your family's board" />
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field
          label="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          autoCapitalize="none"
          autoFocus
          required
        />
        <Field
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
        <FormError message={error} />
        <Button type="submit" disabled={busy || !username || !password} className="mt-1">
          {busy ? 'Signing in' : 'Sign in'}
        </Button>
        <button
          type="button"
          onClick={() => switchTo('code')}
          className="text-center text-xs font-semibold text-fg/40 transition-colors hover:text-fg/70"
        >
          Enter invite code
        </button>
      </form>
    </AuthShell>
  )
}
