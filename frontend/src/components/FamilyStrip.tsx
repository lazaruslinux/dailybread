import { motion } from 'framer-motion'
import { avatarUrl, type FamilyMember } from '../lib/api'
import { Avatar } from './Avatar'
import { LevelBadge } from './LevelBadge'

// The row of faces under the header. The circle stays a clean photo with the
// mood dot on its corner; the level sits in its little circle to the LEFT of
// the name. Everything else about a person lives behind the tap.
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
          className="flex min-w-0 flex-col items-center gap-1 rounded-xl px-1 py-1 transition-opacity hover:opacity-80"
        >
          <Avatar name={m.display_name} src={avatarUrl(m)} mood={m.mood?.level ?? null} />
          <span className="flex max-w-16 items-center gap-1">
            <LevelBadge level={m.level} />
            <span className="min-w-0 truncate text-[11px] font-medium text-fg/60">
              {m.display_name.split(/\s+/)[0]}
            </span>
          </span>
        </button>
      ))}
    </motion.div>
  )
}
