import { useEffect, useState } from 'react'
import { CalendarClock, Check, ChevronRight, HelpCircle, MapPin, X as XIcon } from 'lucide-react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Avatar } from './Avatar'
import { Sheet } from './recipes'
import { compactDate, mapsUrl } from '../lib/items'
import { formatTime } from '../lib/moods'

// Shared village events on the Home board: a strip of open invites for
// parents (kids never see it — attendance is a parent decision), and the
// detail sheet with the per-family RSVP picture. A "going" answer opens the
// attendee picker (whole family preselected) and lands the event on this
// family's board as a real card; the board card itself is rendered by the
// normal feed machinery, not here.

function eventDate(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

function whenLabel(ev: api.VillageEvent): string {
  // A multi-day event reads as its range, and shows only its start time: the
  // end time belongs to the last day, so printing both beside a date range
  // would say the wrong thing about each.
  const spans = Boolean(ev.end_date && ev.end_date > ev.date_for)
  const day = spans
    ? `${compactDate(ev.date_for)} – ${compactDate(ev.end_date!)}`
    : eventDate(ev.date_for)
  if (ev.all_day || !ev.time_of_day) return day
  const start = formatTime(ev.time_of_day)
  return ev.end_time && !spans ? `${day} · ${start} – ${formatTime(ev.end_time)}` : `${day} · ${start}`
}

// One attendee as a chip. Parents: face + full name. Opted-in kids: face +
// first name. Unshared kids: a bare initial in a dashed ring (the villages
// box kid style) and no name at all — that's the whole privacy deal.
function AttendeeChip({ a }: { a: api.EventAttendee }) {
  if (!a.avatar || a.user_id === null) {
    return (
      <span
        aria-label="A kid"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-dashed border-fg/30 bg-fg/5 text-xs font-bold text-fg/55"
      >
        {a.initial}
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1.5 rounded-full border border-fg/10 bg-fg/5 py-0.5 pl-0.5 pr-2.5">
      <Avatar
        name={a.name ?? a.initial}
        src={api.avatarUrl({ id: a.user_id, avatar_updated_at: a.avatar_updated_at })}
        size="sm"
      />
      <span className="text-xs font-semibold text-fg/80">{a.name}</span>
    </span>
  )
}

const RSVP_META: Record<api.RsvpStatus, { label: string; tint: string }> = {
  going: { label: 'Going', tint: 'text-emerald-300' },
  maybe: { label: 'Maybe', tint: 'text-gold' },
  cant: { label: "Can't make it", tint: 'text-fg/50' },
}

function RsvpBuckets({ ev }: { ev: api.VillageEvent }) {
  return (
    <div className="mt-3 flex flex-col gap-2">
      <span className="db-micro">Who's coming</span>
      <div className="flex flex-col gap-1 rounded-xl border border-fg/10 bg-fg/5 px-3 py-2">
        <span className="db-micro">
          {ev.organizer_family_name} · Hosting
        </span>
      </div>
      {ev.rsvps.length === 0 && (
        <p className="px-1 text-xs text-fg/45">No answers yet.</p>
      )}
      {ev.rsvps.map((r) => (
        <div key={r.family_id} className="rounded-xl border border-fg/10 bg-fg/5 px-3 py-2">
          <div className="flex items-baseline justify-between gap-2">
            <span className="db-micro">
              {r.family_name}
            </span>
            <span className={`text-xs font-bold ${RSVP_META[r.status].tint}`}>
              {RSVP_META[r.status].label}
              {r.status === 'going' && r.attendees.length > 0 && ` · ${r.attendees.length}`}
            </span>
          </div>
          {r.attendees.length > 0 && (
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              {r.attendees.map((a, i) => (
                <AttendeeChip key={a.user_id ?? `kid-${i}`} a={a} />
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// Pick who from this family is coming. Everyone preselected; tap to leave
// someone home. Own kids always show their real face and name here — the
// privacy shaping only applies across the family wall.
function AttendeePicker({
  family,
  selected,
  onToggle,
}: {
  family: api.FamilyMember[]
  selected: Set<number>
  onToggle: (id: number) => void
}) {
  return (
    <div className="mt-3 flex flex-col gap-1.5">
      <span className="db-micro">Who's going from your family</span>
      {family.map((m) => {
        const on = selected.has(m.id)
        return (
          <button
            key={m.id}
            type="button"
            onClick={() => onToggle(m.id)}
            aria-pressed={on}
            className={`flex min-h-11 items-center gap-3 rounded-xl border px-3 py-2 text-left transition-colors ${
              on ? 'border-accent-bright/60 bg-accent-bright/15' : 'border-fg/10 bg-fg/5'
            }`}
          >
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 ${
                on ? 'border-emerald-300/70 bg-emerald-400/25' : 'border-fg/30 bg-fg/5'
              }`}
            >
              {on && <Check className="h-3.5 w-3.5 text-emerald-300" strokeWidth={3} />}
            </span>
            <Avatar name={m.display_name} src={api.avatarUrl(m)} size="sm" />
            <span className="truncate text-sm font-semibold text-fg/90">{m.display_name}</span>
          </button>
        )
      })}
    </div>
  )
}

export function VillageEventSheet({
  event,
  family,
  onClose,
  onChanged,
}: {
  event: api.VillageEvent
  family: api.FamilyMember[]
  onClose: () => void
  onChanged: () => void
}) {
  const { user } = useAuth()
  const [ev, setEv] = useState(event)
  const [picking, setPicking] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(() => {
    // An existing going answer keeps its picks; otherwise the whole family
    // starts selected and the parent taps off whoever's staying home.
    const mine = ev.rsvps.find((r) => r.family_id === user?.family_id)
    const kept =
      ev.my_rsvp === 'going' && mine
        ? mine.attendees.map((a) => a.user_id).filter((x): x is number => x !== null)
        : family.map((m) => m.id)
    return new Set(kept)
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const locationHref = ev.location ? mapsUrl(ev.location) : null

  async function answer(status: api.RsvpStatus, attendees: number[] = []) {
    setBusy(true)
    setError(null)
    try {
      const updated = await api.setRsvp(ev.event_id, status, attendees)
      setEv(updated)
      setPicking(false)
      onChanged()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'That didn’t save.')
    } finally {
      setBusy(false)
    }
  }

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <Sheet onClose={onClose}>
      <div className="mb-3 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-accent-bright">
          <CalendarClock className="h-3.5 w-3.5" strokeWidth={2.5} />
          {ev.village_name}
        </span>
        <button
          onClick={onClose}
          aria-label="Close"
          className="-m-2 rounded-lg p-2 text-fg/50 hover:bg-fg/10 hover:text-fg"
        >
          <XIcon className="h-5 w-5" />
        </button>
      </div>

      <h2 className={`font-display text-xl font-semibold tracking-[-0.01em] ${ev.cancelled ? 'text-fg/60 line-through decoration-fg/30' : ''}`}>
        {ev.title}
      </h2>
      <p className="mt-1 text-sm text-fg/55">
        {ev.organizer_family_name}
        {ev.shared_by ? ` · shared by ${ev.shared_by}` : ''}
        {ev.cancelled ? ' · called off' : ''}
      </p>

      <div className="mt-3 flex flex-col gap-1.5 text-sm text-fg/75">
        <div className="flex items-center gap-2">
          <CalendarClock className="h-4 w-4 shrink-0 text-fg/40" />
          {whenLabel(ev)}
        </div>
        {ev.location &&
          (locationHref ? (
            <a
              href={locationHref}
              target="_blank"
              rel="noopener"
              className="flex min-h-11 items-center gap-2 font-semibold text-accent-bright underline decoration-accent-bright/40 underline-offset-2"
            >
              <MapPin className="h-4 w-4 shrink-0" /> {ev.location}
            </a>
          ) : (
            <span className="flex items-center gap-2 text-fg/75">
              <MapPin className="h-4 w-4 shrink-0" /> {ev.location}
            </span>
          ))}
        {ev.notes && <p className="leading-relaxed text-fg/70">{ev.notes}</p>}
      </div>

      <RsvpBuckets ev={ev} />

      {!ev.is_own && (
        <div className="mt-4">
          {picking ? (
            <>
              <AttendeePicker family={family} selected={selected} onToggle={toggle} />
              {error && <p className="text-danger mt-2 text-xs">{error}</p>}
              <div className="mt-3 flex gap-2.5">
                <button
                  type="button"
                  onClick={() => setPicking(false)}
                  className="min-h-11 flex-1 rounded-xl border border-fg/10 bg-fg/5 px-4 py-2.5 text-sm font-semibold text-fg/70 hover:bg-fg/10"
                >
                  Back
                </button>
                <button
                  type="button"
                  disabled={busy || selected.size === 0}
                  onClick={() => answer('going', [...selected])}
                  className="min-h-11 flex-1 rounded-xl bg-accent px-4 py-2.5 text-sm font-bold text-white hover:bg-accent-strong disabled:opacity-50"
                >
                  {busy ? 'Saving' : `We're going · ${selected.size}`}
                </button>
              </div>
            </>
          ) : (
            <>
              {error && <p className="text-danger mb-2 text-xs">{error}</p>}
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setPicking(true)}
                  aria-pressed={ev.my_rsvp === 'going'}
                  className={`flex min-h-11 flex-1 items-center justify-center gap-1.5 rounded-xl border px-3 py-2.5 text-sm font-bold transition-colors ${
                    ev.my_rsvp === 'going'
                      ? 'border-emerald-300/60 bg-emerald-400/20 text-emerald-300'
                      : 'border-fg/10 bg-fg/5 text-fg/75 hover:bg-fg/10'
                  }`}
                >
                  <Check className="h-4 w-4" /> Going
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => answer('maybe')}
                  aria-pressed={ev.my_rsvp === 'maybe'}
                  className={`flex min-h-11 flex-1 items-center justify-center gap-1.5 rounded-xl border px-3 py-2.5 text-sm font-bold transition-colors ${
                    ev.my_rsvp === 'maybe'
                      ? 'border-gold/60 bg-gold/20 text-gold'
                      : 'border-fg/10 bg-fg/5 text-fg/75 hover:bg-fg/10'
                  }`}
                >
                  <HelpCircle className="h-4 w-4" /> Maybe
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => answer('cant')}
                  aria-pressed={ev.my_rsvp === 'cant'}
                  className={`flex min-h-11 flex-1 items-center justify-center gap-1.5 rounded-xl border px-3 py-2.5 text-sm font-bold transition-colors ${
                    ev.my_rsvp === 'cant'
                      ? 'border-fg/30 bg-fg/15 text-fg/80'
                      : 'border-fg/10 bg-fg/5 text-fg/75 hover:bg-fg/10'
                  }`}
                >
                  <XIcon className="h-4 w-4" /> Can't
                </button>
              </div>
              {ev.my_rsvp === 'going' && (
                <button
                  type="button"
                  onClick={() => setPicking(true)}
                  className="mt-2 min-h-11 w-full rounded-xl px-3 py-2 text-xs font-semibold text-fg/50 hover:text-fg/80"
                >
                  Change who's going
                </button>
              )}
            </>
          )}
        </div>
      )}
    </Sheet>
  )
}

// The Home strip: open invites (unanswered or maybe) plus a one-line count
// of upcoming events the family is going to. Hidden entirely when there's
// nothing to show, and never rendered for kids (Home gates on parent).
export function VillageStrip({
  events,
  onOpen,
}: {
  events: api.VillageEvent[]
  onOpen: (ev: api.VillageEvent) => void
}) {
  const open = events.filter((e) => !e.is_own && !e.cancelled && (e.my_rsvp === null || e.my_rsvp === 'maybe'))
  if (open.length === 0) return null
  return (
    <div className="glass db-pad border border-accent-bright/25" data-village-strip>
      {/* The needs-attention idiom: the TabBar's rose dot on the header, a
          solid rose chip per row. A "maybe" still carries the chip — it's in
          the strip because it still needs a final answer. */}
      <div className="db-card-h">
        <span className="db-micro flex items-center gap-1.5 text-accent-bright">
          <span className="h-2 w-2 shrink-0 rounded-full bg-rose-400" />
          Village invites
        </span>
      </div>
      {open.map((ev) => (
        <button
          key={ev.event_id}
          type="button"
          onClick={() => onOpen(ev)}
          className="db-row transition-colors hover:bg-fg/5"
        >
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-semibold text-fg/90">{ev.title}</span>
            <span className="block truncate text-[12.5px] text-fg/50">
              {ev.organizer_family_name} · {whenLabel(ev)}
              {ev.my_rsvp === 'maybe' ? ' · you said maybe' : ''}
            </span>
          </span>
          <span className="shrink-0 rounded-full bg-rose-500/90 px-2 py-0.5 text-[10px] font-semibold text-white">
            RSVP
          </span>
          <ChevronRight className="h-4 w-4 shrink-0 text-fg/30" />
        </button>
      ))}
    </div>
  )
}

// The organizer's village picker when sharing a card: one tap when the
// family has one village, a short list otherwise.
export function ShareEventSheet({
  item,
  onClose,
  onShared,
}: {
  item: api.FeedItem
  onClose: () => void
  onShared: () => void
}) {
  const [villages, setVillages] = useState<api.Village[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listVillages().then(setVillages).catch(() => setVillages([]))
  }, [])

  async function shareTo(villageId: number) {
    setBusy(true)
    setError(null)
    try {
      await api.shareEvent(villageId, item.id)
      onShared()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Sharing failed.')
      setBusy(false)
    }
  }

  return (
    <Sheet onClose={onClose}>
      <h2 className="font-display text-xl font-semibold tracking-[-0.01em]">
        Share with the village
      </h2>
      <p className="mt-1 text-sm text-fg/55">
        Their parents get an invite and can RSVP. You'll see who's coming on the card.
      </p>
      {error && <p className="text-danger mt-3 text-xs">{error}</p>}
      <div className="mt-3 flex flex-col gap-1.5">
        {villages === null ? (
          <p className="py-4 text-center text-sm text-fg/45">Loading…</p>
        ) : villages.length === 0 ? (
          <p className="py-4 text-center text-sm text-fg/45">
            No villages yet. Link up with another family under You &gt; Villages.
          </p>
        ) : (
          villages.map((v) => (
            <button
              key={v.id}
              type="button"
              disabled={busy}
              onClick={() => shareTo(v.id)}
              className="flex min-h-12 items-center justify-between rounded-xl border border-fg/10 bg-fg/5 px-3.5 py-2 text-left text-sm font-semibold text-fg/85 transition-colors hover:bg-fg/10 disabled:opacity-50"
            >
              {v.name}
              <ChevronRight className="h-4 w-4 text-fg/30" />
            </button>
          ))
        )}
      </div>
    </Sheet>
  )
}
