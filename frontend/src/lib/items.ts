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
  if (item.owner_id === user.id || item.assignees.some((a) => a.id === user.id)) return true
  return user.role === 'parent' && item.visibility === 'family'
}
