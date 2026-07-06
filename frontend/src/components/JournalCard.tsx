import { ChevronDown, NotebookPen } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../lib/api'
import { Button } from './ui'

function formatDay(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

// A member's private daily journal, in the You tab. You always edit today's
// entry; earlier days sit below as read-only, tap-to-expand cards. Nothing here
// is ever visible to another member — there is no endpoint to read someone
// else's, so this is the one truly private corner of the app.
export function JournalCard() {
  const today = api.localDate()
  const [text, setText] = useState('')
  const [saved, setSaved] = useState('')
  const [history, setHistory] = useState<api.JournalEntry[]>([])
  const [busy, setBusy] = useState(false)
  const [justSaved, setJustSaved] = useState(false)
  const [openDay, setOpenDay] = useState<string | null>(null)
  const savedTimer = useRef<number | undefined>(undefined)

  const load = useCallback(async () => {
    const [entry, hist] = await Promise.all([api.getJournal(), api.getJournalHistory()])
    setText(entry?.body ?? '')
    setSaved(entry?.body ?? '')
    setHistory(hist)
  }, [])

  useEffect(() => {
    load()
    return () => window.clearTimeout(savedTimer.current)
  }, [load])

  const dirty = text.trim() !== saved.trim()

  async function save() {
    setBusy(true)
    try {
      const entry = await api.saveJournal(text)
      setText(entry.body)
      setSaved(entry.body)
      setHistory(await api.getJournalHistory())
      setJustSaved(true)
      window.clearTimeout(savedTimer.current)
      savedTimer.current = window.setTimeout(() => setJustSaved(false), 2500)
    } finally {
      setBusy(false)
    }
  }

  // Today already lives in the editor above, so keep it out of the list below.
  const past = history.filter((h) => h.date_for !== today)

  return (
    <div className="glass p-4">
      <span className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-fg/50">
        <NotebookPen className="h-3.5 w-3.5 text-accent-bright" /> Journal
      </span>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Write about your day"
        rows={4}
        className="field min-h-[6rem] resize-y leading-relaxed"
      />
      <div className="mt-2 flex items-center justify-between gap-3">
        <span className="text-xs text-fg/40">
          {justSaved ? 'Saved' : dirty ? 'Unsaved changes' : 'Only you can see this'}
        </span>
        <Button
          type="button"
          onClick={save}
          disabled={busy || !dirty}
          className="px-4 py-2 text-xs"
        >
          {busy ? 'Saving' : 'Save'}
        </Button>
      </div>

      {past.length > 0 && (
        <div className="mt-4 border-t border-fg/10 pt-3">
          <span className="mb-2 block text-[11px] font-semibold uppercase tracking-wide text-fg/40">
            Past entries
          </span>
          <div className="flex flex-col gap-1.5">
            {past.map((h) => {
              const open = openDay === h.date_for
              return (
                <div key={h.date_for} className="rounded-xl border border-fg/10 bg-fg/5">
                  <button
                    type="button"
                    onClick={() => setOpenDay(open ? null : h.date_for)}
                    aria-expanded={open}
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
                  >
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-fg/85">
                        {formatDay(h.date_for)}
                      </span>
                      {!open && <span className="block truncate text-xs text-fg/45">{h.body}</span>}
                    </span>
                    <ChevronDown
                      className={`h-4 w-4 shrink-0 text-fg/40 transition-transform ${open ? 'rotate-180' : ''}`}
                    />
                  </button>
                  {open && (
                    <p className="whitespace-pre-wrap px-3 pb-3 text-sm leading-relaxed text-fg/75">
                      {h.body}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
