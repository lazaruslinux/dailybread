import { useEffect, useState } from 'react'
import { getHealth, type Health } from '../lib/api'

type Status = 'loading' | 'ok' | 'error'

interface HealthState {
  status: Status
  data: Health | null
}

// Polls the backend /health endpoint on mount and every 30s so the UI can show
// a live "connected" indicator. A custom hook keeps this logic out of the view.
export function useHealth(intervalMs = 30_000): HealthState {
  const [state, setState] = useState<HealthState>({ status: 'loading', data: null })

  useEffect(() => {
    let active = true

    async function check() {
      try {
        const data = await getHealth()
        if (active) setState({ status: 'ok', data })
      } catch {
        if (active) setState({ status: 'error', data: null })
      }
    }

    check()
    const id = setInterval(check, intervalMs)

    // Cleanup: stop polling and ignore late responses after unmount.
    return () => {
      active = false
      clearInterval(id)
    }
  }, [intervalMs])

  return state
}
