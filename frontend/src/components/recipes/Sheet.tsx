import { motion } from 'framer-motion'
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Button } from '../ui'

// The modal shell shared by the view and the editor. Rendered through a portal
// to <body>: an ancestor with a transform or filter (the animated cards on the
// Kitchen page) makes position:fixed anchor to that ancestor instead of the
// viewport, so a modal nested under one only covers a band. The portal lifts it
// out to the top of the DOM where `fixed inset-0` fills the screen. Body scroll
// is locked while it's open so the page can't drift behind.
// Ref-counted so stacked sheets can't strand the lock: when one sheet opens
// while another is still exit-animating (Nutrition's AddSheet → PortionSheet),
// a save/restore of the previous value would capture 'hidden' and re-apply it
// after both closed, freezing the page until a reload.
let bodyLocks = 0
export function Sheet({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  useEffect(() => {
    if (++bodyLocks === 1) document.body.style.overflow = 'hidden'
    return () => {
      if (--bodyLocks === 0) document.body.style.overflow = ''
    }
  }, [])
  // Escape dismisses too — routed through the same onClose the backdrop uses, so
  // a form's dirty-guard catches it. (A hardware keyboard on a tablet/desktop.)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return createPortal(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 40 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        className="sheet-card max-h-[90svh] w-full max-w-sm overflow-y-auto p-6"
        role="dialog"
        aria-modal="true"
      >
        {children}
      </motion.div>
    </motion.div>,
    document.body,
  )
}

// Autosave + restore a NEW recipe/food form to localStorage, per user, so an
// accidental dismissal or a reload doesn't lose in-progress work. `key` is null
// while editing an existing item (we don't persist half-edits over a saved
// record). `snapshot` is the serialized form; it's saved only while `dirty`, and
// cleared otherwise. On mount, a saved draft is handed back through `restore`.
export function useFormDraft(
  key: string | null,
  snapshot: string,
  dirty: boolean,
  restore: (raw: string) => void,
) {
  const [restored, setRestored] = useState(false)
  const ready = useRef(false)
  useEffect(() => {
    if (key) {
      try {
        const raw = localStorage.getItem(key)
        if (raw) {
          restore(raw)
          setRestored(true)
        }
      } catch {
        // ignore corrupt/blocked storage
      }
    }
    ready.current = true
    // Restore once, keyed by which draft slot this is.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  useEffect(() => {
    if (!key || !ready.current) return
    try {
      if (dirty) localStorage.setItem(key, snapshot)
      else localStorage.removeItem(key)
    } catch {
      // ignore
    }
  }, [key, snapshot, dirty])
  const clear = useCallback(() => {
    if (key) {
      try {
        localStorage.removeItem(key)
      } catch {
        // ignore
      }
    }
    setRestored(false)
  }, [key])
  return { restored, clear }
}

// A confirm bar shown over a sheet when the user tries to dismiss unsaved work.
// Full-screen so a stray tap can't slip past it; "Keep editing" is the safe
// default emphasis, "Discard" the destructive escape hatch.
export function DiscardGuard({ onKeep, onDiscard }: { onKeep: () => void; onDiscard: () => void }) {
  return createPortal(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6"
      onClick={(e) => e.target === e.currentTarget && onKeep()}
    >
      <div className="sheet-card w-full max-w-xs p-5 text-center" role="alertdialog" aria-modal="true">
        <p className="font-display text-lg font-semibold">Discard changes?</p>
        <p className="mt-1 text-sm text-fg/55">Your unsaved edits will be lost.</p>
        <div className="mt-4 flex flex-col gap-2">
          <Button type="button" onClick={onKeep} className="w-full">
            Keep editing
          </Button>
          <Button type="button" variant="danger" onClick={onDiscard} className="w-full">
            Discard
          </Button>
        </div>
      </div>
    </motion.div>,
    document.body,
  )
}
