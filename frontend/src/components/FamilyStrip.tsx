import { BookOpen } from 'lucide-react'
import { motion } from 'framer-motion'
import { avatarUrl, type FamilyMember } from '../lib/api'
import { MOODS } from '../lib/moods'
import { Avatar } from './Avatar'

// The row of faces under the header. The circle stays a clean photo; the
// person's day sits in a tight little row under their name — mood weather
// and the reading-streak book, side by side.
export function FamilyStrip({
  members,
  onOpen,
}: {
  members: FamilyMember[]
  onOpen: (id: number) => void
}) {
  if (!members.length) return null
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-5 flex gap-4 overflow-x-auto pb-1"
    >
      {members.map((m) => {
        const moodMeta = m.mood ? MOODS[m.mood.level] : null
        const streak = m.verse_streak ?? 0
        return (
          <button
            key={m.id}
            onClick={() => onOpen(m.id)}
            className="flex min-w-0 flex-col items-center gap-1 rounded-xl px-1 py-1 transition-opacity hover:opacity-80"
          >
            <Avatar name={m.display_name} src={avatarUrl(m)} />
            <span className="max-w-14 truncate text-[11px] font-medium text-fg/60">
              {m.display_name.split(/\s+/)[0]}
            </span>
            {(moodMeta || streak > 0) && (
              <span className="-mt-0.5 flex items-center gap-1">
                {moodMeta && (
                  <span
                    className={`flex h-4.5 items-center rounded-full px-1 ${moodMeta.chip}`}
                    title={moodMeta.label}
                  >
                    <moodMeta.Icon className={`h-3 w-3 ${moodMeta.tint}`} strokeWidth={2.5} />
                  </span>
                )}
                {streak > 0 && (
                  <span
                    className="flex h-4.5 items-center gap-px rounded-full border border-gold/40 bg-gold/10 px-1 text-[9px] font-bold text-gold"
                    title={`${streak}-day reading streak`}
                  >
                    <BookOpen className="h-3 w-3" strokeWidth={2.5} />
                    x{streak}
                  </span>
                )}
              </span>
            )}
          </button>
        )
      })}
    </motion.div>
  )
}
