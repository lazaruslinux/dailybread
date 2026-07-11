import { motion } from 'framer-motion'
import { avatarUrl, type FamilyMember } from '../lib/api'
import { Avatar } from './Avatar'

// The row of faces under the header: everyone in the family with today's
// mood on their avatar. Tapping someone opens their profile.
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
      {members.map((m) => (
        <button
          key={m.id}
          onClick={() => onOpen(m.id)}
          className="flex min-w-0 flex-col items-center gap-1.5 rounded-xl px-1 py-1 transition-opacity hover:opacity-80"
        >
          <Avatar name={m.display_name} verseStreak={m.verse_streak} src={avatarUrl(m)} />
          <span className="max-w-14 truncate text-[11px] font-medium text-fg/60">
            {m.display_name.split(/\s+/)[0]}
          </span>
        </button>
      ))}
    </motion.div>
  )
}
