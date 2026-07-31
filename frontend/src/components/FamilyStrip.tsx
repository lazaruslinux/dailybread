import { motion } from 'framer-motion'
import { avatarUrl, type FamilyMember } from '../lib/api'
import { Avatar } from './Avatar'
import { LevelBadge } from './LevelBadge'

// The row of faces under the header, as pill rows. The circle stays a clean
// photo with the mood weather icon on its corner; the level sits in its little
// circle after the name. Everything else about a person lives behind the tap.
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
      className="flex gap-2 overflow-x-auto p-px"
    >
      {members.map((m) => (
        // Not .glass: that class is unlayered, so its own radius would beat
        // rounded-full. The pill spells the surface out with the same tokens.
        <button
          key={m.id}
          onClick={() => onOpen(m.id)}
          className="flex min-h-11 shrink-0 items-center gap-2 rounded-full border border-[var(--glass-border)] bg-[var(--card)] py-1 pl-[7px] pr-3 shadow-[var(--card-shadow)] transition-opacity hover:opacity-80"
        >
          <Avatar name={m.display_name} src={avatarUrl(m)} mood={m.mood?.level ?? null} size="sm" />
          <span className="max-w-24 truncate text-[13.5px] font-semibold text-fg/80">
            {m.display_name.split(/\s+/)[0]}
          </span>
          <LevelBadge level={m.level} />
        </button>
      ))}
    </motion.div>
  )
}
