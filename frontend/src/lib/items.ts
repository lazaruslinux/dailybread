import type { FeedItem, User } from './api'

// Can this member check the card off? Routines are per-person: only a
// participant checks their own occurrence. Other kinds can be checked by anyone
// involved (owner or assignee), plus either parent on a family-board card, so
// co-parents share the household's chores. Kept in one place so the board and
// the calendar agree.
export function canCheckItem(item: FeedItem, user: User | null): boolean {
  if (!user) return false
  if (item.kind === 'routine')
    return item.assignee_completions?.some((c) => c.user_id === user.id) ?? false
  if (item.village_event_id != null) return false
  if (item.owner_id === user.id || item.assignees.some((a) => a.id === user.id)) return true
  return user.role === 'parent' && item.visibility === 'family'
}

// ---- multi-day cards --------------------------------------------------------
// An activity or appointment can run across days (a trip, an overnight stay).
// date_for is the first day and end_date the last, so the same card shows up on
// every day between them. On any day after the first it has no start time to
// speak of, and the backend sorts it with the all-day cards; these helpers keep
// the board, the calendar and the timeline agreeing on that.

export function spansDays(item: { date_for: string | null; end_date?: string | null }): boolean {
  return Boolean(item.end_date && item.date_for && item.end_date > item.date_for)
}

// Is this day past the card's first, and still inside its run?
export function continuesOn(
  item: { date_for: string | null; end_date?: string | null },
  dayISO: string,
): boolean {
  return spansDays(item) && item.date_for! < dayISO && dayISO <= item.end_date!
}

function localDay(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

// "Jul 30": no weekday, so two of them still fit a card row.
export function compactDate(iso: string): string {
  return localDay(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// "Mon, Jul 6" for one day, "Jul 30 – Aug 2" for a run of them. The weekday is
// dropped on a range: two of them plus two dates wraps on a phone.
export function dateSpanLabel(start: string, end?: string | null): string {
  if (end && end > start) return `${compactDate(start)} – ${compactDate(end)}`
  return localDay(start).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

// A maps link for a location string, or null when it reads like a placeholder
// rather than an address. A single non-address word ("TBD", "Home", "Park")
// renders as plain text; anything multi-word or carrying a digit links out.
// The misfire cost is one useless maps search, so we err toward linking.
export function mapsUrl(location: string): string | null {
  const trimmed = location.trim()
  if (!/\s/.test(trimmed) && !/\d/.test(trimmed)) return null
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(trimmed)}`
}
