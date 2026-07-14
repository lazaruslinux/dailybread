import { useCallback, useEffect, useState } from 'react'
import { getInboxUnread } from '../lib/api'

// Polls the Inbox unread count on mount and every 60s, same shape as
// useHealth: skip while the tab is hidden, re-check on return, drop late
// responses after unmount. zero() clears the badge the instant the Inbox
// opens — a badge that lingers up to a minute after reading reads as broken.
export function useInboxUnread(intervalMs = 60_000): { count: number; zero: () => void } {
  const [count, setCount] = useState(0)

  useEffect(() => {
    let active = true

    async function check() {
      if (document.visibilityState !== 'visible') return
      try {
        const { count } = await getInboxUnread()
        if (active) setCount(count)
      } catch {
        if (active) setCount(0) // no session / no family: no badge, quietly
      }
    }

    check()
    const id = setInterval(check, intervalMs)
    const onVisible = () => {
      if (document.visibilityState === 'visible') check()
    }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      active = false
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [intervalMs])

  const zero = useCallback(() => setCount(0), [])
  return { count, zero }
}
