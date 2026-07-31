import { AnimatePresence, motion } from 'framer-motion'
import { BookOpen, Check, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, ExternalLink, Zap } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import * as api from '../lib/api'
import { verseLink, versesForDate } from '../lib/verses'
import { CrumbFloat } from './CrumbFloat'

// The day's scripture, kept at the very bottom of the board. There are three
// verses for the day (deterministic from the date, so the whole family sees the
// same set) and small arrows to browse them. The verse text links out to the
// passage on Bible.com (NKJV), which hands off to the YouVersion app when it's
// installed. All text is bundled with the app (see lib/verses.ts for licensing),
// so the card renders offline and phones home to no one.
//
// Members who opted in (You -> Daily verses) can check each verse off.
// Checks are one-way — reading happened; the fold arrow is how the card gets
// out of the way — and once all three are read the +3 breadcrumbs drift up
// and the card folds to a slim "Read today" line, tappable to reopen. The
// streak counts consecutive fully-read days and feeds the milestones.
export function VerseCard() {
  const verses = versesForDate(new Date())
  const [idx, setIdx] = useState(0)
  const [state, setState] = useState<api.Verses | null>(null)
  const [collapsed, setCollapsed] = useState(false)
  // A fresh key per award so the float re-mounts (and re-animates) each time.
  const [float, setFloat] = useState<{ amount: number; key: number } | null>(null)
  const foldTimer = useRef<number | undefined>(undefined)
  const verse = verses[idx]
  const n = verses.length

  useEffect(() => {
    api
      .getVerses()
      .then((v) => {
        setState(v)
        if (v.enabled && v.checks.every(Boolean)) setCollapsed(true)
      })
      .catch(() => {})
    return () => window.clearTimeout(foldTimer.current)
  }, [])

  // The verses themselves are the opt-in now: members who haven't turned
  // them on see nothing here at all (and nothing while the answer loads, so
  // opted-out boards never flash the card).
  if (state === null || !state.enabled) return null

  const enabled = true
  const checked = state.checks[idx] ?? false
  const allRead = state.checks.every(Boolean)

  async function markRead() {
    if (!state || checked) return // one-way: a read verse stays read
    try {
      const next = await api.checkVerse(idx)
      setState(next)
      // The strip should update the moment anything about the person does;
      // Home already refreshes on this event.
      window.dispatchEvent(new Event('db:profile-changed'))
      if (next.crumbs_awarded > 0) {
        setFloat({ amount: next.crumbs_awarded, key: Date.now() })
      }
      if (next.checks.every(Boolean)) {
        // Let the last check (and its +3) land visually, then fold for the day.
        foldTimer.current = window.setTimeout(() => setCollapsed(true), 1500)
      }
    } catch {
      // The tap simply doesn't stick; the next one tries again.
    }
  }

  if (enabled && collapsed) {
    return (
      <motion.button
        type="button"
        onClick={() => setCollapsed(false)}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="glass flex min-h-11 w-full items-center gap-2.5 px-4 py-2.5 text-left"
        data-verse-card-folded
      >
        <BookOpen className="h-4 w-4 shrink-0 text-gold/80" strokeWidth={2} />
        <span className="min-w-0 flex-1 truncate text-[11px] font-bold uppercase tracking-[0.09em] text-gold/80">
          Daily bread
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-fg/35" />
      </motion.button>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 26 }}
      className="glass px-4 pb-3.5 pt-3"
      data-verse-card
    >
      <div className="mb-1.5 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.09em] text-gold/80">
          <BookOpen className="h-3.5 w-3.5" strokeWidth={2} />
          Daily bread
        </span>
        <div className="flex items-center gap-1">
          {allRead && (
            <button
              type="button"
              aria-label="Fold the verses away"
              onClick={() => setCollapsed(true)}
              className="-m-2.5 rounded-lg p-3.5 text-fg/40 transition-colors hover:bg-fg/10 hover:text-fg/75"
            >
              <ChevronUp className="h-4 w-4" strokeWidth={2.5} />
            </button>
          )}
          <button
            type="button"
            aria-label="Previous verse"
            onClick={() => setIdx((i) => (i - 1 + n) % n)}
            className="-m-2.5 rounded-lg p-3.5 text-fg/40 transition-colors hover:bg-fg/10 hover:text-fg/75"
          >
            <ChevronLeft className="h-4 w-4" strokeWidth={2.5} />
          </button>
          <div className="flex items-center gap-1">
            {verses.map((_, i) => (
              <span
                key={i}
                className={`h-1.5 w-1.5 rounded-full transition-colors ${
                  enabled && state?.checks[i]
                    ? 'bg-gold/40'
                    : i === idx
                      ? 'bg-gold/80'
                      : 'bg-fg/20'
                }`}
              />
            ))}
          </div>
          <button
            type="button"
            aria-label="Next verse"
            onClick={() => setIdx((i) => (i + 1) % n)}
            className="-m-2.5 rounded-lg p-3.5 text-fg/40 transition-colors hover:bg-fg/10 hover:text-fg/75"
          >
            <ChevronRight className="h-4 w-4" strokeWidth={2.5} />
          </button>
        </div>
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={idx}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.16 }}
        >
          <a
            href={verseLink(verse)}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Daily verse, ${verse.ref}. Read on Bible.com`}
            className={`block transition-opacity ${checked ? 'opacity-45' : ''}`}
          >
            <p className="font-reading text-[16.5px] leading-[1.55] text-fg/90">{verse.text}</p>
          </a>
          <div className="mt-1.5 flex items-center justify-between gap-3">
            <a
              href={verseLink(verse)}
              target="_blank"
              rel="noopener noreferrer"
              className={`font-reading flex items-center gap-1 text-[12.5px] font-semibold tracking-[0.03em] text-gold ${checked ? 'opacity-60' : ''}`}
            >
              {verse.ref} NKJV
              <ExternalLink className="h-3 w-3" strokeWidth={2} />
            </a>
            {enabled && (
              <span className="relative shrink-0">
                {float && <CrumbFloat key={float.key} amount={float.amount} />}
                <button
                  type="button"
                  onClick={markRead}
                  disabled={checked}
                  aria-pressed={checked}
                  aria-label={checked ? `${verse.ref} read` : `Mark ${verse.ref} read`}
                  className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                    checked
                      ? 'border-gold/50 bg-gold/15 text-gold'
                      : 'border-fg/15 bg-fg/5 text-fg/55 hover:bg-fg/10'
                  }`}
                >
                  <Check className="h-3.5 w-3.5" strokeWidth={3} />
                  {checked ? 'Read' : 'Mark read'}
                </button>
              </span>
            )}
          </div>
          {allRead && !collapsed && (state?.streak ?? 0) > 0 && (
            <p className="mt-1.5 flex items-center justify-center gap-1 text-[11px] font-semibold text-gold/70">
              {state?.streak} day streak
              <Zap className="h-3 w-3 text-gold" strokeWidth={2.5} />
            </p>
          )}
        </motion.div>
      </AnimatePresence>
    </motion.div>
  )
}
