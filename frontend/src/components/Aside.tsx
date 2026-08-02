import { Hourglass } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../lib/api'
import { avatarUrl } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { announceChange } from '../lib/changes'
import { dateSpanLabel } from '../lib/items'
import { formatTimeRange } from '../lib/moods'
import { Avatar } from './Avatar'
import { KIND_STYLE } from './ItemCard'
import { VerseCard } from './VerseCard'

// How many grocery rows the glance shows before it stops and counts the rest.
const GROCERY_ROWS = 6

// The desktop right rail. It stays put across tabs, so it owns its own data
// rather than reading Home's — Home is not mounted when you are on Kitchen.
// Only rendered above 1200px (see useWideLayout), so these two requests never
// happen on a phone.
//
// Both lists are LIVE, not glances. Next 7 days moves here wholesale at this
// width and Home stops drawing it, so this is the only copy left: a row taps
// through to the board with that card's detail sheet open, which is where every
// affordance (check, edit, delete, RSVP, share) already lives. The grocery rows
// check off in place against the same endpoint the Kitchen card uses.
//
// Because this is the only copy at this width, it also has to carry the two
// INDICATORS a board row carries — the gold shared-event mark and the assignee
// faces — or a shared event and a card assigned to someone else would be
// indistinguishable from your own private one, with no second surface to
// correct the impression.
export function Aside({ onOpenItem }: { onOpenItem: (id: number) => void }) {
  const { user } = useAuth()
  const canEditGrocery = user?.role === 'parent'

  // null means "not loaded yet". Kept distinct from an empty array on purpose:
  // at this width there is no second copy of either list, so answering a failed
  // or in-flight fetch with "Nothing in the next 7 days." would quietly tell
  // someone their week is clear.
  const [next7, setNext7] = useState<api.FeedItem[] | null>(null)
  const [next7Error, setNext7Error] = useState<string | null>(null)
  const [grocery, setGrocery] = useState<api.GroceryState | null>(null)
  const [groceryError, setGroceryError] = useState<string | null>(null)
  const [writeError, setWriteError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Retiring the shared-read generation stops a NEW read from joining a stale
  // request; it cannot stop a stale request from landing late and repainting
  // over a change. These sequence numbers do: only the newest read of each
  // list is allowed to set state.
  const boardSeq = useRef(0)
  const grocerySeq = useRef(0)

  const loadBoard = useCallback(async () => {
    const seq = ++boardSeq.current
    try {
      const feed = await api.getFeed()
      if (seq !== boardSeq.current) return
      setNext7(feed.next7.filter((i) => !i.completed))
      setNext7Error(null)
    } catch (err) {
      if (seq !== boardSeq.current) return
      setNext7Error(err instanceof api.ApiError ? err.message : 'Could not load the next 7 days.')
    }
  }, [])

  const loadGrocery = useCallback(async () => {
    const seq = ++grocerySeq.current
    try {
      const state = await api.getGrocery()
      if (seq !== grocerySeq.current) return
      setGrocery(state)
      setGroceryError(null)
    } catch (err) {
      if (seq !== grocerySeq.current) return
      setGroceryError(err instanceof api.ApiError ? err.message : 'Could not load the list.')
    }
  }, [])

  useEffect(() => {
    loadBoard()
    loadGrocery()
  }, [loadBoard, loadGrocery])

  // Two reasons this column goes stale, and it has to answer both. Coming back
  // to the tab covers changes made elsewhere (another member, another device).
  // The change events cover this window: the board's sheet and the Kitchen
  // grocery card both write, and without them a card deleted on the board
  // leaves a row here that looks live and answers no taps.
  useEffect(() => {
    const onVisible = () => document.visibilityState === 'visible' && (loadBoard(), loadGrocery())
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('db:board-changed', loadBoard)
    window.addEventListener('db:grocery-changed', loadGrocery)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('db:board-changed', loadBoard)
      window.removeEventListener('db:grocery-changed', loadGrocery)
    }
  }, [loadBoard, loadGrocery])

  // Grouped by store, in the Kitchen card's own order (each store as it was
  // added, then Unsorted last). A flat list here contradicted the Kitchen tab
  // and lost the only thing that makes the list useful in a shop. The row cap
  // is applied across the whole list first, so the glance never runs long, and
  // a store whose items all fall past the cut simply doesn't appear.
  const open = grocery?.items.filter((i) => !i.checked) ?? []
  const shown = open.slice(0, GROCERY_ROWS)
  const hidden = open.length - shown.length
  const groups: { key: string; label: string; items: api.GroceryItem[] }[] = []
  for (const list of grocery?.lists ?? []) {
    const items = shown.filter((i) => i.list_id === list.id)
    if (items.length) groups.push({ key: `l${list.id}`, label: list.name, items })
  }
  const unsorted = shown.filter((i) => i.list_id === null)
  if (unsorted.length) groups.push({ key: 'unsorted', label: 'Unsorted', items: unsorted })
  // One unnamed bucket is just "the list"; a heading over it would be noise.
  const showStoreHeadings = groups.length > 1

  const check = async (item: api.GroceryItem) => {
    setBusy(true)
    setWriteError(null)
    // Optimistic: the row leaves the open list at once.
    setGrocery((g) =>
      g ? { ...g, items: g.items.map((i) => (i.id === item.id ? { ...i, checked: true } : i)) } : g,
    )
    try {
      await api.updateGrocery(item.id, { checked: true })
      // Tell the Kitchen card, which shows the same list and would otherwise
      // still be offering an item that is already in the basket.
      announceChange('db:grocery-changed')
    } catch (err) {
      // Say so rather than letting the row silently reappear: four quick taps
      // against an expired session would otherwise just snap back one by one.
      setWriteError(
        err instanceof api.ApiError ? err.message : 'Something went wrong. Try again.',
      )
    }
    await loadGrocery()
    setBusy(false)
  }

  return (
    <aside className="db-aside">
      <div className="glass db-pad overflow-hidden">
        <div className="db-card-h">
          <span className="db-micro">Next 7 days</span>
        </div>
        {/* The error sits ABOVE whatever is already loaded rather than
            replacing it, the way the board does: a refetch that fails during a
            deploy must not blank the only copy of this list. */}
        {next7Error && <p className="db-emptyline text-rose-300">{next7Error}</p>}
        {next7 === null ? (
          !next7Error && <p className="db-emptyline">Loading…</p>
        ) : next7.length === 0 ? (
          <p className="db-emptyline">Nothing in the next 7 days.</p>
        ) : (
          next7.map((item) => {
            const when = item.all_day
              ? 'All day'
              : formatTimeRange(item.time_of_day, item.end_time)
            const shared = Boolean(item.village_shared)
            const { Icon, tint, label } = KIND_STYLE[item.kind]
            // A parent needs to see anyone else's waiting mark; the board row
            // shows the same chip.
            const needsApproval =
              user?.role === 'parent' &&
              ((item.pending && item.pending_by !== user?.id) ||
                (item.assignee_completions?.some((c) => c.pending && c.user_id !== user?.id) ??
                  false))
            return (
              <div
                key={item.id}
                className={`db-row ${shared ? 'db-row-shared' : ''}`}
                // Cancelled cards reach this list (only completed ones are
                // filtered out) and the board dims them to 0.55. Without this
                // a called-off event reads as live, and at this width there is
                // no second copy to correct it.
                style={item.cancelled ? { opacity: 0.55 } : undefined}
              >
                <button
                  type="button"
                  onClick={() => onOpenItem(item.id)}
                  className="-my-2 flex min-h-11 min-w-0 flex-1 items-start gap-2 py-2 text-left"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14.5px] font-semibold">{item.title}</span>
                    {/* The meta line mirrors the board row's: the gold shared
                        mark first so it can never be squeezed out, then what
                        kind of card it is, its own dates, and whose it is. */}
                    <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[12.5px] leading-tight text-fg/55">
                      {shared && (
                        <span className="db-chip db-chip-gold shrink-0 py-0 text-[11px]">
                          Shared {item.kind === 'appointment' ? 'appointment' : 'activity'}
                        </span>
                      )}
                      {/* The gold chip already names the kind ("Shared
                          activity"), so the plain label would just repeat it.
                          The board can afford the duplication across a full
                          row; a 268px column cannot. */}
                      {!shared && (
                        <span className={`flex shrink-0 items-center gap-1 ${tint}`}>
                          <Icon className="h-3 w-3 shrink-0" strokeWidth={2.5} />
                          {label}
                        </span>
                      )}
                      {item.cancelled && (
                        <span className="shrink-0 rounded-full bg-gold/20 px-1.5 text-[11px] font-bold text-gold">
                          Cancelled
                        </span>
                      )}
                      {needsApproval && (
                        <span className="flex shrink-0 items-center gap-0.5 rounded-full bg-amber-400/20 px-1.5 text-[11px] font-bold text-amber-300">
                          <Hourglass className="h-2.5 w-2.5" strokeWidth={3} /> Needs approval
                        </span>
                      )}
                      {item.date_for && (
                        <span className="truncate">
                          {dateSpanLabel(item.date_for, item.end_date)}
                        </span>
                      )}
                      {item.assignees.length > 0 && (
                        <span className="ml-auto flex shrink-0 -space-x-2">
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
                        </span>
                      )}
                    </span>
                  </span>
                  {when && <span className="db-chip db-chip-plain shrink-0">{when}</span>}
                </button>
              </div>
            )
          })
        )}
      </div>

      <div className="glass db-pad overflow-hidden">
        <div className="db-card-h">
          <span className="db-micro">Grocery list</span>
          {/* Counts what is on screen, not the whole list: a header saying 9
              over six rows reads as a bug. The rest is named below instead. */}
          {shown.length > 0 && <span className="db-sum">{shown.length} to grab</span>}
        </div>
        {writeError && <p className="db-emptyline text-rose-300">{writeError}</p>}
        {groceryError && <p className="db-emptyline text-rose-300">{groceryError}</p>}
        {grocery === null ? (
          !groceryError && <p className="db-emptyline">Loading…</p>
        ) : shown.length === 0 ? (
          // "Empty" and "all ticked off" are different things, and the Kitchen
          // tab would be showing rows in the second case.
          <p className="db-emptyline">
            {grocery.items.length === 0 ? 'The list is empty.' : 'Nothing left to grab.'}
          </p>
        ) : (
          <>
            {groups.map((group) => (
              <div key={group.key}>
                {showStoreHeadings && (
                  <p className="db-micro px-0.5 pt-2 pb-0.5 text-fg/45">{group.label}</p>
                )}
                {group.items.map((item) => (
                  <div key={item.id} className="db-row">
                    <button
                      type="button"
                      disabled={!canEditGrocery || busy}
                      onClick={() => check(item)}
                      className="-my-2 flex min-h-11 min-w-0 flex-1 items-center gap-3 py-2 text-left"
                    >
                      {/* Only unchecked items reach this list, so the box is
                          always empty; ticking one drops it off the glance. */}
                      <span className="h-5 w-5 shrink-0 rounded-md border border-fg/25" />
                      <span className="min-w-0 flex-1 truncate text-[14.5px] font-semibold">
                        {item.title}
                      </span>
                    </button>
                  </div>
                ))}
              </div>
            ))}
            {hidden > 0 && <p className="db-emptyline">+{hidden} more on the Kitchen tab.</p>}
          </>
        )}
      </div>

      {/* Follows the card above it rather than being pinned to the bottom of
          the column. On a tall widescreen the sticky column is far taller than
          its contents, and mt-auto stranded the verse at the foot of the
          screen with a lake of empty space above it. */}
      <VerseCard />
    </aside>
  )
}
