import { Archive, ChevronDown, NotebookPen } from 'lucide-react'
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

// A member's private daily journal, in the You tab. You only ever write today's
// entry; at midnight it moves to the archive and a fresh page opens. Earlier
// days are tucked behind a button and their text stays hidden until you open a
// specific day, so glancing at the tab never exposes what you wrote. Nothing
// here is visible to another member — there is no endpoint to read someone
// else's, so this is the one truly private corner of the app.
export function JournalCard() {
  const today = api.localDate()
  const [text, setText] = useState('')
  const [saved, setSaved] = useState('')
  const [history, setHistory] = useState<api.JournalEntry[]>([])
  const [busy, setBusy] = useState(false)
  const [justSaved, setJustSaved] = useState(false)
  const [archiveOpen, setArchiveOpen] = useState(false)
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

  // Today already lives in the editor above, so keep it out of the archive.
  const past = history.filter((h) => h.date_for !== today)

  return (
    <div className="glass p-3.5">
      <span className="db-micro flex items-center gap-2">
        <NotebookPen className="h-3.5 w-3.5 text-fg/50" /> Daily journal
      </span>
      <p className="mt-1 font-display text-base leading-tight text-fg">{formatDay(today)}</p>
      <p className="mb-2.5 mt-0.5 text-xs text-fg/45">
        How did your day turn out? Write out how you feel here, and save it if you'd like.
      </p>

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
        <div className="mt-3 border-t border-[var(--line-soft)] pt-2">
          <button
            type="button"
            onClick={() => setArchiveOpen((o) => !o)}
            aria-expanded={archiveOpen}
            className="flex w-full items-center justify-between gap-2 rounded-xl px-1 py-1.5 text-left text-fg/70 transition-colors hover:text-fg"
          >
            <span className="flex items-center gap-2 text-sm font-semibold">
              <Archive className="h-4 w-4 text-fg/45" />
              Past entries
              <span className="text-fg/40">({past.length})</span>
            </span>
            <ChevronDown
              className={`h-4 w-4 shrink-0 text-fg/40 transition-transform ${archiveOpen ? 'rotate-180' : ''}`}
            />
          </button>

          {archiveOpen && (
            <div className="mt-1.5 flex flex-col gap-1">
              {past.map((h) => {
                const open = openDay === h.date_for
                return (
                  <div key={h.date_for} className="rounded-xl border border-fg/10 bg-fg/5">
                    <button
                      type="button"
                      onClick={() => setOpenDay(open ? null : h.date_for)}
                      aria-expanded={open}
                      className="flex min-h-11 w-full items-center justify-between gap-2 px-3 py-1.5 text-left"
                    >
                      {/* Date only — the entry's text stays hidden until this
                          day is opened, so the archive never shows content at a glance. */}
                      <span className="text-[13.5px] font-semibold text-fg/85">{formatDay(h.date_for)}</span>
                      <ChevronDown
                        className={`h-4 w-4 shrink-0 text-fg/40 transition-transform ${open ? 'rotate-180' : ''}`}
                      />
                    </button>
                    {open && (
                      <p className="whitespace-pre-wrap px-3 pb-2.5 text-[13.5px] leading-relaxed text-fg/75">
                        {h.body}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
