// Tiny API client. All requests go through the /api prefix, which the Vite dev
// server proxies to the FastAPI backend (see vite.config.ts). On the home server
// the same /api path is routed to the backend by the LAN-only Caddy proxy.
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

// ---- items and the home feed --------------------------------------------------

// The phone's local calendar date, YYYY-MM-DD. Sent with every "today"
// request because the server may live in a different timezone.
export function localDate(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export type ItemKind = 'routine' | 'todo' | 'event'

export interface FeedItem {
  id: number
  kind: ItemKind
  title: string
  notes: string
  assignee: User | null
  time_of_day: string | null // "HH:MM:SS"
  date_for: string | null // "YYYY-MM-DD"
  completed: boolean
  streak: number | null
}

export interface Feed {
  date: string
  today: FeedItem[]
  anytime: FeedItem[]
  upcoming: FeedItem[]
}

export interface ItemPayload {
  kind: ItemKind
  title: string
  notes?: string
  assignee_id?: number | null
  time_of_day?: string | null
  date_for?: string | null
}

export const getFeed = () => request<Feed>(`/items/feed?date=${localDate()}`)

export const createItem = (payload: ItemPayload) =>
  request<FeedItem>('/items', { method: 'POST', body: JSON.stringify(payload) })

export const updateItem = (id: number, payload: Partial<ItemPayload>) =>
  request<FeedItem>(`/items/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })

export const deleteItem = (id: number) => request<void>(`/items/${id}`, { method: 'DELETE' })

export const completeItem = (id: number) =>
  request<FeedItem>(`/items/${id}/complete?date=${localDate()}`, { method: 'POST' })

export const uncompleteItem = (id: number) =>
  request<FeedItem>(`/items/${id}/complete?date=${localDate()}`, { method: 'DELETE' })

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
