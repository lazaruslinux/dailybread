import { Clock } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

// A time field you can type into ("8am", "8:00 AM", "14:30") or pick from a
// list of half-hours. Deliberately NOT a native <input type="time">: iOS
// ignores the step attribute, so the native picker makes every entry a
// minute-by-minute wheel. Values are held as "HH:MM" on a 24-hour clock, the
// same string the rest of the form and the API use; labels are 12-hour.

const HALF_HOURS = Array.from({ length: 48 }, (_, i) => {
  const h = Math.floor(i / 2)
  return `${String(h).padStart(2, '0')}:${i % 2 === 0 ? '00' : '30'}`
})

// "14:30" -> "2:30 PM"
export function to12h(hhmm: string): string {
  const [h, m] = hhmm.split(':').map(Number)
  const hour = h % 12 === 0 ? 12 : h % 12
  return `${hour}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}

// Read what a person typed. Accepts "8", "8am", "8:05 pm", "830", "0830",
// "14:30", with or without a space before the meridiem. Returns "HH:MM", or
// null when the text can't be read as a time at all.
export function parseTime(raw: string): string | null {
  const s = raw.trim().toLowerCase().replace(/\./g, '').replace(/\s+/g, ' ')
  const m = s.match(/^(\d{1,2})(?::?(\d{2}))?\s*(am|pm)?$/)
  if (!m) return null
  let h = Number(m[1])
  const minutes = m[2] === undefined ? 0 : Number(m[2])
  if (minutes > 59) return null
  if (m[3]) {
    if (h < 1 || h > 12) return null
    h = (h % 12) + (m[3] === 'pm' ? 12 : 0)
  } else if (h > 23) return null
  return `${String(h).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
}

// The half-hour row a time falls in ("11:15" -> "11:00"), so the list can open
// where the time already is.
function halfHourRow(hhmm: string): string | null {
  const [h, m] = hhmm.split(':').map(Number)
  if (!Number.isFinite(h) || !Number.isFinite(m)) return null
  return `${String(h).padStart(2, '0')}:${m < 30 ? '00' : '30'}`
}

export function TimeCombo({
  label,
  value,
  anchor,
  onChange,
  required = false,
  placeholder = '8:00 AM',
}: {
  label: string
  value: string // "HH:MM", or "" for none
  // Where to open the list when the field is EMPTY: a To field takes the From
  // field's time, so picking 11:00 AM to start opens the end list right there
  // instead of at midnight. Positions the scroll only; it never selects.
  anchor?: string
  onChange: (value: string) => void
  required?: boolean
  placeholder?: string
}) {
  const inputId = `time-${label.toLowerCase().replace(/\s+/g, '-')}`
  const [text, setText] = useState(value ? to12h(value) : '')
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const list = useRef<HTMLUListElement>(null)
  // What we last handed the form, so a value the form changed on its own (an
  // all-day switch clearing the times, a card loading for edit) refreshes the
  // text while someone's own half-typed entry is left alone.
  const emitted = useRef(value)

  useEffect(() => {
    if (value === emitted.current) return
    emitted.current = value
    setText(value ? to12h(value) : '')
    setUnread(false)
  }, [value])

  // The list mounts with `open`, so by the time this runs the rows exist. Its
  // own scrollTop is set rather than scrollIntoView: that would scroll every
  // ancestor too, dragging the sheet behind the dropdown around.
  useEffect(() => {
    if (!open) return
    const key = halfHourRow(value || anchor || '')
    if (!key) return
    const row = list.current?.querySelector<HTMLElement>(`[data-time="${key}"]`)
    if (row) list.current!.scrollTop = row.offsetTop
    // Only on the OPEN: the position is where the list starts, not something
    // that chases the value while it is being picked.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  function commit(next: string) {
    emitted.current = next
    onChange(next)
  }

  function commitText() {
    const typed = text.trim()
    if (!typed) {
      setUnread(false)
      commit('')
      return
    }
    const parsed = parseTime(typed)
    if (parsed === null) {
      // Keep the text so it can be corrected, but the form holds no time:
      // whatever was typed isn't one, and pretending otherwise would save a
      // time nobody asked for.
      setUnread(true)
      commit('')
      return
    }
    setUnread(false)
    setText(to12h(parsed))
    commit(parsed)
  }

  function pick(hhmm: string) {
    setUnread(false)
    setText(to12h(hhmm))
    commit(hhmm)
    setOpen(false)
  }

  return (
    <div ref={box} className="min-w-0">
      <label
        htmlFor={inputId}
        className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50"
      >
        {label}
      </label>
      <div className="relative">
        <input
          id={inputId}
          className="field pr-12"
          type="text"
          inputMode="text"
          autoComplete="off"
          required={required}
          placeholder={placeholder}
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            setUnread(false)
          }}
          onBlur={commitText}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              commitText()
              setOpen(false)
            }
            if (e.key === 'Escape' && open) setOpen(false)
          }}
        />
        <button
          type="button"
          aria-label={`Pick a time for ${label.toLowerCase()}`}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          // A resting tint, not a hover-only one: phones have no hover, and
          // without it the clock reads as decoration rather than a button.
          className="absolute right-1 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-xl bg-fg/10 text-fg/70 transition-colors hover:bg-fg/20 hover:text-fg active:bg-fg/25"
        >
          <Clock className="h-4 w-4" strokeWidth={2} />
        </button>
        {open && (
          <ul
            ref={list}
            role="listbox"
            aria-label={label}
            // Held open through the click: pressing a row would otherwise blur
            // the input first and the list would be gone before the tap landed.
            onMouseDown={(e) => e.preventDefault()}
            className="absolute left-0 right-0 top-full z-20 mt-1 max-h-56 overflow-y-auto rounded-xl border border-fg/15 bg-[var(--surface)] py-1 shadow-lg"
          >
            {HALF_HOURS.map((t) => (
              <li key={t}>
                <button
                  type="button"
                  role="option"
                  data-time={t}
                  aria-selected={t === value}
                  onClick={() => pick(t)}
                  className={`flex min-h-11 w-full items-center px-4 text-sm font-semibold transition-colors ${
                    t === value ? 'bg-accent-bright/20 text-fg' : 'text-fg/75 hover:bg-fg/10'
                  }`}
                >
                  {to12h(t)}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {unread && <p className="mt-1 text-xs text-fg/50">Try a time like 8:00 AM.</p>}
    </div>
  )
}
