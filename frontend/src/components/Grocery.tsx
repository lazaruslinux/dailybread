import { Check, FolderInput, Plus, Store, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { announceChange } from '../lib/changes'
import { Button, FormError } from './ui'
import { CollapsibleCard } from './CollapsibleCard'

// "All" is the combined view (every store's items at once); a store id filters to
// that store; null is the built-in "Unsorted" bucket (items with no store).
type Tab = 'all' | number | null

// The family's shared grocery lists: one per store, plus a built-in bucket for
// store-less items ("Unsorted"). The default "All" tab shows everything at once,
// grouped by store. Everyone can read; only parents can touch (2026-07-03).
// Self-contained: fetches its own data so pages can just drop it in.
export function GroceryPanel() {
  const { user } = useAuth()
  const canEdit = user?.role === 'parent'

  const [lists, setLists] = useState<api.GroceryList[]>([])
  const [items, setItems] = useState<api.GroceryItem[]>([])
  // Selected tab: "All" (combined) by default, a store id, or null (Unsorted).
  const [active, setActive] = useState<Tab>('all')
  const [title, setTitle] = useState('')
  const [addingStore, setAddingStore] = useState(false)
  const [storeName, setStoreName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // The item whose "move to…" chips are showing, if any.
  const [movingId, setMovingId] = useState<number | null>(null)
  // Read-ordering guard for refresh(); see there.
  const listSeq = useRef(0)

  const isAll = active === 'all'
  // Items shown in the flat (single-store / Unsorted) views.
  const visible = isAll ? items : items.filter((i) => i.list_id === active)
  const checkedItems = visible.filter((i) => i.checked)
  const unchecked = (listId: number | null) =>
    items.filter((i) => i.list_id === listId && !i.checked).length
  const hasUnsorted = items.some((i) => i.list_id === null)

  // For the "All" view: stores (in tab order) that have items, then an Unsorted
  // group for store-less items. Empty stores are left out — "all the stores that
  // have items".
  const groups = (): { key: string; label: string; items: api.GroceryItem[] }[] => {
    const out: { key: string; label: string; items: api.GroceryItem[] }[] = []
    for (const l of lists) {
      const its = items.filter((i) => i.list_id === l.id)
      if (its.length) out.push({ key: `s${l.id}`, label: l.name, items: its })
    }
    const unsorted = items.filter((i) => i.list_id === null)
    if (unsorted.length) out.push({ key: 'unsorted', label: 'Unsorted', items: unsorted })
    return out
  }

  const refresh = useCallback(async () => {
    // Only the newest read may paint: a slow pre-write request can otherwise
    // land after the post-write one and put the old list back on screen.
    const seq = ++listSeq.current
    try {
      const state = await api.getGrocery()
      if (seq !== listSeq.current) return
      setLists(state.lists)
      setItems(state.items)
      // If the active store was removed elsewhere, fall back to the All view.
      setActive((a) =>
        a === 'all' || a === null || state.lists.some((l) => l.id === a) ? a : 'all',
      )
      setError(null)
    } catch (err) {
      if (seq !== listSeq.current) return
      setError(err instanceof api.ApiError ? err.message : 'Could not load the list.')
    }
  }, [])

  useEffect(() => {
    refresh()
    const onVisible = () => document.visibilityState === 'visible' && refresh()
    // Other Kitchen features (a recipe pushing its ingredients) announce list
    // changes with this event so the panel refreshes without a reload.
    const onChanged = () => refresh()
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('db:grocery-changed', onChanged)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('db:grocery-changed', onChanged)
    }
  }, [refresh])

  async function run(action: () => Promise<unknown>) {
    setError(null)
    setBusy(true)
    try {
      await action()
      // Announce before reloading, not after: the desktop aside shows the same
      // list and its refetch then coalesces with this one into a single
      // request instead of arriving as a second round trip.
      announceChange('db:grocery-changed')
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
    // From "All" (which isn't a store), new items go to Unsorted.
    const target = isAll ? null : active
    await run(() => api.addGrocery(t, target))
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

  async function clearChecked() {
    await run(async () => {
      if (isAll) {
        // Clear checked across every list that has one.
        const listIds = [...new Set(checkedItems.map((i) => i.list_id))]
        await Promise.all(listIds.map((lid) => api.clearCheckedGrocery(lid)))
      } else {
        await api.clearCheckedGrocery(active)
      }
    })
  }

  const activeStore = lists.find((l) => l.id === active)

  // The button keeps the full 44px touch box; the coloured pill inside it is
  // deliberately shorter, so the row reads light without shrinking the target.
  // The invisible-slop trick (db-tap44) cannot help on this row: the card
  // header sits hard above it and the add-item field hard below, and both win
  // the hit test inside the slop.
  const chipButton = 'group flex min-h-11 shrink-0 items-center'
  const chipPill = (selected: boolean) =>
    `flex h-8 items-center gap-1.5 rounded-full px-3 text-sm font-semibold transition-colors ${
      selected ? 'bg-accent-bright/25 text-fg' : 'bg-fg/5 text-fg/55 group-hover:bg-fg/10'
    }`

  const toGrab = items.filter((i) => !i.checked).length

  async function moveItem(id: number, listId: number | null) {
    setMovingId(null)
    await run(() => api.updateGrocery(id, { list_id: listId }))
  }

  // One grocery row (checkbox + title + parent-only move/delete), reused by the
  // flat and grouped views. The move button reveals destination chips (every
  // store + Unsorted, minus where it already is) so an item can be re-filed.
  const renderItem = (item: api.GroceryItem) => {
    const destinations: { id: number | null; label: string }[] = [
      { id: null, label: 'Unsorted' },
      ...lists.map((l) => ({ id: l.id as number | null, label: l.name })),
    ].filter((d) => d.id !== item.list_id)
    return (
      // The row wraps: the "move to" chips ride a second line inside it.
      <li key={item.id} className="db-row flex-wrap gap-x-1 gap-y-0">
        <button
          type="button"
          disabled={!canEdit || busy}
          onClick={() => run(() => api.updateGrocery(item.id, { checked: !item.checked }))}
          className="-my-2 flex min-h-11 min-w-0 flex-1 items-center gap-3 py-2 text-left"
        >
          <span
            className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-colors ${
              item.checked ? 'border-emerald-400/60 bg-emerald-400/25' : 'border-fg/25'
            }`}
          >
            {item.checked && <Check className="h-3.5 w-3.5 text-emerald-300" strokeWidth={3} />}
          </span>
          <span
            className={`truncate text-[0.9375rem] ${item.checked ? 'text-fg/45 line-through decoration-fg/30' : 'text-fg/90'}`}
          >
            {item.title}
          </span>
        </button>
        {canEdit && destinations.length > 0 && (
          <button
            type="button"
            disabled={busy}
            onClick={() => setMovingId((m) => (m === item.id ? null : item.id))}
            aria-label={`Move ${item.title}`}
            aria-expanded={movingId === item.id}
            className={`-m-2.5 shrink-0 rounded-lg p-3.5 transition-colors hover:bg-fg/10 ${
              movingId === item.id ? 'text-accent-bright' : 'text-fg/30 hover:text-fg/70'
            }`}
          >
            <FolderInput className="h-4 w-4" />
          </button>
        )}
        {canEdit && (
          <button
            type="button"
            disabled={busy}
            onClick={() => run(() => api.deleteGrocery(item.id))}
            aria-label={`Delete ${item.title}`}
            className="-m-2.5 shrink-0 rounded-lg p-3.5 text-fg/30 transition-colors hover:bg-fg/10 hover:text-rose-300"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
        {movingId === item.id && (
          <div className="ml-8 flex w-full flex-wrap gap-1.5 pb-1">
            <span className="self-center text-[11px] font-semibold uppercase tracking-wide text-fg/40">
              Move to
            </span>
            {destinations.map((d) => (
              <button
                key={d.id ?? 'unsorted'}
                type="button"
                disabled={busy}
                onClick={() => moveItem(item.id, d.id)}
                className="inline-flex min-h-11 items-center rounded-full bg-fg/5 px-2.5 py-1 text-xs font-semibold text-fg/70 transition-colors hover:bg-accent-bright/20 hover:text-fg"
              >
                {d.label}
              </button>
            ))}
          </div>
        )}
      </li>
    )
  }

  return (
    <CollapsibleCard
      title="Grocery list"
      summary={toGrab > 0 ? `${toGrab} to grab` : undefined}
      storageKey="grocery"
      defaultOpen
      flush
    >
      {/* Tabs, store form and the add line stay padded; the list below is full bleed. */}
      <div className="px-3.5">
        {/* Tabs: All (combined) + Unsorted (store-less) + one per store; parents add more. */}
        <div className="-mx-1 mb-2 flex gap-1.5 overflow-x-auto px-1 pb-1 [scrollbar-width:none]">
          <button type="button" onClick={() => setActive('all')} className={chipButton}>
            <span className={chipPill(isAll)}>
              All
              {toGrab > 0 && <span className="text-xs text-fg/50">{toGrab}</span>}
            </span>
          </button>
          {(hasUnsorted || active === null) && (
            <button type="button" onClick={() => setActive(null)} className={chipButton}>
              <span className={chipPill(active === null)}>
                Unsorted
                {unchecked(null) > 0 && <span className="text-xs text-fg/50">{unchecked(null)}</span>}
              </span>
            </button>
          )}
          {lists.map((l) => (
            <button key={l.id} type="button" onClick={() => setActive(l.id)} className={chipButton}>
              <span className={chipPill(active === l.id)}>
                {l.name}
                {unchecked(l.id) > 0 && <span className="text-xs text-fg/50">{unchecked(l.id)}</span>}
              </span>
            </button>
          ))}
          {canEdit && !addingStore && (
            <button type="button" onClick={() => setAddingStore(true)} className={chipButton}>
              <span className="flex h-8 items-center gap-1 rounded-full border border-dashed border-fg/25 px-3 text-sm font-semibold text-fg/55 transition-colors group-hover:bg-fg/10">
                <Store className="h-3.5 w-3.5" /> Add store
              </span>
            </button>
          )}
      </div>

      {addingStore && (
        <form onSubmit={onAddStore} className="mb-2.5 flex gap-2">
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
        <form onSubmit={onAdd} className="mb-1.5 flex gap-2">
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

      </div>

      {isAll ? (
        // Combined view: every store that has items, then Unsorted.
        groups().length === 0 ? (
          <p className="db-emptyline">
            The list is empty.{canEdit ? ' Add the first item above.' : ''}
          </p>
        ) : (
          <div>
            {groups().map((g) => (
              <div key={g.key}>
                <div className="db-sect">
                  <span>{g.label}</span>
                </div>
                <ul>{g.items.map(renderItem)}</ul>
              </div>
            ))}
          </div>
        )
      ) : (
        <>
          {visible.length === 0 && (
            <p className="db-emptyline">
              {activeStore ? `Nothing for ${activeStore.name} yet.` : 'Nothing unsorted.'}
              {canEdit ? ' Add the first item above.' : ''}
            </p>
          )}
          <ul>{visible.map(renderItem)}</ul>
        </>
      )}

      <div className="px-3.5">
        <FormError message={error} />
        {canEdit && checkedItems.length > 0 && (
          <Button type="button" variant="danger" disabled={busy} onClick={clearChecked} className="mt-2.5 min-h-11 w-full">
            Clear checked ({checkedItems.length})
          </Button>
        )}
        {canEdit && activeStore && (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(async () => {
                await api.removeGroceryStore(activeStore.id)
                setActive('all')
              })
            }
            className="mt-2.5 w-full text-center text-xs font-semibold text-fg/35 transition-colors hover:text-rose-300"
          >
            Remove {activeStore.name} (its items move to Unsorted)
          </button>
        )}
      </div>
    </CollapsibleCard>
  )
}
