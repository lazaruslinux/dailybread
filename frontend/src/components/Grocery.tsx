import { Check, Plus, Store, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Button, FormError } from './ui'
import { CollapsibleCard } from './CollapsibleCard'

// The family's shared grocery lists, one per store plus a built-in General
// list (list_id null). Everyone can read; only parents can touch (2026-07-03).
// Self-contained: fetches its own data so pages can just drop it in.
export function GroceryPanel() {
  const { user } = useAuth()
  const canEdit = user?.role === 'parent'

  const [lists, setLists] = useState<api.GroceryList[]>([])
  const [items, setItems] = useState<api.GroceryItem[]>([])
  // Which store chip is selected; null is the General list.
  const [active, setActive] = useState<number | null>(null)
  const [title, setTitle] = useState('')
  const [addingStore, setAddingStore] = useState(false)
  const [storeName, setStoreName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const visible = items.filter((i) => i.list_id === active)
  const checkedCount = visible.filter((i) => i.checked).length
  const unchecked = (listId: number | null) =>
    items.filter((i) => i.list_id === listId && !i.checked).length

  const refresh = useCallback(async () => {
    try {
      const state = await api.getGrocery()
      setLists(state.lists)
      setItems(state.items)
      // If the active store was removed elsewhere, fall back to General.
      setActive((a) => (a === null || state.lists.some((l) => l.id === a) ? a : null))
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
    await run(() => api.addGrocery(t, active))
    setTitle('')
  }

  async function onAddStore(e: FormEvent) {
    e.preventDefault()
    const name = storeName.trim()
    if (!name) return
    await run(async () => {
      const store = await api.addGroceryStore(name)
      setActive(store.id) // jump straight into the new store's list
    })
    setStoreName('')
    setAddingStore(false)
  }

  const activeStore = lists.find((l) => l.id === active)

  const chip = (selected: boolean) =>
    `flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold transition-colors ${
      selected ? 'bg-accent-bright/25 text-fg' : 'bg-fg/5 text-fg/55 hover:bg-fg/10'
    }`

  const toGrab = items.filter((i) => !i.checked).length

  return (
    <CollapsibleCard
      title="Grocery list"
      summary={toGrab > 0 ? `${toGrab} to grab` : undefined}
      storageKey="grocery"
    >
      {/* Store chips. General is built in; parents can add more. */}
      <div className="-mx-1 mb-4 flex gap-1.5 overflow-x-auto px-1 pb-1 [scrollbar-width:none]">
        <button type="button" onClick={() => setActive(null)} className={chip(active === null)}>
          General
          {unchecked(null) > 0 && <span className="text-xs text-fg/50">{unchecked(null)}</span>}
        </button>
        {lists.map((l) => (
          <button
            key={l.id}
            type="button"
            onClick={() => setActive(l.id)}
            className={chip(active === l.id)}
          >
            {l.name}
            {unchecked(l.id) > 0 && <span className="text-xs text-fg/50">{unchecked(l.id)}</span>}
          </button>
        ))}
        {canEdit && !addingStore && (
          <button
            type="button"
            onClick={() => setAddingStore(true)}
            className="flex shrink-0 items-center gap-1 rounded-full border border-dashed border-fg/25 px-3 py-1.5 text-sm font-semibold text-fg/55 transition-colors hover:bg-fg/10"
          >
            <Store className="h-3.5 w-3.5" /> Add store
          </button>
        )}
      </div>

      {addingStore && (
        <form onSubmit={onAddStore} className="mb-4 flex gap-2">
          <input
            value={storeName}
            onChange={(e) => setStoreName(e.target.value)}
            maxLength={60}
            placeholder="Store name"
            aria-label="Store name"
            className="field flex-1"
            autoFocus
          />
          <button
            type="submit"
            disabled={busy || !storeName.trim()}
            aria-label="Add this store"
            className="flex w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-r from-accent to-accent-strong disabled:opacity-40"
          >
            <Check className="h-5 w-5" strokeWidth={2.5} />
          </button>
          <button
            type="button"
            onClick={() => {
              setAddingStore(false)
              setStoreName('')
            }}
            aria-label="Cancel adding store"
            className="flex w-11 shrink-0 items-center justify-center rounded-xl bg-fg/10 text-fg/60"
          >
            <X className="h-5 w-5" />
          </button>
        </form>
      )}

      {canEdit && (
        <form onSubmit={onAdd} className="mb-3 flex gap-2">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={120}
            placeholder={activeStore ? `Add an item for ${activeStore.name}` : 'Add an item'}
            aria-label="Add an item"
            className="field flex-1"
          />
          <button
            type="submit"
            disabled={busy || !title.trim()}
            aria-label="Add to the list"
            className="flex w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-r from-accent to-accent-strong disabled:opacity-40"
          >
            <Plus className="h-5 w-5" strokeWidth={2.5} />
          </button>
        </form>
      )}

      {visible.length === 0 && (
        <p className="py-6 text-center text-sm text-fg/50">
          {activeStore ? `Nothing for ${activeStore.name} yet.` : 'The list is empty.'}
          {canEdit ? ' Add the first item above.' : ''}
        </p>
      )}
      <ul className="flex flex-col gap-1">
        {visible.map((item) => (
          <li key={item.id} className="flex items-center gap-1">
            <button
              type="button"
              disabled={!canEdit || busy}
              onClick={() => run(() => api.updateGrocery(item.id, { checked: !item.checked }))}
              className="flex min-w-0 flex-1 items-center gap-3 rounded-xl p-2.5 text-left transition-colors enabled:hover:bg-fg/5"
            >
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-colors ${
                  item.checked ? 'border-emerald-400/60 bg-emerald-400/25' : 'border-fg/25'
                }`}
              >
                {item.checked && <Check className="h-3.5 w-3.5 text-emerald-300" strokeWidth={3} />}
              </span>
              <span
                className={`truncate ${
                  item.checked ? 'text-fg/45 line-through decoration-fg/30' : 'text-fg/90'
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
                className="shrink-0 rounded-lg p-2 text-fg/30 transition-colors hover:bg-fg/10 hover:text-rose-300"
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
          onClick={() => run(() => api.clearCheckedGrocery(active))}
          className="mt-3 w-full"
        >
          Clear checked ({checkedCount})
        </Button>
      )}
      {canEdit && activeStore && (
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            run(async () => {
              await api.removeGroceryStore(activeStore.id)
              setActive(null)
            })
          }
          className="mt-3 w-full text-center text-xs font-semibold text-fg/35 transition-colors hover:text-rose-300"
        >
          Remove {activeStore.name} (its items move to General)
        </button>
      )}
    </CollapsibleCard>
  )
}
