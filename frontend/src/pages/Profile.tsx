import { motion } from 'framer-motion'
import { Check, Circle, EyeOff, Pencil, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
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
  // This member's slice of the board: cards assigned to them, today + anytime.
  const [day, setDay] = useState<{ today: api.FeedItem[]; anytime: api.FeedItem[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editingBio, setEditingBio] = useState(false)
  const [bioDraft, setBioDraft] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [p, feed] = await Promise.all([api.getProfile(userId), api.getFeed()])
      setProfile(p)
      const mine = (items: api.FeedItem[]) => items.filter((i) => i.assignee?.id === userId)
      setDay({ today: mine(feed.today), anytime: mine(feed.anytime) })
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
      else await api.setMyMood(level, profile.mood?.hidden ?? false)
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  async function toggleHidden() {
    if (!profile?.mood) return
    setBusy(true)
    try {
      await api.setMyMood(profile.mood.level, !profile.mood.hidden)
      await refresh()
    } finally {
      setBusy(false)
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
        <Avatar name={profile.display_name} mood={profile.mood} size="lg" />
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{profile.display_name}</h2>
          <p className="text-sm text-white/50">@{profile.username}</p>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-semibold text-white/70">
            {profile.role === 'parent' ? 'Parent' : 'Child'}
          </span>
          {profile.is_admin && (
            <span className="flex items-center gap-1 rounded-full bg-indigo-400/20 px-2.5 py-1 text-[11px] font-semibold text-indigo-200">
              <ShieldCheck className="h-3 w-3" /> Admin
            </span>
          )}
        </div>
        <p className="text-xs text-white/35">Here since {joined}</p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="glass mb-4 p-5"
      >
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-widest text-white/40">About</p>
          {isSelf && !editingBio && (
            <button
              onClick={() => {
                setBioDraft(profile.bio)
                setEditingBio(true)
              }}
              aria-label="Edit bio"
              className="rounded-lg p-1.5 text-white/50 hover:bg-white/10 hover:text-white"
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
              placeholder="A line about you"
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
          <p className="text-sm leading-relaxed text-white/70">
            {profile.bio || <span className="text-white/35">Nothing here yet.</span>}
          </p>
        )}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="glass p-5"
      >
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-white/40">
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
                        ? `border-white/30 ${meta.chip}`
                        : 'border-white/10 bg-white/5 hover:bg-white/10'
                    }`}
                  >
                    <meta.Icon className={`h-6 w-6 ${meta.tint}`} strokeWidth={2} />
                    <span className={`text-[10px] font-semibold ${active ? 'text-white' : 'text-white/50'}`}>
                      {meta.label}
                    </span>
                  </button>
                )
              })}
            </div>
            {profile.mood && (
              <label className="mt-4 flex cursor-pointer items-center justify-between rounded-xl border border-white/10 bg-white/5 px-4 py-3">
                <span className="flex items-center gap-2 text-sm font-semibold text-white/80">
                  <EyeOff className="h-4 w-4 text-white/50" /> Keep it to myself
                </span>
                <input
                  type="checkbox"
                  checked={profile.mood.hidden}
                  onChange={toggleHidden}
                  disabled={busy}
                  className="h-5 w-5 accent-indigo-400"
                />
              </label>
            )}
            <p className="mt-3 text-xs leading-relaxed text-white/35">
              The family sees your mood on your avatar unless you keep it to yourself. Tap the
              current one to clear it.
            </p>
          </>
        ) : moodMeta ? (
          <div className={`flex items-center gap-3 rounded-xl px-4 py-3 ${moodMeta.chip}`}>
            <moodMeta.Icon className={`h-6 w-6 ${moodMeta.tint}`} strokeWidth={2} />
            <span className="font-semibold">{moodMeta.label} today</span>
          </div>
        ) : (
          <p className="text-sm text-white/40">No mood shared today.</p>
        )}
      </motion.div>

      {day && (
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="glass mt-4 p-5"
        >
          <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-white/40">
            {isSelf ? 'On your board' : 'On their board'}
          </p>

          {day.today.length === 0 && day.anytime.length === 0 ? (
            <p className="text-sm text-white/40">Nothing assigned today.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {[...day.today, ...day.anytime].map((item) => (
                <li key={item.id} className="flex items-center gap-3 rounded-xl px-1 py-2">
                  <span
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-lg ${
                      item.completed ? 'bg-emerald-400/25' : 'bg-white/10'
                    }`}
                  >
                    {item.completed ? (
                      <Check className="h-3.5 w-3.5 text-emerald-300" strokeWidth={2.5} />
                    ) : (
                      <Circle className="h-3 w-3 text-white/40" strokeWidth={2} />
                    )}
                  </span>
                  <span
                    className={`min-w-0 flex-1 truncate text-sm ${
                      item.completed
                        ? 'text-white/45 line-through decoration-white/30'
                        : 'text-white/85'
                    }`}
                  >
                    {item.title}
                  </span>
                  {item.time_of_day && (
                    <span className="shrink-0 text-xs font-medium text-white/45">
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
