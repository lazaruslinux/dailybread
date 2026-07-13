// Color themes. A theme is just a set of CSS-variable overrides on the root
// (see index.css); here we persist the choice per user (family members share
// devices, so key it by user id) and toggle the data-theme attribute.

export type Theme = 'light' | 'dark'

// Two choices, plainly named. Light Amber is the app default (the bare :root
// in index.css); Dark Crust is the opt-in alternative.
export const THEMES: { id: Theme; label: string }[] = [
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
]

// Anything not in this set (including retired themes like crimson/forest a user
// may still have saved) falls back to the default, which is now Light Amber.
const VALID = new Set<Theme>(['light', 'dark'])

function storageKey(userId?: number): string {
  return `db_theme_${userId ?? 'anon'}`
}

export function getTheme(userId?: number): Theme {
  const t = localStorage.getItem(storageKey(userId)) as Theme | null
  return t && VALID.has(t) ? t : 'light'
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  // Light Amber is the bare root, so it carries no attribute; only the dark
  // theme sets one.
  if (theme === 'dark') root.setAttribute('data-theme', 'dark')
  else root.removeAttribute('data-theme')
}

export function setTheme(userId: number | undefined, theme: Theme): void {
  localStorage.setItem(storageKey(userId), theme)
  applyTheme(theme)
}
