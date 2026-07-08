import { Check } from 'lucide-react'
import { useEffect, useRef } from 'react'
import * as api from '../lib/api'
import { formatTimeRange } from '../lib/moods'
import { Avatar } from './Avatar'
import { KIND_STYLE } from './ItemCard'

// The board's day view: a static time gutter from 12 AM to midnight on the
// left, and today's timed cards laid onto it, sized by their time slot the way
// a desktop calendar does it. Cards keep the app's glass look rather than
// Outlook's solid blocks. Untimed cards stay in the list sections around this.

const HOUR_PX = 64
const PX_PER_MIN = HOUR_PX / 60
// A card shorter than this is unreadable, so short/open-ended slots get a
// minimum visual height; packing uses the same effective size so neighbours
// never draw on top of each other.
const MIN_PX = 44

const minutesOf = (t: string) => {
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}

const hourLabel = (h: number) => {
  const suffix = h < 12 ? 'AM' : 'PM'
  const hour = h % 12 === 0 ? 12 : h % 12
  return `${hour} ${suffix}`
}

interface Placed {
  item: api.FeedItem
  top: number
  height: number
  col: number
  cols: number
}

// Lay the cards out like a calendar: overlapping cards share the width of
// their overlap cluster, each in the leftmost column that's free at its start.
function layout(items: api.FeedItem[]): Placed[] {
  const sorted = [...items].sort(
    (a, b) => minutesOf(a.time_of_day!) - minutesOf(b.time_of_day!) || a.title.localeCompare(b.title),
  )
  const placed: Placed[] = []
  // Effective extents in px, floored to MIN_PX so clamped cards still pack.
  const extents = sorted.map((item) => {
    const start = minutesOf(item.time_of_day!) * PX_PER_MIN
    const rawEnd = item.end_time ? minutesOf(item.end_time) * PX_PER_MIN : start
    return { start, end: Math.max(rawEnd, start + MIN_PX) }
  })

  let cluster: number[] = [] // indices in the current overlap run
  let clusterEnd = -1
  let colEnds: number[] = [] // per-column bottom edge within the cluster

  const flush = () => {
    for (const i of cluster) placed[i].cols = colEnds.length
    cluster = []
    colEnds = []
  }

  sorted.forEach((item, i) => {
    const { start, end } = extents[i]
    if (cluster.length > 0 && start >= clusterEnd) flush()
    let col = colEnds.findIndex((e) => e <= start)
    if (col === -1) {
      col = colEnds.length
      colEnds.push(end)
    } else {
      colEnds[col] = end
    }
    cluster.push(i)
    clusterEnd = Math.max(clusterEnd, end)
    placed[i] = { item, top: start, height: end - start, col, cols: 1 }
  })
  flush()
  return placed
}

function TimelineCard({
  placed,
  canCheck,
  onToggle,
  onOpen,
}: {
  placed: Placed
  canCheck: boolean
  onToggle?: () => void
  onOpen: () => void
}) {
  const { item, top, height, col, cols } = placed
  const { Icon, tint } = KIND_STYLE[item.kind]
  const roomy = height >= 56
  const width = 100 / cols
  // Who the card is for, budgeted to the room the card actually has: tall
  // full-width cards fit a small stack, a short shared-lane sliver fits one
  // face at most. Whatever's cut off is a +N; the detail sheet has everyone.
  const maxFaces = roomy ? (cols === 1 ? 3 : 2) : cols === 1 ? 2 : 1
  const faces = item.assignees.slice(0, maxFaces)
  const extra = item.assignees.length - faces.length
  // A card tall enough has dead space under the time row - park the faces
  // there instead of squeezing the text. Shorter cards keep them inline.
  const facesBelow = faces.length > 0 && height >= 88
  return (
    <div
      onClick={onOpen}
      className={`glass absolute flex cursor-pointer touch-pan-y select-none items-start gap-2 overflow-hidden rounded-xl px-2.5 ${
        roomy ? 'py-2' : 'py-1'
      } ${item.completed ? 'opacity-55' : ''}`}
      style={{
        top,
        height: height - 3, // breathing room so back-to-back cards don't fuse
        // Columns after the first give up the 4px they're shifted by, so the
        // last one ends exactly at the lane's edge - nothing to scroll to.
        left: `calc(${col * width}% + ${col > 0 ? 4 : 0}px)`,
        width: `calc(${width}% - ${col > 0 ? 4 : 0}px)`,
      }}
    >
      {canCheck && onToggle && (
        <button
          type="button"
          aria-label={item.completed ? `Mark ${item.title} not done` : `Mark ${item.title} done`}
          onClick={(e) => {
            e.stopPropagation()
            onToggle()
          }}
          className="mt-px shrink-0"
        >
          <span
            className={`flex h-5 w-5 items-center justify-center rounded-full border-2 transition-colors ${
              item.completed ? 'border-emerald-300/70 bg-emerald-400/25' : 'border-fg/30 bg-fg/5'
            }`}
          >
            {item.completed && <Check className="h-3 w-3 text-emerald-300" strokeWidth={3} />}
          </span>
        </button>
      )}
      <div className="min-w-0 flex-1">
        <p
          className={`truncate text-sm font-semibold leading-5 ${
            item.completed ? 'text-fg/60 line-through decoration-fg/30' : 'text-fg'
          }`}
        >
          {item.title}
        </p>
        {roomy && (
          <p className="mt-0.5 flex items-center gap-1 truncate text-[11px] font-semibold text-fg/55">
            <Icon className={`h-3 w-3 shrink-0 ${tint}`} strokeWidth={2.5} />
            {formatTimeRange(item.time_of_day, item.end_time)}
          </p>
        )}
      </div>
      {faces.length > 0 && (
        <div
          className={`flex -space-x-2 ${
            facesBelow ? 'absolute bottom-2 right-2.5' : 'shrink-0 self-center'
          }`}
        >
          {faces.map((a) => (
            <Avatar
              key={a.id}
              name={a.display_name}
              src={api.avatarUrl(a)}
              size="sm"
              className="ring-2 ring-black/40"
            />
          ))}
          {extra > 0 && (
            <span className="z-10 flex h-7 w-7 items-center justify-center rounded-full bg-fg/15 text-[10px] font-bold ring-2 ring-black/40">
              +{extra}
            </span>
          )}
        </div>
      )}
      {/* On a short full-width card the time rides inline; once cards share
          the lane there's no room for it — the title wins, detail has the rest. */}
      {!roomy && cols === 1 && (
        <span className="shrink-0 whitespace-nowrap text-[11px] font-semibold leading-5 text-fg/55 tabular-nums">
          {formatTimeRange(item.time_of_day, item.end_time)}
        </span>
      )}
    </div>
  )
}

export function DayTimeline({
  items,
  nowMinutes,
  canCheck,
  onToggle,
  onOpen,
}: {
  items: api.FeedItem[] // today's timed cards, open and done alike
  nowMinutes: number
  canCheck: (item: api.FeedItem) => boolean
  onToggle: (item: api.FeedItem) => void
  onOpen: (item: api.FeedItem) => void
}) {
  const scrollRef = useRef<HTMLDivElement>(null)

  // The day scrolls inside this panel, never the page: switching to Timeline
  // keeps the header and family strip right where they were. The panel opens
  // an hour above the now line for context; after that the reader owns it.
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = Math.max(nowMinutes * PX_PER_MIN - HOUR_PX, 0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const placed = layout(items)
  const nowY = nowMinutes * PX_PER_MIN

  return (
    <div
      ref={scrollRef}
      className="relative overflow-x-hidden overflow-y-auto overscroll-contain rounded-2xl border border-fg/10 [scrollbar-width:thin]"
      style={{ height: 'min(58svh, 560px)' }}
      data-day-timeline
    >
      <div className="relative flex" style={{ height: 24 * HOUR_PX }}>
        {/* the static hour gutter */}
        <div className="relative w-11 shrink-0">
          {Array.from({ length: 24 }, (_, h) => (
            <span
              key={h}
              className="absolute right-2 -translate-y-1/2 text-[10px] font-semibold text-fg/40 tabular-nums"
              style={{ top: h * HOUR_PX }}
            >
              {hourLabel(h)}
            </span>
          ))}
        </div>

        {/* hour hairlines + the cards */}
        <div className="relative min-w-0 flex-1">
          {Array.from({ length: 24 }, (_, h) => (
            <div
              key={h}
              className="absolute left-0 right-0 border-t border-fg/10"
              style={{ top: h * HOUR_PX }}
            />
          ))}

          {/* now line */}
          <div className="absolute -left-1.5 right-0 z-10" style={{ top: nowY }} data-now-line>
            <span className="absolute -top-[3px] left-0 h-1.5 w-1.5 rounded-full bg-accent-bright" />
            <div className="border-t-2 border-accent-bright/70" />
          </div>

          {placed.map((p) => (
            <TimelineCard
              key={p.item.id}
              placed={p}
              canCheck={canCheck(p.item)}
              onToggle={canCheck(p.item) ? () => onToggle(p.item) : undefined}
              onOpen={() => onOpen(p.item)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
