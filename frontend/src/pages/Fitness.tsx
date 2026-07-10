import { AnimatePresence } from 'framer-motion'
import { Check, Copy, Flame, Footprints, HeartPulse, Link2, Timer, Unplug } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import * as api from '../lib/api'
import { Sheet } from '../components/Recipes'
import { Button, FormError } from '../components/ui'

// The Fitness tab: imported Apple Health numbers, self-only like the diary.
// Nothing here is visible to other family members or villages, ever.
//
// Design note: the layout takes its cues from the familiar phone fitness
// summary (rings up top, a grid of metric cards with mini charts) but the
// rendering is deliberately our own — three separate rings rather than the
// trademark concentric trio, our validated metric palette rather than
// red/green/cyan, our labels, our glass. Familiar shape, our identity.

// Daily goals behind the rings. Family defaults for now; per-member goals
// can become a setting once real use says which ones people want to tune.
const GOALS = { steps: 10000, active_kcal: 500, exercise_minutes: 30 }

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

// ---- rings ----------------------------------------------------------------------

function Ring({
  colorVar,
  fraction,
  icon: Icon,
  size = 76,
}: {
  colorVar: string
  fraction: number
  icon: typeof Footprints
  size?: number
}) {
  const stroke = 7
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const filled = Math.min(Math.max(fraction, 0), 1)
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          className="text-fg/10"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`var(${colorVar})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - filled)}
        />
      </svg>
      <Icon
        className="absolute left-1/2 top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2 text-fg/60"
        strokeWidth={2}
      />
    </div>
  )
}

function RingStat({
  colorVar,
  icon,
  label,
  value,
  goal,
  unit,
}: {
  colorVar: string
  icon: typeof Footprints
  label: string
  value: number | null
  goal: number
  unit?: string
}) {
  return (
    <div className="flex flex-1 flex-col items-center gap-2">
      <Ring colorVar={colorVar} fraction={(value ?? 0) / goal} icon={icon} />
      <div className="text-center">
        <p className="text-lg font-bold leading-tight" style={{ color: `var(${colorVar})` }}>
          {fmtNumber(value)}
          {unit && <span className="ml-0.5 text-[11px] font-semibold">{unit}</span>}
        </p>
        <p className="text-[11px] leading-tight text-fg/45">
          of {goal.toLocaleString()}
          {unit ? ` ${unit}` : ''}
        </p>
        <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-fg/50">
          {label}
        </p>
      </div>
    </div>
  )
}

// ---- metric cards ---------------------------------------------------------------

function MiniBars({
  week,
  pick,
  colorVar,
  unit,
}: {
  week: api.FitnessWeekDay[]
  pick: (d: api.FitnessWeekDay) => number | null
  colorVar: string
  unit: string
}) {
  const values = week.map(pick)
  const max = Math.max(...values.map((v) => v ?? 0), 1)
  return (
    <div className="mt-3 flex items-end justify-between gap-1" style={{ height: 44 }}>
      {week.map((day, i) => {
        const v = values[i]
        const date = new Date(day.date_for + 'T00:00:00')
        const letter = DAY_LETTERS[(date.getDay() + 6) % 7]
        const h = v ? Math.max(5, Math.round((v / max) * 36)) : 3
        return (
          <div key={day.date_for} className="flex flex-1 flex-col items-center gap-1">
            <div
              className="w-full max-w-4 rounded-[3px]"
              style={{
                height: h,
                background: v
                  ? `var(${colorVar})`
                  : 'color-mix(in srgb, var(--fg) 10%, transparent)',
              }}
              title={v ? `${Math.round(v).toLocaleString()} ${unit}` : 'No data'}
            />
            <span className="text-[9px] font-semibold text-fg/35">{letter}</span>
          </div>
        )
      })}
    </div>
  )
}

function MetricCard({
  icon: Icon,
  label,
  colorVar,
  value,
  unit,
  week,
  pick,
}: {
  icon: typeof Footprints
  label: string
  colorVar: string
  value: number | null
  unit?: string
  week: api.FitnessWeekDay[]
  pick: (d: api.FitnessWeekDay) => number | null
}) {
  return (
    <div className="glass p-4">
      <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-fg/50">
        <Icon className="h-3.5 w-3.5" style={{ color: `var(${colorVar})` }} /> {label}
      </span>
      <p className="mt-1 text-[11px] text-fg/45">Today</p>
      <p className="text-2xl font-bold tracking-tight" style={{ color: `var(${colorVar})` }}>
        {fmtNumber(value)}
        {unit && <span className="ml-1 text-sm font-semibold">{unit}</span>}
      </p>
      <MiniBars week={week} pick={pick} colorVar={colorVar} unit={unit ?? label.toLowerCase()} />
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
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
        style={{ background: 'color-mix(in srgb, var(--fit-active) 16%, transparent)' }}
      >
        <Flame className="h-5 w-5" style={{ color: 'var(--fit-active)' }} />
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
          <div className="glass p-5">
            <span className="mb-4 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              Today's rings
            </span>
            <div className="flex items-start gap-2">
              <RingStat
                colorVar="--fit-steps"
                icon={Footprints}
                label="Steps"
                value={data.today.steps}
                goal={GOALS.steps}
              />
              <RingStat
                colorVar="--fit-active"
                icon={Flame}
                label="Active"
                value={data.today.active_kcal}
                goal={GOALS.active_kcal}
                unit="kcal"
              />
              <RingStat
                colorVar="--fit-exercise"
                icon={Timer}
                label="Exercise"
                value={data.today.exercise_minutes}
                goal={GOALS.exercise_minutes}
                unit="min"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <MetricCard
              icon={Footprints}
              label="Step count"
              colorVar="--fit-steps"
              value={data.today.steps}
              week={data.week}
              pick={(d) => d.steps}
            />
            <MetricCard
              icon={Flame}
              label="Active energy"
              colorVar="--fit-active"
              value={data.today.active_kcal}
              unit="kcal"
              week={data.week}
              pick={(d) => d.active_kcal}
            />
            <MetricCard
              icon={Timer}
              label="Exercise"
              colorVar="--fit-exercise"
              value={data.today.exercise_minutes}
              unit="min"
              week={data.week}
              pick={(d) => d.exercise_minutes}
            />
            <MetricCard
              icon={HeartPulse}
              label="Resting HR"
              colorVar="--fit-hr"
              value={data.today.resting_hr}
              unit="bpm"
              week={data.week}
              pick={(d) => d.resting_hr}
            />
          </div>

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
