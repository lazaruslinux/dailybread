import { useHealth } from '../hooks/useHealth'

// A quiet connectivity warning. When the app can reach the backend (the normal
// case) this renders nothing — there's no reason to tell someone their app is
// working. It only appears to explain a problem: still connecting on a cold
// start, or offline when the server can't be reached.
export function HealthBadge() {
  const { status } = useHealth()

  if (status === 'ok') return null

  const label = status === 'loading' ? 'Connecting' : 'Offline'
  const dotColor = status === 'loading' ? 'bg-gold' : 'bg-rose-400'

  return (
    <div className="glass flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium text-fg/80">
      <span className={`h-2 w-2 rounded-full ${dotColor} ${status === 'loading' ? 'animate-pulse' : ''}`} />
      {label}
    </div>
  )
}
