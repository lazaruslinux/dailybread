import { AnimatePresence } from 'framer-motion'
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Dumbbell,
  Lock,
  Flame,
  Footprints,
  Plus,
  SlidersHorizontal,
  Trash2,
  Watch,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import * as api from '../lib/api'
import { CrumbFloat } from '../components/CrumbFloat'
import {
  FoodPicker,
  Sheet,
  UNIT_LABEL,
  servingIndex,
  unitsForBase,
} from '../components/Recipes'
import {
  PortionSheet,
  SLOTS,
  kcal,
  nowHM,
  trim,
  type Picked,
} from '../components/PortionSheet'
import { Button, Field, FormError } from '../components/ui'

// The Nutrition tab: a personal food diary, Cronometer-shaped. Targets and
// what the day consumed up top, the day's entries grouped by meal below.
// Everything here is one member's own; the backend never shows anyone
// another member's diary. Targets are personal too - each member sets their
// own calorie budget and macro split.

const SLOT_LABEL = Object.fromEntries(SLOTS.map((s) => [s.id, s.label])) as Record<
  api.DiarySlot,
  string
>

function addDays(iso: string, n: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const date = new Date(y, m - 1, d + n)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function dateLabel(iso: string): string {
  const today = api.localDate()
  if (iso === today) return 'Today'
  if (iso === addDays(today, -1)) return 'Yesterday'
  if (iso === addDays(today, 1)) return 'Tomorrow'
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

// "07:30:00" -> "7:30 am"
function fmtTime(t: string | null): string | null {
  if (!t) return null
  const [h, m] = t.split(':').map(Number)
  const ampm = h < 12 ? 'am' : 'pm'
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${ampm}`
}

// How an entry's portion reads on its row: the saved human phrasing when a
// named serving was picked, otherwise the raw amount and unit.
function portionText(e: api.DiaryEntry): string {
  if (e.label) return e.label
  if (e.unit === 'srv') return e.amount === 1 ? '1 serving' : `${trim(e.amount)} servings`
  return `${trim(e.amount)} ${UNIT_LABEL[e.unit] ?? e.unit}`
}

// ---- targets: consumed-vs-target bars --------------------------------------------

const BARS: {
  key: 'calories' | 'protein_g' | 'carbs_g' | 'fat_g'
  label: string
  unit: string
  color: string
}[] = [
  { key: 'calories', label: 'Energy', unit: 'kcal', color: 'bg-accent-bright' },
  { key: 'protein_g', label: 'Protein', unit: 'g', color: 'bg-emerald-400' },
  { key: 'carbs_g', label: 'Carbs', unit: 'g', color: 'bg-sky-400' },
  { key: 'fat_g', label: 'Fat', unit: 'g', color: 'bg-violet-400' },
]

function TargetsCard({ day, onEdit }: { day: api.DiaryDay; onEdit: () => void }) {
  return (
    <section className="glass p-4" data-targets>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-fg/50">Targets</span>
        <button
          onClick={onEdit}
          aria-label="Edit your targets"
          className="-my-3.5 flex items-center gap-1.5 rounded-lg px-2 py-3.5 text-xs font-semibold text-fg/55 transition-colors hover:bg-fg/10 hover:text-fg"
        >
          <SlidersHorizontal className="h-3.5 w-3.5" /> Edit
        </button>
      </div>
      <div className="flex flex-col gap-2.5">
        {BARS.map(({ key, label, unit, color }) => {
          const eaten = day.consumed[key] ?? 0
          const target = day.targets[key]
          const pct = target > 0 ? Math.round((eaten / target) * 100) : 0
          return (
            <div key={key}>
              <div className="mb-1 flex items-baseline justify-between text-[13px]">
                <span className="font-semibold text-fg/80">
                  {label}
                  <span className="ml-1.5 font-normal text-fg/50">
                    {Math.round(eaten * 10) / 10} / {target} {unit}
                  </span>
                </span>
                <span className={`text-xs font-semibold ${pct > 100 ? 'text-gold' : 'text-fg/55'}`}>
                  {pct}%
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-fg/10">
                <div
                  className={`h-full rounded-full ${color}`}
                  style={{ width: `${Math.min(pct, 100)}%` }}
                />
              </div>
              {key === 'calories' && day.targets.exercise_kcal > 0 && (
                <p className="mt-0.5 text-[11px] text-emerald-500">
                  includes +{Math.round(day.targets.exercise_kcal)} kcal earned from workouts
                </p>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

// ---- targets editor ----------------------------------------------------------------

function TargetsSheet({
  targets,
  health,
  onClose,
  onSaved,
}: {
  targets: api.NutritionTargets
  health: api.Health | null
  onClose: () => void
  onSaved: () => void
}) {
  const [mode, setMode] = useState<api.TargetMode>(targets.mode)
  const autoAvailable = health?.computed != null
  const [calories, setCalories] = useState(String(targets.calories))
  const [pcts, setPcts] = useState({
    protein: String(targets.protein_pct),
    carbs: String(targets.carbs_pct),
    fat: String(targets.fat_pct),
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const manualCal = Number(calories) || 0
  const cal = mode === 'auto' && health?.computed ? health.computed.auto_calories : manualCal
  const sum = (Number(pcts.protein) || 0) + (Number(pcts.carbs) || 0) + (Number(pcts.fat) || 0)

  const gramsFor = (pct: string, per: number) =>
    cal > 0 && Number(pct) > 0 ? `${Math.round((cal * Number(pct)) / 100 / per)} g` : '—'

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (sum !== 100) {
      setError('The three percentages should add up to 100.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.setNutritionTargets({
        calories: manualCal || targets.calories,
        protein_pct: Number(pcts.protein) || 0,
        carbs_pct: Number(pcts.carbs) || 0,
        fat_pct: Number(pcts.fat) || 0,
        mode,
      })
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  const rows: { key: keyof typeof pcts; label: string; per: number }[] = [
    { key: 'protein', label: 'Protein', per: 4 },
    { key: 'carbs', label: 'Carbs', per: 4 },
    { key: 'fat', label: 'Fat', per: 9 },
  ]

  return (
    <Sheet onClose={onClose}>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-bold">Your targets</h2>
        <button onClick={onClose} aria-label="Close" className="-m-3 rounded-lg p-3 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <p className="text-xs leading-relaxed text-fg/50">
          Yours alone. Pick a daily calorie budget and how it splits across the three macros.
        </p>
        <div>
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
            Calorie budget
          </span>
          <div className="grid grid-cols-2 gap-1.5" data-target-mode>
            <button
              type="button"
              onClick={() => setMode('manual')}
              className={`rounded-xl border px-3 py-2 text-sm font-semibold transition-colors ${
                mode === 'manual'
                  ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
                  : 'border-fg/10 bg-fg/5 text-fg/55 hover:bg-fg/10'
              }`}
            >
              Manual
            </button>
            <button
              type="button"
              onClick={() => autoAvailable && setMode('auto')}
              disabled={!autoAvailable}
              className={`rounded-xl border px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                mode === 'auto'
                  ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
                  : 'border-fg/10 bg-fg/5 text-fg/55 hover:bg-fg/10'
              }`}
            >
              Auto from profile
            </button>
          </div>
          {!autoAvailable && (
            <p className="mt-1.5 text-xs text-fg/40">
              Auto needs your health profile (and a weigh-in), set up under You.
            </p>
          )}
        </div>
        {mode === 'auto' && health?.computed ? (
          <div className="rounded-xl border border-fg/10 bg-fg/5 px-3.5 py-2.5">
            <p className="text-sm font-semibold text-accent-bright">
              {health.computed.auto_calories.toLocaleString()} kcal/day
            </p>
            <p className="mt-0.5 text-xs text-fg/45">
              Computed from your profile and goal; each weigh-in adjusts it.
            </p>
          </div>
        ) : (
          <div className="w-36">
            <Field
              label="Calories / day"
              inputMode="numeric"
              value={calories}
              onChange={(e) => setCalories(e.target.value.replace(/[^0-9]/g, ''))}
              required
            />
          </div>
        )}
        <div>
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
            Macro split
          </span>
          <div className="flex flex-col gap-2">
            {rows.map(({ key, label, per }) => (
              <div key={key} className="flex items-center gap-3">
                <span className="w-16 text-sm font-semibold text-fg/75">{label}</span>
                <div className="relative w-24">
                  <input
                    aria-label={`${label} percent`}
                    inputMode="numeric"
                    value={pcts[key]}
                    onChange={(e) =>
                      setPcts({ ...pcts, [key]: e.target.value.replace(/[^0-9]/g, '') })
                    }
                    className="field"
                    style={{ paddingRight: '1.9rem' }}
                  />
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-fg/40">
                    %
                  </span>
                </div>
                <span className="text-sm text-fg/45">{gramsFor(pcts[key], per)}</span>
              </div>
            ))}
          </div>
          <p className={`mt-2 text-xs font-semibold ${sum === 100 ? 'text-fg/40' : 'text-gold'}`}>
            Total {sum}%{sum !== 100 && ' (should be 100%)'}
          </p>
        </div>
        <FormError message={error} />
        <Button type="submit" disabled={busy}>
          {busy ? 'Saving' : 'Save targets'}
        </Button>
      </form>
    </Sheet>
  )
}


// ---- add flow: pick a food (search / scan / custom) or one of the recipes -----------

function AddSheet({
  onClose,
  onPicked,
}: {
  onClose: () => void
  onPicked: (p: Picked) => void
}) {
  const [mode, setMode] = useState<'food' | 'recipes'>('food')
  const [recipes, setRecipes] = useState<api.Recipe[] | null>(null)

  useEffect(() => {
    if (mode === 'recipes' && recipes === null)
      api.getRecipes().then(setRecipes).catch(() => setRecipes([]))
  }, [mode, recipes])

  return (
    <Sheet onClose={onClose}>
      <div className="mb-3 grid grid-cols-2 gap-1.5" data-add-mode>
        {(
          [
            { id: 'food', label: 'Foods' },
            { id: 'recipes', label: 'Your recipes' },
          ] as const
        ).map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => setMode(m.id)}
            className={`rounded-xl border px-3 py-2 text-sm font-semibold transition-colors ${
              mode === m.id
                ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
                : 'border-fg/10 bg-fg/5 text-fg/55 hover:bg-fg/10'
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {mode === 'food' ? (
        <FoodPicker onPick={(food) => onPicked({ kind: 'food', food })} onBack={onClose} />
      ) : (
        <div>
          {recipes === null ? (
            <p className="px-2 py-6 text-center text-sm text-fg/45">Loading…</p>
          ) : recipes.length === 0 ? (
            <p className="px-2 py-6 text-center text-sm text-fg/45">
              No recipes yet. Build one on the Kitchen tab and it shows up here.
            </p>
          ) : (
            <div className="flex flex-col">
              {recipes.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => onPicked({ kind: 'recipe', recipe: r })}
                  className="flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2.5 text-left transition-colors hover:bg-fg/10"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <BookOpen className="h-4 w-4 shrink-0 text-accent-bright" />
                    <span className="truncate text-sm font-medium">{r.name}</span>
                  </span>
                  <span className="shrink-0 text-xs text-fg/45">
                    {kcal(r.per_serving.calories)} cal / serving
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </Sheet>
  )
}

// ---- editing an existing entry -------------------------------------------------------

function EditEntrySheet({
  entry,
  onClose,
  onSaved,
}: {
  entry: api.DiaryEntry
  onClose: () => void
  onSaved: () => void
}) {
  const isRecipe = entry.unit === 'srv'
  const servings = entry.food_servings
  const base = entry.food_base_unit
  // A food with named servings and its source still around can be edited by
  // serving, exactly like the add sheet. Otherwise (recipe, deleted food, or a
  // food with no servings) we keep the plain amount + fixed unit.
  const canServe = !isRecipe && entry.food_id != null && servings.length > 0 && base != null

  // Reopen on the portion the entry was logged as. When a serving was used, the
  // amount is stored in the base unit and the serving name lives in the label;
  // match it back so the picker lands on that serving with the right count.
  // Anything else (logged in raw g/mL, or no label) reopens in the raw unit.
  const seed = useMemo(() => {
    if (canServe && entry.label) {
      const want = entry.label.replace(/^[\d.]+\s*/, '').trim().toLowerCase()
      const idx = servings.findIndex(
        (s) => s.name.replace(/^1\s+/, '').trim().toLowerCase() === want,
      )
      if (idx >= 0 && servings[idx].grams > 0) {
        return { unit: `serving:${idx}`, amount: trim(entry.amount / servings[idx].grams) }
      }
    }
    return { unit: entry.unit, amount: trim(entry.amount) }
    // Seed once from the entry as opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const [amount, setAmount] = useState(seed.amount)
  const [unit, setUnit] = useState(seed.unit)
  const [slot, setSlot] = useState<api.DiarySlot>(entry.slot)
  const [time, setTime] = useState(entry.time_of_day ? entry.time_of_day.slice(0, 5) : '')
  const [armed, setArmed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const amt = Number(amount) || 0

  // Show what a chosen serving resolves to in the base unit, e.g. "= 160 g".
  const resolved = useMemo(() => {
    if (base == null) return null
    const si = servingIndex(unit)
    if (si == null || !servings[si]) return null
    return `${trim(amt * servings[si].grams)} ${base === 'ml' ? 'mL' : 'g'}`
  }, [amt, unit, base, servings])

  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const patch: api.DiaryEntryPatch = { slot, time_of_day: time || null }
      if (canServe) {
        // The unit selector is in play. A serving pick converts to the base
        // unit for storage (the server recomputes nutrition) and its phrasing
        // rides in the label; a raw unit clears the label.
        const si = servingIndex(unit)
        const s = si != null ? servings[si] : null
        patch.amount = s ? amt * s.grams : amt
        patch.unit = (s && base ? base : unit) as api.AmountUnit
        patch.label = s ? `${trim(amt)} ${s.name.replace(/^1\s+/, '')}` : null
      } else {
        // Recipe entry, deleted food, or a food with no servings: the unit is
        // fixed and not editable here, so never send it (a recipe's "srv" is
        // not an AmountUnit). Drop a now-stale serving label only if the
        // portion actually changed.
        patch.amount = amt
        if (amt !== entry.amount) patch.label = null
      }
      await api.updateDiaryEntry(entry.id, patch)
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  async function remove() {
    if (!armed) {
      setArmed(true)
      return
    }
    setBusy(true)
    try {
      await api.deleteDiaryEntry(entry.id)
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <Sheet onClose={onClose}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <h2 className="min-w-0 text-lg font-bold leading-snug">{entry.name}</h2>
        <button onClick={onClose} aria-label="Close" className="shrink-0 -m-3 rounded-lg p-3 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>

      <form onSubmit={save} className="flex flex-col gap-4">
        <div className="flex items-end gap-2">
          <div className="w-20 shrink-0">
            <Field
              label="Amount"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ''))}
              required
            />
          </div>
          {canServe ? (
            <label className="block min-w-0 flex-1">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
                Unit
              </span>
              <select value={unit} onChange={(e) => setUnit(e.target.value)} className="field">
                <optgroup label="Servings">
                  {servings.map((s, i) => (
                    <option key={`s${i}`} value={`serving:${i}`}>
                      {s.name}
                    </option>
                  ))}
                </optgroup>
                <optgroup label={base === 'ml' ? 'Volume' : 'Weight'}>
                  {unitsForBase(base!).map((u) => (
                    <option key={u} value={u}>
                      {UNIT_LABEL[u] ?? u}
                    </option>
                  ))}
                </optgroup>
              </select>
            </label>
          ) : (
            <span className="field flex flex-1 items-center text-fg/70">
              {isRecipe ? 'servings' : (UNIT_LABEL[entry.unit] ?? entry.unit)}
            </span>
          )}
        </div>
        {resolved && <p className="-mt-2 text-xs text-fg/45">= {resolved}</p>}

        <div>
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
            Meal
          </span>
          <div className="grid grid-cols-4 gap-1.5">
            {SLOTS.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setSlot(s.id)}
                className={`rounded-xl border px-1 py-2 text-xs font-semibold transition-colors ${
                  slot === s.id
                    ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
                    : 'border-fg/10 bg-fg/5 text-fg/55 hover:bg-fg/10'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        <div className="w-36">
          <Field
            label="Time"
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            onClear={() => setTime('')}
          />
        </div>

        <FormError message={error} />
        <Button type="submit" disabled={busy || amt <= 0}>
          {busy ? 'Saving' : 'Save changes'}
        </Button>
        <button
          type="button"
          onClick={remove}
          disabled={busy}
          className={`flex items-center justify-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-semibold transition-colors disabled:opacity-50 ${
            armed
              ? 'border-gold/50 bg-gold/15 text-gold'
              : 'border-fg/10 bg-fg/5 text-fg/60 hover:bg-fg/10'
          }`}
        >
          <Trash2 className="h-4 w-4" />
          {armed ? 'Tap again to remove' : 'Remove from diary'}
        </button>
      </form>
    </Sheet>
  )
}

// ---- exercise: MET mirror for the live preview --------------------------------------

const EXERCISE_META: {
  id: api.ExerciseActivity
  label: string
  mets: Record<api.ExerciseEffort, number>
}[] = [
  { id: 'running', label: 'Running', mets: { light: 4.8, moderate: 6.3, vigorous: 9.8 } },
  { id: 'walking', label: 'Walking', mets: { light: 2.8, moderate: 3.5, vigorous: 5.0 } },
  { id: 'weightlifting', label: 'Weightlifting', mets: { light: 3.0, moderate: 3.5, vigorous: 6.0 } },
]

const EFFORTS: { id: api.ExerciseEffort; label: string; hint: string }[] = [
  { id: 'light', label: 'Light', hint: 'Easy pace; you could chat the whole time' },
  { id: 'moderate', label: 'Moderate', hint: 'Faster heart rate and breathing, not out of breath' },
  { id: 'vigorous', label: 'Vigorous', hint: 'Hard effort; talking is difficult' },
]

const EFFORT_LABEL = Object.fromEntries(EFFORTS.map((e) => [e.id, e.label])) as Record<
  api.ExerciseEffort,
  string
>

function ExerciseSheet({
  entry,
  health,
  date,
  onClose,
  onSaved,
}: {
  entry: api.ExerciseEntry | null // null = logging a new one
  health: api.Health | null
  date: string
  onClose: () => void
  onSaved: () => void
}) {
  const creating = entry === null
  const [activity, setActivity] = useState<api.ExerciseActivity>(entry?.activity ?? 'running')
  const [effort, setEffort] = useState<api.ExerciseEffort>(entry?.effort ?? 'moderate')
  const [minutes, setMinutes] = useState(entry ? trim(entry.minutes) : '30')
  const [time, setTime] = useState(entry?.time_of_day ? entry.time_of_day.slice(0, 5) : nowHM())
  const [armed, setArmed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const weightKg = health?.latest_weight?.weight_kg ?? null
  const mins = Number(minutes) || 0
  const met = EXERCISE_META.find((a) => a.id === activity)!.mets[effort]
  const preview = weightKg && mins > 0 ? Math.round(met * weightKg * (mins / 60) * 10) / 10 : null

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (creating) {
        await api.logExercise({
          date_for: date,
          activity,
          effort,
          minutes: mins,
          time_of_day: time || null,
        })
      } else {
        await api.updateExercise(entry.id, { minutes: mins, effort, time_of_day: time || null })
      }
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  async function remove() {
    if (!armed) {
      setArmed(true)
      return
    }
    setBusy(true)
    try {
      await api.deleteExercise(entry!.id)
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  const chip = (active: boolean) =>
    `rounded-xl border px-3 py-2 text-sm font-semibold transition-colors ${
      active
        ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
        : 'border-fg/10 bg-fg/5 text-fg/55 hover:bg-fg/10'
    }`

  return (
    <Sheet onClose={onClose}>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-bold">
          <Footprints className="h-5 w-5 text-accent-bright" />
          {creating ? 'Add manual exercise' : entry.label}
        </h2>
        <button onClick={onClose} aria-label="Close" className="-m-3 rounded-lg p-3 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>

      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {creating && (
          <div className="grid grid-cols-2 gap-1.5">
            {EXERCISE_META.map((a) => (
              <button key={a.id} type="button" onClick={() => setActivity(a.id)} className={chip(activity === a.id)}>
                {a.label}
              </button>
            ))}
          </div>
        )}

        <div>
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
            Effort
          </span>
          <div className="flex flex-col gap-1.5">
            {EFFORTS.map((ef) => (
              <button
                key={ef.id}
                type="button"
                onClick={() => setEffort(ef.id)}
                className={`${chip(effort === ef.id)} text-left`}
              >
                {ef.label}
                <span className="ml-2 text-xs font-normal text-fg/45">{ef.hint}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-end gap-2">
          <div className="relative w-28">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              Duration
            </span>
            <div className="relative">
              <input
                aria-label="Duration minutes"
                inputMode="numeric"
                value={minutes}
                onChange={(e) => setMinutes(e.target.value.replace(/[^0-9]/g, ''))}
                className="field"
                style={{ paddingRight: '2.4rem' }}
                required
              />
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-fg/40">
                min
              </span>
            </div>
          </div>
          <div className="w-36">
            <Field label="Time" type="time" value={time} onChange={(e) => setTime(e.target.value)} onClear={() => setTime('')} />
          </div>
        </div>

        {weightKg === null ? (
          <p className="rounded-xl border border-fg/10 bg-fg/5 px-3.5 py-2.5 text-xs leading-relaxed text-fg/50">
            Log a weight in your health profile first; the burn is computed from it.
          </p>
        ) : preview !== null ? (
          <div className="rounded-xl border border-fg/10 bg-fg/5 px-3.5 py-2.5">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-accent-bright">
              <Flame className="h-4 w-4" /> ≈ {preview.toLocaleString()} kcal burned
            </p>
            <p className="mt-0.5 text-xs text-fg/45">
              Based on your weight of {Math.round((weightKg * 2.20462) * 10) / 10} lb. Added onto
              today's energy target.
            </p>
          </div>
        ) : null}

        <FormError message={error} />
        <Button type="submit" disabled={busy || mins <= 0 || weightKg === null}>
          {busy ? 'Saving' : creating ? 'Add to diary' : 'Save changes'}
        </Button>
        {!creating && (
          <button
            type="button"
            onClick={remove}
            disabled={busy}
            className={`flex items-center justify-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-semibold transition-colors disabled:opacity-50 ${
              armed ? 'border-gold/50 bg-gold/15 text-gold' : 'border-fg/10 bg-fg/5 text-fg/60 hover:bg-fg/10'
            }`}
          >
            <Trash2 className="h-4 w-4" />
            {armed ? 'Tap again to remove' : 'Remove from diary'}
          </button>
        )}
      </form>
    </Sheet>
  )
}

// A synced workout's line under Exercise. Deliberately not a button: these
// cards belong to the health data and are display-only here - no taps, no
// edits, no delete. The kcal chip only shows when the opt-in counts it.
function SyncedWorkoutRow({ workout, counted }: { workout: api.DiaryWorkout; counted: boolean }) {
  const started = new Date(workout.started_at)
  const when = fmtTime(`${started.getHours()}:${started.getMinutes()}`)
  const sub = [
    when,
    workout.duration_s ? `${Math.round(workout.duration_s / 60)} min` : null,
    `Synced from ${workout.source === 'android' ? 'Health Connect' : 'Apple Health'}`,
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <div className="-mx-1.5 flex items-center justify-between gap-3 rounded-lg px-1.5 py-2">
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 truncate text-sm font-medium">
          <Watch className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
          {workout.activity}
        </span>
        <span className="block truncate text-xs text-fg/45">{sub}</span>
      </span>
      {counted && workout.kcal != null && workout.kcal > 0 && (
        <span className="shrink-0 text-sm font-semibold text-emerald-500">
          +{Math.round(workout.kcal)}
          <span className="ml-1 text-[10px] font-normal opacity-70">kcal</span>
        </span>
      )}
    </div>
  )
}

function ExerciseCard({
  exercise,
  workouts,
  watchCounted,
  burned,
  onAdd,
  onEdit,
}: {
  exercise: api.ExerciseEntry[]
  workouts: api.DiaryWorkout[]
  // Whether the member's opt-in is counting synced calories today.
  watchCounted: boolean
  burned: number
  onAdd: () => void
  onEdit: (e: api.ExerciseEntry) => void
}) {
  const empty = exercise.length === 0 && workouts.length === 0
  return (
    <section className="glass p-4" data-exercise>
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-fg/90">Exercise</h3>
        <button
          onClick={onAdd}
          className="-my-1.5 flex min-h-11 shrink-0 items-center gap-1 rounded-lg px-2 text-xs font-semibold text-accent-bright transition-colors hover:bg-accent-bright/15"
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2.5} /> Add manual exercise
        </button>
      </div>
      {burned > 0 && (
        <p className="mb-1 text-xs font-semibold text-emerald-500">
          +{Math.round(burned)} kcal earned from workouts
        </p>
      )}

      {empty ? (
        <button
          onClick={onAdd}
          className="mt-1 w-full rounded-xl border border-dashed border-fg/20 px-3 py-2.5 text-left text-sm text-fg/40 transition-colors hover:border-accent-bright/40 hover:text-fg/60"
        >
          + Add manual exercise
        </button>
      ) : (
        <div className="flex flex-col">
          {workouts.map((w, i) => (
            <SyncedWorkoutRow key={`${w.started_at}-${i}`} workout={w} counted={watchCounted} />
          ))}
          {exercise.map((e) => {
            const sub = [fmtTime(e.time_of_day), `${trim(e.minutes)} min`, EFFORT_LABEL[e.effort]]
              .filter(Boolean)
              .join(' · ')
            return (
              <button
                key={e.id}
                onClick={() => onEdit(e)}
                className="-mx-1.5 flex items-center justify-between gap-3 rounded-lg px-1.5 py-2 text-left transition-colors hover:bg-fg/10"
              >
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 truncate text-sm font-medium">
                    {e.activity === 'weightlifting' ? (
                      <Dumbbell className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                    ) : (
                      <Footprints className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                    )}
                    {e.label}
                  </span>
                  {sub && <span className="block truncate text-xs text-fg/45">{sub}</span>}
                </span>
                <span className="shrink-0 text-sm font-semibold text-emerald-500">
                  +{Math.round(e.kcal)}
                  <span className="ml-1 text-[10px] font-normal opacity-70">kcal</span>
                </span>
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}

// ---- one meal group --------------------------------------------------------------

// The day's sign-off: lock in the tracking (+2 breadcrumbs the first time a
// date is locked) and the diary goes read-only until unlocked. Unlock, fix,
// re-lock all you like; the crumbs paid once.
function LockCard({ day, onChanged }: { day: api.DiaryDay; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [float, setFloat] = useState<{ amount: number; key: number } | null>(null)

  if (day.entries.length === 0 && !day.locked) return null

  async function flip() {
    setBusy(true)
    try {
      if (day.locked) {
        await api.unlockDiaryDay(day.date)
      } else {
        const res = await api.lockDiaryDay(day.date)
        if (res.crumbs_awarded > 0) {
          setFloat({ amount: res.crumbs_awarded, key: Date.now() })
          window.dispatchEvent(new Event('db:profile-changed'))
          await new Promise((r) => setTimeout(r, 1100)) // let the +2 land
        }
      }
      onChanged()
    } catch {
      // the tap didn't stick; the next one tries again
    } finally {
      setBusy(false)
    }
  }

  if (day.locked) {
    return (
      <div className="glass flex items-center gap-2.5 px-4 py-3" data-lock-card>
        <Lock className="h-4 w-4 shrink-0 text-gold" strokeWidth={2.5} />
        <span className="min-w-0 flex-1 text-sm font-medium text-fg/80">
          Day locked in
        </span>
        <button
          type="button"
          disabled={busy}
          onClick={flip}
          className="shrink-0 text-xs font-semibold text-accent-bright"
        >
          Unlock to edit
        </button>
      </div>
    )
  }
  return (
    <div className="relative" data-lock-card>
      {float && <CrumbFloat key={float.key} amount={float.amount} />}
      <button
        type="button"
        disabled={busy}
        onClick={flip}
        className="glass flex w-full items-center gap-2.5 px-4 py-3 text-left transition-colors hover:bg-fg/5"
      >
        <Lock className="h-4 w-4 shrink-0 text-gold" strokeWidth={2.5} />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-fg/85">Lock in my day</span>
          <span className="block text-xs text-fg/45">
            Done tracking? Locking in earns breadcrumbs
          </span>
        </span>
      </button>
    </div>
  )
}


function SlotCard({
  slot,
  entries,
  locked,
  onAdd,
  onEdit,
}: {
  slot: api.DiarySlot
  entries: api.DiaryEntry[]
  locked: boolean
  onAdd: () => void
  onEdit: (e: api.DiaryEntry) => void
}) {
  const total = entries.reduce((sum, e) => sum + (e.calories ?? 0), 0)

  return (
    <section className="glass p-4" data-slot={slot}>
      <div className="mb-1 flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <h3 className="font-semibold text-fg/90">{SLOT_LABEL[slot]}</h3>
          {entries.length > 0 && (
            <span className="text-xs text-fg/45">{Math.round(total)} kcal</span>
          )}
        </div>
        {!locked && (
          <button
            onClick={onAdd}
            aria-label={`Add to ${SLOT_LABEL[slot]}`}
            className="-m-3.5 rounded-lg p-3.5 text-accent-bright transition-colors hover:bg-accent-bright/15"
          >
            <Plus className="h-4.5 w-4.5" strokeWidth={2.5} />
          </button>
        )}
      </div>

      {entries.length === 0 ? (
        locked ? (
          <p className="mt-1 px-1 text-sm text-fg/35">Nothing logged.</p>
        ) : (
          <button
            onClick={onAdd}
            className="mt-1 w-full rounded-xl border border-dashed border-fg/20 px-3 py-2.5 text-left text-sm text-fg/40 transition-colors hover:border-accent-bright/40 hover:text-fg/60"
          >
            + Add {slot === 'snack' ? 'a snack' : slot}
          </button>
        )
      ) : (
        <div className="flex flex-col">
          {entries.map((e) => {
            const sub = [fmtTime(e.time_of_day), portionText(e)].filter(Boolean).join(' · ')
            return (
              <button
                key={e.id}
                disabled={locked}
                onClick={() => onEdit(e)}
                className="-mx-1.5 flex items-center justify-between gap-3 rounded-lg px-1.5 py-2 text-left transition-colors hover:bg-fg/10"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {e.brand ? `${e.brand}, ${e.name}` : e.name}
                  </span>
                  {sub && <span className="block truncate text-xs text-fg/45">{sub}</span>}
                </span>
                <span className="shrink-0 text-sm font-semibold text-fg/70">
                  {kcal(e.calories)}
                  <span className="ml-1 text-[10px] font-normal text-fg/40">kcal</span>
                </span>
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}

// ---- the tab ---------------------------------------------------------------------

// Kid mode, second layer: App never routes a minor here and the server 403s
// the APIs anyway, but if either slips this renders nothing rather than a
// tab full of failed requests.
export function Nutrition() {
  const { user } = useAuth()
  if (user?.is_minor) return null
  return <NutritionTab />
}

function NutritionTab() {
  const [date, setDate] = useState(api.localDate())
  const [day, setDay] = useState<api.DiaryDay | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [adding, setAdding] = useState<api.DiarySlot | null>(null)
  const [picked, setPicked] = useState<Picked | null>(null)
  // Bumped every time an add flow opens. Keying the sheets on it stops
  // AnimatePresence from reviving a still-exiting sheet (with its stale
  // amount/busy state) when the next one opens under the same key.
  const [flow, setFlow] = useState(0)
  const [editing, setEditing] = useState<api.DiaryEntry | null>(null)
  const [editingTargets, setEditingTargets] = useState(false)
  // Kept for the Targets card's auto-calorie mode and the exercise burn
  // calc; the health calculator card itself lives only under You now.
  const [health, setHealth] = useState<api.Health | null>(null)
  // null = closed; {entry:null} = logging new; {entry:e} = editing.
  const [exercising, setExercising] = useState<{ entry: api.ExerciseEntry | null } | null>(null)

  const refresh = useCallback(async () => {
    try {
      setDay(await api.getDiary(date))
      setLoadError(null)
    } catch (err) {
      setLoadError(err instanceof api.ApiError ? err.message : 'Could not load the diary.')
    }
    // Health is separate so a failure here never blanks the diary.
    api.getHealthProfile().then(setHealth).catch(() => {})
  }, [date])

  useEffect(() => {
    refresh()
  }, [refresh])

  const bySlot = useMemo(() => {
    const groups = { breakfast: [], lunch: [], dinner: [], snack: [] } as Record<
      api.DiarySlot,
      api.DiaryEntry[]
    >
    day?.entries.forEach((e) => groups[e.slot].push(e))
    return groups
  }, [day])

  const closeAll = () => {
    setAdding(null)
    setPicked(null)
    setEditing(null)
    setEditingTargets(false)
    setExercising(null)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between" data-date-nav>
        <button
          onClick={() => setDate(addDays(date, -1))}
          aria-label="Previous day"
          className="rounded-lg p-2 text-fg/55 transition-colors hover:bg-fg/10 hover:text-fg"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <button
          onClick={() => setDate(api.localDate())}
          className="text-[15px] font-bold tracking-tight"
        >
          {dateLabel(date)}
        </button>
        <button
          onClick={() => setDate(addDays(date, 1))}
          aria-label="Next day"
          className="rounded-lg p-2 text-fg/55 transition-colors hover:bg-fg/10 hover:text-fg"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>

      <FormError message={loadError} />

      {day === null && !loadError ? (
        <p className="py-10 text-center text-sm text-fg/40">Loading</p>
      ) : day !== null ? (
        <>
          <TargetsCard day={day} onEdit={() => setEditingTargets(true)} />
          <LockCard day={day} onChanged={refresh} />
          {/* The health calculator (body, plan, weigh-ins) lives only under
              You now; Nutrition keeps the day's food and the Targets card. */}
          {SLOTS.map((s) => (
            <SlotCard
              key={s.id}
              slot={s.id}
              entries={bySlot[s.id]}
              locked={day.locked}
              onAdd={() => {
                setFlow((f) => f + 1)
                setAdding(s.id)
              }}
              onEdit={setEditing}
            />
          ))}
          <ExerciseCard
            exercise={day.exercise}
            workouts={day.workouts}
            watchCounted={day.watch_kcal !== null}
            burned={day.burned}
            onAdd={() => setExercising({ entry: null })}
            onEdit={(e) => setExercising({ entry: e })}
          />
        </>
      ) : null}

      <AnimatePresence>
        {adding !== null && picked === null && (
          <AddSheet key={`add-${flow}`} onClose={() => setAdding(null)} onPicked={setPicked} />
        )}
        {adding !== null && picked !== null && (
          <PortionSheet
            key={`portion-${flow}`}
            pick={picked}
            date={date}
            slot={adding}
            onClose={() => setPicked(null)}
            onSaved={() => {
              closeAll()
              refresh()
            }}
          />
        )}
        {editing && (
          <EditEntrySheet
            // Remount per entry so the once-only serving seed is always fresh.
            key={editing.id}
            entry={editing}
            onClose={() => setEditing(null)}
            onSaved={() => {
              closeAll()
              refresh()
            }}
          />
        )}
        {editingTargets && day && (
          <TargetsSheet
            key="targets"
            targets={day.targets}
            health={health}
            onClose={() => setEditingTargets(false)}
            onSaved={() => {
              closeAll()
              refresh()
            }}
          />
        )}
        {exercising && (
          <ExerciseSheet
            key={exercising.entry ? `ex-${exercising.entry.id}` : `ex-new-${flow}`}
            entry={exercising.entry}
            health={health}
            date={date}
            onClose={() => setExercising(null)}
            onSaved={() => {
              closeAll()
              refresh()
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
