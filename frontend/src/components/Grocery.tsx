import { motion } from 'framer-motion'
import { Check, ChevronRight, Plus, ShoppingCart, Trash2, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import * as api from '../lib/api'
import { Button, FormError } from './ui'

// The family's shared grocery list. Everyone can open it and read it; only
// parents can add, check, delete, or clear (decided 2026-07-03).

// Pinned card that sits above the day's feed and opens the sheet.
export function GroceryCard({ items, onOpen }: { items: api.GroceryItem[]; onOpen: () => void }) {
  const toGrab = items.filter((i) => !i.checked).length
  const checked = items.length - toGrab
  const summary =
    items.length === 0
      ? 'Nothing on the list'
      : `${toGrab} to grab${checked > 0 ? ` · ${checked} checked` : ''}`

  return (
    <motion.button
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      whileTap={{ scale: 0.97 }}
      onClick={onOpen}
      className="glass mb-3 flex w-full items-center gap-4 p-4 text-left"
    >
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-emerald-400/15">
        <ShoppingCart className="h-5 w-5 text-emerald-300" strokeWidth={2} />
      </div>
      <div className="min-w-0 flex-1">
        <span className="block text-[10px] font-semibold uppercase tracking-wide text-white/50">
          Groceries
        </span>
        <p className="truncate font-semibold text-white">Grocery list</p>
        <p className="truncate text-sm text-white/60">{summary}</p>
      </div>
      <ChevronRight className="h-5 w-5 shrink-0 text-white/35" />
    </motion.button>
  )
}

// Bottom-sheet checklist. Same shell as ItemSheet: tap outside or X to close.
export function GrocerySheet({
  items,
  canEdit,
  onClose,
  onChanged,
}: {
  items: api.GroceryItem[]
  canEdit: boolean
  onClose: () => void
  onChanged: () => void
}) {
  const [title, setTitle] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const checkedCount = items.filter((i) => i.checked).length

  async function run(action: () => Promise<unknown>) {
    setError(null)
    setBusy(true)
    try {
      await action()
      onChanged()
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
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/50 p-4 backdrop-blur-sm sm:items-center"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 40 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        className="glass flex max-h-[90svh] w-full max-w-sm flex-col p-6"
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold">Grocery list</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-white/50 hover:bg-white/10 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {canEdit && (
          <form onSubmit={onAdd} className="mb-4 flex gap-2">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={120}
              placeholder="Add an item"
              aria-label="Add an item"
              className="field flex-1"
              autoFocus
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

        <div className="min-h-0 flex-1 overflow-y-auto">
          {items.length === 0 && (
            <p className="py-8 text-center text-sm text-white/50">
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
        </div>

        <FormError message={error} />
        {canEdit && checkedCount > 0 && (
          <Button
            type="button"
            variant="danger"
            disabled={busy}
            onClick={() => run(() => api.clearCheckedGrocery())}
            className="mt-3"
          >
            Clear checked ({checkedCount})
          </Button>
        )}
      </motion.div>
    </motion.div>
  )
}
