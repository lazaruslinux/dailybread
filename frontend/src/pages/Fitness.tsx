import { AnimatePresence } from 'framer-motion'
import {
  Check,
  ChevronRight,
  Copy,
  Flame,
  Footprints,
  HeartPulse,
  Link2,
  Timer,
  Unplug,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import * as api from '../lib/api'
import { Sheet } from '../components/Recipes'
import { Button, Field, FormError } from '../components/ui'

// The Fitness tab: imported Apple Health numbers, self-only like the diary.
// Nothing here is visible to other family members or villages, ever.
//
// Design note: the layout takes its cues from the familiar phone fitness
// summary (rings up top, a grid of metric cards with mini charts) but the
// rendering is deliberately our own — three separate rings rather than the
// trademark concentric trio, our validated metric palette rather than
// red/green/cyan, our labels, our glass. Familiar shape, our identity.

// Everything the tab knows about one metric, in one place: the cards, the
// rings, and the detail sheets all read from this. goalKey marks the metrics
// with a tunable daily target (resting HR has none — lower is its own story).
type MetricDef = {
  key: 'steps' | 'active_kcal' | 'exercise_minutes' | 'resting_hr'
  label: string
  title: string
  icon: typeof Footprints
  colorVar: string
  unit?: string
  goalKey?: keyof api.FitnessGoals
  bestWord: string
  bestPick: 'max' | 'min'
}

const METRICS: MetricDef[] = [
  {
    key: 'steps',
    label: 'Step count',
    title: 'Steps',
    icon: Footprints,
    colorVar: '--fit-steps',
    goalKey: 'steps',
    bestWord: 'Best day',
    bestPick: 'max',
  },
  {
    key: 'active_kcal',
    label: 'Active energy',
    title: 'Active energy',
    icon: Flame,
    colorVar: '--fit-active',
    unit: 'kcal',
    goalKey: 'active_kcal',
    bestWord: 'Best day',
    bestPick: 'max',
  },
  {
    key: 'exercise_minutes',
    label: 'Exercise',
    title: 'Exercise minutes',
    icon: Timer,
    colorVar: '--fit-exercise',
    unit: 'min',
    goalKey: 'exercise_minutes',
    bestWord: 'Best day',
    bestPick: 'max',
  },
  {
    key: 'resting_hr',
    label: 'Resting HR',
    title: 'Resting heart rate',
    icon: HeartPulse,
    colorVar: '--fit-hr',
    unit: 'bpm',
    bestWord: 'Lowest',
    bestPick: 'min',
  },
]

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

function fmtShortDate(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  })
}

function fmtReadoutDate(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
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
  def,
  value,
  week,
  onOpen,
}: {
  def: MetricDef
  value: number | null
  week: api.FitnessWeekDay[]
  onOpen: () => void
}) {
  const { icon: Icon, label, colorVar, unit } = def
  return (
    <button type="button" onClick={onOpen} className="glass relative p-4 text-left">
      <ChevronRight className="absolute right-3 top-4 h-4 w-4 text-fg/30" />
      <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-fg/50">
        <Icon className="h-3.5 w-3.5" style={{ color: `var(${colorVar})` }} /> {label}
      </span>
      <p className="mt-1 text-[11px] text-fg/45">Today</p>
      <p className="text-2xl font-bold tracking-tight" style={{ color: `var(${colorVar})` }}>
        {fmtNumber(value)}
        {unit && <span className="ml-1 text-sm font-semibold">{unit}</span>}
      </p>
      <MiniBars
        week={week}
        pick={(d) => d[def.key]}
        colorVar={colorVar}
        unit={unit ?? label.toLowerCase()}
      />
    </button>
  )
}

// ---- per-metric detail ------------------------------------------------------------

// The last 30 days as tappable bars. Tap a day and the readout above the
// chart names it; the dashed line marks the daily goal where one exists.
function HistoryBars({
  days,
  def,
  goal,
  selected,
  onSelect,
}: {
  days: api.FitnessWeekDay[]
  def: MetricDef
  goal?: number
  selected: string | null
  onSelect: (date: string) => void
}) {
  const HEIGHT = 112
  const values = days.map((d) => d[def.key])
  const max = Math.max(...values.map((v) => v ?? 0), goal ?? 0, 1)
  const goalY = goal ? Math.round((goal / max) * HEIGHT) : null
  return (
    <div>
      <div className="relative" style={{ height: HEIGHT }}>
        {goalY !== null && (
          <div
            className="pointer-events-none absolute inset-x-0 border-t border-dashed border-fg/25"
            style={{ bottom: goalY }}
          >
            <span className="absolute right-0 -top-4 text-[9px] font-semibold uppercase tracking-wide text-fg/40">
              goal
            </span>
          </div>
        )}
        <div className="flex h-full items-end gap-[2px]">
          {days.map((day, i) => {
            const v = values[i]
            const h = v ? Math.max(5, Math.round((v / max) * HEIGHT)) : 3
            const isSelected = selected === day.date_for
            return (
              <button
                key={day.date_for}
                type="button"
                onClick={() => onSelect(day.date_for)}
                aria-label={fmtReadoutDate(day.date_for)}
                className="flex h-full flex-1 items-end"
              >
                <div
                  className="w-full rounded-t-[3px]"
                  style={{
                    height: h,
                    background: v
                      ? `var(${def.colorVar})`
                      : 'color-mix(in srgb, var(--fg) 10%, transparent)',
                    opacity: !v || selected === null || isSelected ? 1 : 0.45,
                  }}
                />
              </button>
            )
          })}
        </div>
      </div>
      <div className="mt-1 flex justify-between text-[10px] font-semibold text-fg/35">
        <span>{fmtShortDate(days[0].date_for)}</span>
        <span>Today</span>
      </div>
    </div>
  )
}

function DetailStat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-fg/45">{label}</p>
      <p className="truncate text-sm font-bold text-fg/90">{value}</p>
      {sub && <p className="text-[11px] text-fg/50">{sub}</p>}
    </div>
  )
}

// "Daily goal · 10,000 · Change" with an inline editor. Saving a number sets
// this member's own target; the reset link goes back to the recommended one.
function GoalEditor({
  def,
  goal,
  onGoals,
}: {
  def: MetricDef
  goal: number
  onGoals: (goals: api.FitnessGoals) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function save(value: number | null) {
    if (!def.goalKey) return
    setBusy(true)
    setError(null)
    try {
      onGoals(await api.updateFitnessGoals({ [def.goalKey]: value }))
      setEditing(false)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  function submit() {
    const n = Number(draft)
    if (!draft.trim() || !Number.isFinite(n) || n <= 0) {
      setError('Enter a number.')
      return
    }
    void save(Math.round(n))
  }

  if (!editing) {
    return (
      <div className="flex items-center justify-between rounded-xl bg-fg/5 px-4 py-3">
        <p className="text-sm text-fg/70">
          Daily goal{' '}
          <span className="font-bold text-fg/90">
            {goal.toLocaleString()}
            {def.unit ? ` ${def.unit}` : ''}
          </span>
        </p>
        <button
          type="button"
          onClick={() => {
            setDraft(String(goal))
            setEditing(true)
          }}
          className="text-sm font-semibold text-accent-bright hover:underline"
        >
          Change
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2 rounded-xl bg-fg/5 px-4 py-3">
      <Field
        label={`Daily goal${def.unit ? ` (${def.unit})` : ''}`}
        type="number"
        inputMode="numeric"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      <FormError message={error} />
      <div className="grid grid-cols-2 gap-2">
        <Button variant="ghost" onClick={() => setEditing(false)} disabled={busy}>
          Never mind
        </Button>
        <Button onClick={submit} disabled={busy}>
          {busy ? 'Saving…' : 'Save'}
        </Button>
      </div>
      <button
        type="button"
        onClick={() => void save(null)}
        disabled={busy}
        className="text-xs font-semibold text-fg/45 hover:text-fg/70"
      >
        Use the recommended goal
      </button>
    </div>
  )
}

function MetricDetail({
  def,
  today,
  history,
  goals,
  onGoals,
  onClose,
}: {
  def: MetricDef
  today: number | null
  history: api.FitnessWeekDay[] | null
  goals: api.FitnessGoals
  onGoals: (goals: api.FitnessGoals) => void
  onClose: () => void
}) {
  const [selected, setSelected] = useState<string | null>(null)
  const goal = def.goalKey ? goals[def.goalKey] : undefined

  const days = history ?? []
  const withData = days.filter((d) => d[def.key] !== null)
  const avgOf = (subset: api.FitnessWeekDay[]) =>
    subset.length
      ? Math.round(subset.reduce((sum, d) => sum + (d[def.key] ?? 0), 0) / subset.length)
      : null
  const avg7 = avgOf(days.slice(-7).filter((d) => d[def.key] !== null))
  const avg30 = avgOf(withData)
  const best = withData.length
    ? withData.reduce((a, b) =>
        def.bestPick === 'max'
          ? (b[def.key] ?? 0) > (a[def.key] ?? 0)
            ? b
            : a
          : (b[def.key] ?? Infinity) < (a[def.key] ?? Infinity)
            ? b
            : a,
      )
    : null

  const selectedDay = history?.find((d) => d.date_for === selected) ?? null
  const Icon = def.icon
  const unitSuffix = def.unit ? ` ${def.unit}` : ''

  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 flex items-center gap-2 text-lg font-bold">
        <Icon className="h-5 w-5" style={{ color: `var(${def.colorVar})` }} />
        {def.title}
      </h3>
      <p className="text-[11px] text-fg/45">Today</p>
      <p className="text-3xl font-bold tracking-tight" style={{ color: `var(${def.colorVar})` }}>
        {fmtNumber(today)}
        {def.unit && <span className="ml-1 text-base font-semibold">{def.unit}</span>}
      </p>

      {history === null ? (
        <p className="mt-6 text-sm text-fg/40">Loading</p>
      ) : history.length === 0 ? (
        <p className="mt-6 text-sm text-fg/40">Couldn't load the last 30 days.</p>
      ) : (
        <div className="mt-4 flex flex-col gap-4">
          <div>
            <p className="mb-2 h-4 text-xs text-fg/55">
              {selectedDay
                ? `${fmtReadoutDate(selectedDay.date_for)} · ${
                    selectedDay[def.key] === null
                      ? 'no data'
                      : fmtNumber(selectedDay[def.key]) + unitSuffix
                  }`
                : 'Last 30 days · tap a bar'}
            </p>
            <HistoryBars
              days={history}
              def={def}
              goal={goal}
              selected={selected}
              onSelect={(d) => setSelected(selected === d ? null : d)}
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <DetailStat label="7-day avg" value={avg7 === null ? '–' : fmtNumber(avg7) + unitSuffix} />
            <DetailStat label="30-day avg" value={avg30 === null ? '–' : fmtNumber(avg30) + unitSuffix} />
            <DetailStat
              label={def.bestWord}
              value={best === null ? '–' : fmtNumber(best[def.key]) + unitSuffix}
              sub={best === null ? undefined : fmtShortDate(best.date_for)}
            />
          </div>

          {goal !== undefined && <GoalEditor def={def} goal={goal} onGoals={onGoals} />}
        </div>
      )}
    </Sheet>
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
  const [detail, setDetail] = useState<MetricDef | null>(null)
  const [history, setHistory] = useState<api.FitnessWeekDay[] | null>(null)

  const refresh = useCallback(async () => {
    try {
      setData(await api.getFitness(api.localDate()))
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load fitness data.')
    }
  }, [])

  // The 30-day window is one cheap fetch shared by all four detail views;
  // grab it the first time any card opens.
  function openDetail(def: MetricDef) {
    setDetail(def)
    if (history === null) {
      api
        .getFitnessHistory(api.localDate())
        .then((h) => setHistory(h.days))
        .catch(() => setHistory([]))
    }
  }

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
                goal={data.goals.steps}
              />
              <RingStat
                colorVar="--fit-active"
                icon={Flame}
                label="Active"
                value={data.today.active_kcal}
                goal={data.goals.active_kcal}
                unit="kcal"
              />
              <RingStat
                colorVar="--fit-exercise"
                icon={Timer}
                label="Exercise"
                value={data.today.exercise_minutes}
                goal={data.goals.exercise_minutes}
                unit="min"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {METRICS.map((def) => (
              <MetricCard
                key={def.key}
                def={def}
                value={data.today[def.key]}
                week={data.week}
                onOpen={() => openDetail(def)}
              />
            ))}
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
        {detail && (
          <MetricDetail
            def={detail}
            today={data.today[detail.key]}
            history={history}
            goals={data.goals}
            onGoals={(goals) => setData((d) => (d ? { ...d, goals } : d))}
            onClose={() => setDetail(null)}
          />
        )}
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
