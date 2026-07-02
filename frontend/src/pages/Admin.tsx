import { AnimatePresence, motion } from 'framer-motion'
import { KeyRound, Pencil, Plus, ShieldCheck, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Button, Field, FormError } from '../components/ui'

// Admin dashboard v1: family member management. List, add, edit, reset
// password, remove. Only reachable when the signed-in user is an admin (the
// backend re-checks every call; hiding the UI is convenience, not security).

const ROLE_LABEL: Record<api.Role, string> = { parent: 'Parent', child: 'Child' }

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
}

// ---- member row -------------------------------------------------------------

function MemberRow({
  member,
  isSelf,
  onEdit,
  onDelete,
  index,
}: {
  member: api.User
  isSelf: boolean
  onEdit: () => void
  onDelete: () => void
  index: number
}) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ delay: index * 0.04, type: 'spring', stiffness: 300, damping: 26 }}
      className="glass flex items-center gap-4 p-4"
    >
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-400/60 to-violet-500/60 text-sm font-bold">
        {initialsOf(member.display_name)}
      </div>

      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 truncate font-semibold text-white">
          {member.display_name}
          {isSelf && <span className="text-[10px] font-semibold text-white/40">you</span>}
        </p>
        <p className="truncate text-sm text-white/55">@{member.username}</p>
      </div>

      <div className="flex shrink-0 items-center gap-1.5">
        <span className="rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-semibold text-white/70">
          {ROLE_LABEL[member.role]}
        </span>
        {member.is_admin && (
          <span className="flex items-center gap-1 rounded-full bg-indigo-400/20 px-2.5 py-1 text-[11px] font-semibold text-indigo-200">
            <ShieldCheck className="h-3 w-3" /> Admin
          </span>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <button
          onClick={onEdit}
          aria-label={`Edit ${member.display_name}`}
          className="rounded-lg p-2 text-white/50 transition-colors hover:bg-white/10 hover:text-white"
        >
          <Pencil className="h-4 w-4" />
        </button>
        {!isSelf && (
          <button
            onClick={onDelete}
            aria-label={`Remove ${member.display_name}`}
            className="rounded-lg p-2 text-white/50 transition-colors hover:bg-rose-500/20 hover:text-rose-300"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
    </motion.div>
  )
}

// ---- add / edit sheet ---------------------------------------------------------

interface SheetProps {
  member: api.User | null // null = creating a new member
  isSelf: boolean
  onClose: () => void
  onSaved: () => void
}

function MemberSheet({ member, isSelf, onClose, onSaved }: SheetProps) {
  const creating = member === null
  const [displayName, setDisplayName] = useState(member?.display_name ?? '')
  const [username, setUsername] = useState(member?.username ?? '')
  const [role, setRole] = useState<api.Role>(member?.role ?? 'child')
  const [isAdmin, setIsAdmin] = useState(member?.is_admin ?? false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Keep the form honest: flipping to child clears admin, since the backend
  // will refuse that combination anyway.
  function pickRole(next: api.Role) {
    setRole(next)
    if (next === 'child') setIsAdmin(false)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (creating && password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (!creating && password && password.length < 8) {
      setError('New password must be at least 8 characters.')
      return
    }
    setBusy(true)
    try {
      if (creating) {
        await api.createUser({ username, display_name: displayName, password, role, is_admin: isAdmin })
      } else {
        await api.updateUser(member.id, {
          display_name: displayName,
          role,
          is_admin: isAdmin,
          ...(password ? { password } : {}),
        })
      }
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/50 p-4 backdrop-blur-sm sm:items-center"
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
          <h2 className="text-lg font-bold">{creating ? 'Add family member' : `Edit ${member.display_name}`}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-white/50 hover:bg-white/10 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <Field
            label="Name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            autoFocus={creating}
            required
          />
          {creating ? (
            <Field
              label="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoCapitalize="none"
              minLength={3}
              required
            />
          ) : (
            <p className="text-xs text-white/40">
              Signing in as <span className="font-semibold text-white/60">@{member.username}</span>
              {' '}(usernames can't be changed)
            </p>
          )}

          <div>
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-white/50">
              Role
            </span>
            <div className="grid grid-cols-2 gap-2">
              {(['parent', 'child'] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => pickRole(r)}
                  className={`rounded-xl border px-3 py-2 text-sm font-semibold transition-colors ${
                    role === r
                      ? 'border-indigo-400/60 bg-indigo-400/20 text-white'
                      : 'border-white/10 bg-white/5 text-white/55 hover:bg-white/10'
                  }`}
                >
                  {ROLE_LABEL[r]}
                </button>
              ))}
            </div>
          </div>

          <label
            className={`flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-4 py-3 ${
              role === 'child' || (isSelf && member?.is_admin) ? 'opacity-50' : 'cursor-pointer'
            }`}
          >
            <span className="flex items-center gap-2 text-sm font-semibold text-white/80">
              <ShieldCheck className="h-4 w-4 text-indigo-300" /> Admin dashboard access
            </span>
            <input
              type="checkbox"
              checked={isAdmin}
              onChange={(e) => setIsAdmin(e.target.checked)}
              // Children can't be admins, and you can't demote yourself.
              disabled={role === 'child' || (isSelf && member?.is_admin)}
              className="h-5 w-5 accent-indigo-400"
            />
          </label>
          {isSelf && member?.is_admin && (
            <p className="-mt-2 text-xs text-white/40">
              You can't remove your own admin access. That guarantees the family always has an
              admin.
            </p>
          )}

          <Field
            label={creating ? 'Password' : 'Reset password (optional)'}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={creating ? 'At least 8 characters' : 'Leave blank to keep current'}
            autoComplete="new-password"
            required={creating}
          />
          {!creating && password && (
            <p className="-mt-2 flex items-center gap-1.5 text-xs text-amber-300/80">
              <KeyRound className="h-3.5 w-3.5" /> This will replace their current password.
            </p>
          )}

          <FormError message={error} />
          <Button type="submit" disabled={busy} className="mt-1">
            {busy ? 'Saving' : creating ? 'Add member' : 'Save changes'}
          </Button>
        </form>
      </motion.div>
    </motion.div>
  )
}

// ---- delete confirm ----------------------------------------------------------

function DeleteConfirm({
  member,
  onClose,
  onDeleted,
}: {
  member: api.User
  onClose: () => void
  onDeleted: () => void
}) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      await api.deleteUser(member.id)
      onDeleted()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="glass w-full max-w-xs p-6 text-center"
        role="alertdialog"
        aria-modal="true"
      >
        <p className="mb-1 font-bold">Remove {member.display_name}?</p>
        <p className="mb-5 text-sm text-white/55">
          @{member.username} will be signed out everywhere and their account deleted.
        </p>
        <FormError message={error} />
        <div className="mt-2 grid grid-cols-2 gap-2">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="danger" onClick={confirm} disabled={busy}>
            {busy ? 'Removing' : 'Remove'}
          </Button>
        </div>
      </motion.div>
    </motion.div>
  )
}

// ---- the dashboard ------------------------------------------------------------

export function Admin() {
  const { user } = useAuth()
  const [members, setMembers] = useState<api.User[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [sheet, setSheet] = useState<{ open: boolean; member: api.User | null }>({
    open: false,
    member: null,
  })
  const [deleting, setDeleting] = useState<api.User | null>(null)

  const refresh = useCallback(async () => {
    try {
      setMembers(await api.listUsers())
      setLoadError(null)
    } catch (err) {
      setLoadError(err instanceof api.ApiError ? err.message : 'Could not load family members.')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight">Family members</h2>
          <p className="text-sm text-white/50">Accounts on this dailybread</p>
        </div>
        <Button onClick={() => setSheet({ open: true, member: null })} className="flex items-center gap-1.5">
          <Plus className="h-4 w-4" /> Add
        </Button>
      </div>

      <FormError message={loadError} />

      <div className="flex flex-col gap-3">
        <AnimatePresence>
          {members?.map((m, i) => (
            <MemberRow
              key={m.id}
              member={m}
              index={i}
              isSelf={m.id === user?.id}
              onEdit={() => setSheet({ open: true, member: m })}
              onDelete={() => setDeleting(m)}
            />
          ))}
        </AnimatePresence>
        {members === null && !loadError && (
          <p className="py-8 text-center text-sm text-white/40">Loading</p>
        )}
      </div>

      <AnimatePresence>
        {sheet.open && (
          <MemberSheet
            member={sheet.member}
            isSelf={sheet.member?.id === user?.id}
            onClose={() => setSheet({ open: false, member: null })}
            onSaved={() => {
              setSheet({ open: false, member: null })
              refresh()
            }}
          />
        )}
        {deleting && (
          <DeleteConfirm
            member={deleting}
            onClose={() => setDeleting(null)}
            onDeleted={() => {
              setDeleting(null)
              refresh()
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
