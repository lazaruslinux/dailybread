import { useEffect, useState } from 'react'
import { getHealth, type Health } from '../lib/api'

type Status = 'loading' | 'ok' | 'error'

interface HealthState {
  status: Status
  data: Health | null
}

// Polls the backend /health endpoint on mount and every 60s so the UI can show
// a live "connected" indicator. Skips the request while the tab is hidden (a
// backgrounded phone shouldn't keep waking the radio) and re-checks the moment
// it becomes visible again. A custom hook keeps this logic out of the view.
export function useHealth(intervalMs = 60_000): HealthState {
  const [state, setState] = useState<HealthState>({ status: 'loading', data: null })

  useEffect(() => {
    let active = true

    async function check() {
      if (document.visibilityState !== 'visible') return
      try {
        const data = await getHealth()
        if (active) setState({ status: 'ok', data })
      } catch {
        if (active) setState({ status: 'error', data: null })
      }
    }

    check()
    const id = setInterval(check, intervalMs)
    const onVisible = () => {
      if (document.visibilityState === 'visible') check()
    }
    document.addEventListener('visibilitychange', onVisible)

    // Cleanup: stop polling and ignore late responses after unmount.
    return () => {
      active = false
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [intervalMs])

  return state
}
