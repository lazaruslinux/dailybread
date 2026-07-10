import { AnimatePresence } from 'framer-motion'
import { Check, Copy, Flame, Footprints, HeartPulse, Link2, Timer, Unplug } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import * as api from '../lib/api'
import { Sheet } from '../components/Recipes'
import { Button, FormError } from '../components/ui'

// The Fitness tab: imported Apple Health numbers, self-only like the diary.
// Nothing here is visible to other family members or villages, ever.

const DAY_LETTERS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'] // Date.getDay(), Monday-shifted

function fmtNumber(value: number | null): string {
  if (value === null) return '–'
  return Math.round(value).toLocaleString()
}

function fmtWhen(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' }) +
    ' · ' +
    d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

function fmtMiles(meters: number | null): string | null {
  if (meters === null) return null
  return `${(meters / 1609.344).toFixed(1)} mi`
}

// ---- connect flow ---------------------------------------------------------------

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {}
  }
  return (
    <div className="min-w-0">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-fg/50">
        {label}
      </span>
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded-lg bg-fg/10 px-3 py-2 text-xs">
          {value}
        </code>
        <button
          type="button"
          onClick={copy}
          aria-label={`Copy ${label.toLowerCase()}`}
          className="shrink-0 rounded-full p-2 text-fg/50 transition-colors hover:bg-fg/10 hover:text-fg"
        >
          {copied ? <Check className="h-4 w-4 text-accent-bright" /> : <Copy className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}

function ConnectSheet({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [minted, setMinted] = useState<api.IngestToken | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function mint() {
    setBusy(true)
    setError(null)
    try {
      setMinted(await api.mintIngestToken())
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet onClose={minted ? onDone : onClose}>
      <h3 className="mb-1 text-lg font-bold">Connect Apple Health</h3>
      {minted === null ? (
        <>
          <p className="mb-4 text-sm text-fg/60">
            Your phone sends the numbers here itself; no cloud service ever sees them. You
            need an iPhone app that can send Apple Health data to a web address on a
            schedule (Health Auto Export is the one the docs walk through). This makes a
            sync key for it. If you already have one, this replaces it.
          </p>
          <FormError message={error} />
          <Button onClick={mint} disabled={busy}>
            {busy ? 'Making a key…' : 'Make my sync key'}
          </Button>
        </>
      ) : (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-fg/60">
            Point the exporter app at this address, add the header below, and choose which
            metrics to send. The key is shown only this once.
          </p>
          <CopyRow label="Send to" value={`${window.location.origin}${minted.path}`} />
          <CopyRow label="Authorization header" value={`Bearer ${minted.token}`} />
          <p className="text-xs text-fg/45">
            Data lands whenever the phone is on your home network and catches up after time
            away. Only you can see it.
          </p>
          <Button onClick={onDone}>Done</Button>
        </div>
      )}
    </Sheet>
  )
}

// ---- pieces ---------------------------------------------------------------------

function StatTile({
  icon: Icon,
  label,
  value,
  unit,
}: {
  icon: typeof Footprints
  label: string
  value: string
  unit?: string
}) {
  return (
    <div className="glass flex flex-col gap-1 p-4">
      <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-fg/50">
        <Icon className="h-3.5 w-3.5 text-accent-bright" /> {label}
      </span>
      <span className="text-2xl font-bold tracking-tight">
        {value}
        {unit && <span className="ml-1 text-sm font-semibold text-fg/45">{unit}</span>}
      </span>
    </div>
  )
}

function WeekBars({ week }: { week: api.FitnessWeekDay[] }) {
  const max = Math.max(...week.map((d) => d.steps ?? 0), 1)
  return (
    <div className="glass p-4">
      <span className="mb-3 block text-xs font-semibold uppercase tracking-wide text-fg/50">
        Steps this week
      </span>
      <div className="flex items-end justify-between gap-2" style={{ height: 72 }}>
        {week.map((day) => {
          const date = new Date(day.date_for + 'T00:00:00')
          const letter = DAY_LETTERS[(date.getDay() + 6) % 7]
          const h = day.steps ? Math.max(6, Math.round((day.steps / max) * 64)) : 4
          return (
            <div key={day.date_for} className="flex flex-1 flex-col items-center gap-1.5">
              <div
                className={`w-full max-w-7 rounded-md ${
                  day.steps ? 'bg-accent-bright/70' : 'bg-fg/10'
                }`}
                style={{ height: h }}
                title={day.steps ? `${Math.round(day.steps).toLocaleString()} steps` : 'No data'}
              />
              <span className="text-[10px] font-semibold text-fg/40">{letter}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function WorkoutRow({ workout }: { workout: api.Workout }) {
  const bits = [
    workout.duration_s ? `${Math.round(workout.duration_s / 60)} min` : null,
    workout.kcal ? `${Math.round(workout.kcal)} kcal` : null,
    fmtMiles(workout.distance_m),
    workout.avg_hr ? `${Math.round(workout.avg_hr)} bpm avg` : null,
  ].filter(Boolean)
  return (
    <div className="glass flex items-center gap-3 p-4">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-bright/15">
        <Flame className="h-5 w-5 text-accent-bright" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold text-fg/90">{workout.activity}</p>
        <p className="truncate text-xs text-fg/50">{fmtWhen(workout.started_at)}</p>
      </div>
      <p className="shrink-0 text-right text-xs leading-relaxed text-fg/60">
        {bits.map((b) => (
          <span key={b} className="block">
            {b}
          </span>
        ))}
      </p>
    </div>
  )
}

// ---- the tab --------------------------------------------------------------------

export function Fitness() {
  const [data, setData] = useState<api.Fitness | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setData(await api.getFitness(api.localDate()))
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load fitness data.')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function disconnect() {
    try {
      await api.revokeIngestToken()
      setDisconnecting(false)
      await refresh()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
    }
  }

  if (error) return <FormError message={error} />
  if (data === null) return <p className="text-sm text-fg/40">Loading</p>

  const hasAnything =
    data.today.steps !== null ||
    data.workouts.length > 0 ||
    data.week.some((d) => d.steps !== null)

  return (
    <div className="flex flex-col gap-4">
      {!data.connected && !hasAnything && (
        <div className="glass flex flex-col items-center gap-3 p-8 text-center">
          <HeartPulse className="h-8 w-8 text-accent-bright" />
          <p className="font-semibold text-fg/90">Your day, in numbers</p>
          <p className="text-sm text-fg/55">
            Steps, workouts, and weigh-ins from your Apple Watch land here, straight from
            your phone to your own server. Only you can see them.
          </p>
          <Button onClick={() => setConnecting(true)}>Connect Apple Health</Button>
        </div>
      )}

      {(data.connected || hasAnything) && (
        <>
          <div className="grid grid-cols-2 gap-2">
            <StatTile icon={Footprints} label="Steps" value={fmtNumber(data.today.steps)} />
            <StatTile icon={Flame} label="Active" value={fmtNumber(data.today.active_kcal)} unit="kcal" />
            <StatTile icon={Timer} label="Exercise" value={fmtNumber(data.today.exercise_minutes)} unit="min" />
            <StatTile icon={HeartPulse} label="Resting HR" value={fmtNumber(data.today.resting_hr)} unit="bpm" />
          </div>

          <WeekBars week={data.week} />

          {data.workouts.length > 0 && (
            <div className="flex flex-col gap-2">
              <span className="px-1 text-xs font-semibold uppercase tracking-wide text-fg/50">
                Workouts
              </span>
              {data.workouts.map((w) => (
                <WorkoutRow key={w.id} workout={w} />
              ))}
            </div>
          )}

          <div className="glass flex items-center gap-3 p-4">
            <Link2 className="h-4 w-4 shrink-0 text-accent-bright" />
            <p className="min-w-0 flex-1 text-sm text-fg/60">
              {data.connected
                ? data.last_sync
                  ? `Connected · last sync ${fmtWhen(data.last_sync)}`
                  : 'Connected · waiting for the first sync'
                : 'Not connected'}
            </p>
            <button
              onClick={() => setConnecting(true)}
              className="shrink-0 text-sm font-semibold text-accent-bright hover:underline"
            >
              {data.connected ? 'New key' : 'Connect'}
            </button>
            {data.connected && (
              <button
                onClick={() => setDisconnecting(true)}
                aria-label="Disconnect"
                className="shrink-0 rounded-full p-1.5 text-fg/40 transition-colors hover:bg-red-500/15 hover:text-red-400"
              >
                <Unplug className="h-4 w-4" />
              </button>
            )}
          </div>
        </>
      )}

      <AnimatePresence>
        {connecting && (
          <ConnectSheet
            onClose={() => setConnecting(false)}
            onDone={() => {
              setConnecting(false)
              void refresh()
            }}
          />
        )}
        {disconnecting && (
          <Sheet onClose={() => setDisconnecting(false)}>
            <p className="mb-1 font-bold">Disconnect Apple Health?</p>
            <p className="mb-5 text-sm text-fg/55">
              The sync key stops working right away. Numbers already here stay put.
            </p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <Button variant="ghost" onClick={() => setDisconnecting(false)}>
                Keep it
              </Button>
              <Button variant="danger" onClick={disconnect}>
                Disconnect
              </Button>
            </div>
          </Sheet>
        )}
      </AnimatePresence>
    </div>
  )
}
