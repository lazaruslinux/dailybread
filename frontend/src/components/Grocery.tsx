import { Check, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Button, FormError } from './ui'

// The family's shared grocery list, now living on the Kitchen tab. Everyone
// can read it; only parents can add, check, delete, or clear (2026-07-03).
// Self-contained: fetches its own data so pages can just drop it in.
export function GroceryPanel() {
  const { user } = useAuth()
  const canEdit = user?.role === 'parent'

  const [items, setItems] = useState<api.GroceryItem[]>([])
  const [title, setTitle] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const checkedCount = items.filter((i) => i.checked).length

  const refresh = useCallback(async () => {
    try {
      setItems(await api.listGrocery())
      setError(null)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load the list.')
    }
  }, [])

  useEffect(() => {
    refresh()
    const onVisible = () => document.visibilityState === 'visible' && refresh()
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [refresh])

  async function run(action: () => Promise<unknown>) {
    setError(null)
    setBusy(true)
    try {
      await action()
      await refresh()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  async function onAdd(e: FormEvent) {
    e.preventDefault()
    const t = title.trim()
    if (!t) return
    await run(() => api.addGrocery(t))
    setTitle('')
  }

  return (
    <section className="glass p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="font-bold">Grocery list</h2>
        {items.length > 0 && (
          <span className="text-xs text-white/50">
            {items.length - checkedCount} to grab
            {checkedCount > 0 ? ` · ${checkedCount} checked` : ''}
          </span>
        )}
      </div>

      {canEdit && (
        <form onSubmit={onAdd} className="mb-3 flex gap-2">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={120}
            placeholder="Add an item"
            aria-label="Add an item"
            className="field flex-1"
          />
          <button
            type="submit"
            disabled={busy || !title.trim()}
            aria-label="Add to the list"
            className="flex w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 disabled:opacity-40"
          >
            <Plus className="h-5 w-5" strokeWidth={2.5} />
          </button>
        </form>
      )}

      {items.length === 0 && (
        <p className="py-6 text-center text-sm text-white/50">
          The list is empty{canEdit ? '. Add the first item above.' : '.'}
        </p>
      )}
      <ul className="flex flex-col gap-1">
        {items.map((item) => (
          <li key={item.id} className="flex items-center gap-1">
            <button
              type="button"
              disabled={!canEdit || busy}
              onClick={() => run(() => api.updateGrocery(item.id, { checked: !item.checked }))}
              className="flex min-w-0 flex-1 items-center gap-3 rounded-xl p-2.5 text-left transition-colors enabled:hover:bg-white/5"
            >
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-colors ${
                  item.checked ? 'border-emerald-400/60 bg-emerald-400/25' : 'border-white/25'
                }`}
              >
                {item.checked && <Check className="h-3.5 w-3.5 text-emerald-300" strokeWidth={3} />}
              </span>
              <span
                className={`truncate ${
                  item.checked ? 'text-white/45 line-through decoration-white/30' : 'text-white/90'
                }`}
              >
                {item.title}
              </span>
            </button>
            {canEdit && (
              <button
                type="button"
                disabled={busy}
                onClick={() => run(() => api.deleteGrocery(item.id))}
                aria-label={`Delete ${item.title}`}
                className="shrink-0 rounded-lg p-2 text-white/30 transition-colors hover:bg-white/10 hover:text-rose-300"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </li>
        ))}
      </ul>

      <FormError message={error} />
      {canEdit && checkedCount > 0 && (
        <Button
          type="button"
          variant="danger"
          disabled={busy}
          onClick={() => run(() => api.clearCheckedGrocery())}
          className="mt-3 w-full"
        >
          Clear checked ({checkedCount})
        </Button>
      )}
    </section>
  )
}
