import { useHealth } from '../hooks/useHealth'

// Small pill in the header showing whether the frontend can reach the backend.
// Green = connected, amber = checking, red = offline.
export function HealthBadge() {
  const { status, data } = useHealth()

  const label =
    status === 'loading' ? 'Connecting' : status === 'ok' ? `Online (${data?.mode})` : 'Offline'

  const dotColor =
    status === 'loading' ? 'bg-amber-400' : status === 'ok' ? 'bg-emerald-400' : 'bg-rose-400'

  return (
    <div className="glass flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium text-white/80">
      <span className={`h-2 w-2 rounded-full ${dotColor} ${status === 'loading' ? 'animate-pulse' : ''}`} />
      {label}
    </div>
  )
}
