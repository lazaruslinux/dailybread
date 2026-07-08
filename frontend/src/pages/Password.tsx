import { AnimatePresence, motion } from 'framer-motion'
import { Check, KeyRound, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../lib/api'
import { AuthShell, Brand, Button, Field, FormError } from '../components/ui'

// Both ways a member sets their own password: the Preferences sheet on the
// You tab, and the full-screen gate shown after an admin reset (the account
// can't reach anything else until it trades the generated password for its
// own — the backend enforces that; these screens just make it pleasant).

function PasswordForm({
  currentLabel,
  submitLabel,
  onDone,
}: {
  currentLabel: string
  submitLabel: string
  onDone?: () => void
}) {
  const { changePassword } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (next.length < 8) {
      setError('New password must be at least 8 characters.')
      return
    }
    if (next !== confirm) {
      setError("Those passwords don't match.")
      return
    }
    setBusy(true)
    try {
      await changePassword(current, next)
      onDone?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <Field
        label={currentLabel}
        type="password"
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        autoComplete="current-password"
        required
      />
      <Field
        label="New password"
        type="password"
        value={next}
        onChange={(e) => setNext(e.target.value)}
        placeholder="At least 8 characters"
        autoComplete="new-password"
        required
      />
      <Field
        label="Confirm new password"
        type="password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        autoComplete="new-password"
        required
      />
      <FormError message={error} />
      <Button type="submit" disabled={busy || !current || !next || !confirm} className="mt-1">
        {busy ? 'Saving' : submitLabel}
      </Button>
    </form>
  )
}

// Full-screen gate after an admin reset: the generated password signed them
// in, and this is the only thing their session can do until they replace it.
export function ForcedPasswordChange() {
  const { user, logout } = useAuth()

  return (
    <AuthShell>
      <Brand subtitle="Choose your own password" />
      <p className="mb-5 text-sm leading-relaxed text-fg/60">
        {user ? `Hi ${user.display_name.split(' ')[0]}. ` : ''}
        Your password was reset to a temporary one. Pick your own to keep using dailybread. The
        temporary password stops working the moment you do.
      </p>
      <PasswordForm currentLabel="Temporary password" submitLabel="Set my password" />
      <button
        onClick={logout}
        className="mt-4 w-full text-center text-sm font-medium text-fg/45 transition-colors hover:text-fg/70"
      >
        Sign out instead
      </button>
    </AuthShell>
  )
}

// The Preferences sheet, opened from the You tab. Success lingers for a
// moment of reassurance (other devices got signed out; this one didn't).
export function ChangePasswordSheet({ onClose }: { onClose: () => void }) {
  const [done, setDone] = useState(false)

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 40 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        className="glass w-full max-w-sm p-6"
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-bold">
            <KeyRound className="h-5 w-5 text-accent-bright" /> Change password
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <AnimatePresence mode="wait">
          {done ? (
            <motion.div
              key="done"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col gap-4"
            >
              <p className="flex items-start gap-2.5 text-sm leading-relaxed text-fg/70">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent-bright" />
                <span>
                  Password changed. Anywhere else you were signed in got signed out; this device
                  stays in.
                </span>
              </p>
              <Button onClick={onClose}>Done</Button>
            </motion.div>
          ) : (
            <motion.div key="form" exit={{ opacity: 0, y: -8 }}>
              <PasswordForm
                currentLabel="Current password"
                submitLabel="Change password"
                onDone={() => setDone(true)}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  )
}
