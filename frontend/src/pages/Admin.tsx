import { AnimatePresence, motion } from 'framer-motion'
import { Copy, Home, KeyRound, ListTree, Pencil, Plus, ShieldCheck, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Sheet } from '../components/Recipes'
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
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent-bright/60 to-accent-strong/60 text-sm font-bold">
        {initialsOf(member.display_name)}
      </div>

      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 truncate font-semibold text-fg">
          {member.display_name}
          {isSelf && <span className="text-[10px] font-semibold text-fg/40">you</span>}
        </p>
        <p className="truncate text-sm text-fg/55">@{member.username}</p>
      </div>

      <div className="flex shrink-0 items-center gap-1.5">
        <span className="rounded-full bg-fg/10 px-2.5 py-1 text-[11px] font-semibold text-fg/70">
          {ROLE_LABEL[member.role]}
        </span>
        {member.is_owner ? (
          <span className="flex items-center gap-1 rounded-full bg-gold/20 px-2.5 py-1 text-[11px] font-semibold text-gold">
            <ShieldCheck className="h-3 w-3" /> Server admin
          </span>
        ) : member.is_admin ? (
          <span className="flex items-center gap-1 rounded-full bg-accent-bright/20 px-2.5 py-1 text-[11px] font-semibold text-accent-bright">
            <ShieldCheck className="h-3 w-3" /> Admin
          </span>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <button
          onClick={onEdit}
          aria-label={`Edit ${member.display_name}`}
          className="rounded-lg p-2 text-fg/50 transition-colors hover:bg-fg/10 hover:text-fg"
        >
          <Pencil className="h-4 w-4" />
        </button>
        {!isSelf && (
          <button
            onClick={onDelete}
            aria-label={`Remove ${member.display_name}`}
            className="rounded-lg p-2 text-fg/50 transition-colors hover:bg-rose-500/20 hover:text-rose-300"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
    </motion.div>
  )
}

// ---- reset to a generated password ---------------------------------------------

// Lives inside the edit sheet, replacing the typed-password field once used.
// Two-tap arming (the same pattern as card delete) because the reset signs the
// member out everywhere the moment it runs.
function ResetPasswordSection({ member }: { member: api.User }) {
  const [armed, setArmed] = useState(false)
  const [generated, setGenerated] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run() {
    if (!armed) {
      setArmed(true)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await api.resetPassword(member.id)
      setGenerated(res.password)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setArmed(false)
    }
    setBusy(false)
  }

  async function copy() {
    // Clipboard needs a secure context; over plain-http LAN access this can
    // fail, and the password is still right there to read out or long-press.
    try {
      await navigator.clipboard.writeText(generated ?? '')
      setCopied(true)
    } catch {
      /* leave the button as-is; the text itself is selectable */
    }
  }

  if (generated) {
    return (
      <div className="rounded-xl border border-accent-bright/30 bg-accent-bright/10 p-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg/50">
          Their new password
        </p>
        <div className="flex items-center gap-2">
          <code className="flex-1 select-all rounded-lg bg-fg/10 px-3 py-2 font-mono text-sm font-semibold tracking-wide">
            {generated}
          </code>
          <button
            type="button"
            onClick={copy}
            aria-label="Copy password"
            className="rounded-lg p-2 text-fg/60 transition-colors hover:bg-fg/10 hover:text-fg"
          >
            <Copy className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-2.5 text-xs leading-relaxed text-fg/55">
          {copied ? 'Copied. ' : ''}Give this to {member.display_name}. It's shown only once.
          They're signed out everywhere, and at their next sign-in they'll choose their own
          password before anything else.
        </p>
      </div>
    )
  }

  return (
    <div>
      <button
        type="button"
        onClick={run}
        disabled={busy}
        className={`flex w-full items-center gap-2 rounded-xl border px-4 py-3 text-left text-sm font-semibold transition-colors disabled:opacity-50 ${
          armed
            ? 'border-gold/50 bg-gold/15 text-gold'
            : 'border-fg/10 bg-fg/5 text-fg/70 hover:bg-fg/10'
        }`}
      >
        <KeyRound className="h-4 w-4 shrink-0" />
        {busy
          ? 'Resetting'
          : armed
            ? 'Tap again to reset (signs them out everywhere)'
            : 'Reset password'}
      </button>
      {!armed && (
        <p className="mt-1.5 text-xs text-fg/40">
          Forgot it? This generates a password you hand over; they pick their own at next sign-in.
        </p>
      )}
      <FormError message={error} />
    </div>
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
  const [birthdate, setBirthdate] = useState(member?.birthdate ?? '')
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
    if (creating && username.trim().length < 3) {
      setError('Username must be at least 3 characters.')
      return
    }
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
        await api.createUser({
          username,
          display_name: displayName,
          password,
          role,
          is_admin: isAdmin,
          ...(role === 'child' && birthdate ? { birthdate } : {}),
        })
      } else {
        await api.updateUser(member.id, {
          display_name: displayName,
          role,
          is_admin: isAdmin,
          // Adults own their birthdate (they set it in Nutrition); the admin
          // sheet only ever writes a child's.
          ...(role === 'child' ? { birthdate: birthdate || null } : {}),
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
    <Sheet onClose={onClose}>
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-lg font-bold">{creating ? 'Add family member' : `Edit ${member.display_name}`}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
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
            <p className="text-xs text-fg/40">
              Signing in as <span className="font-semibold text-fg/60">@{member.username}</span>
              {' '}(usernames can't be changed)
            </p>
          )}

          <div>
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
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
                      ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
                      : 'border-fg/10 bg-fg/5 text-fg/55 hover:bg-fg/10'
                  }`}
                >
                  {ROLE_LABEL[r]}
                </button>
              ))}
            </div>
          </div>

          {role === 'child' && (
            <>
              <p className="-mt-1 text-xs leading-relaxed text-fg/45">
                Child accounts have the Nutrition tab disabled, view-only access to the family
                calendar except their own assigned tasks, and a mood and journal only parents
                can see. Most families create one so parents can track a kid's routines and
                activities, rather than for the child to use the app themselves.
              </p>
              <div>
                <Field
                  label="Birthdate"
                  type="date"
                  value={birthdate}
                  onChange={(e) => setBirthdate(e.target.value)}
                  onClear={() => setBirthdate('')}
                />
                <p className="mt-1.5 text-xs text-fg/40">
                  Optional. Just for the family's reference.
                </p>
              </div>
            </>
          )}

          <label
            className={`flex items-center justify-between rounded-xl border border-fg/10 bg-fg/5 px-4 py-3 ${
              role === 'child' || (isSelf && member?.is_admin) ? 'opacity-50' : 'cursor-pointer'
            }`}
          >
            <span className="flex items-center gap-2 text-sm font-semibold text-fg/80">
              <ShieldCheck className="h-4 w-4 text-accent-bright" /> Can manage the family
            </span>
            <input
              type="checkbox"
              checked={isAdmin}
              onChange={(e) => setIsAdmin(e.target.checked)}
              // Children can't be admins, and you can't demote yourself.
              disabled={role === 'child' || (isSelf && member?.is_admin)}
              className="h-5 w-5 accent-accent-bright"
            />
          </label>
          {isSelf && member?.is_admin && (
            <p className="-mt-2 text-xs text-fg/40">
              You can't remove your own admin access. That guarantees the family always has an
              admin.
            </p>
          )}

          {creating || isSelf ? (
            <>
              {creating && (
                <Field
                  label="Password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  autoComplete="new-password"
                  required
                />
              )}
              {isSelf && !creating && (
                <p className="text-xs text-fg/40">
                  Change your own password under the You tab.
                </p>
              )}
            </>
          ) : (
            <>
              <Field
                label="Set a password (optional)"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Leave blank to keep current"
                autoComplete="new-password"
              />
              {password ? (
                <p className="-mt-2 flex items-center gap-1.5 text-xs text-gold/80">
                  <KeyRound className="h-3.5 w-3.5" /> This will replace their current password.
                </p>
              ) : (
                <ResetPasswordSection member={member} />
              )}
            </>
          )}

          <FormError message={error} />
          <Button type="submit" disabled={busy} className="mt-1">
            {busy ? 'Saving' : creating ? 'Add member' : 'Save changes'}
          </Button>
        </form>
    </Sheet>
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
    <Sheet onClose={onClose}>
        <p className="mb-1 font-bold">Remove {member.display_name}?</p>
        <p className="mb-5 text-sm text-fg/55">
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
    </Sheet>
  )
}

// ---- invite another household -------------------------------------------------

// Deliberately separate from "Add family member". This creates a family-LESS
// parent account: whoever signs in with it founds their own, fully separate
// household (their board never mixes with yours). You hand them the username
// and password; they name their family on first sign-in.
function InviteHouseholdSheet({ onClose }: { onClose: () => void }) {
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [invite, setInvite] = useState<api.SignupInvite | null>(null)
  const [copied, setCopied] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      setInvite(await api.mintInvite(displayName))
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(invite?.code ?? '')
      setCopied(true)
    } catch {
      /* http contexts have no clipboard API; the code is selectable */
    }
  }

  return (
    <Sheet onClose={onClose}>
        <div className="mb-5 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-bold">
            <Home className="h-5 w-5 text-accent-bright" /> Invite to dailybread
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {invite ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm leading-relaxed text-fg/70">
              Give this code to <span className="font-semibold text-fg">{invite.display_name}</span>.
              On the sign-in screen they tap "Enter invite code", pick their own username and
              password, and set up their own family. It works once and expires in 15 minutes; if
              it lapses, just mint another.
            </p>
            <div className="flex items-center justify-center gap-3 rounded-xl border border-fg/10 bg-fg/5 p-4">
              <span className="select-all font-mono text-2xl font-bold tracking-widest text-fg/90">
                {invite.code}
              </span>
              <button
                type="button"
                onClick={copy}
                aria-label="Copy invite code"
                className="rounded-full bg-fg/10 p-2 text-fg/60 hover:bg-fg/20 hover:text-fg"
              >
                <Copy className="h-4 w-4" />
              </button>
            </div>
            {copied && <p className="-mt-2 text-center text-xs text-fg/50">Copied</p>}
            <Button onClick={onClose}>Done</Button>
          </div>
        ) : (
          <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
            <p className="text-xs leading-relaxed text-fg/50">
              This invites someone to start their own family on this dailybread, with their own
              board, completely separate from yours. Use "Add family member" instead if you're
              adding someone to your own family.
            </p>
            <Field
              label="Their name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoFocus
              required
            />
            <FormError message={error} />
            <Button type="submit" disabled={busy} className="mt-1">
              {busy ? 'Creating invite' : 'Create invite code'}
            </Button>
          </form>
        )}
    </Sheet>
  )
}

// ---- the server overview ---------------------------------------------------------

// Server admin only: every village, family, and member on the install, as an
// indented tree. Read-only by design — management still happens per family.
function ServerOverview() {
  const [tree, setTree] = useState<api.Overview | null>(null)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function toggle() {
    const next = !open
    setOpen(next)
    if (next && tree === null) {
      try {
        setTree(await api.getOverview())
      } catch (err) {
        setError(err instanceof api.ApiError ? err.message : 'Could not load the overview.')
      }
    }
  }

  const userRow = (u: api.OverviewUser) => (
    <p key={u.id} className="flex items-center gap-2 pl-8 text-sm text-fg/70">
      <span className="font-semibold text-fg/85">{u.display_name}</span>
      <span className="text-xs text-fg/45">@{u.username}</span>
      <span className="text-[10px] font-semibold uppercase tracking-wide text-fg/40">
        {u.is_owner ? 'server admin' : u.is_admin ? `${ROLE_LABEL[u.role]} · admin` : ROLE_LABEL[u.role]}
      </span>
    </p>
  )

  const familyBlock = (f: api.OverviewFamily) => (
    <div key={f.id} className="flex flex-col gap-1">
      <p className="pl-4 text-sm font-semibold text-fg/80">{f.name}</p>
      {f.users.map(userRow)}
    </div>
  )

  return (
    <div className="mt-3">
      <button
        onClick={toggle}
        className="glass flex w-full items-center gap-3 p-4 text-left font-semibold text-fg/80 transition-colors hover:text-fg"
      >
        <ListTree className="h-4 w-4 text-accent-bright" /> Server overview
      </button>
      {open && (
        <div className="glass mt-2 flex flex-col gap-3 p-4">
          <FormError message={error} />
          {tree === null && !error && <p className="text-sm text-fg/40">Loading</p>}
          {tree?.villages.map((v) => (
            <div key={v.id} className="flex flex-col gap-1.5">
              <p className="text-xs font-semibold uppercase tracking-widest text-accent-bright">
                Village · {v.name}
              </p>
              {v.families.map(familyBlock)}
            </div>
          ))}
          {tree && tree.solo_families.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p className="text-xs font-semibold uppercase tracking-widest text-fg/40">
                Not in a village
              </p>
              {tree.solo_families.map(familyBlock)}
            </div>
          )}
          {tree && tree.homeless_users.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p className="text-xs font-semibold uppercase tracking-widest text-fg/40">
                Still setting up
              </p>
              {tree.homeless_users.map(userRow)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---- rename the family ---------------------------------------------------------

function RenameFamilySheet({
  current,
  onClose,
  onRenamed,
}: {
  current: string
  onClose: () => void
  onRenamed: () => void
}) {
  const [name, setName] = useState(current)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.renameFamily(name.trim())
      onRenamed()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
      setBusy(false)
    }
  }

  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 text-lg font-bold">Family name</h3>
      <p className="mb-4 text-sm text-fg/60">
        This is how your family appears across the app, and to families you link with in a
        village. Lots of families share a last name, so a fun, custom name works best.
      </p>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field
          label="Family name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={80}
          autoFocus
          required
        />
        <FormError message={error} />
        <Button type="submit" disabled={busy || !name.trim()}>
          {busy ? 'Saving…' : 'Save'}
        </Button>
      </form>
    </Sheet>
  )
}

// ---- the dashboard ------------------------------------------------------------

export function Admin() {
  const { user } = useAuth()
  const [members, setMembers] = useState<api.User[] | null>(null)
  const [family, setFamily] = useState<api.Family | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [sheet, setSheet] = useState<{ open: boolean; member: api.User | null }>({
    open: false,
    member: null,
  })
  const [deleting, setDeleting] = useState<api.User | null>(null)
  const [inviting, setInviting] = useState(false)
  const [renaming, setRenaming] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setMembers(await api.listUsers())
      setFamily(await api.getMyFamily())
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
          <button
            type="button"
            onClick={() => setRenaming(true)}
            className="group flex items-center gap-1.5 text-sm text-fg/50 transition-colors hover:text-fg/80"
            aria-label="Rename family"
          >
            {family?.name ?? '…'}
            <Pencil className="h-3 w-3 text-fg/30 transition-colors group-hover:text-fg/60" />
          </button>
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
          <p className="py-8 text-center text-sm text-fg/40">Loading</p>
        )}
      </div>

      {/* Server-admin only. A separate concept from the member list above: this
          founds a whole new family on the install, not a member of yours. Only
          the instance owner can do it, so a family B admin never sees this. */}
      {user?.is_owner && (
        <div className="mt-8 border-t border-fg/10 pt-5">
          <p className="text-xs font-semibold uppercase tracking-widest text-fg/40">
            Server admin
          </p>
          <p className="mt-1 mb-3 text-sm text-fg/50">
            Invite someone to found their own family on this dailybread with an invite code. They
            run their own board; you won't see their members here.
          </p>
          <button
            onClick={() => setInviting(true)}
            className="glass flex w-full items-center gap-3 p-4 text-left font-semibold text-fg/80 transition-colors hover:text-fg"
          >
            <Home className="h-4 w-4 text-accent-bright" /> Invite to dailybread
          </button>
          <ServerOverview />
        </div>
      )}

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
        {inviting && <InviteHouseholdSheet onClose={() => setInviting(false)} />}
        {renaming && family && (
          <RenameFamilySheet
            current={family.name}
            onClose={() => setRenaming(false)}
            onRenamed={() => {
              setRenaming(false)
              refresh()
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
