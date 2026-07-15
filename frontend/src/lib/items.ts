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

// A maps link for a location string, or null when it reads like a placeholder
// rather than an address. A single non-address word ("TBD", "Home", "Park")
// renders as plain text; anything multi-word or carrying a digit links out.
// The misfire cost is one useless maps search, so we err toward linking.
export function mapsUrl(location: string): string | null {
  const trimmed = location.trim()
  if (!/\s/.test(trimmed) && !/\d/.test(trimmed)) return null
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(trimmed)}`
}
