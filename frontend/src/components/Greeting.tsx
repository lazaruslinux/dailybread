import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import * as api from '../lib/api'
import { MOODS, MOOD_ORDER, timeGreeting } from '../lib/moods'
import { Button, Field } from './ui'
import { Sheet } from './recipes'

// The first open of the day says hello and offers to set today's mood and
// status. Once is once: saving, a mood already set on another device, or
// "I'll set it later" all quiet it until tomorrow. Re-offering on every
// visit read as nagging.

const dayKey = (id: number) => `db_greet_${id}`

export function DailyGreeting() {
  const { user } = useAuth()
  const [profile, setProfile] = useState<api.Profile | null>(null)
  const [mood, setMood] = useState<api.MoodLevel | null>(null)
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!user) return
    const today = api.localDate()
    if (localStorage.getItem(dayKey(user.id)) === today) return
    let cancelled = false
    api
      .getProfile(user.id)
      .then((p) => {
        if (cancelled) return
        if (p.mood) {
          // Today's mood is already set; nothing left to ask.
          localStorage.setItem(dayKey(user.id), today)
          return
        }
        setStatus(p.bio)
        setProfile(p)
      })
      .catch(() => {
        // A failed fetch just means no greeting this visit.
      })
    return () => {
      cancelled = true
    }
  }, [user])

  if (!user || !profile) return null

  const later = () => {
    localStorage.setItem(dayKey(user.id), api.localDate())
    setProfile(null)
  }

  const save = async () => {
    setBusy(true)
    try {
      if (mood) await api.setMyMood(mood, false)
      if (status.trim() !== profile.bio) await api.updateMyProfile({ bio: status.trim() })
      localStorage.setItem(dayKey(user.id), api.localDate())
      window.dispatchEvent(new Event('db:profile-changed'))
      setProfile(null)
    } catch {
      setBusy(false)
    }
  }

  const firstName = user.display_name.split(/\s+/)[0]
  const dirty = mood !== null || status.trim() !== profile.bio

  return (
    <Sheet onClose={later}>
      <h2 className="font-display text-xl font-semibold tracking-[-0.02em]" data-greeting>
        {timeGreeting()}, {firstName}
      </h2>
      <p className="mb-3 mt-1 text-xs leading-relaxed text-fg/50">
        How's your day looking? Set a mood and status for the family board, or come back to it
        later.
      </p>

      <div className="grid grid-cols-5 gap-2">
        {MOOD_ORDER.map((level) => {
          const meta = MOODS[level]
          const active = mood === level
          return (
            <button
              key={level}
              type="button"
              onClick={() => setMood(active ? null : level)}
              className={`flex flex-col items-center gap-1 rounded-xl border px-1 py-2.5 transition-colors ${
                active ? `border-fg/30 ${meta.chip}` : 'border-fg/10 bg-fg/5 hover:bg-fg/10'
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

      <div className="mt-3">
        <Field
          label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          placeholder="optional"
          maxLength={500}
        />
      </div>

      <div className="mt-4 flex flex-col gap-2">
        <Button type="button" onClick={save} disabled={busy || !dirty}>
          {busy ? 'Saving' : 'Save'}
        </Button>
        <button
          type="button"
          onClick={later}
          className="rounded-xl px-3 py-2 text-sm font-semibold text-fg/50 transition-colors hover:bg-fg/10 hover:text-fg"
        >
          I'll set it later
        </button>
      </div>
    </Sheet>
  )
}
