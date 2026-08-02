import { useEffect, useState } from 'react'

// True once there is room for the right-hand aside beside the content column.
// The shell's other two shapes are pure CSS, but this one gates a React branch
// on purpose: the aside fetches its own feed and grocery list, and a phone
// should not pay for two requests it will never show. It also keeps the cards
// that move into the aside from being mounted twice — one source of truth for
// the verse's check state instead of a visible copy and a hidden one.
const WIDE = '(min-width: 1200px)'

export function useWideLayout(): boolean {
  const [wide, setWide] = useState(() => window.matchMedia(WIDE).matches)
  useEffect(() => {
    const mq = window.matchMedia(WIDE)
    const onChange = (e: MediaQueryListEvent) => setWide(e.matches)
    mq.addEventListener('change', onChange)
    // A resize between render and effect would otherwise be missed.
    setWide(mq.matches)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return wide
}
