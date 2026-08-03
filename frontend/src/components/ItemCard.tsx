import { motion } from 'framer-motion'
import { Activity, CalendarClock, Check, Circle, Flame, Hourglass, Pencil, Repeat, type LucideIcon , X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { avatarUrl, type FamilyMember, type FeedItem, type ItemKind } from '../lib/api'
import { continuesOn, dateSpanLabel, spansDays } from '../lib/items'
import { formatTimeRange } from '../lib/moods'
import { Avatar } from './Avatar'
import { CrumbFloat } from './CrumbFloat'

export const KIND_STYLE: Record<ItemKind, { Icon: LucideIcon; tint: string; label: string }> = {
  routine: { Icon: Repeat, tint: 'text-sky-300', label: 'Routine' },
  task: { Icon: Circle, tint: 'text-gold', label: 'Task' },
  activity: { Icon: Activity, tint: 'text-emerald-300', label: 'Activity' },
  appointment: { Icon: CalendarClock, tint: 'text-accent-strong', label: 'Appointment' },
}

// A face with a small check badge when that person has done their own bit.
// Used for routines, which are completed per person.
function ParticipantAvatar({
  name,
  src = null,
  done,
  pending = false,
}: {
  name: string
  src?: string | null
  done: boolean
  pending?: boolean
}) {
  return (
    <span className="relative">
      <Avatar
        name={name}
        src={src}
        size="sm"
        className={`ring-2 ring-black/40 ${done || pending ? '' : 'opacity-45'}`}
      />
      {done && (
        <span className="absolute -bottom-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-emerald-400 ring-2 ring-black/40">
          <Check className="h-2.5 w-2.5 text-black" strokeWidth={4} />
        </span>
      )}
      {pending && !done && (
        // Kid mode: this member's mark is waiting on a parent.
        <span className="absolute -bottom-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-amber-400 ring-2 ring-black/40">
          <Hourglass className="h-2 w-2 text-black" strokeWidth={4} />
        </span>
      )}
    </span>
  )
}

// One row on the board. The board is a single card and this is a line in it:
// state mark, title over a muted meta line, then the time chip, who it's for,
// and the edit shortcut. The row completes nothing: the whole line is one tap
// target that opens the detail sheet, and every state change is an explicit
// button in there. Rows that are settled — done, called off, or a calendar
// entry whose moment has gone by — stay in place but visibly retire by
// dimming. The strike through the title is reserved for done: it is this
// app's word for finished, and a passed row has not claimed that.
export function ItemCard({
  item,
  index,
  family,
  flag,
  showDate,
  day,
  passed = false,
  viewerId,
  viewerIsParent,
  onOpen,
  onEdit,
}: {
  item: FeedItem
  index: number
  family?: FamilyMember[]
  flag?: 'overdue' | 'due' | null
  showDate?: boolean
  // The day this card is being drawn on. Only multi-day cards care: past their
  // first day they have no start time left to show.
  day?: string
  // The clock has gone past this occurrence: it fades, but it is not done and
  // is never struck through.
  passed?: boolean
  viewerId?: number
  viewerIsParent?: boolean
  onOpen?: () => void
  onEdit?: () => void
}) {
  const { Icon, tint, label } = KIND_STYLE[item.kind]
  const continuing = day != null && continuesOn(item, day)
  const timeLabel =
    item.all_day || continuing ? 'All day' : formatTimeRange(item.time_of_day, item.end_time)
  // "Mon, Jul 6" — the card's own date, shown for cards that aren't today's
  // (past due and the next-7-days list), so a member can tell them apart
  // without repeated date separators. A card that runs across days always
  // says so: "Jul 30 – Aug 2".
  const dateLine =
    item.date_for && (showDate || spansDays(item))
      ? dateSpanLabel(item.date_for, item.end_date)
      : null
  // Done, called off, or simply gone by: all three read the same way.
  const settled = item.completed || item.cancelled || passed

  // The +n breadcrumb float: Home dispatches db:crumbs when a completion
  // response paid out; the card whose item it was drifts the number up from
  // its state mark. Event-driven so the award needs no prop plumbing
  // through both board views.
  const [float, setFloat] = useState<{ amount: number; key: number } | null>(null)
  useEffect(() => {
    function onCrumbs(e: Event) {
      const detail = (e as CustomEvent).detail as { itemId?: number; amount?: number } | null
      if (detail?.itemId === item.id && (detail.amount ?? 0) > 0) {
        setFloat({ amount: detail.amount!, key: Date.now() })
      }
    }
    window.addEventListener('db:crumbs', onCrumbs)
    return () => window.removeEventListener('db:crumbs', onCrumbs)
  }, [item.id])

  // Kid mode. The viewer's own mark awaiting a parent draws as an amber
  // hourglass; for a parent, anyone's waiting mark flags the card as needing
  // approval. Both are read-outs: the sheet is where they are answered.
  const myPending = item.pending && item.pending_by === viewerId
  const needsApproval =
    Boolean(viewerIsParent) &&
    ((item.pending && item.pending_by !== viewerId) ||
      (item.assignee_completions?.some((c) => c.pending && c.user_id !== viewerId) ?? false))

  // Routines are per-person: show each participant's own check, always, since
  // the row itself no longer says anything about the viewer's own bit.
  const perPerson =
    item.kind === 'routine' && item.assignee_completions && item.assignee_completions.length >= 1
      ? item.assignee_completions.map((c) => ({
          user: family?.find((m) => m.id === c.user_id),
          completed: c.completed,
          pending: c.pending,
        }))
      : null
  const doneCount = perPerson?.filter((p) => p.completed).length ?? 0

  // A card involved in a village event (the organizer's shared source or a
  // landed copy) wears the village colors: a gold border and a filled gold
  // flag across the top, so cross-family plans read differently from the
  // family's own at a glance.
  const shared = Boolean(item.village_shared)

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: settled ? 0.55 : 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ delay: index * 0.05, type: 'spring', stiffness: 300, damping: 26 }}
      whileTap={{ scale: 0.99 }}
      className={`db-row touch-pan-y select-none ${shared ? 'db-row-shared' : ''}`}
    >
      {/* The whole line is one target and it only ever opens the sheet. The
          edit pencil sits outside it so it stays its own button rather than
          nesting one inside another. */}
      <button
        type="button"
        onClick={onOpen}
        className="-my-2 flex min-h-11 min-w-0 flex-1 cursor-pointer items-center gap-[0.6875rem] py-2 text-left"
      >
        {/* A 22px slot that says where the card stands without offering to
            change it: done, called off, waiting on a parent, or its kind. */}
        <span
          className={`relative flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full ${
            item.completed ? 'bg-emerald-400/25' : myPending ? 'bg-amber-400/25' : ''
          }`}
        >
          {float && <CrumbFloat key={float.key} amount={float.amount} />}
          {item.completed ? (
            <Check className="h-3.5 w-3.5 text-emerald-300" strokeWidth={3} />
          ) : item.cancelled ? (
            <X className="h-3.5 w-3.5 text-gold" strokeWidth={3} />
          ) : myPending ? (
            <Hourglass className="h-3 w-3 text-amber-300" strokeWidth={2.5} />
          ) : (
            <Icon className={`h-4 w-4 ${tint}`} strokeWidth={2} />
          )}
        </span>

        <div className="min-w-0 flex-1">
          {/* A passed row is dimmed but NEVER struck: in this app a line
              through a title means done, and a routine nobody has done yet
              would be claiming otherwise a minute after its time. */}
          <p
            className={`truncate text-[14.5px] font-semibold leading-tight ${
              item.completed
                ? 'text-fg/60 line-through decoration-fg/30'
                : passed
                  ? 'text-fg/60'
                  : 'text-fg'
            }`}
          >
            {item.title}
          </p>
          {/* One muted meta line under the title carries everything that used to
              need its own row: kind, flags, the card's own dates, streak, notes.
              State (shared, overdue, approval, streak) is shrink-0 so it can never
              be squeezed out; the plain text pieces shrink and ellipsize instead.
              The line wraps rather than clipping, because on a 390px phone the
              state chips alone can outrun the column, and a hidden cutoff would
              lose state silently. Only a genuinely busy row grows past 48px. */}
          <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[12.5px] leading-tight text-fg/55">
            {shared && (
              <span className="db-chip db-chip-gold shrink-0 py-0 text-[11px]">
                Shared {item.kind === 'appointment' ? 'appointment' : 'activity'}
              </span>
            )}
            {/* The kind's own icon already sits in the slot on the left, so the
                meta line just names it. */}
            <span className="min-w-0 truncate">{label}</span>
            {flag === 'overdue' && (
              <span className="shrink-0 rounded-full bg-rose-500/20 px-1.5 text-[11px] font-bold text-rose-300">
                Overdue
              </span>
            )}
            {flag === 'due' && (
              <span className="shrink-0 rounded-full bg-gold/20 px-1.5 text-[11px] font-bold text-gold">
                Due
              </span>
            )}
            {needsApproval && (
              <span className="flex shrink-0 items-center gap-0.5 rounded-full bg-amber-400/20 px-1.5 text-[11px] font-bold text-amber-300">
                <Hourglass className="h-2.5 w-2.5" strokeWidth={3} /> Needs approval
              </span>
            )}
            {perPerson && perPerson.length > 1 && (
              <span className="shrink-0 font-bold text-fg/40">
                {doneCount}/{perPerson.length}
              </span>
            )}
            {dateLine && <span className="min-w-0 truncate font-semibold text-fg/65">{dateLine}</span>}
            {(item.streak ?? 0) >= 3 && (
              <span className="flex shrink-0 items-center gap-0.5 font-bold text-orange-300">
                <Flame className="h-3 w-3" /> {item.streak}
              </span>
            )}
            {myPending ? (
              <span className="shrink-0 font-medium text-amber-300/90">Waiting for a parent</span>
            ) : (
              item.notes && <span className="min-w-0 truncate">{item.notes}</span>
            )}
          </span>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {timeLabel && (
            <span
              className={`db-chip whitespace-nowrap tabular-nums ${
                flag === 'overdue' ? 'bg-rose-500/15 text-rose-300' : ''
              }`}
            >
              {timeLabel}
            </span>
          )}
          {perPerson ? (
            // Per-person routine: each face carries its own check state.
            <div className="flex -space-x-2">
              {perPerson.slice(0, 3).map((p, i) => (
                <ParticipantAvatar
                  key={i}
                  name={p.user?.display_name ?? '?'}
                  src={p.user ? avatarUrl(p.user) : null}
                  done={p.completed}
                  pending={p.pending}
                />
              ))}
              {perPerson.length > 3 && (
                <span className="z-10 flex h-7 w-7 items-center justify-center rounded-full bg-fg/15 text-[10px] font-bold ring-2 ring-black/40">
                  +{perPerson.length - 3}
                </span>
              )}
            </div>
          ) : (
            item.assignees.length > 0 && (
              // Overlapping cluster; the ring separates faces. Cap at three, then
              // a +N so a card for several people never overflows the row.
              <div className="flex -space-x-2">
                {item.assignees.slice(0, 3).map((a) => (
                  <Avatar
                    key={a.id}
                    name={a.display_name}
                    src={avatarUrl(a)}
                    size="sm"
                    className="ring-2 ring-black/40"
                  />
                ))}
                {item.assignees.length > 3 && (
                  <span className="z-10 flex h-7 w-7 items-center justify-center rounded-full bg-fg/15 text-[10px] font-bold ring-2 ring-black/40">
                    +{item.assignees.length - 3}
                  </span>
                )}
              </div>
            )
          )}
        </div>
      </button>

      {onEdit && (
        // Shortcut straight into the editor for parents; the detail sheet
        // has Edit too.
        <button
          type="button"
          aria-label={`Edit ${item.title}`}
          onClick={onEdit}
          className="-my-3 -mr-2 shrink-0 rounded-xl p-3.5 text-fg/35 transition-colors hover:bg-fg/10 hover:text-fg/70 active:bg-fg/15"
        >
          <Pencil className="h-4 w-4" strokeWidth={2} />
        </button>
      )}
    </motion.div>
  )
}

// A thin labelled hairline between groups of rows inside the board card
// (Past due, Now, Coming up, ...). The label sits centered between two rules,
// small-caps; the "Now" line is accented so the eye lands on what's current.
// The label string is written normally and uppercased by CSS.
export function SectionDivider({ label, accent = false }: { label: string; accent?: boolean }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className={`db-sect ${accent ? 'db-sect-accent' : ''}`}
    >
      <span>{label}</span>
    </motion.div>
  )
}
