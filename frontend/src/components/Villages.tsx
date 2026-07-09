import { AnimatePresence } from 'framer-motion'
import { Copy, Plus } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import {
  ApiError,
  checkVillageCode,
  createVillage,
  joinVillage,
  leaveVillage,
  listVillages,
  regenerateInvite,
  type Village,
} from '../lib/api'
import { CollapsibleCard } from './CollapsibleCard'
import { Sheet } from './Recipes'
import { Button, Field, FormError } from './ui'

// Villages: private circles of linked families. This card is the whole
// membership UI — founding, joining by code, regenerating a code, leaving.
// The code itself appears exactly once (the server stores only a hash), so
// the sheet that shows it is the owner's one chance to pass it along.

// Two huts side by side: an old village. Drawn in lucide's visual language
// (24-grid, 2px stroke, round caps) so it sits naturally among the real icons.
function VillageIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2 12l4.5-4L11 12" />
      <path d="M3.5 11v7h6v-7" />
      <path d="M12.5 9.5L17.5 5 22 9.5" />
      <path d="M14 8.5V18h7V8.5" />
      <path d="M17.5 18v-3.5" />
    </svg>
  )
}

function expiresIn(iso: string | null): string {
  if (!iso) return ''
  const hours = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 3_600_000))
  return hours < 1 ? 'expires within the hour' : `expires in ${hours}h`
}

// The one-time reveal. Shown right after founding a village or regenerating
// its code; once dismissed the code is gone for good (only regenerable).
function CodeSheet({
  village,
  code,
  expiresAt,
  onClose,
}: {
  village: string
  code: string
  expiresAt: string | null
  onClose: () => void
}) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
    } catch {
      /* http preview contexts have no clipboard API; the code is selectable */
    }
  }
  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 text-lg font-bold">Invite to {village}</h3>
      <p className="mb-4 text-sm text-fg/60">
        Pass this code to the other family's admin. They enter it under Villages on their own
        You tab. It works once, {expiresIn(expiresAt)}, and can't be shown again. Lose it and
        you just make a new one.
      </p>
      <div className="mb-4 flex items-center justify-center gap-3 rounded-xl border border-fg/10 bg-fg/5 p-4">
        <span className="select-all font-mono text-2xl font-bold tracking-widest text-fg/90">
          {code}
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
      {copied && <p className="mb-3 text-center text-xs text-fg/50">Copied</p>}
      <Button type="button" className="w-full" onClick={onClose}>
        Done
      </Button>
    </Sheet>
  )
}

function CreateSheet({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (v: { id: number; name: string; code: string; expiresAt: string | null }) => void
}) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const created = await createVillage(name.trim())
      onCreated({
        id: created.id,
        name: created.name,
        code: created.invite_code,
        expiresAt: created.invite_expires_at,
      })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
      setBusy(false)
    }
  }

  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 text-lg font-bold">New village</h3>
      <p className="mb-4 text-sm text-fg/60">
        Creating a village links your family to other families you can invite via a code.
        Boards, kitchens, and calendars stay private to each family.
      </p>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field
          label="Village name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={80}
          placeholder="The Cousins"
          autoFocus
          required
        />
        <FormError message={error} />
        <Button type="submit" disabled={busy || !name.trim()}>
          {busy ? 'Creating…' : 'Create & get invite code'}
        </Button>
      </form>
    </Sheet>
  )
}

function JoinSheet({ onClose, onJoined }: { onClose: () => void; onJoined: () => void }) {
  const [code, setCode] = useState('')
  const [found, setFound] = useState<{ name: string; families: string[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function check(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      setFound(await checkVillageCode(code))
      setBusy(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
      setBusy(false)
    }
  }

  async function join() {
    setBusy(true)
    setError(null)
    try {
      await joinVillage(code)
      onJoined()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
      setBusy(false)
    }
  }

  if (found) {
    return (
      <Sheet onClose={onClose}>
        <h3 className="mb-1 text-lg font-bold">Join {found.name}?</h3>
        <p className="mb-3 text-sm text-fg/60">
          They won't be able to see anything of yours unless you share.
        </p>
        <div className="mb-4 flex flex-wrap gap-1.5">
          {found.families.map((name) => (
            <span
              key={name}
              className="rounded-full border border-fg/10 bg-fg/10 px-2.5 py-0.5 text-xs font-semibold text-fg/70"
            >
              {name}
            </span>
          ))}
        </div>
        <FormError message={error} />
        <div className="flex gap-2">
          <Button type="button" variant="ghost" className="flex-1" onClick={() => setFound(null)}>
            Back
          </Button>
          <Button type="button" className="flex-1" disabled={busy} onClick={join}>
            {busy ? 'Joining…' : 'Join'}
          </Button>
        </div>
      </Sheet>
    )
  }

  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 text-lg font-bold">Join a village</h3>
      <p className="mb-4 text-sm text-fg/60">
        Enter the invite code given to you by another family to join their village.
      </p>
      <form onSubmit={check} className="flex flex-col gap-4">
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
        <Button type="submit" disabled={busy || !code.trim()}>
          {busy ? 'Checking…' : 'Continue'}
        </Button>
      </form>
    </Sheet>
  )
}

export function VillagesCard() {
  const { user } = useAuth()
  const [villages, setVillages] = useState<Village[]>([])
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [joining, setJoining] = useState(false)
  const [reveal, setReveal] = useState<{
    village: string
    code: string
    expiresAt: string | null
  } | null>(null)
  const [armedLeave, setArmedLeave] = useState<number | null>(null)

  const refresh = useCallback(() => {
    listVillages()
      .then((v) => {
        setVillages(v)
        setError(null)
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load villages'))
  }, [])

  useEffect(() => {
    refresh()
    window.addEventListener('db:villages', refresh)
    return () => window.removeEventListener('db:villages', refresh)
  }, [refresh])

  if (!user) return null
  const isAdmin = user.is_admin

  async function regenerate(v: Village) {
    try {
      const fresh = await regenerateInvite(v.id)
      setReveal({ village: v.name, code: fresh.invite_code, expiresAt: fresh.invite_expires_at })
      refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
    }
  }

  async function leave(v: Village) {
    if (armedLeave !== v.id) {
      setArmedLeave(v.id)
      setTimeout(() => setArmedLeave((cur) => (cur === v.id ? null : cur)), 4000)
      return
    }
    setArmedLeave(null)
    try {
      await leaveVillage(v.id)
      refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
    }
  }

  return (
    <CollapsibleCard
      title="Villages"
      summary={villages.length ? villages.map((v) => v.name).join(' · ') : undefined}
      storageKey="villages"
      defaultOpen
    >
      <div className="flex flex-col gap-4">
        {villages.length === 0 && (
          <p className="text-sm text-fg/55">
            <span className="font-semibold text-fg/70">"It takes a village"</span> - Villages
            link your family to another to share recipes or plan get-togethers. Your family's
            board, nutrition, and Kitchen data is never shared with them. Shared
            recipes/activities appear in separate sections.
          </p>
        )}

        {villages.map((v) => (
          <div key={v.id} className="rounded-xl border border-fg/10 bg-fg/5 p-4">
            <div className="mb-2 flex items-center gap-2">
              <VillageIcon className="h-4 w-4 shrink-0 text-accent-bright" />
              <span className="min-w-0 truncate font-semibold text-fg/90">{v.name}</span>
            </div>
            <div className="flex flex-col gap-2.5">
              {v.families.map((f) => (
                <div key={f.id}>
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-fg/45">
                    {f.name}
                  </p>
                  <div className="flex flex-wrap gap-3">
                    {f.parents.map((p) => (
                      <span key={p.id} className="flex w-12 flex-col items-center gap-1">
                        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-accent-bright/60 to-accent-strong/60 text-xs font-bold text-fg">
                          {p.display_name
                            .split(/\s+/)
                            .slice(0, 2)
                            .map((w) => w[0]?.toUpperCase() ?? '')
                            .join('')}
                        </span>
                        <span className="w-full truncate text-center text-[10px] text-fg/55">
                          {p.display_name.split(/\s+/)[0]}
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            {isAdmin && (
              <div className="mt-3 flex items-center justify-between gap-2 text-xs">
                <span className="text-fg/45">
                  {v.invite_active ? `Invite active · ${expiresIn(v.invite_expires_at)}` : ''}
                </span>
                <span className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => regenerate(v)}
                    className="font-semibold text-accent-bright hover:underline"
                  >
                    New invite code
                  </button>
                  <button
                    type="button"
                    onClick={() => leave(v)}
                    className={`font-semibold ${armedLeave === v.id ? 'text-danger' : 'text-fg/45'} hover:underline`}
                  >
                    {armedLeave === v.id ? 'Really leave?' : 'Leave'}
                  </button>
                </span>
              </div>
            )}
          </div>
        ))}

        <FormError message={error} />

        {isAdmin && villages.length === 0 && (
          <div className="flex gap-2">
            <Button type="button" variant="ghost" className="flex-1" onClick={() => setCreating(true)}>
              <Plus className="mr-1 inline h-4 w-4" /> New village
            </Button>
            <Button type="button" variant="ghost" className="flex-1" onClick={() => setJoining(true)}>
              Join with a code
            </Button>
          </div>
        )}
      </div>

      <AnimatePresence>
        {creating && (
          <CreateSheet
            onClose={() => setCreating(false)}
            onCreated={(v) => {
              setCreating(false)
              setReveal({ village: v.name, code: v.code, expiresAt: v.expiresAt })
              refresh()
            }}
          />
        )}
        {joining && (
          <JoinSheet
            onClose={() => setJoining(false)}
            onJoined={() => {
              setJoining(false)
              refresh()
            }}
          />
        )}
        {reveal && (
          <CodeSheet
            village={reveal.village}
            code={reveal.code}
            expiresAt={reveal.expiresAt}
            onClose={() => setReveal(null)}
          />
        )}
      </AnimatePresence>
    </CollapsibleCard>
  )
}
