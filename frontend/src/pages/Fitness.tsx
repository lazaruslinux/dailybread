import { AnimatePresence } from 'framer-motion'
import {
  Bike,
  Check,
  ChevronRight,
  Copy,
  Dumbbell,
  Eye,
  EyeOff,
  Flame,
  Footprints,
  HeartPulse,
  Link2,
  Mountain,
  Route,
  Scale,
  Timer,
  Unplug,
  Watch,
  Waves,
} from 'lucide-react'
import { useCallback, useEffect, useState, type ComponentType, type CSSProperties } from 'react'
import * as api from '../lib/api'
import { Sheet } from '../components/recipes'
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
  key: 'steps' | 'active_kcal' | 'distance' | 'exercise_minutes' | 'resting_hr'
  label: string
  title: string
  icon: typeof Footprints
  colorVar: string
  unit?: string
  goalKey?: keyof api.FitnessGoals
  bestWord: string
  bestPick: 'max' | 'min'
  // How the stored value reads to a person. Defaults to a rounded count; the
  // distance metric is stored in meters and rendered as miles.
  fmt?: (v: number | null) => string
}

// The distance metric arrives in meters; every surface shows one decimal mile.
const fmtMilesNum = (v: number | null): string =>
  v === null ? '–' : (v / 1609.344).toFixed(1)

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
    key: 'distance',
    label: 'Distance',
    title: 'Distance',
    icon: Route,
    colorVar: '--fit-distance',
    unit: 'mi',
    bestWord: 'Best day',
    bestPick: 'max',
    fmt: fmtMilesNum,
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

// All five metrics share the 2-col grid; resting HR is the static one - no
// chart on its card, and its detail is plain 7/30-day averages (one reading
// a day is too sparse to be worth graphing).
const GRID_METRICS = METRICS

// The hourly series for the metrics that get a time-of-day chart. Undefined —
// so the card falls back to the week view — for other metrics, before intraday
// loads, or on a day the exporter sent only daily totals (an all-null series).
function hourlyFor(
  def: MetricDef,
  intraday: api.FitnessIntraday | null,
): (number | null)[] | undefined {
  if (!intraday) return undefined
  const series =
    def.key === 'steps'
      ? intraday.steps
      : def.key === 'active_kcal'
        ? intraday.active_kcal
        : def.key === 'distance'
          ? intraday.distance
          : undefined
  return series && series.some((v) => v != null) ? series : undefined
}

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
          className="-m-1.5 shrink-0 rounded-full p-3.5 text-fg/50 transition-colors hover:bg-fg/10 hover:text-fg"
        >
          {copied ? <Check className="h-4 w-4 text-accent-bright" /> : <Copy className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}

type Platform = 'apple' | 'android'

// The device someone opens this sheet on is almost always the phone the
// health data lives on, so lead with its own path. A desktop browser says
// nothing about the phone in their pocket — those get asked. The instruction
// screen always offers the other path, so a wrong guess costs one tap.
function detectPlatform(): Platform | null {
  const ua = navigator.userAgent
  if (/Android/i.test(ua)) return 'android'
  if (/iPhone|iPad|iPod/.test(ua)) return 'apple'
  return null
}

const PLATFORM_LABEL: Record<Platform, string> = {
  apple: 'iPhone + Apple Watch',
  android: 'Android + Pixel Watch',
}

const PLATFORM_COPY: Record<Platform, { title: string; intro: string; after: string }> = {
  apple: {
    title: 'Connect Apple Health',
    intro:
      'Your phone sends the numbers here itself; no cloud service ever sees them. You need an iPhone app that can send Apple Health data to a web address on a schedule (Health Auto Export is the one the docs walk through). This makes a sync key for it. If you already have one, this replaces it.',
    after:
      'Point the exporter app at this address, add the header below, and choose which metrics to send. Turn on route data for the little run maps.',
  },
  android: {
    title: 'Connect Health Connect',
    intro:
      'Pixel Watch, Fitbit, and Samsung data all land in Health Connect on your phone, and a small bridge app sends it here on a schedule; no cloud service ever sees it. HC Webhook (free, open source, on Google Play) is the one this was built against. This makes a sync key for it. If you already have one, this replaces it.',
    after:
      'In HC Webhook: add this address as the webhook URL, add the header below as a custom header, grant it the Health Connect permissions you want to share (steps, calories, heart rate, exercise, weight, body fat), and pick a schedule.',
  },
}

function ConnectSheet({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [platform, setPlatform] = useState<Platform | null>(detectPlatform)
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

  if (platform === null) {
    return (
      <Sheet onClose={onClose}>
        <h3 className="mb-1 text-lg font-bold">Connect your watch</h3>
        <p className="mb-4 text-sm text-fg/60">
          What kind of phone does the data live on? Either way it flows straight from your
          phone to your own server.
        </p>
        <div className="flex flex-col gap-2">
          <Button type="button" onClick={() => setPlatform('apple')} className="w-full">
            {PLATFORM_LABEL.apple}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setPlatform('android')} className="w-full">
            {PLATFORM_LABEL.android}
          </Button>
        </div>
      </Sheet>
    )
  }

  const copy = PLATFORM_COPY[platform]
  const other: Platform = platform === 'apple' ? 'android' : 'apple'
  // The key itself is platform-agnostic, so switching after minting just
  // swaps the instructions — never re-mints.
  const switchLink = (
    <button
      type="button"
      onClick={() => setPlatform(other)}
      className="self-start py-1 text-xs font-semibold text-accent-bright"
    >
      {PLATFORM_LABEL[other]} instead?
    </button>
  )
  return (
    <Sheet onClose={minted ? onDone : onClose}>
      <h3 className="mb-1 text-lg font-bold">{copy.title}</h3>
      {minted === null ? (
        <>
          <p className="mb-4 text-sm text-fg/60">{copy.intro}</p>
          <FormError message={error} />
          <div className="flex flex-col gap-2">
            <Button onClick={mint} disabled={busy}>
              {busy ? 'Making a key…' : 'Make my sync key'}
            </Button>
            {switchLink}
          </div>
        </>
      ) : (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-fg/60">
            {copy.after} The key is shown only this once.
          </p>
          <CopyRow label="Send to" value={`${window.location.origin}${minted.path}`} />
          <CopyRow label="Authorization header" value={`Bearer ${minted.token}`} />
          <p className="text-xs text-fg/45">
            Data lands whenever the phone is on your home network and catches up after time
            away. Only you can see it.
          </p>
          <Button onClick={onDone}>Done</Button>
          {switchLink}
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
        const isToday = i === week.length - 1
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
                opacity: v && !isToday ? 0.4 : 1,
                boxShadow:
                  isToday && v
                    ? `0 0 0 2px color-mix(in srgb, var(${colorVar}) 55%, transparent)`
                    : undefined,
              }}
              title={v ? `${Math.round(v).toLocaleString()} ${unit}` : 'No data'}
            />
            <span
              className={`text-[9px] font-semibold ${isToday ? '' : 'text-fg/35'}`}
              style={isToday ? { color: `var(${colorVar})` } : undefined}
            >
              {letter}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// A few labelled anchors under the 24-bar time-of-day chart; 12AM start.
const HOUR_TICKS: Record<number, string> = { 0: '12a', 6: '6a', 12: '12p', 18: '6p' }

function hourLabel(h: number): string {
  const ampm = h < 12 ? 'AM' : 'PM'
  return `${h % 12 === 0 ? 12 : h % 12} ${ampm}`
}

// The day by time of day: 24 hourly bars, midnight on the left. Same bar
// language as MiniBars, a different x-axis.
function HourBars({
  hours,
  colorVar,
  unit,
  fmt,
  height = 44,
}: {
  hours: (number | null)[]
  colorVar: string
  unit: string
  fmt?: (v: number | null) => string
  // Bar-area height; the detail passes a taller value for the zoomed view.
  height?: number
}) {
  const max = Math.max(...hours.map((v) => v ?? 0), 1)
  const barMax = height - 10
  return (
    <div className="mt-3 flex items-end justify-between gap-px" style={{ height }}>
      {hours.map((v, h) => (
        <div key={h} className="flex flex-1 flex-col items-center gap-1">
          <div
            className="w-full rounded-[2px]"
            style={{
              height: v ? Math.max(4, Math.round((v / max) * barMax)) : 3,
              background: v
                ? `var(${colorVar})`
                : 'color-mix(in srgb, var(--fg) 10%, transparent)',
            }}
            title={
              v
                ? `${fmt ? fmt(v) : Math.round(v).toLocaleString()} ${unit} · ${hourLabel(h)}`
                : hourLabel(h)
            }
          />
          <span className="h-2 text-[8px] font-semibold leading-none text-fg/35">
            {HOUR_TICKS[h] ?? ''}
          </span>
        </div>
      ))}
    </div>
  )
}

// The week at a glance with today spotlit: the "today vs the week" view a
// metric card opens into.
function WeekStrip({
  week,
  def,
}: {
  week: api.FitnessWeekDay[]
  def: MetricDef
}) {
  const vals = week.map((d) => d[def.key])
  const max = Math.max(...vals.map((v) => v ?? 0), 1)
  return (
    <div className="flex items-stretch gap-1.5" style={{ height: 84 }}>
      {week.map((d, i) => {
        const v = vals[i]
        const isToday = i === week.length - 1
        const h = v ? Math.max(6, Math.round((v / max) * 60)) : 4
        const letter = DAY_LETTERS[(new Date(d.date_for + 'T00:00:00').getDay() + 6) % 7]
        return (
          <div
            key={d.date_for}
            className={`flex flex-1 flex-col items-center justify-end gap-1 rounded-lg pb-1 ${
              isToday ? 'bg-fg/[0.06]' : ''
            }`}
            style={isToday ? { boxShadow: `inset 0 0 0 1px color-mix(in srgb, var(${def.colorVar}) 35%, transparent)` } : undefined}
          >
            <div
              className="w-full rounded-[3px]"
              style={{
                height: h,
                maxWidth: '1.5rem',
                background: v
                  ? `var(${def.colorVar})`
                  : 'color-mix(in srgb, var(--fg) 10%, transparent)',
                opacity: v && !isToday ? 0.4 : 1,
              }}
            />
            <span
              className={`text-[10px] font-bold ${isToday ? '' : 'font-semibold text-fg/35'}`}
              style={isToday ? { color: `var(${def.colorVar})` } : undefined}
            >
              {letter}
            </span>
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
  hourly,
  staticNote,
  onOpen,
}: {
  def: MetricDef
  value: number | null
  week: api.FitnessWeekDay[]
  // When present, the front chart shows today by time of day; otherwise the week.
  hourly?: (number | null)[]
  // A static card carries no chart at all - just this line under the value.
  staticNote?: string
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
        {(def.fmt ?? fmtNumber)(value)}
        {unit && <span className="ml-1 text-sm font-semibold">{unit}</span>}
      </p>
      {staticNote ? (
        <p className="mt-2 text-[11px] text-fg/45">{staticNote}</p>
      ) : hourly ? (
        <HourBars hours={hourly} colorVar={colorVar} unit={unit ?? label.toLowerCase()} fmt={def.fmt} />
      ) : (
        <MiniBars
          week={week}
          pick={(d) => d[def.key]}
          colorVar={colorVar}
          unit={unit ?? label.toLowerCase()}
        />
      )}
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
  week,
  hourly,
  history,
  goals,
  onGoals,
  onClose,
}: {
  def: MetricDef
  today: number | null
  week: api.FitnessWeekDay[]
  // Present for the metrics with a time-of-day chart; the detail then leads with
  // the zoomed hourly day instead of the week comparison.
  hourly?: (number | null)[]
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
  const fmtVal = def.fmt ?? fmtNumber

  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 flex items-center gap-2 text-lg font-bold">
        <Icon className="h-5 w-5" style={{ color: `var(${def.colorVar})` }} />
        {def.title}
      </h3>
      <p className="text-[11px] text-fg/45">Today</p>
      <p className="text-3xl font-bold tracking-tight" style={{ color: `var(${def.colorVar})` }}>
        {fmtVal(today)}
        {def.unit && <span className="ml-1 text-base font-semibold">{def.unit}</span>}
      </p>

      <div className="mt-4">
        {hourly ? (
          <>
            <p className="mb-2 text-xs text-fg/55">Today, by the hour</p>
            <HourBars
              hours={hourly}
              colorVar={def.colorVar}
              unit={def.unit ?? def.label.toLowerCase()}
              fmt={def.fmt}
              height={128}
            />
          </>
        ) : (
          <>
            <p className="mb-2 text-xs text-fg/55">Today vs the week</p>
            <WeekStrip week={week} def={def} />
          </>
        )}
      </div>

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
                      : fmtVal(selectedDay[def.key]) + unitSuffix
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
            <DetailStat label="7-day avg" value={avg7 === null ? '–' : fmtVal(avg7) + unitSuffix} />
            <DetailStat label="30-day avg" value={avg30 === null ? '–' : fmtVal(avg30) + unitSuffix} />
            <DetailStat
              label={def.bestWord}
              value={best === null ? '–' : fmtVal(best[def.key]) + unitSuffix}
              sub={best === null ? undefined : fmtShortDate(best.date_for)}
            />
          </div>

          {goal !== undefined && <GoalEditor def={def} goal={goal} onGoals={onGoals} />}
        </div>
      )}
    </Sheet>
  )
}

// ---- weight trend -----------------------------------------------------------------

const LB_PER_KG = 2.20462
const lb1 = (kg: number) => Math.round(kg * LB_PER_KG * 10) / 10

type WeighPoint = { date: string; t: number; kg: number; fat: number | null }

// The last 90 days of weigh-ins, oldest first, with dates as timestamps so
// the chart can place sparse entries at their honest positions in time.
function weighSeries(weights: api.WeightEntry[]): WeighPoint[] {
  const cutoff = Date.now() - 90 * 86400_000
  return weights
    .map((w) => ({
      date: w.date_for,
      t: new Date(w.date_for + 'T00:00:00').getTime(),
      kg: w.weight_kg,
      fat: w.body_fat_pct,
    }))
    .filter((p) => p.t >= cutoff)
    .sort((a, b) => a.t - b.t)
}

// One time-scaled line panel. Weight and body fat live on different scales,
// so each gets its own panel with its own y range — never two scales on one
// chart — while t0/t1 keep the two panels' time axes aligned. Every point
// gets a full-height tap column split at the midpoints between neighbours.
function LinePanel({
  points,
  pick,
  t0,
  t1,
  height,
  colorVar,
  goal,
  selected,
  onSelect,
}: {
  points: WeighPoint[]
  pick: (p: WeighPoint) => number
  t0: number
  t1: number
  height: number
  colorVar: string
  goal?: number | null
  selected: string | null
  onSelect: (date: string) => void
}) {
  const W = 320
  const PAD_X = 10
  const PAD_Y = 12
  const span = Math.max(t1 - t0, 86400_000)
  const vals = points.map(pick)
  let vmin = Math.min(...vals)
  let vmax = Math.max(...vals)
  // Fold the goal into the range only when it's near the data; a far-off
  // goal would flatten the line into noise, so it stays a stat instead.
  const spread = vmax - vmin
  if (goal != null && goal >= vmin - spread && goal <= vmax + spread) {
    vmin = Math.min(vmin, goal)
    vmax = Math.max(vmax, goal)
  }
  const pad = (vmax - vmin) * 0.15 || Math.max(vmax * 0.03, 1)
  vmin -= pad
  vmax += pad
  const x = (t: number) => PAD_X + ((t - t0) / span) * (W - 2 * PAD_X)
  const y = (v: number) => PAD_Y + (1 - (v - vmin) / (vmax - vmin)) * (height - 2 * PAD_Y)
  const path = points
    .map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)} ${y(pick(p)).toFixed(1)}`)
    .join(' ')
  const goalY = goal != null && goal > vmin && goal < vmax ? y(goal) : null
  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="w-full" role="img">
      {goalY !== null && (
        <>
          <line
            x1={0}
            x2={W}
            y1={goalY}
            y2={goalY}
            stroke="currentColor"
            className="text-fg/25"
            strokeDasharray="4 4"
            strokeWidth={1}
          />
          <text
            x={W - 2}
            y={goalY - 4}
            textAnchor="end"
            fontSize={9}
            fontWeight={600}
            fill="currentColor"
            className="text-fg/40"
          >
            GOAL
          </text>
        </>
      )}
      <path
        d={path}
        fill="none"
        stroke={`var(${colorVar})`}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {points.map((p) => (
        <circle
          key={p.date}
          cx={x(p.t)}
          cy={y(pick(p))}
          r={selected === p.date ? 5 : 3.5}
          fill={`var(${colorVar})`}
          stroke="var(--surface)"
          strokeWidth={2}
        />
      ))}
      {points.map((p, i) => {
        const left = i === 0 ? 0 : (x(points[i - 1].t) + x(p.t)) / 2
        const right = i === points.length - 1 ? W : (x(p.t) + x(points[i + 1].t)) / 2
        return (
          <rect
            key={p.date}
            x={left}
            y={0}
            width={right - left}
            height={height}
            fill="transparent"
            role="button"
            aria-label={fmtReadoutDate(p.date)}
            onClick={() => onSelect(p.date)}
            style={{ cursor: 'pointer' }}
          />
        )
      })}
    </svg>
  )
}

// The card's small static preview of the same series.
function WeightSparkline({ points }: { points: WeighPoint[] }) {
  const W = 96
  const H = 36
  const t0 = points[0].t
  const span = Math.max(points[points.length - 1].t - t0, 86400_000)
  const vals = points.map((p) => p.kg)
  const vmin = Math.min(...vals)
  const spread = Math.max(...vals) - vmin || 1
  const path = points
    .map(
      (p, i) =>
        `${i ? 'L' : 'M'}${(3 + ((p.t - t0) / span) * (W - 6)).toFixed(1)} ${(
          4 +
          (1 - (p.kg - vmin) / spread) * (H - 8)
        ).toFixed(1)}`,
    )
    .join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} aria-hidden>
      <path
        d={path}
        fill="none"
        stroke="var(--fit-weight)"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}

// "Goal 200 lb by Nov 3": the Health Calculator's plan, one line. Pure
// arithmetic on the profile (lbs to go / lbs per week), empty when there's
// no active lose/gain plan.
function weightGoalText(health: api.Health): string | null {
  const p = health.profile
  const w = health.latest_weight
  const c = health.computed
  if (!p || !w || !c || c.at_goal || p.goal_weight_kg == null) return null
  const goalLb = lb1(p.goal_weight_kg)
  if (p.goal !== 'lose' && p.goal !== 'gain') return `Goal ${goalLb} lb`
  const rate = p.rate_lbs_per_week ?? 0
  if (rate <= 0) return `Goal ${goalLb} lb`
  const lbsToGo = Math.abs(w.weight_kg - p.goal_weight_kg) * 2.20462
  const days = Math.round((lbsToGo / rate) * 7)
  if (days <= 0 || days >= 365 * 3) return `Goal ${goalLb} lb`
  const when = new Date(Date.now() + days * 86_400_000)
  const label = when.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    ...(when.getFullYear() !== new Date().getFullYear() ? { year: 'numeric' } : {}),
  })
  return `Goal ${goalLb} lb by ${label}`
}


// Weight is the most personal number on the page, so it stays blurred behind a
// tap. First tap reveals it in place; once revealed, the card opens the full
// chart and a hide button re-blurs it. The reveal state lives in the parent and
// resets when the tab remounts, so the number is never left showing after you
// leave.
function WeightCard({
  points,
  goal,
  revealed,
  onReveal,
  onHide,
  onOpen,
}: {
  points: WeighPoint[]
  // The plan, read-only: the goal is EDITED in Nutrition's Health Calculator
  // (where the calorie budget lives); here it just captions the progress.
  goal: string | null
  revealed: boolean
  onReveal: () => void
  onHide: () => void
  onOpen: () => void
}) {
  const latest = points[points.length - 1]
  const label = (
    <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-fg/50">
      <Scale className="h-3.5 w-3.5" style={{ color: 'var(--fit-weight)' }} /> Weight
    </span>
  )

  if (!revealed) {
    return (
      <button
        type="button"
        onClick={onReveal}
        aria-label="Show weight"
        className="glass relative flex items-center gap-3 p-4 text-left"
      >
        <div className="min-w-0 flex-1">
          {label}
          <div className="relative">
            <div className="pointer-events-none select-none blur-[7px]" aria-hidden>
              <p className="mt-1 text-[11px] text-fg/45">Last weigh-in · {fmtShortDate(latest.date)}</p>
              <p className="text-2xl font-bold tracking-tight" style={{ color: 'var(--fit-weight)' }}>
                {lb1(latest.kg).toLocaleString()}
                <span className="ml-1 text-sm font-semibold">lb</span>
              </p>
            </div>
            <span className="absolute inset-0 flex items-center gap-1.5 text-sm font-semibold text-fg/60">
              <Eye className="h-4 w-4" /> Tap to show
            </span>
          </div>
        </div>
        {points.length > 1 && (
          <div className="pointer-events-none select-none blur-[7px]" aria-hidden>
            <WeightSparkline points={points} />
          </div>
        )}
      </button>
    )
  }

  return (
    <div className="glass relative flex items-center gap-2 p-4">
      <button
        type="button"
        onClick={onOpen}
        aria-label="Open weight detail"
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
      >
        <div className="min-w-0 flex-1">
          {label}
          <p className="mt-1 text-[11px] text-fg/45">
            Last weigh-in · {fmtShortDate(latest.date)}
            {goal && ` · ${goal}`}
          </p>
          <p className="text-2xl font-bold tracking-tight" style={{ color: 'var(--fit-weight)' }}>
            {lb1(latest.kg).toLocaleString()}
            <span className="ml-1 text-sm font-semibold">lb</span>
            {latest.fat !== null && (
              <span className="ml-2 text-sm font-semibold" style={{ color: 'var(--fit-bodyfat)' }}>
                {latest.fat}% body fat
              </span>
            )}
          </p>
        </div>
        {points.length > 1 && <WeightSparkline points={points} />}
        <ChevronRight className="h-4 w-4 shrink-0 text-fg/30" />
      </button>
      <button
        type="button"
        onClick={onHide}
        aria-label="Hide weight"
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-fg/40 transition-colors hover:bg-fg/10 hover:text-fg"
      >
        <EyeOff className="h-4 w-4" />
      </button>
    </div>
  )
}

function WeightDetail({ health, onClose }: { health: api.Health; onClose: () => void }) {
  const [selected, setSelected] = useState<string | null>(null)
  const points = weighSeries(health.weights)
  const latest = points[points.length - 1]
  const first = points[0]
  const fatPoints = points.filter((p) => p.fat !== null)
  // The right edge is today, so a stretch without weigh-ins shows as the
  // honest flat gap it is.
  const t0 = first.t
  const t1 = Math.max(latest.t, new Date().setHours(0, 0, 0, 0))
  const goalKg = health.profile?.goal_weight_kg ?? null

  const sel = selected !== null ? points.find((p) => p.date === selected) ?? null : null
  const delta = points.length > 1 ? lb1(latest.kg) - lb1(first.kg) : null

  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 flex items-center gap-2 text-lg font-bold">
        <Scale className="h-5 w-5" style={{ color: 'var(--fit-weight)' }} />
        Weight
      </h3>
      <p className="text-[11px] text-fg/45">Last weigh-in</p>
      <p className="text-3xl font-bold tracking-tight" style={{ color: 'var(--fit-weight)' }}>
        {lb1(latest.kg).toLocaleString()}
        <span className="ml-1 text-base font-semibold">lb</span>
      </p>

      <div className="mt-4 flex flex-col gap-4">
        <div>
          <p className="mb-2 h-4 text-xs text-fg/55">
            {sel
              ? `${fmtReadoutDate(sel.date)} · ${lb1(sel.kg)} lb${
                  sel.fat !== null ? ` · ${sel.fat}% body fat` : ''
                }`
              : 'Last 90 days · tap a point'}
          </p>
          <LinePanel
            points={points}
            pick={(p) => p.kg}
            t0={t0}
            t1={t1}
            height={120}
            colorVar="--fit-weight"
            goal={goalKg}
            selected={selected}
            onSelect={(d) => setSelected(selected === d ? null : d)}
          />
          <div className="mt-1 flex justify-between text-[10px] font-semibold text-fg/35">
            <span>{fmtShortDate(first.date)}</span>
            <span>Today</span>
          </div>
        </div>

        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide" style={{ color: 'var(--fit-bodyfat)' }}>
            Body fat %
          </p>
          {fatPoints.length > 0 ? (
            <LinePanel
              points={fatPoints}
              pick={(p) => p.fat as number}
              t0={t0}
              t1={t1}
              height={64}
              colorVar="--fit-bodyfat"
              goal={health.profile?.goal_body_fat_pct ?? null}
              selected={selected}
              onSelect={(d) => setSelected(selected === d ? null : d)}
            />
          ) : (
            <p className="rounded-xl bg-fg/5 px-4 py-3 text-xs text-fg/50">
              If your scale measures body fat, add Body Fat Percentage to the metrics your
              exporter sends and it draws here alongside the weight line.
            </p>
          )}
        </div>

        <div className="grid grid-cols-3 gap-3">
          <DetailStat label="Latest" value={`${lb1(latest.kg)} lb`} sub={fmtShortDate(latest.date)} />
          <DetailStat
            label="Change"
            value={
              delta === null ? '–' : `${delta > 0 ? '+' : ''}${Math.round(delta * 10) / 10} lb`
            }
            sub={delta === null ? undefined : `since ${fmtShortDate(first.date)}`}
          />
          <DetailStat
            label="Goal"
            value={goalKg === null ? '–' : `${lb1(goalKg)} lb`}
            sub={
              goalKg === null
                ? undefined
                : `${Math.round(Math.abs(lb1(latest.kg) - lb1(goalKg)) * 10) / 10} lb to go`
            }
          />
        </div>

        <p className="text-xs text-fg/45">
          Weigh-ins are logged on the You tab, or arrive with your scale's sync. Only you see
          this.
        </p>
      </div>
    </Sheet>
  )
}

// Resting HR gets numbers, not charts: today's reading and the 7- and
// 30-day averages from the daily history the watch already syncs.
function HRDetail({
  resting,
  history,
  source,
  onClose,
}: {
  resting: number | null
  history: api.FitnessWeekDay[] | null
  source: string
  onClose: () => void
}) {
  const avgOf = (days: api.FitnessWeekDay[]): string => {
    const vals = days
      .map((d) => d.resting_hr)
      .filter((v): v is number => v != null)
    if (vals.length === 0) return '–'
    return `${Math.round(vals.reduce((a, b) => a + b, 0) / vals.length)} bpm`
  }
  const month = history ?? []
  const lows = month.map((d) => d.resting_hr).filter((v): v is number => v != null)
  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 flex items-center gap-2 text-lg font-bold">
        <HeartPulse className="h-5 w-5" style={{ color: 'var(--fit-hr)' }} /> Resting heart rate
      </h3>
      <p className="text-[11px] text-fg/45">Today</p>
      <p className="text-3xl font-bold tracking-tight" style={{ color: 'var(--fit-hr)' }}>
        {resting != null ? fmtNumber(resting) : '–'}
        <span className="ml-1 text-base font-semibold">bpm</span>
      </p>

      <div className="mt-4 grid grid-cols-3 gap-3">
        <DetailStat label="7-day average" value={avgOf(month.slice(-7))} />
        <DetailStat label="30-day average" value={avgOf(month)} />
        <DetailStat
          label="Lowest · 30 days"
          value={lows.length ? `${Math.round(Math.min(...lows))} bpm` : '–'}
        />
      </div>
      <p className="mt-4 text-xs text-fg/45">
        One reading a day, synced from {source}. A gently falling trend usually means fitness
        is improving.
      </p>
    </Sheet>
  )
}

// A running figure in the street-sign style; the icon set has walkers and
// bikes but no runner, so this one is drawn to its 24px stroke grammar.
function Runner({ className, style }: { className?: string; style?: CSSProperties }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      aria-hidden
    >
      <circle cx="13" cy="4" r="1" />
      <path d="M4 17l5 1 .75-1.5" />
      <path d="M15 21v-4l-4-3 1-6" />
      <path d="M7 12V9l5-1 3 3 3 1" />
    </svg>
  )
}

type ActivityIcon = ComponentType<{ className?: string; style?: CSSProperties }>

// Each kind of workout wears its own face; the flame stays for anything the
// list doesn't know. Matched on the activity name Apple sends.
const ACTIVITY_ICONS: [RegExp, ActivityIcon][] = [
  [/run/i, Runner],
  [/hik/i, Mountain],
  [/walk/i, Footprints],
  [/strength|core|weight/i, Dumbbell],
  [/swim/i, Waves],
  [/cycl|bike/i, Bike],
]

function activityIcon(activity: string): ActivityIcon {
  const hit = ACTIVITY_ICONS.find(([re]) => re.test(activity))
  return hit ? hit[1] : Flame
}

// Project a GPS route into an S×S box, latitude corrected so the shape isn't
// stretched. Shared by the row thumbnail and the larger detail map. Still just
// a trace of the stored 60-point shape — nothing here calls a map service.
function projectRoute(route: number[][], S: number, PAD: number) {
  const lats = route.map((p) => p[0])
  const lons = route.map((p) => p[1])
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const minLon = Math.min(...lons)
  const maxLon = Math.max(...lons)
  const kx = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180)
  const w = (maxLon - minLon) * kx || 1e-9
  const h = maxLat - minLat || 1e-9
  const s = Math.min((S - 2 * PAD) / w, (S - 2 * PAD) / h)
  const ox = (S - w * s) / 2
  const oy = (S - h * s) / 2
  const pt = ([lat, lon]: number[]): [number, number] => [
    ox + (lon - minLon) * kx * s,
    oy + (maxLat - lat) * s,
  ]
  return {
    points: route.map((p) => pt(p).map((n) => n.toFixed(1)).join(',')).join(' '),
    start: pt(route[0]),
    end: pt(route[route.length - 1]),
  }
}

// A tiny map-less trace of where the workout went. Decoration only — the row's
// text carries the information.
function RouteThumb({ route }: { route: number[][] }) {
  const S = 48
  const { points, start } = projectRoute(route, S, 5)
  return (
    <svg width={S} height={S} viewBox={`0 0 ${S} ${S}`} aria-hidden className="shrink-0">
      <polyline
        points={points}
        fill="none"
        stroke="var(--fit-active)"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.85}
      />
      <circle cx={start[0]} cy={start[1]} r={2.5} fill="var(--fit-active)" />
    </svg>
  )
}

// The same trace, drawn large for the detail sheet, with the start and finish
// marked. No splits or per-second heart rate exist in the stored data, so the
// route plus the summary stats are the whole picture.
function RouteMap({ route }: { route: number[][] }) {
  const S = 260
  const { points, start, end } = projectRoute(route, S, 20)
  return (
    <svg
      viewBox={`0 0 ${S} ${S}`}
      role="img"
      aria-label="Workout route"
      className="mx-auto block w-full max-w-[280px]"
    >
      <polyline
        points={points}
        fill="none"
        stroke="var(--fit-active)"
        strokeWidth={3}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={start[0]} cy={start[1]} r={5} fill="var(--fit-active)" stroke="var(--surface)" strokeWidth={2} />
      <circle cx={end[0]} cy={end[1]} r={5} fill="var(--fg)" stroke="var(--surface)" strokeWidth={2} />
    </svg>
  )
}

function WorkoutRow({ workout, onOpen }: { workout: api.Workout; onOpen: () => void }) {
  const Icon = activityIcon(workout.activity)
  const bits = [
    workout.duration_s ? `${Math.round(workout.duration_s / 60)} min` : null,
    workout.kcal ? `${Math.round(workout.kcal)} kcal` : null,
    fmtMiles(workout.distance_m),
    workout.avg_hr ? `${Math.round(workout.avg_hr)} bpm avg` : null,
  ].filter(Boolean)
  return (
    <button type="button" onClick={onOpen} className="glass flex w-full items-center gap-3 p-4 text-left">
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
        style={{ background: 'color-mix(in srgb, var(--fit-active) 16%, transparent)' }}
      >
        <Icon className="h-5 w-5" style={{ color: 'var(--fit-active)' }} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold text-fg/90">{workout.activity}</p>
        <p className="truncate text-xs text-fg/50">{fmtWhen(workout.started_at)}</p>
      </div>
      {workout.route && workout.route.length > 1 && <RouteThumb route={workout.route} />}
      <p className="shrink-0 text-right text-xs leading-relaxed text-fg/60">
        {bits.map((b) => (
          <span key={b} className="block">
            {b}
          </span>
        ))}
      </p>
      <ChevronRight className="h-4 w-4 shrink-0 text-fg/30" />
    </button>
  )
}

function fmtDuration(seconds: number | null): string | null {
  if (!seconds) return null
  const mins = Math.round(seconds / 60)
  if (mins < 60) return `${mins} min`
  return `${Math.floor(mins / 60)}h ${mins % 60}m`
}

// Average pace in min/mile, only when there's real distance to divide by.
function fmtPace(workout: api.Workout): string | null {
  if (!workout.distance_m || !workout.duration_s) return null
  const miles = workout.distance_m / 1609.344
  if (miles < 0.05) return null
  const secPerMile = workout.duration_s / miles
  const m = Math.floor(secPerMile / 60)
  const s = Math.round(secPerMile % 60)
  return `${m}:${s.toString().padStart(2, '0')} /mi`
}

// Tapping a workout opens this. Route drawn large where GPS came along (Apple),
// then the summary stats. Splits and per-second heart rate aren't in the stored
// data, so they aren't invented here.
function WorkoutDetail({ workout, onClose }: { workout: api.Workout; onClose: () => void }) {
  const Icon = activityIcon(workout.activity)
  const stats: [string, string][] = (
    [
      ['Duration', fmtDuration(workout.duration_s)],
      ['Distance', fmtMiles(workout.distance_m)],
      ['Avg pace', fmtPace(workout)],
      ['Calories', workout.kcal ? `${Math.round(workout.kcal)} kcal` : null],
      ['Avg HR', workout.avg_hr ? `${Math.round(workout.avg_hr)} bpm` : null],
    ] as [string, string | null][]
  ).filter((s): s is [string, string] => s[1] !== null)
  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 flex items-center gap-2 text-lg font-bold">
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
          style={{ background: 'color-mix(in srgb, var(--fit-active) 16%, transparent)' }}
        >
          <Icon className="h-5 w-5" style={{ color: 'var(--fit-active)' }} />
        </span>
        {workout.activity}
      </h3>
      <p className="text-[11px] text-fg/45">{fmtWhen(workout.started_at)}</p>

      {workout.route && workout.route.length > 1 && (
        <div className="mt-4 rounded-2xl bg-fg/5 p-3">
          <RouteMap route={workout.route} />
        </div>
      )}

      <div className="mt-4 grid grid-cols-3 gap-3">
        {stats.map(([label, value]) => (
          <DetailStat key={label} label={label} value={value} />
        ))}
      </div>

      <p className="mt-4 text-xs text-fg/45">
        Synced from {workout.source === 'android' ? 'Health Connect' : 'Apple Health'}.
      </p>
    </Sheet>
  )
}

// ---- the tab --------------------------------------------------------------------

export function Fitness() {
  const [data, setData] = useState<api.Fitness | null>(null)
  const [health, setHealth] = useState<api.Health | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)
  const [detail, setDetail] = useState<MetricDef | null>(null)
  const [weightOpen, setWeightOpen] = useState(false)
  const [weightRevealed, setWeightRevealed] = useState(false)
  const [workoutOpen, setWorkoutOpen] = useState<api.Workout | null>(null)
  const [showAllWorkouts, setShowAllWorkouts] = useState(false)
  const [history, setHistory] = useState<api.FitnessWeekDay[] | null>(null)
  const [intraday, setIntraday] = useState<api.FitnessIntraday | null>(null)

  const refresh = useCallback(async () => {
    // The weight log rides along for the trend card; if it can't load, the
    // card just doesn't appear — the rings are the tab's real job.
    api.getHealthProfile().then(setHealth).catch(() => {})
    // Today's hour-by-hour buckets for the time-of-day charts; if it can't
    // load, the cards fall back to the week view.
    api.getFitnessIntraday(api.localDate()).then(setIntraday).catch(() => setIntraday(null))
    try {
      setData(await api.getFitness(api.localDate()))
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load fitness data.')
    }
  }, [])

  // The 30-day window is one cheap fetch shared by every detail view; grab it
  // the first time any card opens.
  function loadHistory() {
    if (history === null) {
      api
        .getFitnessHistory(api.localDate())
        .then((h) => setHistory(h.days))
        .catch(() => setHistory([]))
    }
  }
  function openDetail(def: MetricDef) {
    setDetail(def)
    loadHistory()
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

  async function toggleWatchKcal() {
    if (!data) return
    try {
      const res = await api.setWatchKcal(!data.count_watch_kcal)
      setData((d) => (d ? { ...d, count_watch_kcal: res.enabled } : d))
    } catch {
      // The switch simply stays put; the next tap tries again.
    }
  }

  if (error) return <FormError message={error} />
  if (data === null) return <p className="text-sm text-fg/40">Loading</p>

  const hasAnything =
    data.today.steps !== null ||
    data.workouts.length > 0 ||
    data.week.some((d) => d.steps !== null)

  // Where the health data comes from, for the static resting HR card. A
  // synced workout says for sure; failing that, the phone in hand is almost
  // certainly the phone that syncs.
  const syncPlatform = data.workouts.find((w) => w.source)?.source ?? detectPlatform()
  const syncSourceName =
    syncPlatform === 'android'
      ? 'Health Connect'
      : syncPlatform === 'apple'
        ? 'Apple Health'
        : 'your phone'

  return (
    <div className="flex flex-col gap-4">
      {!data.connected && !hasAnything && (
        <div className="glass flex flex-col items-center gap-3 p-8 text-center">
          <HeartPulse className="h-8 w-8 text-red-400" />
          <p className="font-semibold text-fg/90">Your activity on one page</p>
          <p className="text-sm text-fg/55">
            Steps, workouts, and weigh-ins from your watch land here, straight from
            your phone to your own server. Only you can see them.
          </p>
          <Button onClick={() => setConnecting(true)}>Connect your watch</Button>
        </div>
      )}

      {(data.connected || hasAnything) && (
        <>
          <div className="glass p-5">
            {data.last_sync && (
              <p className="mb-1 text-sm font-bold text-fg/80">
                Last sync: {fmtWhen(data.last_sync)}
              </p>
            )}
            <span className="mb-4 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              Today's activity
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
                label="Active Calories"
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
            {GRID_METRICS.map((def) => (
              <MetricCard
                key={def.key}
                def={def}
                value={data.today[def.key]}
                week={data.week}
                hourly={hourlyFor(def, intraday)}
                staticNote={def.key === 'resting_hr' ? `Synced from ${syncSourceName}` : undefined}
                onOpen={() => openDetail(def)}
              />
            ))}
          </div>

          {health !== null && weighSeries(health.weights).length > 0 && (
            <WeightCard
              points={weighSeries(health.weights)}
              goal={weightGoalText(health)}
              revealed={weightRevealed}
              onReveal={() => setWeightRevealed(true)}
              onHide={() => setWeightRevealed(false)}
              onOpen={() => setWeightOpen(true)}
            />
          )}

          {data.workouts.length > 0 && (
            <div className="flex flex-col gap-2">
              <span className="px-1 text-xs font-semibold uppercase tracking-wide text-fg/50">
                Workouts
              </span>
              {(showAllWorkouts ? data.workouts : data.workouts.slice(0, 3)).map((w) => (
                <WorkoutRow key={w.id} workout={w} onOpen={() => setWorkoutOpen(w)} />
              ))}
              {data.workouts.length > 3 && (
                <button
                  type="button"
                  onClick={() => setShowAllWorkouts((v) => !v)}
                  className="self-center px-4 py-2 text-sm font-semibold text-accent-bright hover:underline"
                >
                  {showAllWorkouts
                    ? 'Show fewer'
                    : `Show ${data.workouts.length - 3} more`}
                </button>
              )}
            </div>
          )}

          <div className="glass flex items-center gap-3 p-4">
            <Link2 className="h-4 w-4 shrink-0 text-fg/55" />
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
                className="-m-2 shrink-0 rounded-full p-3.5 text-fg/40 transition-colors hover:bg-red-500/15 hover:text-red-400"
              >
                <Unplug className="h-4 w-4" />
              </button>
            )}
          </div>

          {data.connected && (
            <div className="glass p-4">
              <button
                type="button"
                role="switch"
                aria-checked={data.count_watch_kcal}
                onClick={toggleWatchKcal}
                className="flex w-full items-center justify-between gap-3 text-left"
              >
                <span className="flex min-w-0 items-center gap-3">
                  <Watch className="h-4 w-4 shrink-0 text-fg/55" />
                  <span className="text-sm text-fg/80">
                    Add workout calories to daily calorie target
                  </span>
                </span>
                <span
                  className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${
                    data.count_watch_kcal ? 'bg-accent' : 'bg-fg/15'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-fg transition-all ${
                      data.count_watch_kcal ? 'left-[1.125rem]' : 'left-0.5'
                    }`}
                  />
                </span>
              </button>
              <p className="mt-2 text-xs text-fg/45">
                Each workout synced from the health data on your Apple or Android phone will add
                the calories burned to your daily calorie target. This is recommended.
              </p>
            </div>
          )}
        </>
      )}

      <AnimatePresence>
        {detail && detail.key === 'resting_hr' && (
          <HRDetail
            resting={data.today.resting_hr}
            history={history}
            source={syncSourceName}
            onClose={() => setDetail(null)}
          />
        )}
        {detail && detail.key !== 'resting_hr' && (
          <MetricDetail
            def={detail}
            today={data.today[detail.key]}
            week={data.week}
            hourly={hourlyFor(detail, intraday)}
            history={history}
            goals={data.goals}
            onGoals={(goals) => setData((d) => (d ? { ...d, goals } : d))}
            onClose={() => setDetail(null)}
          />
        )}
        {weightOpen && health !== null && (
          <WeightDetail health={health} onClose={() => setWeightOpen(false)} />
        )}
        {workoutOpen && (
          <WorkoutDetail workout={workoutOpen} onClose={() => setWorkoutOpen(null)} />
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
