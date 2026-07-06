import { AnimatePresence, motion } from 'framer-motion'
import { BookOpen, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react'
import { useState } from 'react'
import { verseLink, versesForDate } from '../lib/verses'

// The day's scripture, kept at the very bottom of the board. There are three
// verses for the day (deterministic from the date, so the whole family sees the
// same set) and small arrows to browse them. The verse text links out to the
// passage on Bible.com (NKJV), which hands off to the YouVersion app when it's
// installed. All text is bundled with the app (see lib/verses.ts for licensing),
// so the card renders offline and phones home to no one.
export function VerseCard() {
  const verses = versesForDate(new Date())
  const [idx, setIdx] = useState(0)
  const verse = verses[idx]
  const n = verses.length

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
                  i === idx ? 'bg-gold/80' : 'bg-fg/20'
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
        <motion.a
          key={idx}
          href={verseLink(verse)}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Daily verse, ${verse.ref}. Read on Bible.com`}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.16 }}
          className="block"
        >
          <p className="font-reading text-[17.5px] leading-relaxed text-fg/90">{verse.text}</p>
          <span className="mt-2 flex items-center gap-1 text-xs font-medium text-fg/45">
            {verse.ref} NKJV
            <ExternalLink className="h-3 w-3" strokeWidth={2} />
          </span>
        </motion.a>
      </AnimatePresence>
    </motion.div>
  )
}
