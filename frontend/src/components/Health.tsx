import { HeartPulse, Scale, Target, X } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import * as api from '../lib/api'
import { Button, Field, FormError } from './ui'
import { Sheet } from './Recipes'

// The health layer: an OPTIONAL profile (birthdate, sex, height, activity),
// a weight log, and a goal that turns into a computed daily calorie target.
// Setup lives here on the Nutrition tab - deliberately not a sign-in gate;
// the board half of the app never asks anyone their body fat percentage.

const LB_PER_KG = 2.20462

const lb = (kg: number) => kg * LB_PER_KG
const kg = (pounds: number) => pounds / LB_PER_KG
const fmtLb = (kgV: number) => `${Math.round(lb(kgV) * 10) / 10} lb`

function cmToFtIn(cm: number): { ft: string; inch: string } {
  const total = cm / 2.54
  let ft = Math.floor(total / 12)
  let inch = Math.round(total % 12)
  if (inch === 12) {
    ft += 1
    inch = 0
  }
  return { ft: String(ft), inch: String(inch) }
}

// Hints describe the shape of a normal day, not workouts - exercise is logged
// separately and added on top, so counting it here would double-dip.
const ACTIVITY: { id: api.ActivityLevel; label: string; hint: string; factor: number }[] = [
  {
    id: 'sedentary',
    label: 'Sedentary',
    hint: 'Office job, little or no physical activity during the day',
    factor: 1.2,
  },
  { id: 'light', label: 'Lightly active', hint: 'On your feet part of the day', factor: 1.375 },
  {
    id: 'moderate',
    label: 'Moderately active',
    hint: 'Moving around for much of the day',
    factor: 1.5,
  },
  { id: 'active', label: 'Active', hint: 'On your feet nearly all day', factor: 1.725 },
  {
    id: 'very_active',
    label: 'Very active',
    hint: 'Hard physical work most of the day',
    factor: 1.9,
  },
]

const GOALS: { id: api.GoalType; label: string }[] = [
  { id: 'lose', label: 'Lose' },
  { id: 'maintain', label: 'Maintain' },
  { id: 'gain', label: 'Gain' },
]

const RATES = [0.5, 1, 1.5, 2]

// Client-side mirror of app.health.compute, for the live preview while the
// sheet is being filled in. The server's number is authoritative on save.
function previewCalories(f: {
  birthdate: string
  sex: api.Sex | null
  ft: string
  inch: string
  weightLb: string
  bodyFat: string
  activity: api.ActivityLevel | null
  goal: api.GoalType
  rate: number
}): number | null {
  const heightCm = (Number(f.ft) * 12 + Number(f.inch)) * 2.54
  const weightKg = kg(Number(f.weightLb))
  if (!f.birthdate || !f.sex || !f.activity || !heightCm || !weightKg) return null
  const bd = new Date(f.birthdate)
  const now = new Date()
  let age = now.getFullYear() - bd.getFullYear()
  if (now.getMonth() < bd.getMonth() || (now.getMonth() === bd.getMonth() && now.getDate() < bd.getDate())) age -= 1
  if (age <= 0 || age > 120) return null

  const bf = Number(f.bodyFat)
  const bmr = bf > 0
    ? 370 + 21.6 * (weightKg * (1 - bf / 100))
    : 10 * weightKg + 6.25 * heightCm - 5 * age + (f.sex === 'male' ? 5 : -161)
  const tdee = bmr * (ACTIVITY.find((a) => a.id === f.activity)?.factor ?? 1.5)
  const shift = f.rate * 500
  const raw = f.goal === 'lose' ? tdee - shift : f.goal === 'gain' ? tdee + shift : tdee
  const floor = f.sex === 'female' ? 1200 : 1500
  return Math.max(Math.round(raw / 10) * 10, floor)
}

// ---- the full profile sheet -----------------------------------------------------

export function HealthSheet({
  health,
  onClose,
  onSaved,
}: {
  health: api.Health
  onClose: () => void
  onSaved: () => void
}) {
  const { user } = useAuth()
  const isChild = user?.role === 'child'
  const p = health.profile
  const initFtIn = p?.height_cm ? cmToFtIn(p.height_cm) : { ft: '', inch: '' }

  const [birthdate, setBirthdate] = useState(p?.birthdate ?? '')
  const [sex, setSex] = useState<api.Sex | null>(p?.sex ?? null)
  const [ft, setFt] = useState(initFtIn.ft)
  const [inch, setInch] = useState(initFtIn.inch)
  const [activity, setActivity] = useState<api.ActivityLevel | null>(p?.activity_level ?? null)
  const [weightLb, setWeightLb] = useState(
    health.latest_weight ? String(Math.round(lb(health.latest_weight.weight_kg) * 10) / 10) : '',
  )
  const [bodyFat, setBodyFat] = useState(
    health.latest_weight?.body_fat_pct ? String(health.latest_weight.body_fat_pct) : '',
  )
  const [goal, setGoal] = useState<api.GoalType>(p?.goal ?? 'maintain')
  const [rate, setRate] = useState<number>(p?.rate_lbs_per_week ?? 1)
  const [goalWeightLb, setGoalWeightLb] = useState(
    p?.goal_weight_kg ? String(Math.round(lb(p.goal_weight_kg) * 10) / 10) : '',
  )
  const [goalBodyFat, setGoalBodyFat] = useState(
    p?.goal_body_fat_pct ? String(p.goal_body_fat_pct) : '',
  )
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // The 2 lb/week rate requires reading the warning and saying so.
  const [ackRate, setAckRate] = useState(false)

  const preview = useMemo(
    () => previewCalories({ birthdate, sex, ft, inch, weightLb, bodyFat, activity, goal, rate }),
    [birthdate, sex, ft, inch, weightLb, bodyFat, activity, goal, rate],
  )

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const heightCm = (Number(ft) * 12 + Number(inch)) * 2.54
      await api.updateHealthProfile({
        birthdate: birthdate || null,
        sex,
        height_cm: heightCm > 0 ? Math.round(heightCm * 10) / 10 : null,
        activity_level: activity,
      })
      if (Number(weightLb) > 0) {
        await api.logWeight(
          api.localDate(),
          Math.round(kg(Number(weightLb)) * 100) / 100,
          Number(bodyFat) > 0 ? Number(bodyFat) : null,
        )
      }
      if (!isChild) {
        await api.setHealthGoal({
          goal,
          rate_lbs_per_week: goal === 'maintain' ? null : rate,
          goal_weight_kg:
            Number(goalWeightLb) > 0 ? Math.round(kg(Number(goalWeightLb)) * 100) / 100 : null,
          goal_body_fat_pct: Number(goalBodyFat) > 0 ? Number(goalBodyFat) : null,
        })
      }
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
          <HeartPulse className="h-5 w-5 text-accent-bright" /> Health profile
        </h2>
        <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>

      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <p className="text-xs leading-relaxed text-fg/50">
          Fill in this form as accurately as possible, and dailybread will automatically
          calculate a daily calorie target for you, with default macro-nutrient goals.
        </p>
        <p className="-mt-2 text-xs leading-relaxed text-fg/50">
          All optional, and stored privately: no one else can see your weight, health, or food
          log, not even an admin. Child accounts don't have a Nutrition area at all.
        </p>

        <div className="w-44">
          <Field
            label="Birthdate"
            type="date"
            value={birthdate}
            onChange={(e) => setBirthdate(e.target.value)}
          />
        </div>

        <div>
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
            Gender
          </span>
          <div className="grid grid-cols-2 gap-1.5">
            {(['male', 'female'] as const).map((s) => (
              <button key={s} type="button" onClick={() => setSex(s)} className={chip(sex === s)}>
                {s === 'male' ? 'Male' : 'Female'}
              </button>
            ))}
          </div>
        </div>

        <div>
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
            Height
          </span>
          <div className="flex items-center gap-2">
            <div className="relative w-20">
              <input aria-label="Height feet" inputMode="numeric" value={ft}
                onChange={(e) => setFt(e.target.value.replace(/[^0-9]/g, ''))}
                className="field" style={{ paddingRight: '1.7rem' }} />
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-fg/40">ft</span>
            </div>
            <div className="relative w-20">
              <input aria-label="Height inches" inputMode="numeric" value={inch}
                onChange={(e) => setInch(e.target.value.replace(/[^0-9]/g, ''))}
                className="field" style={{ paddingRight: '1.7rem' }} />
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-fg/40">in</span>
            </div>
          </div>
        </div>

        <div>
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
            Activity level
          </span>
          <p className="mb-1.5 text-xs leading-relaxed text-fg/40">
            Pick what describes your everyday life, not including your exercise. Log your
            exercise in addition to food and it will be added to the day's target calories!
          </p>
          <div className="flex flex-col gap-1.5">
            {ACTIVITY.map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => setActivity(a.id)}
                className={`${chip(activity === a.id)} text-left`}
              >
                {a.label}
                <span className="ml-2 text-xs font-normal text-fg/45">{a.hint}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-end gap-2">
          <div className="relative w-28">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              Weight
            </span>
            <div className="relative">
              <input aria-label="Weight pounds" inputMode="decimal" value={weightLb}
                onChange={(e) => setWeightLb(e.target.value.replace(/[^0-9.]/g, ''))}
                className="field" style={{ paddingRight: '1.9rem' }} />
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-fg/40">lb</span>
            </div>
          </div>
          <div className="relative w-28">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              Body fat
            </span>
            <div className="relative">
              <input aria-label="Body fat percent" inputMode="decimal" value={bodyFat}
                onChange={(e) => setBodyFat(e.target.value.replace(/[^0-9.]/g, ''))}
                placeholder="optional" className="field" style={{ paddingRight: '1.7rem' }} />
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-fg/40">%</span>
            </div>
          </div>
        </div>
        {Number(bodyFat) > 0 && (
          <p className="-mt-2 text-xs text-fg/40">
            With body fat known, the estimate uses your lean mass - more accurate.
          </p>
        )}

        {isChild ? (
          <p className="rounded-xl border border-fg/10 bg-fg/5 px-3.5 py-2.5 text-xs leading-relaxed text-fg/50">
            Weight goals for child accounts are set by a parent.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <div>
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
                Goal
              </span>
              <div className="grid grid-cols-3 gap-1.5">
                {GOALS.map((g) => (
                  <button key={g.id} type="button" onClick={() => setGoal(g.id)} className={chip(goal === g.id)}>
                    {g.label}
                  </button>
                ))}
              </div>
            </div>
            {goal !== 'maintain' && (
              <>
                <div>
                  <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
                    {goal === 'lose' ? 'Lose' : 'Gain'} per week
                  </span>
                  <div className="grid grid-cols-4 gap-1.5">
                    {RATES.map((r) => (
                      <button
                        key={r}
                        type="button"
                        onClick={() => {
                          setRate(r)
                          setAckRate(false)
                        }}
                        className={chip(rate === r)}
                      >
                        {r} lb
                      </button>
                    ))}
                  </div>
                  {rate === 1.5 && (
                    <p className="mt-2 rounded-xl border border-fg/10 bg-fg/5 px-3.5 py-2.5 text-xs leading-relaxed text-fg/55" data-rate-note>
                      This is a large gap between what you eat and what you burn. It works for
                      some people, but many find it hard to keep up. Watch your energy and
                      recovery, and slow the pace if it stops feeling right.
                    </p>
                  )}
                  {rate === 2 && (
                    <div className="mt-2 rounded-xl border border-gold/40 bg-gold/10 px-3.5 py-2.5" data-rate-warning>
                      <p className="text-xs leading-relaxed text-fg/70">
                        This is a very large gap between intake and burn. At this pace many
                        people notice low energy, more hunger, and slower recovery, and the
                        computed calorie target can sit near the safe minimum. A slower rate is
                        easier to sustain.
                      </p>
                      <label className="mt-2.5 flex cursor-pointer items-start gap-2.5 text-xs font-semibold text-fg/75">
                        <input
                          type="checkbox"
                          checked={ackRate}
                          onChange={(e) => setAckRate(e.target.checked)}
                          className="mt-0.5 h-4 w-4 accent-accent-bright"
                        />
                        I've read this and want the 2 lb/week pace anyway.
                      </label>
                    </div>
                  )}
                </div>
                <div>
                  <div className="flex items-end gap-2">
                    <div className="relative w-32">
                      <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
                        Goal weight
                      </span>
                      <div className="relative">
                        <input aria-label="Goal weight pounds" inputMode="decimal" value={goalWeightLb}
                          onChange={(e) => setGoalWeightLb(e.target.value.replace(/[^0-9.]/g, ''))}
                          placeholder="optional" className="field" style={{ paddingRight: '1.9rem' }} />
                        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-fg/40">lb</span>
                      </div>
                    </div>
                    <div className="relative w-32">
                      <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
                        Goal body fat
                      </span>
                      <div className="relative">
                        <input aria-label="Goal body fat percent" inputMode="decimal" value={goalBodyFat}
                          onChange={(e) => setGoalBodyFat(e.target.value.replace(/[^0-9.]/g, ''))}
                          placeholder="optional" className="field" style={{ paddingRight: '1.7rem' }} />
                        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-fg/40">%</span>
                      </div>
                    </div>
                  </div>
                  <p className="mt-1.5 text-xs text-fg/40">
                    At your goal weight the plan flips to maintaining automatically.
                  </p>
                </div>
              </>
            )}
          </div>
        )}

        {preview !== null && (
          <div className="rounded-xl border border-fg/10 bg-fg/5 px-3.5 py-2.5">
            <p className="text-sm font-semibold text-accent-bright">
              ≈ {preview.toLocaleString()} kcal/day
              {!isChild && goal !== 'maintain' && ` to ${goal} ${rate} lb/week`}
            </p>
          </div>
        )}

        <FormError message={error} />
        <Button type="submit" disabled={busy || (!isChild && goal !== 'maintain' && rate === 2 && !ackRate)}>
          {busy ? 'Saving' : 'Save health profile'}
        </Button>
        <p className="text-center text-[10px] leading-relaxed text-fg/30">
          Estimates from standard formulas (Mifflin-St Jeor, Katch-McArdle), not medical advice.
        </p>
      </form>
    </Sheet>
  )
}

// ---- quick weigh-in ---------------------------------------------------------------

export function WeightSheet({
  health,
  onClose,
  onSaved,
}: {
  health: api.Health
  onClose: () => void
  onSaved: () => void
}) {
  const [weightLb, setWeightLb] = useState('')
  const [bodyFat, setBodyFat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.logWeight(
        api.localDate(),
        Math.round(kg(Number(weightLb)) * 100) / 100,
        Number(bodyFat) > 0 ? Number(bodyFat) : null,
      )
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <Sheet onClose={onClose}>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-bold">
          <Scale className="h-5 w-5 text-accent-bright" /> Log weight
        </h2>
        <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {health.latest_weight && (
          <p className="text-xs text-fg/45">
            Last weigh-in: {fmtLb(health.latest_weight.weight_kg)} on {health.latest_weight.date_for}
          </p>
        )}
        <div className="flex items-end gap-2">
          <div className="relative w-28">
            <Field
              label="Weight"
              inputMode="decimal"
              value={weightLb}
              onChange={(e) => setWeightLb(e.target.value.replace(/[^0-9.]/g, ''))}
              required
            />
          </div>
          <div className="relative w-28">
            <Field
              label="Body fat %"
              inputMode="decimal"
              value={bodyFat}
              onChange={(e) => setBodyFat(e.target.value.replace(/[^0-9.]/g, ''))}
              placeholder="optional"
            />
          </div>
        </div>
        <p className="text-xs text-fg/40">
          Each weigh-in nudges your computed calorie target, so the plan adjusts as you go.
        </p>
        <FormError message={error} />
        <Button type="submit" disabled={busy || !(Number(weightLb) > 0)}>
          {busy ? 'Saving' : 'Log weigh-in'}
        </Button>
      </form>
    </Sheet>
  )
}

// ---- the card on the Nutrition tab --------------------------------------------------

export function HealthCard({
  health,
  targetsMode,
  onEdit,
  onLogWeight,
}: {
  health: api.Health | null
  targetsMode: api.TargetMode
  onEdit: () => void
  onLogWeight: () => void
}) {
  if (health === null) return null

  // Not set up yet: a quiet invitation, never a gate.
  if (health.computed === null) {
    return (
      <button
        onClick={onEdit}
        className="glass flex w-full items-center gap-3 p-4 text-left transition-colors hover:bg-fg/5"
        data-health-setup
      >
        <HeartPulse className="h-5 w-5 shrink-0 text-accent-bright" />
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-fg/85">Set up your health profile</span>
          <span className="block text-xs text-fg/50">
            Optional. Get a daily calorie target computed for you, and a plan that adjusts as you
            weigh in. Private: only you can see it.
          </span>
        </span>
      </button>
    )
  }

  const p = health.profile!
  const w = health.latest_weight!
  const goalText = health.computed.at_goal
    ? 'At goal - maintaining'
    : p.goal === 'lose'
      ? `Losing ${p.rate_lbs_per_week ?? 1} lb/week`
      : p.goal === 'gain'
        ? `Gaining ${p.rate_lbs_per_week ?? 1} lb/week`
        : 'Maintaining'

  return (
    <section className="glass p-4" data-health-card>
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-fg/50">
          <HeartPulse className="h-3.5 w-3.5 text-accent-bright" /> Health
        </span>
        <button
          onClick={onEdit}
          className="flex shrink-0 items-center gap-1.5 rounded-xl border border-accent-bright/40 bg-accent-bright/15 px-3 py-2 text-xs font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
        >
          <Target className="h-3.5 w-3.5" /> Manage goals
        </button>
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-fg/85">
            {fmtLb(w.weight_kg)}
            {!health.computed.at_goal &&
              (p.goal_weight_kg != null || p.goal_body_fat_pct != null) && (
                <span className="font-normal text-fg/50">
                  {' '}
                  →{' '}
                  {[
                    p.goal_weight_kg != null ? fmtLb(p.goal_weight_kg) : null,
                    p.goal_body_fat_pct != null ? `${p.goal_body_fat_pct}% bf` : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              )}
          </p>
          <p className="truncate text-xs text-fg/50">
            {goalText} · burn ≈ {health.computed.maintenance_calories.toLocaleString()} kcal
            {targetsMode === 'auto' && ' · auto'}
          </p>
        </div>
        <button
          onClick={onLogWeight}
          className="flex shrink-0 items-center gap-1.5 rounded-xl border border-accent-bright/40 bg-accent-bright/15 px-3 py-2 text-xs font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
        >
          <Scale className="h-3.5 w-3.5" /> Log weight
        </button>
      </div>
    </section>
  )
}
