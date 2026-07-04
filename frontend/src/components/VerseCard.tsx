import { motion } from 'framer-motion'
import { BookOpen, ExternalLink } from 'lucide-react'
import { verseForDate, verseLink } from '../lib/verses'

// The day's verse, kept at the very bottom of the board: the last thing
// read after the day's cards. The whole card is a link that opens the
// passage on Bible.com (NKJV), which hands off to the YouVersion app when
// it's installed. Text shown here is NKJV bundled with the app (see
// lib/verses.ts for the licensing notes), so the card renders offline and
// phones home to no one.
export function VerseCard() {
  const verse = verseForDate(new Date())

  return (
    <motion.a
      href={verseLink(verse)}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`Daily verse, ${verse.ref}. Read on Bible.com`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 26 }}
      className="glass mt-6 block p-4"
      data-verse-card
    >
      <span className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-amber-200/70">
        <BookOpen className="h-3.5 w-3.5" strokeWidth={2} />
        Daily bread
      </span>
      <p className="text-[15px] leading-relaxed text-white/90">{verse.text}</p>
      <span className="mt-2 flex items-center gap-1 text-xs font-medium text-white/45">
        {verse.ref} NKJV
        <ExternalLink className="h-3 w-3" strokeWidth={2} />
      </span>
    </motion.a>
  )
}
