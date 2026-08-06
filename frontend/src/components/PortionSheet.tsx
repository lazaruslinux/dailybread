import { Pencil, X } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import * as api from '../lib/api'
import {
  FoodIdentity,
  Sheet,
  EDIT_MACROS,
  UNIT_GROUPS,
  UNIT_LABEL,
  decimalOnly,
  implausibleMacros,
  portionHint,
  servingIndex,
  toBase,
} from './recipes'
import type { MacroValues } from './recipes'
import { Button, Field, FormError } from './ui'

// The portion sheet: how much of a picked food or recipe to log, with an
// editable macro block for correcting incomplete barcode data. Lifted out of
// the Nutrition page so the health-check scanner can reuse it without pulling
// in the whole diary chunk.

export const SLOTS: { id: api.DiarySlot; label: string }[] = [
  { id: 'breakfast', label: 'Breakfast' },
  { id: 'lunch', label: 'Lunch' },
  { id: 'dinner', label: 'Dinner' },
  { id: 'snack', label: 'Snacks' },
]

export const nowHM = () => {
  const d = new Date()
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export const kcal = (v: number | null) => (v != null ? `${Math.round(v)}` : '—')
export const trim = (n: number) =>
  Number.isInteger(n) ? String(n) : String(Math.round(n * 100) / 100)

export type Picked = { kind: 'food'; food: api.Food } | { kind: 'recipe'; recipe: api.Recipe }

// Live nutrition for the chosen portion; null when the source doesn't know.
export function portionMacros(pick: Picked, amount: number, unit: string): api.RecipeMacros {
  // sugar_g rides along unshown: the plausibility check is built on it.
  const keys: (keyof api.RecipeMacros)[] = [
    'calories', 'protein_g', 'carbs_g', 'fat_g', 'sugar_g',
  ]
  const out = {} as api.RecipeMacros
  if (pick.kind === 'recipe') {
    for (const k of keys) {
      const v = pick.recipe.per_serving[k]
      out[k] = v != null ? v * amount : null
    }
    return out
  }
  const factor = foodBase(pick.food, amount, unit) / 100
  for (const k of keys) {
    const v = pick.food[k as keyof api.Food] as number | null
    out[k] = v != null ? v * factor : null
  }
  return out
}

// Grams (or mL) the chosen amount + unit resolves to for a food. A named
// serving is already in base units; anything else goes through toBase, which
// crosses measure families by the food's density the way the server does.
function foodBase(food: api.Food, amount: number, unit: string): number {
  const si = servingIndex(unit)
  return si != null && food.servings[si]
    ? amount * food.servings[si].grams
    : toBase(food, amount, unit)
}

// All ten nutrients scaled to the portion, the base for a per-entry override.
const ENTRY_NUTRIENTS = [
  'calories', 'protein_g', 'carbs_g', 'fat_g', 'saturated_fat_g',
  'trans_fat_g', 'cholesterol_mg', 'sodium_mg', 'fiber_g', 'sugar_g',
] as const

export function foodTotals(food: api.Food, amount: number, unit: string): api.DiaryTotals {
  const factor = foodBase(food, amount, unit) / 100
  const out = {} as api.DiaryTotals
  for (const k of ENTRY_NUTRIENTS) {
    const v = food[k] as number | null
    out[k] = v != null ? v * factor : null
  }
  return out
}

// Seed the editable fields from computed macros: a rounded number, or empty
// when the source didn't have it (so a missing value reads as a blank to fill).
function seedMacros(m: api.RecipeMacros): MacroValues {
  const one = (v: number | null) => (v != null ? String(Math.round(v)) : '')
  return { calories: one(m.calories), protein_g: one(m.protein_g), carbs_g: one(m.carbs_g), fat_g: one(m.fat_g) }
}

function missingPrimary(m: api.RecipeMacros): boolean {
  return EDIT_MACROS.some((f) => m[f.key] == null)
}

// The editor opens by itself for numbers that are missing OR that contradict
// each other (see implausibleMacros). Both mean the same thing to the member:
// look at the package before this lands in the diary.
const needsAttention = (m: api.RecipeMacros) => missingPrimary(m) || implausibleMacros(m)

const parseMacro = (s: string): number | null => {
  const t = s.trim()
  if (t === '') return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

function MacroLine({ m }: { m: api.RecipeMacros }) {
  const parts = [
    `${kcal(m.calories)} cal`,
    m.protein_g != null ? `${Math.round(m.protein_g)}g protein` : null,
    m.carbs_g != null ? `${Math.round(m.carbs_g)}g carbs` : null,
    m.fat_g != null ? `${Math.round(m.fat_g)}g fat` : null,
  ].filter(Boolean)
  return <p className="text-sm font-semibold text-accent-bright">{parts.join(' · ')}</p>
}

export function PortionSheet({
  pick,
  date,
  slot,
  onClose,
  onSaved,
}: {
  pick: Picked
  date: string
  slot: api.DiarySlot
  onClose: () => void
  onSaved: () => void
}) {
  const food = pick.kind === 'food' ? pick.food : null
  const [amount, setAmount] = useState(() =>
    food && food.servings.length === 0 ? '100' : '1',
  )
  const [unit, setUnit] = useState(() =>
    food ? (food.servings.length > 0 ? 'serving:0' : food.base_unit) : 'srv',
  )
  const [chosenSlot, setChosenSlot] = useState<api.DiarySlot>(slot)
  const [time, setTime] = useState(nowHM())
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const amt = Number(amount) || 0
  const macros = useMemo(
    () => portionMacros(pick, amt, unit),
    [pick, amt, unit],
  )

  // Editable per-entry macros (foods only). Barcode/search data is sometimes
  // incomplete (Open Food Facts often has no carbs) or wrong, so the member can
  // fill in or correct the numbers; a touched editor sends an explicit override.
  const editable = pick.kind === 'food'
  const [macroValues, setMacroValues] = useState<MacroValues>(() =>
    seedMacros(portionMacros(pick, amt, unit)),
  )
  const [macrosTouched, setMacrosTouched] = useState(false)
  const [editingMacros, setEditingMacros] = useState(
    () => editable && needsAttention(portionMacros(pick, amt, unit)),
  )

  // The portion is the base: changing amount/unit re-seeds the fields to the
  // freshly scaled values and drops any edit (edits sit on top of a set base).
  useEffect(() => {
    setMacroValues(seedMacros(portionMacros(pick, amt, unit)))
    setMacrosTouched(false)
  }, [pick, amt, unit])

  const editMacro = (key: keyof MacroValues, raw: string) => {
    setMacroValues((prev) => ({ ...prev, [key]: decimalOnly(raw) }))
    setMacrosTouched(true)
  }
  const missingMacros = editable && EDIT_MACROS.some((f) => macroValues[f.key] === '')
  // Shown only when the numbers are all there but disagree with each other.
  const dontAddUp = editable && !missingMacros && implausibleMacros(macros)

  // What the chosen portion resolves to, so a serving pick shows its weight and
  // a cross-family pick says how it was converted.
  const hint = useMemo(
    () => (food ? portionHint(food, amt, unit, food.servings) : null),
    [food, amt, unit],
  )

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (amt <= 0) {
      setError('Amount has to be more than zero.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const common = {
        date_for: date,
        slot: chosenSlot,
        time_of_day: time || null,
      }
      if (pick.kind === 'recipe') {
        await api.createDiaryEntry({
          ...common,
          recipe_id: pick.recipe.id,
          amount: amt,
          label: amt === 1 ? '1 serving' : `${trim(amt)} servings`,
        })
      } else {
        const f = pick.kind === 'food' ? pick.food : null
        const si = servingIndex(unit)
        const serving = si != null ? f!.servings[si] : null
        // Only send a totals override when the member actually edited the
        // macros; otherwise the server scales the food's stored nutrition as
        // before. Edited fields win; untouched ones ride the scaled values.
        const totals = macrosTouched
          ? {
              ...foodTotals(f!, amt, unit),
              calories: parseMacro(macroValues.calories),
              protein_g: parseMacro(macroValues.protein_g),
              carbs_g: parseMacro(macroValues.carbs_g),
              fat_g: parseMacro(macroValues.fat_g),
            }
          : undefined
        await api.createDiaryEntry({
          ...common,
          amount: serving ? amt * serving.grams : amt,
          unit: (serving ? f!.base_unit : unit) as api.AmountUnit,
          label: serving ? `${trim(amt)} ${serving.name.replace(/^1\s+/, '')}` : null,
          food_id: f!.id ?? undefined,
          source: f!.source,
          source_id: f!.source_id,
          name: f!.name,
          brand: f!.brand,
          base_unit: f!.base_unit,
          density_g_per_ml: f!.density_g_per_ml,
          calories: f!.calories,
          protein_g: f!.protein_g,
          carbs_g: f!.carbs_g,
          fat_g: f!.fat_g,
          saturated_fat_g: f!.saturated_fat_g,
          trans_fat_g: f!.trans_fat_g,
          cholesterol_mg: f!.cholesterol_mg,
          sodium_mg: f!.sodium_mg,
          fiber_g: f!.fiber_g,
          sugar_g: f!.sugar_g,
          ...(totals ? { totals } : {}),
        })
      }
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  const name = pick.kind === 'food' ? pick.food.name : pick.recipe.name

  return (
    <Sheet onClose={onClose}>
      <div className="mb-3.5 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-bold leading-snug">{name}</h2>
          {/* Brand + label serving + database badge: enough to spot a wrong
              product before it lands in the diary. */}
          {food && (
            <div className="mt-1">
              <FoodIdentity food={food} />
            </div>
          )}
        </div>
        <button onClick={onClose} aria-label="Close" className="shrink-0 -m-3 rounded-lg p-3 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>

      <form onSubmit={onSubmit} className="flex flex-col gap-3.5">
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
          <label className="block min-w-0 flex-1">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              Unit
            </span>
            {pick.kind === 'recipe' ? (
              <span className="field flex items-center text-fg/70">servings</span>
            ) : (
              <select value={unit} onChange={(e) => setUnit(e.target.value)} className="field">
                {food!.servings.length > 0 && (
                  <optgroup label="Servings">
                    {food!.servings.map((s, i) => (
                      <option key={`s${i}`} value={`serving:${i}`}>
                        {s.name}
                      </option>
                    ))}
                  </optgroup>
                )}
                {/* Both families, whatever the food is measured in: milk gets
                    poured in millilitres and logged in grams. */}
                {UNIT_GROUPS.map((g) => (
                  <optgroup key={g.label} label={g.label}>
                    {g.units.map((u) => (
                      <option key={u} value={u}>
                        {UNIT_LABEL[u] ?? u}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            )}
          </label>
        </div>
        {hint && <p className="-mt-2 text-xs text-fg/45">{hint}</p>}

        <div>
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
            Meal
          </span>
          <div className="grid grid-cols-4 gap-1.5">
            {SLOTS.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setChosenSlot(s.id)}
                className={`min-h-11 rounded-xl border px-1 py-2 text-xs font-semibold transition-colors ${
                  chosenSlot === s.id
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

        <div className="rounded-xl border border-fg/10 bg-fg/5 px-3.5 py-2.5">
          {editable && editingMacros ? (
            <div className="flex flex-col gap-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-fg/50">
                  This entry
                </span>
                <button
                  type="button"
                  onClick={() => setEditingMacros(false)}
                  className="-m-3.5 rounded-lg p-3.5 text-xs font-semibold text-accent-bright"
                >
                  Done
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {EDIT_MACROS.map((f) => (
                  <label key={f.key} className="block">
                    <span className="mb-1 block text-[11px] font-medium text-fg/55">
                      {f.label}
                      {f.unit ? ` (${f.unit})` : ''}
                    </span>
                    <input
                      inputMode="decimal"
                      value={macroValues[f.key]}
                      placeholder="Add"
                      onChange={(e) => editMacro(f.key, e.target.value)}
                      className={`field ${macroValues[f.key] === '' ? 'ring-1 ring-amber-400/60' : ''}`}
                    />
                  </label>
                ))}
              </div>
              {dontAddUp && (
                <p className="text-[11px] leading-snug text-amber-500">
                  These numbers don't add up; check them against the label.
                </p>
              )}
              {missingMacros && (
                <p className="text-[11px] leading-snug text-amber-500">
                  The highlighted macros weren't in the scan. Add them from the package label if you have it.
                </p>
              )}
            </div>
          ) : (
            <button
              type="button"
              onClick={() => editable && setEditingMacros(true)}
              className={`-my-2.5 flex min-h-11 w-full items-center justify-between gap-2 py-2.5 text-left ${
                editable ? '' : 'cursor-default'
              }`}
            >
              <MacroLine m={macros} />
              {editable && <Pencil className="h-4 w-4 shrink-0 text-fg/40" />}
            </button>
          )}
        </div>

        <FormError message={error} />
        <Button type="submit" disabled={busy || amt <= 0}>
          {busy ? 'Adding' : 'Add to diary'}
        </Button>
      </form>
    </Sheet>
  )
}
