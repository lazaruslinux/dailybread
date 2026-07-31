import { motion } from 'framer-motion'
import { Camera, Check, Circle, Pencil, ShieldCheck } from 'lucide-react'
import { type ChangeEvent, useCallback, useEffect, useState } from 'react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Avatar } from '../components/Avatar'
import { Coin } from '../components/BreadIcon'
import { LevelBadge, TIER_META, tierOf } from '../components/LevelBadge'
import { AvatarCrop } from '../components/AvatarCrop'
import { Button, FormError } from '../components/ui'
import { formatTime, MOODS, MOOD_ORDER } from '../lib/moods'

// A member's page: who they are, their bio, and how their day is going.
// Everything self-serve is inline: your own page grows a mood picker and a
// bio editor; someone else's page is read-only.
export function Profile({
  userId,
  onOpenCrumbs,
}: {
  userId: number
  // Present only where a breadcrumbs explainer can open (the You tab).
  onOpenCrumbs?: () => void
}) {
  const { user: viewer } = useAuth()
  const isSelf = viewer?.id === userId

  const [profile, setProfile] = useState<api.Profile | null>(null)
  // This member's slice of the board: cards assigned to them plus whole-family
  // cards (those are everyone's, so they belong on everyone's day).
  const [day, setDay] = useState<api.FeedItem[] | null>(null)
  // Kid privacy's flip side: a minor's journal, readable by their parents.
  const [journal, setJournal] = useState<api.JournalEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editingBio, setEditingBio] = useState(false)
  const [bioDraft, setBioDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [avatarBusy, setAvatarBusy] = useState(false)
  // A freshly picked photo waits in the crop sheet until it's framed.
  const [cropFile, setCropFile] = useState<File | null>(null)
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
      if (viewer?.role === 'parent' && viewer.id !== userId && p.is_minor) {
        // Separate so a hiccup here never blanks the profile.
        api.getMemberJournal(userId).then(setJournal).catch(() => {})
      }
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load this profile.')
    }
  }, [userId, viewer])

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

  function onPickAvatar(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // let the same file be re-picked after a cancel
    if (file) setCropFile(file)
  }

  async function uploadCropped(blob: Blob) {
    setAvatarBusy(true)
    setError(null)
    try {
      // The server returns the fresh profile (new avatar_updated_at), so the
      // photo swaps in immediately without another round-trip.
      setProfile(await api.uploadAvatar(userId, blob))
      setCropFile(null)
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
      {cropFile && (
        <AvatarCrop
          file={cropFile}
          busy={avatarBusy}
          onCancel={() => setCropFile(null)}
          onSave={uploadCropped}
        />
      )}
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass mb-3 flex flex-col items-center gap-2.5 p-4 text-center"
      >
        <div className="relative">
          <Avatar
            name={profile.display_name}
            mood={profile.mood?.level ?? null}
            size="lg"
            src={api.avatarUrl(profile)}
            className={avatarBusy ? 'opacity-50' : ''}
          />
          {canEditAvatar && (
            // A camera pip in the top corner (the mood dot owns the bottom
            // one). The label wraps a hidden picker; accept="image/*"
            // lets a phone offer camera or library.
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
          <h2 className="text-xl font-bold tracking-tight">{profile.display_name}</h2>
          <p className="text-[13px] text-fg/50">@{profile.username}</p>
          {moodMeta && (
            <p className="mt-1.5 flex items-center justify-center gap-1.5 text-sm text-fg/70">
              <moodMeta.Icon className={`h-4 w-4 ${moodMeta.tint}`} strokeWidth={2.5} />
              {moodMeta.label}
            </p>
          )}
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
        {/* The economy panel: the level circle, the tier's name, and how far
            to the next one. Warm numbers, no meters screaming for attention. */}
        <div className="flex w-full max-w-64 flex-col items-center gap-2" data-economy>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-fg/55">Level</span>
            <LevelBadge level={profile.level} size="md" />
            <span className={`text-sm font-bold ${TIER_META[tierOf(profile.level)].text}`}>
              {TIER_META[tierOf(profile.level)].label}
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-fg/10">
            <div
              className="h-full rounded-full bg-gold/70 transition-all"
              style={{ width: `${Math.min((profile.level_progress / profile.next_level_cost) * 100, 100)}%` }}
            />
          </div>
          <p className="flex items-center gap-1 text-[11px] text-fg/40">
            <span
              className="flex items-center gap-1 font-semibold text-gold"
              title={`${profile.crumbs} breadcrumb${profile.crumbs === 1 ? '' : 's'} earned`}
            >
              <Coin className="h-3.5 w-3.5" />
              {profile.crumbs}
            </span>
            · {profile.next_level_cost - profile.level_progress} to level {profile.level + 1}
          </p>
          {isSelf && onOpenCrumbs && (
            <button
              onClick={onOpenCrumbs}
              className="-my-3.5 flex min-h-11 items-center self-center rounded-lg px-3 text-xs font-semibold text-accent-bright"
            >
              How do breadcrumbs work?
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
        className="glass mb-3 p-3.5"
      >
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <div>
            <p className="db-micro">Status</p>
            {isSelf && <p className="mt-0.5 text-[11px] text-fg/35">Clears each night</p>}
          </div>
          {isSelf && !editingBio && (
            <button
              onClick={() => {
                setBioDraft(profile.bio)
                setEditingBio(true)
              }}
              aria-label="Edit status"
              className="-m-2 rounded-lg p-3.5 text-fg/50 hover:bg-fg/10 hover:text-fg"
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
        className="glass p-3.5"
      >
        <p className="db-micro mb-2.5">{isSelf ? 'How is your day' : 'Their day'}</p>

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
                    className={`flex flex-col items-center gap-1 rounded-xl border px-1 py-2.5 transition-colors ${
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
            <p className="mt-2.5 text-xs leading-relaxed text-fg/35">
              The family sees your mood on your profile. Tap the current one to clear it.
            </p>
          </>
        ) : moodMeta ? (
          <div className={`flex items-center gap-3 rounded-xl px-3.5 py-2.5 ${moodMeta.chip}`}>
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
          className="glass db-pad mt-3 overflow-hidden"
        >
          <div className="db-card-h">
            <span className="db-micro">{isSelf ? 'On your board' : 'On their board'}</span>
          </div>

          {day.length === 0 ? (
            <p className="db-emptyline">Nothing assigned today.</p>
          ) : (
            <ul>
              {day.map((item) => (
                <li key={item.id} className="db-row">
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
                    className={`min-w-0 flex-1 truncate text-[14.5px] ${
                      item.completed
                        ? 'text-fg/45 line-through decoration-fg/30'
                        : 'text-fg/85'
                    }`}
                  >
                    {item.title}
                  </span>
                  {item.time_of_day && (
                    <span className="db-chip db-chip-plain whitespace-nowrap tabular-nums">
                      {formatTime(item.time_of_day)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </motion.div>
      )}

      {journal && journal.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass mt-3 p-3.5"
        >
          <p className="db-micro mb-1">Their journal</p>
          <p className="mb-2.5 text-[11px] text-fg/35">
            Visible to parents while they're a kid.
          </p>
          <div className="flex flex-col gap-2.5">
            {journal.slice(0, 7).map((entry) => (
              <div key={entry.date_for}>
                <p className="mb-0.5 text-[11px] font-semibold text-fg/45">
                  {new Date(`${entry.date_for}T12:00:00`).toLocaleDateString(undefined, {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                  })}
                </p>
                <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-fg/75">
                  {entry.body}
                </p>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      <FormError message={error} />
    </div>
  )
}
