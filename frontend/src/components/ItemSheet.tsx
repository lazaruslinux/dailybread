import { motion } from 'framer-motion'
import { Trash2, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import * as api from '../lib/api'
import { Button, Field, FormError } from './ui'

const KIND_LABEL: Record<api.ItemKind, string> = {
  routine: 'Routine',
  todo: 'To-do',
  event: 'Schedule',
}

const KIND_HINT: Record<api.ItemKind, string> = {
  routine: 'Repeats every day',
  todo: 'One-off, date optional',
  event: 'On a specific day',
}

// Bottom sheet for parents to add or edit a card. Same pattern as the admin
// member sheet: tap outside or the X to close, primary action at the bottom.
export function ItemSheet({
  item,
  family,
  onClose,
  onSaved,
}: {
  item: api.FeedItem | null // null = creating
  family: api.FamilyMember[]
  onClose: () => void
  onSaved: () => void
}) {
  const creating = item === null
  const [kind, setKind] = useState<api.ItemKind>(item?.kind ?? 'routine')
  const [title, setTitle] = useState(item?.title ?? '')
  const [notes, setNotes] = useState(item?.notes ?? '')
  const [assignee, setAssignee] = useState<number | ''>(item?.assignee?.id ?? '')
  const [time, setTime] = useState(item?.time_of_day?.slice(0, 5) ?? '')
  const [date, setDate] = useState(item?.date_for ?? '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    const payload: api.ItemPayload = {
      kind,
      title,
      notes,
      assignee_id: assignee === '' ? null : assignee,
      time_of_day: time || null,
      date_for: kind === 'routine' ? null : date || null,
    }
    try {
      if (creating) await api.createItem(payload)
      else await api.updateItem(item.id, payload)
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  async function onDelete() {
    if (creating) return
    setBusy(true)
    try {
      await api.deleteItem(item.id)
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
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
        className="glass max-h-[90svh] w-full max-w-sm overflow-y-auto p-6"
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-lg font-bold">{creating ? 'Add to the board' : 'Edit card'}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-white/50 hover:bg-white/10 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div>
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-white/50">
              Type
            </span>
            <div className="grid grid-cols-3 gap-2">
              {(Object.keys(KIND_LABEL) as api.ItemKind[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setKind(k)}
                  disabled={!creating}
                  className={`rounded-xl border px-2 py-2 text-sm font-semibold transition-colors disabled:opacity-60 ${
                    kind === k
                      ? 'border-indigo-400/60 bg-indigo-400/20 text-white'
                      : 'border-white/10 bg-white/5 text-white/55 hover:bg-white/10'
                  }`}
                >
                  {KIND_LABEL[k]}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-white/40">{KIND_HINT[kind]}</p>
          </div>

          <Field label="Title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} autoFocus={creating} required />
          <Field label="Notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={300} />

          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-white/50">
              Who is it for
            </span>
            <select
              value={assignee}
              onChange={(e) => setAssignee(e.target.value === '' ? '' : Number(e.target.value))}
              className="field appearance-none"
            >
              <option value="">Everyone</option>
              {family.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </label>

          <div className={`grid gap-3 ${kind === 'routine' ? '' : 'grid-cols-2'}`}>
            <Field label="Time (optional)" type="time" value={time} onChange={(e) => setTime(e.target.value)} />
            {kind !== 'routine' && (
              <Field label="Date (optional)" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            )}
          </div>

          <FormError message={error} />
          <Button type="submit" disabled={busy || !title.trim()} className="mt-1">
            {busy ? 'Saving' : creating ? 'Add card' : 'Save changes'}
          </Button>
          {!creating && (
            <Button type="button" variant="danger" onClick={onDelete} disabled={busy} className="flex items-center justify-center gap-1.5">
              <Trash2 className="h-4 w-4" /> Remove from board
            </Button>
          )}
        </form>
      </motion.div>
    </motion.div>
  )
}
