import { motion } from 'framer-motion'
import { Camera, Check, Circle, Pencil, ShieldCheck } from 'lucide-react'
import { type ChangeEvent, useCallback, useEffect, useState } from 'react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Avatar } from '../components/Avatar'
import { Button, FormError } from '../components/ui'
import { formatTime, MOODS, MOOD_ORDER } from '../lib/moods'

// A member's page: who they are, their bio, and how their day is going.
// Everything self-serve is inline: your own page grows a mood picker and a
// bio editor; someone else's page is read-only.
export function Profile({ userId }: { userId: number }) {
  const { user: viewer } = useAuth()
  const isSelf = viewer?.id === userId

  const [profile, setProfile] = useState<api.Profile | null>(null)
  // This member's slice of the board: cards assigned to them plus whole-family
  // cards (those are everyone's, so they belong on everyone's day).
  const [day, setDay] = useState<api.FeedItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editingBio, setEditingBio] = useState(false)
  const [bioDraft, setBioDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [avatarBusy, setAvatarBusy] = useState(false)
  // Only a parent sets photos, and only their own or a child's — never another
  // parent's. Children set none, so this is false for them even on their own
  // page. Mirrors the backend rule in users._require_can_set_avatar.
  const canEditAvatar =
    viewer?.role === 'parent' && (isSelf || profile?.role === 'child')

  const refresh = useCallback(async () => {
    try {
      const [p, feed] = await Promise.all([api.getProfile(userId), api.getFeed()])
      setProfile(p)
      const mine = (items: api.FeedItem[]) =>
        items.filter((i) => i.assignees.length === 0 || i.assignees.some((a) => a.id === userId))
      // Their day: what's due today plus anything of theirs still past due.
      setDay([...mine(feed.overdue), ...mine(feed.today)])
      setError(null)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load this profile.')
    }
  }, [userId])

  useEffect(() => {
    refresh()
  }, [refresh])

  async function pickMood(level: api.MoodLevel) {
    if (!profile) return
    setBusy(true)
    try {
      // Tapping the current mood again clears it.
      if (profile.mood?.level === level) await api.clearMyMood()
      else await api.setMyMood(level, false)
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  async function onPickAvatar(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // let the same file be re-picked after an error
    if (!file) return
    setAvatarBusy(true)
    setError(null)
    try {
      // The server returns the fresh profile (new avatar_updated_at), so the
      // photo swaps in immediately without another round-trip.
      setProfile(await api.uploadAvatar(userId, file))
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not upload that photo.')
    } finally {
      setAvatarBusy(false)
    }
  }

  async function removeAvatar() {
    setAvatarBusy(true)
    setError(null)
    try {
      await api.removeAvatar(userId)
      await refresh()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not remove that photo.')
    } finally {
      setAvatarBusy(false)
    }
  }

  async function saveBio() {
    setBusy(true)
    try {
      await api.updateMyProfile({ bio: bioDraft })
      setEditingBio(false)
      await refresh()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not save.')
    } finally {
      setBusy(false)
    }
  }

  if (!profile) return <FormError message={error} />

  const joined = new Date(profile.created_at).toLocaleDateString(undefined, {
    month: 'long',
    year: 'numeric',
  })
  const moodMeta = profile.mood ? MOODS[profile.mood.level] : null

  return (
    <div>
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass mb-4 flex flex-col items-center gap-3 p-7 text-center"
      >
        <div className="relative">
          <Avatar
            name={profile.display_name}
            mood={profile.mood}
            size="lg"
            src={api.avatarUrl(profile)}
            className={avatarBusy ? 'opacity-50' : ''}
          />
          {canEditAvatar && (
            // A camera pip in the top corner (the mood badge owns the bottom
            // one). The label wraps a hidden picker; accept="image/*" lets a
            // phone offer camera or library.
            <label
              aria-label="Change photo"
              className="absolute -right-1 -top-1 flex h-8 w-8 cursor-pointer items-center justify-center rounded-full bg-accent text-white shadow-lg ring-2 ring-[var(--bg-base)] transition-transform hover:scale-105"
            >
              <Camera className="h-4 w-4" strokeWidth={2} />
              <input
                type="file"
                accept="image/*"
                className="hidden"
                disabled={avatarBusy}
                onChange={onPickAvatar}
              />
            </label>
          )}
        </div>
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{profile.display_name}</h2>
          <p className="text-sm text-fg/50">@{profile.username}</p>
          {canEditAvatar && profile.avatar_updated_at && (
            <button
              onClick={removeAvatar}
              disabled={avatarBusy}
              className="mt-1 text-xs font-medium text-fg/40 underline decoration-fg/20 underline-offset-2 hover:text-fg/70 disabled:opacity-50"
            >
              Remove photo
            </button>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="rounded-full bg-fg/10 px-2.5 py-1 text-[11px] font-semibold text-fg/70">
            {profile.role === 'parent' ? 'Parent' : 'Child'}
          </span>
          {profile.is_owner ? (
            <span className="flex items-center gap-1 rounded-full bg-gold/20 px-2.5 py-1 text-[11px] font-semibold text-gold">
              <ShieldCheck className="h-3 w-3" /> Server admin
            </span>
          ) : profile.is_admin ? (
            <span className="flex items-center gap-1 rounded-full bg-accent-bright/20 px-2.5 py-1 text-[11px] font-semibold text-accent-bright">
              <ShieldCheck className="h-3 w-3" /> Admin
            </span>
          ) : null}
        </div>
        <p className="text-xs text-fg/35">Here since {joined}</p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="glass mb-4 p-5"
      >
        <div className="mb-2 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-fg/40">Status</p>
            {isSelf && <p className="mt-0.5 text-[11px] text-fg/35">Clears each night</p>}
          </div>
          {isSelf && !editingBio && (
            <button
              onClick={() => {
                setBioDraft(profile.bio)
                setEditingBio(true)
              }}
              aria-label="Edit status"
              className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg"
            >
              <Pencil className="h-4 w-4" />
            </button>
          )}
        </div>
        {editingBio ? (
          <div className="flex flex-col gap-3">
            <textarea
              value={bioDraft}
              onChange={(e) => setBioDraft(e.target.value)}
              maxLength={500}
              rows={3}
              className="field resize-none"
              placeholder="How are you doing?"
              autoFocus
            />
            <div className="grid grid-cols-2 gap-2">
              <Button variant="ghost" onClick={() => setEditingBio(false)} disabled={busy}>
                Cancel
              </Button>
              <Button onClick={saveBio} disabled={busy}>
                {busy ? 'Saving' : 'Save'}
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-sm leading-relaxed text-fg/70">
            {profile.bio || <span className="text-fg/35">No status yet.</span>}
          </p>
        )}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="glass p-5"
      >
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-fg/40">
          {isSelf ? 'How is your day' : 'Their day'}
        </p>

        {isSelf ? (
          <>
            <div className="grid grid-cols-5 gap-2">
              {MOOD_ORDER.map((level) => {
                const meta = MOODS[level]
                const active = profile.mood?.level === level
                return (
                  <button
                    key={level}
                    onClick={() => pickMood(level)}
                    disabled={busy}
                    className={`flex flex-col items-center gap-1.5 rounded-xl border px-1 py-3 transition-colors ${
                      active
                        ? `border-fg/30 ${meta.chip}`
                        : 'border-fg/10 bg-fg/5 hover:bg-fg/10'
                    }`}
                  >
                    <meta.Icon className={`h-6 w-6 ${meta.tint}`} strokeWidth={2} />
                    <span className={`text-[10px] font-semibold ${active ? 'text-fg' : 'text-fg/50'}`}>
                      {meta.label}
                    </span>
                  </button>
                )
              })}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-fg/35">
              The family sees your mood on your avatar. Tap the current one to clear it.
            </p>
          </>
        ) : moodMeta ? (
          <div className={`flex items-center gap-3 rounded-xl px-4 py-3 ${moodMeta.chip}`}>
            <moodMeta.Icon className={`h-6 w-6 ${moodMeta.tint}`} strokeWidth={2} />
            <span className="font-semibold">{moodMeta.label} today</span>
          </div>
        ) : (
          <p className="text-sm text-fg/40">No mood shared today.</p>
        )}
      </motion.div>

      {day && (
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="glass mt-4 p-5"
        >
          <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-fg/40">
            {isSelf ? 'On your board' : 'On their board'}
          </p>

          {day.length === 0 ? (
            <p className="text-sm text-fg/40">Nothing assigned today.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {day.map((item) => (
                <li key={item.id} className="flex items-center gap-3 rounded-xl px-1 py-2">
                  <span
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-lg ${
                      item.completed ? 'bg-emerald-400/25' : 'bg-fg/10'
                    }`}
                  >
                    {item.completed ? (
                      <Check className="h-3.5 w-3.5 text-emerald-300" strokeWidth={2.5} />
                    ) : (
                      <Circle className="h-3 w-3 text-fg/40" strokeWidth={2} />
                    )}
                  </span>
                  <span
                    className={`min-w-0 flex-1 truncate text-sm ${
                      item.completed
                        ? 'text-fg/45 line-through decoration-fg/30'
                        : 'text-fg/85'
                    }`}
                  >
                    {item.title}
                  </span>
                  {item.time_of_day && (
                    <span className="shrink-0 text-xs font-medium text-fg/45">
                      {formatTime(item.time_of_day)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </motion.div>
      )}

      <FormError message={error} />
    </div>
  )
}
