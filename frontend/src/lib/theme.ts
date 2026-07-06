// Color themes. A theme is just a set of CSS-variable overrides on the root
// (see index.css); here we persist the choice per user (family members share
// devices, so key it by user id) and toggle the data-theme attribute.

export type Theme = 'default' | 'crimson' | 'forest' | 'light'

export const THEMES: { id: Theme; label: string; hint: string }[] = [
  { id: 'default', label: 'Default', hint: 'Indigo aurora' },
  { id: 'crimson', label: 'Crimson', hint: 'Near-black + crimson' },
  { id: 'forest', label: 'Forest', hint: 'Near-black + greens' },
  { id: 'light', label: 'Light', hint: 'Soft light + indigo' },
]

const VALID = new Set<Theme>(['default', 'crimson', 'forest', 'light'])

function storageKey(userId?: number): string {
  return `db_theme_${userId ?? 'anon'}`
}

export function getTheme(userId?: number): Theme {
  const t = localStorage.getItem(storageKey(userId)) as Theme | null
  return t && VALID.has(t) ? t : 'default'
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'default') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
}

export function setTheme(userId: number | undefined, theme: Theme): void {
  localStorage.setItem(storageKey(userId), theme)
  applyTheme(theme)
}
