import { AnimatePresence, motion } from 'framer-motion'
import { BookOpen, Check, ChevronDown, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import * as api from '../lib/api'
import { verseLink, versesForDate } from '../lib/verses'

// The day's scripture, kept at the very bottom of the board. There are three
// verses for the day (deterministic from the date, so the whole family sees the
// same set) and small arrows to browse them. The verse text links out to the
// passage on Bible.com (NKJV), which hands off to the YouVersion app when it's
// installed. All text is bundled with the app (see lib/verses.ts for licensing),
// so the card renders offline and phones home to no one.
//
// Members who opted in (You -> Daily verses) can check each verse off; a
// checked verse settles quiet, and once all three are read the card folds to a
// slim "Read today" line for the rest of the day — tappable to reopen. The
// streak counts consecutive fully-read days and wears the little book badge
// by their avatar.
export function VerseCard() {
  const verses = versesForDate(new Date())
  const [idx, setIdx] = useState(0)
  const [state, setState] = useState<api.Verses | null>(null)
  const [collapsed, setCollapsed] = useState(false)
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

  const enabled = state?.enabled ?? false
  const checked = enabled && (state?.checks[idx] ?? false)
  const allRead = enabled && (state?.checks.every(Boolean) ?? false)

  async function toggle() {
    if (!state) return
    try {
      const next = checked ? await api.uncheckVerse(idx) : await api.checkVerse(idx)
      setState(next)
      if (next.checks.every(Boolean)) {
        // Let the last check land visually, then fold for the day.
        foldTimer.current = window.setTimeout(() => setCollapsed(true), 700)
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
        className="glass mt-6 flex w-full items-center gap-2.5 px-4 py-3 text-left"
        data-verse-card-folded
      >
        <BookOpen className="h-4 w-4 shrink-0 text-gold/80" strokeWidth={2} />
        <span className="min-w-0 flex-1 truncate text-sm text-fg/60">Read today</span>
        {(state?.streak ?? 0) > 0 && (
          <span className="shrink-0 rounded-full border border-gold/40 bg-gold/10 px-2 py-0.5 text-[11px] font-bold text-gold">
            x{state?.streak}
          </span>
        )}
        <ChevronDown className="h-4 w-4 shrink-0 text-fg/35" />
      </motion.button>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 26 }}
      className="glass mt-6 p-4"
      data-verse-card
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-gold/70">
          <BookOpen className="h-3.5 w-3.5" strokeWidth={2} />
          Daily bread
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Previous verse"
            onClick={() => setIdx((i) => (i - 1 + n) % n)}
            className="rounded-lg p-1 text-fg/40 transition-colors hover:bg-fg/10 hover:text-fg/75"
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
            className="rounded-lg p-1 text-fg/40 transition-colors hover:bg-fg/10 hover:text-fg/75"
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
            <p className="font-reading text-[17.5px] leading-relaxed text-fg/90">{verse.text}</p>
          </a>
          <div className="mt-2 flex items-center justify-between gap-3">
            <a
              href={verseLink(verse)}
              target="_blank"
              rel="noopener noreferrer"
              className={`flex items-center gap-1 text-xs font-medium text-fg/45 ${checked ? 'opacity-60' : ''}`}
            >
              {verse.ref} NKJV
              <ExternalLink className="h-3 w-3" strokeWidth={2} />
            </a>
            {enabled && (
              <button
                type="button"
                onClick={toggle}
                aria-pressed={checked}
                aria-label={checked ? `Mark ${verse.ref} unread` : `Mark ${verse.ref} read`}
                className={`flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                  checked
                    ? 'border-gold/50 bg-gold/15 text-gold'
                    : 'border-fg/15 bg-fg/5 text-fg/55 hover:bg-fg/10'
                }`}
              >
                <Check className="h-3.5 w-3.5" strokeWidth={3} />
                {checked ? 'Read' : 'Mark read'}
              </button>
            )}
          </div>
          {allRead && !collapsed && (
            <p className="mt-2 text-center text-[11px] font-semibold text-gold/70">
              All three read today{(state?.streak ?? 0) > 1 ? ` · ${state?.streak} days running` : ''}
            </p>
          )}
        </motion.div>
      </AnimatePresence>
    </motion.div>
  )
}
