import { invalidateReads } from './api'

// The app tells itself about writes with window events, so every surface
// showing a piece of data refetches without anyone wiring components together.
// The convention predates the desktop layout (db:recipes-changed,
// db:foods-changed, db:profile-changed and friends are dispatched directly);
// these two are the ones a second surface depends on for correctness rather
// than freshness, which is why they go through here.
//
// db:board-changed exists because at >=1200px the right aside carries the only
// copy of Next 7 days. Without it a card deleted from the board's sheet leaves
// a row in the aside that looks live and answers no taps.
export type ChangeEvent = 'db:board-changed' | 'db:grocery-changed'

// Announce a write. Always retires the shared-read generation FIRST: the
// listeners this wakes are about to refetch, and without the invalidation they
// could join a request that left before the write landed and paint pre-write
// data back over the change that just happened.
export function announceChange(event: ChangeEvent) {
  invalidateReads()
  window.dispatchEvent(new Event(event))
}
