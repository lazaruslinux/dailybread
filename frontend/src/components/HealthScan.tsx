import { ChevronRight, PlusCircle, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import * as api from '../lib/api'
import { BarcodeScanner } from './BarcodeScanner'
import {
  FoodIdentity,
  FoodSheet,
  NutritionPanel,
  Sheet,
  foldersOf,
} from './Recipes'
import { PortionSheet, foodTotals } from './PortionSheet'
import { Button } from './ui'

// The health-check scanner: a masthead entry point that scans a barcode, reads
// its ingredients and nutrition, and shows a verdict with the flags behind it.
// From the result the member can log the food, save it as a custom food, or
// drop it into one of their recipes. Adults only (the endpoint 403s kids).

// The verdict tiers, with their user-facing labels and banner tones. Emerald
// for whole/clean, amber for a mixed read, rose for a poor one, a neutral fg
// wash when there wasn't enough data. Plain palette utilities (not dark:) so
// both themes read the same, matching the rest of the app.
const VERDICT: Record<
  api.HealthVerdict,
  { label: string; sub: string; box: string; text: string }
> = {
  whole: {
    label: 'Whole food',
    sub: 'A single, minimally processed food.',
    box: 'border-emerald-500/40 bg-emerald-500/10',
    text: 'text-emerald-600',
  },
  clean: {
    label: 'Looks clean',
    sub: 'Nothing on the watch list turned up.',
    box: 'border-emerald-500/40 bg-emerald-500/10',
    text: 'text-emerald-600',
  },
  mixed: {
    label: 'Some concerns',
    sub: 'A few things worth a look below.',
    box: 'border-amber-500/40 bg-amber-500/10',
    text: 'text-amber-600',
  },
  poor: {
    label: 'Highly processed',
    sub: 'Several flags to weigh below.',
    box: 'border-rose-500/40 bg-rose-500/10',
    text: 'text-rose-600',
  },
  unknown: {
    label: 'Limited data',
    sub: 'Only the nutrition numbers were checked.',
    box: 'border-fg/15 bg-fg/5',
    text: 'text-fg/70',
  },
}

const SEV_DOT: Record<api.HealthSeverity, string> = {
  bad: 'bg-rose-500',
  warn: 'bg-amber-500',
  info: 'bg-fg/35',
}

const SEV_ORDER: Record<api.HealthSeverity, number> = { bad: 0, warn: 1, info: 2 }

// The meal a scan lands in by default, by the time of day.
function slotByHour(): api.DiarySlot {
  const h = new Date().getHours()
  if (h < 11) return 'breakfast'
  if (h < 15) return 'lunch'
  if (h < 20) return 'dinner'
  return 'snack'
}

// Digits and a single decimal point (a second dot would make Number() NaN),
// matching the add-sheet's amount input.
function sanitizeAmount(raw: string): string {
  let s = raw.replace(/[^0-9.]/g, '')
  const dot = s.indexOf('.')
  if (dot !== -1) s = s.slice(0, dot + 1) + s.slice(dot + 1).replace(/\./g, '')
  return s
}

type Phase = 'scan' | 'loading' | 'result' | 'unknown' | 'error'
type Action = 'diary' | 'custom' | 'recipe' | null

export function HealthScan({ onClose }: { onClose: () => void }) {
  const [phase, setPhase] = useState<Phase>('scan')
  const [result, setResult] = useState<api.FoodHealth | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [action, setAction] = useState<Action>(null)
  // The serving size the member types when the scanned food carries none, so
  // the nutrition panel can show per-serving facts off the label they're holding.
  const [servingAmt, setServingAmt] = useState('100')
  // Existing custom-food folders, so "Save as custom food" offers the same
  // datalist the Kitchen entry point does.
  const [folders, setFolders] = useState<string[]>([])

  useEffect(() => {
    api
      .getCustomFoods()
      .then((foods) => setFolders(foldersOf(foods)))
      .catch(() => setFolders([]))
  }, [])

  async function scanned(c: string) {
    setCode(c)
    setPhase('loading')
    setError(null)
    setServingAmt('100')
    try {
      setResult(await api.healthCheck(c))
      setPhase('result')
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 404) {
        setPhase('unknown')
      } else {
        setError(err instanceof api.ApiError ? err.message : 'Barcode lookup failed.')
        setPhase('error')
      }
    }
  }

  if (phase === 'scan') {
    return <BarcodeScanner onCode={scanned} onClose={onClose} />
  }

  if (phase === 'loading') {
    return (
      <Sheet onClose={onClose}>
        <p className="py-6 text-center text-sm text-fg/50">Checking the label…</p>
      </Sheet>
    )
  }

  if (phase === 'error') {
    return (
      <Sheet onClose={onClose}>
        <div className="mb-4 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wide text-accent-bright">
            Health check
          </span>
          <button onClick={onClose} aria-label="Close" className="-m-2 rounded-lg p-2 text-fg/50 hover:bg-fg/10 hover:text-fg">
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="py-4 text-sm text-fg/70">{error}</p>
        <Button onClick={() => setPhase('scan')}>Try another</Button>
      </Sheet>
    )
  }

  if (phase === 'unknown') {
    return (
      <>
        <Sheet onClose={onClose}>
          <div className="mb-4 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-accent-bright">
              Health check
            </span>
            <button onClick={onClose} aria-label="Close" className="-m-2 rounded-lg p-2 text-fg/50 hover:bg-fg/10 hover:text-fg">
              <X className="h-5 w-5" />
            </button>
          </div>
          <p className="text-sm leading-relaxed text-fg/70">
            No food database knows barcode <span className="font-semibold text-fg">{code}</span> yet.
            You can enter its label once as a custom food, and a later scan will find it right away.
          </p>
          <div className="mt-5">
            <Button onClick={() => setAction('custom')}>Create custom food</Button>
          </div>
        </Sheet>
        {action === 'custom' && (
          <FoodSheet
            food={null}
            folders={folders}
            barcode={code}
            onClose={() => setAction(null)}
            onSaved={(saved) => {
              if (saved) window.dispatchEvent(new Event('db:foods-changed'))
              setAction(null)
              onClose()
            }}
          />
        )}
      </>
    )
  }

  // phase === 'result'
  if (!result) return null
  const food = result.food
  const { verdict, flags } = result.assessment
  const v = VERDICT[verdict]
  const sorted = [...flags].sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity])
  const hasServing = food.servings.length > 0
  const unitLabel = food.base_unit === 'ml' ? 'mL' : 'g'
  // With no named serving the member types the label's serving size and the
  // panel rescales live; empty/invalid/zero falls back to 100.
  const typedAmt = Number(servingAmt) || 0
  const noServingAmt = typedAmt > 0 ? typedAmt : 100
  // All ten nutrients for one serving, so the panel's expandable rows (sat
  // fat, sodium, fiber) back up the flags above it.
  const perServe = foodTotals(
    food,
    hasServing ? 1 : noServingAmt,
    hasServing ? 'serving:0' : food.base_unit,
  )
  // When the member typed a serving size for a food that carried none, carry it
  // into the three actions as one synthetic client-side serving so the app
  // remembers it: a saved custom food seeds this row (rename-able), and the
  // diary/recipe pickers default to it. An untouched 100 means they told us
  // nothing, so the raw food rides through unchanged.
  const actionFood: api.Food =
    !hasServing && noServingAmt !== 100
      ? {
          ...food,
          servings: [{ name: '1 serving', grams: noServingAmt }],
        }
      : food

  return (
    <>
      <Sheet onClose={onClose}>
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-bold leading-snug">{food.name}</h2>
            <div className="mt-1">
              <FoodIdentity food={food} />
            </div>
          </div>
          <button onClick={onClose} aria-label="Close" className="shrink-0 -m-3 rounded-lg p-3 text-fg/50 hover:bg-fg/10 hover:text-fg">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className={`rounded-2xl border px-4 py-3 ${v.box}`}>
          <p className={`text-base font-bold ${v.text}`}>{v.label}</p>
          <p className="mt-0.5 text-xs text-fg/60">{v.sub}</p>
        </div>

        {sorted.length > 0 && (
          <ul className="mt-4 flex flex-col gap-3">
            {sorted.map((f, i) => (
              <li key={`${f.category}-${i}`} className="flex gap-2.5">
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEV_DOT[f.severity]}`} />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-fg/90">{f.label}</p>
                  <p className="text-sm leading-snug text-fg/55">{f.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-5">
          {hasServing ? (
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-fg/50">
              {food.servings[0].name}
            </p>
          ) : (
            <>
              <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-fg/50">
                <span>Per</span>
                <input
                  inputMode="decimal"
                  value={servingAmt}
                  onChange={(e) => setServingAmt(sanitizeAmount(e.target.value))}
                  aria-label="Serving size"
                  className="min-h-11 w-16 rounded-lg border border-fg/15 bg-transparent px-2 text-center text-sm font-semibold normal-case tracking-normal text-fg focus:border-accent-bright focus:outline-none"
                />
                <span>{unitLabel}</span>
              </div>
              <p className="mb-2 text-xs text-fg/50">Type the serving size from the label.</p>
            </>
          )}
          <NutritionPanel m={perServe} />
        </div>

        <div className="mt-6 flex flex-col gap-2">
          <Button className="min-h-11" onClick={() => setAction('diary')}>
            Add to diary
          </Button>
          <Button className="min-h-11" variant="ghost" onClick={() => setAction('custom')}>
            Save as custom food
          </Button>
          <Button className="min-h-11" variant="ghost" onClick={() => setAction('recipe')}>
            Add to a recipe
          </Button>
        </div>
      </Sheet>

      {action === 'diary' && (
        <PortionSheet
          pick={{ kind: 'food', food: actionFood }}
          date={api.localDate()}
          slot={slotByHour()}
          onClose={() => setAction(null)}
          onSaved={() => {
            setAction(null)
            onClose()
          }}
        />
      )}
      {action === 'custom' && (
        <FoodSheet
          food={null}
          prefill={actionFood}
          folders={folders}
          barcode={food.source_id}
          onClose={() => setAction(null)}
          onSaved={(saved) => {
            if (saved) window.dispatchEvent(new Event('db:foods-changed'))
            setAction(null)
            onClose()
          }}
        />
      )}
      {action === 'recipe' && (
        <RecipePickSheet
          food={actionFood}
          onClose={() => setAction(null)}
          onDone={() => {
            setAction(null)
            onClose()
          }}
        />
      )}
    </>
  )
}

// Pick one of the member's recipes to drop the scanned food into as a new
// ingredient line. The whole ingredient array is re-sent (the API replaces the
// list), so the existing lines are mapped back to payloads alongside the new
// one.
function RecipePickSheet({
  food,
  onClose,
  onDone,
}: {
  food: api.Food
  onClose: () => void
  onDone: () => void
}) {
  const [recipes, setRecipes] = useState<api.Recipe[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getRecipes().then(setRecipes).catch(() => setRecipes([]))
  }, [])

  function newLine(): api.RecipeIngredientPayload {
    // One serving's worth when the food has a named serving, else 100 base
    // units. The cook adjusts the amount in the recipe afterward.
    const grams = food.servings.length > 0 ? food.servings[0].grams : 100
    return {
      food_id: food.id ?? undefined,
      source: food.source,
      source_id: food.source_id,
      name: food.name,
      brand: food.brand,
      calories: food.calories,
      protein_g: food.protein_g,
      carbs_g: food.carbs_g,
      fat_g: food.fat_g,
      saturated_fat_g: food.saturated_fat_g,
      trans_fat_g: food.trans_fat_g,
      cholesterol_mg: food.cholesterol_mg,
      sodium_mg: food.sodium_mg,
      fiber_g: food.fiber_g,
      sugar_g: food.sugar_g,
      amount: grams,
      unit: food.base_unit,
    }
  }

  async function pick(recipe: api.Recipe) {
    setBusy(true)
    setError(null)
    const existing: api.RecipeIngredientPayload[] = recipe.ingredients.map((ing) => ({
      food_id: ing.food_id,
      source: ing.source,
      source_id: ing.source_id,
      name: ing.name,
      brand: ing.brand,
      calories: ing.calories,
      protein_g: ing.protein_g,
      carbs_g: ing.carbs_g,
      fat_g: ing.fat_g,
      saturated_fat_g: ing.saturated_fat_g,
      trans_fat_g: ing.trans_fat_g,
      cholesterol_mg: ing.cholesterol_mg,
      sodium_mg: ing.sodium_mg,
      fiber_g: ing.fiber_g,
      sugar_g: ing.sugar_g,
      amount: ing.amount,
      unit: ing.unit as api.AmountUnit,
    }))
    try {
      await api.updateRecipe(recipe.id, {
        name: recipe.name,
        servings: recipe.servings,
        steps: recipe.steps,
        ingredients: [...existing, newLine()],
      })
      window.dispatchEvent(new Event('db:recipes-changed'))
      onDone()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not add to the recipe.')
      setBusy(false)
    }
  }

  return (
    <Sheet onClose={onClose}>
      <div className="mb-4 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-accent-bright">
          Add to a recipe
        </span>
        <button onClick={onClose} aria-label="Close" className="-m-2 rounded-lg p-2 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>
      <p className="mb-3 text-sm text-fg/55">
        Adds <span className="font-semibold text-fg/80">{food.name}</span> as a new ingredient. You
        can set the amount in the recipe after.
      </p>
      {recipes === null ? (
        <p className="py-4 text-sm text-fg/45">Loading your recipes…</p>
      ) : recipes.length === 0 ? (
        <p className="py-4 text-sm text-fg/45">You don't have any recipes yet.</p>
      ) : (
        <div className="flex flex-col">
          {recipes.map((r) => (
            <button
              key={r.id}
              type="button"
              disabled={busy}
              onClick={() => void pick(r)}
              className="flex min-h-11 items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-fg/10 disabled:opacity-50"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{r.name}</span>
                <span className="block text-xs text-fg/45">
                  {r.ingredients.length} ingredient{r.ingredients.length === 1 ? '' : 's'}
                </span>
              </span>
              {busy ? (
                <PlusCircle className="h-4 w-4 shrink-0 animate-pulse text-fg/40" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-fg/40" />
              )}
            </button>
          ))}
        </div>
      )}
      {error && <p className="mt-3 text-sm text-rose-500">{error}</p>}
    </Sheet>
  )
}
