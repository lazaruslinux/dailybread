import { useCallback, useRef } from 'react'

// Long-press detection with pointer events, for "hold a card to edit it".
// A short tap still fires onTap. Moving the pointer (scrolling) cancels both,
// so scrolling through the feed never accidentally opens the editor.
export function useLongPress(onLongPress: () => void, onTap?: () => void, delayMs = 450) {
  const timer = useRef<number | null>(null)
  const fired = useRef(false)

  const clear = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  const onPointerDown = useCallback(() => {
    fired.current = false
    clear()
    timer.current = window.setTimeout(() => {
      fired.current = true
      onLongPress()
    }, delayMs)
  }, [clear, delayMs, onLongPress])

  const onPointerUp = useCallback(() => {
    clear()
    if (!fired.current) onTap?.()
  }, [clear, onTap])

  const onPointerMove = useCallback(() => {
    // Finger drifted: treat as a scroll, not a press of either kind.
    fired.current = true
    clear()
  }, [clear])

  return {
    onPointerDown,
    onPointerUp,
    onPointerMove,
    onPointerLeave: clear,
    onContextMenu: (e: React.MouseEvent) => e.preventDefault(),
  }
}
