import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import { AuthShell, Brand, Button, Field, FormError } from '../components/ui'

export function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

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
      </form>
    </AuthShell>
  )
}
