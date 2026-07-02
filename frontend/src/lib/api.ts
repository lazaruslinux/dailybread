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
