// Tiny API client. All requests go through the /api prefix, which the Vite dev
// server proxies to the FastAPI backend (see vite.config.ts). In production the
// same /api path is routed to the backend by whatever reverse proxy fronts the
// app.
//
// Security notes:
// - The session lives in an httpOnly cookie the browser attaches by itself.
//   This file never sees, stores, or logs a token, so a script injection has
//   nothing to steal from JS-land.
// - `credentials: 'same-origin'` sends the cookie only to our own origin.

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: 'same-origin',
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
  if (!res.ok) {
    // FastAPI errors carry a {"detail": "..."} body; fall back to the status.
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* non-JSON error body; keep the fallback message */
    }
    throw new ApiError(res.status, detail)
  }
  // 204 No Content has no body to parse.
  if (res.status === 204) return undefined as T
  return res.json()
}

// ---- health ----------------------------------------------------------------

export interface Health {
  status: string
  mode: string
  demo: boolean
}

export const getHealth = () => request<Health>('/health')

// ---- auth ------------------------------------------------------------------

export type Role = 'parent' | 'child'

export interface User {
  id: number
  username: string
  display_name: string
  role: Role
  is_admin: boolean
  // The instance "server admin": the only account that can invite new
  // households. Distinct from is_admin, which is family board management.
  is_owner: boolean
  // null only for a fresh "new household" account that hasn't run its
  // create-your-family wizard yet. The app uses this to route them there.
  family_id: number | null
}

export interface SetupState {
  initialized: boolean
}

export const getSetup = () => request<SetupState>('/auth/setup')

export const getMe = () => request<User>('/auth/me')

export const login = (username: string, password: string) =>
  request<User>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })

export const bootstrap = (username: string, display_name: string, password: string) =>
  request<User>('/auth/bootstrap', {
    method: 'POST',
    body: JSON.stringify({ username, display_name, password }),
  })

export const logout = () => request<void>('/auth/logout', { method: 'POST' })

// ---- admin: family member management ----------------------------------------

export interface CreateUserPayload {
  username: string
  display_name: string
  password: string
  role: Role
  is_admin?: boolean
  // True creates a family-less parent account: whoever signs in with it
  // founds their own separate household via the create-family wizard. Used
  // only by "Invite another household", never by "Add family member".
  new_household?: boolean
}

export interface UpdateUserPayload {
  display_name?: string
  role?: Role
  is_admin?: boolean
  password?: string
}

export const listUsers = () => request<User[]>('/auth/users')

export const createUser = (payload: CreateUserPayload) =>
  request<User>('/auth/users', { method: 'POST', body: JSON.stringify(payload) })

export const updateUser = (id: number, payload: UpdateUserPayload) =>
  request<User>(`/auth/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })

export const deleteUser = (id: number) =>
  request<void>(`/auth/users/${id}`, { method: 'DELETE' })

// ---- families ----------------------------------------------------------------

export interface Family {
  id: number
  name: string
}

// The create-your-family wizard: a family-less account names its household and
// becomes its head (parent + admin). One family per account, ever.
export const createFamily = (name: string) =>
  request<Family>('/families', { method: 'POST', body: JSON.stringify({ name }) })

// ---- items and the home feed --------------------------------------------------

// The phone's local calendar date, YYYY-MM-DD. Sent with every "today"
// request because the server may live in a different timezone.
export function localDate(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export type ItemKind = 'routine' | 'task' | 'activity' | 'appointment'

// Who can SEE a card, separate from who is assigned to DO it. private = the
// owner plus anyone assigned; family = shown on the whole household's board.
export type Visibility = 'private' | 'family'

export type RepeatType = 'weekly' | 'monthly'

// A routine's recurrence. days are weekday numbers, 0 = Monday .. 6 = Sunday
// (weekly); month_day is a day of the month, 1-31 (monthly). interval is
// "every N weeks/months".
export interface Repeat {
  type: RepeatType
  days: number[]
  interval: number
  month_day: number | null
}

// One participant's own state on a routine, since routines are per-person.
export interface AssigneeCompletion {
  user_id: number
  completed: boolean
  streak: number
}

export interface FeedItem {
  id: number
  owner_id: number | null
  kind: ItemKind
  title: string
  notes: string
  visibility: Visibility
  assignees: User[]
  shared_to_feed: boolean
  time_of_day: string | null // start / "From", "HH:MM:SS"
  end_time: string | null // end / "To", "HH:MM:SS"
  all_day: boolean // all-day appointment
  date_for: string | null // "YYYY-MM-DD"
  repeat: Repeat | null // routines only
  // The requesting member's own view: for a routine, their own check and
  // streak (or, for a non-participant, whether everyone is done). For other
  // kinds, the single shared check.
  completed: boolean
  streak: number | null
  // Per-participant state for routines; null for every other kind.
  assignee_completions: AssigneeCompletion[] | null
}

export interface Feed {
  date: string
  today: FeedItem[]
  anytime: FeedItem[]
  upcoming: FeedItem[]
}

// The repeat object sent when creating/editing a routine. days/month_day are
// filled per type; the server ignores the ones the type doesn't use.
export interface RepeatInput {
  type: RepeatType
  days?: number[]
  interval?: number
  month_day?: number | null
}

export interface ItemPayload {
  kind: ItemKind
  title: string
  notes?: string
  // Who the card is shared with. Empty on a personal card means the owner
  // alone; set visibility to 'family' for Everyone.
  assignee_ids?: number[]
  visibility?: Visibility
  time_of_day?: string | null // start / "From"
  end_time?: string | null // end / "To"
  all_day?: boolean
  date_for?: string | null
  repeat?: RepeatInput | null // required for routines, ignored otherwise
  shared_to_feed?: boolean
}

export const getFeed = () => request<Feed>(`/items/feed?date=${localDate()}`)

export const createItem = (payload: ItemPayload) =>
  request<FeedItem>('/items', { method: 'POST', body: JSON.stringify(payload) })

export const updateItem = (id: number, payload: Partial<ItemPayload>) =>
  request<FeedItem>(`/items/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })

export const deleteItem = (id: number) => request<void>(`/items/${id}`, { method: 'DELETE' })

// forUserId lets a parent check a routine off on another member's behalf.
const completePath = (id: number, forUserId?: number) =>
  `/items/${id}/complete?date=${localDate()}${forUserId != null ? `&for=${forUserId}` : ''}`

export const completeItem = (id: number, forUserId?: number) =>
  request<FeedItem>(completePath(id, forUserId), { method: 'POST' })

export const uncompleteItem = (id: number, forUserId?: number) =>
  request<FeedItem>(completePath(id, forUserId), { method: 'DELETE' })

// ---- grocery list -----------------------------------------------------------

export interface GroceryItem {
  id: number
  title: string
  checked: boolean
  list_id: number | null // null = the General list
}

export interface GroceryList {
  id: number
  name: string
}

export interface GroceryState {
  lists: GroceryList[]
  items: GroceryItem[]
}

export const getGrocery = () => request<GroceryState>('/grocery')

export const addGroceryStore = (name: string) =>
  request<GroceryList>('/grocery/lists', { method: 'POST', body: JSON.stringify({ name }) })

export const removeGroceryStore = (id: number) =>
  request<void>(`/grocery/lists/${id}`, { method: 'DELETE' })

export const addGrocery = (title: string, listId: number | null) =>
  request<GroceryItem>('/grocery', {
    method: 'POST',
    body: JSON.stringify({ title, list_id: listId }),
  })

export const updateGrocery = (
  id: number,
  payload: { title?: string; checked?: boolean; list_id?: number | null },
) => request<GroceryItem>(`/grocery/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })

export const deleteGrocery = (id: number) =>
  request<void>(`/grocery/${id}`, { method: 'DELETE' })

export const clearCheckedGrocery = (listId: number | null) =>
  request<GroceryState>(`/grocery/clear-checked${listId !== null ? `?list_id=${listId}` : ''}`, {
    method: 'POST',
  })

// ---- profiles and moods ---------------------------------------------------------

export type MoodLevel = 'sunny' | 'partly' | 'cloudy' | 'rainy' | 'stormy'

export interface Mood {
  level: MoodLevel
  hidden: boolean
}

export interface FamilyMember extends User {
  mood: Mood | null
}

export interface Profile extends FamilyMember {
  bio: string
  created_at: string
}

export const getFamily = () => request<FamilyMember[]>(`/users?date=${localDate()}`)

export const getProfile = (id: number) =>
  request<Profile>(`/users/${id}/profile?date=${localDate()}`)

export const updateMyProfile = (payload: { display_name?: string; bio?: string }) =>
  request<Profile>('/me/profile', { method: 'PATCH', body: JSON.stringify(payload) })

export const setMyMood = (level: MoodLevel, hidden: boolean) =>
  request<Mood>('/me/mood', {
    method: 'PUT',
    body: JSON.stringify({ date_for: localDate(), level, hidden }),
  })

export const clearMyMood = () =>
  request<void>(`/me/mood?date=${localDate()}`, { method: 'DELETE' })
