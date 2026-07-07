import { motion } from 'framer-motion'
import { BookOpen, ChevronDown, ChevronLeft, Pencil, Plus, Search, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Button, FormError } from './ui'

// Mass units only: a volume like "1 cup" needs the food's density to become
// grams, which the databases don't give us, so we don't offer it. Mirror of the
// backend GRAMS_PER_UNIT — nutrition is computed live here as the cook edits.
const GRAMS_PER_UNIT: Record<api.MassUnit, number> = { g: 1, oz: 28.3495, lb: 453.592 }
const UNITS: api.MassUnit[] = ['g', 'oz', 'lb']

// An ingredient line while editing: the food's per-100g macros travel with it so
// totals recompute instantly, without a round-trip, when the amount changes.
interface EditLine {
  key: string
  food_id: number | null
  source: api.FoodSource
  source_id: string | null
  name: string
  brand: string
  calories: number | null
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  saturated_fat_g: number | null
  trans_fat_g: number | null
  cholesterol_mg: number | null
  sodium_mg: number | null
  fiber_g: number | null
  sugar_g: number | null
  amount: number
  unit: api.MassUnit
}

let _keySeq = 0
const nextKey = () => `l${_keySeq++}`

function lineFromFood(food: api.Food): EditLine {
  return {
    key: nextKey(),
    food_id: food.id,
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
    amount: 100,
    unit: 'g',
  }
}

// Rebuild an editor line from a saved recipe line. The API sends each macro
// already scaled to the line's grams, so back out the per-100g figure the
// editor works in (grams is always > 0 for a saved line).
function lineFromSaved(ing: api.RecipeIngredient): EditLine {
  const per100 = (v: number | null) => (v != null && ing.grams > 0 ? (v * 100) / ing.grams : null)
  return {
    key: nextKey(),
    food_id: ing.food_id,
    source: ing.source,
    source_id: ing.source_id,
    name: ing.name,
    brand: ing.brand,
    calories: per100(ing.calories),
    protein_g: per100(ing.protein_g),
    carbs_g: per100(ing.carbs_g),
    fat_g: per100(ing.fat_g),
    saturated_fat_g: per100(ing.saturated_fat_g),
    trans_fat_g: per100(ing.trans_fat_g),
    cholesterol_mg: per100(ing.cholesterol_mg),
    sodium_mg: per100(ing.sodium_mg),
    fiber_g: per100(ing.fiber_g),
    sugar_g: per100(ing.sugar_g),
    amount: ing.amount,
    unit: (ing.unit as api.MassUnit) in GRAMS_PER_UNIT ? (ing.unit as api.MassUnit) : 'g',
  }
}

const gramsOf = (l: EditLine) => l.amount * GRAMS_PER_UNIT[l.unit]

// The whole Nutrition Facts label, mirroring the backend FOOD_NUTRIENTS so live
// editing totals match what the server computes on save.
const MACROS = [
  'calories',
  'protein_g',
  'carbs_g',
  'fat_g',
  'saturated_fat_g',
  'trans_fat_g',
  'cholesterol_mg',
  'sodium_mg',
  'fiber_g',
  'sugar_g',
] as const
type Macro = (typeof MACROS)[number]

// Per-serving totals, live, from the editor lines. A nutrient stays null until
// some food supplies it, so an empty or macro-less recipe reads "—", never a
// fake 0.
function perServing(lines: EditLine[], servings: number): api.RecipeMacros {
  const totals = Object.fromEntries(MACROS.map((m) => [m, null])) as Record<Macro, number | null>
  for (const l of lines) {
    const factor = gramsOf(l) / 100
    for (const m of MACROS) {
      const v = l[m]
      if (v != null) totals[m] = (totals[m] ?? 0) + v * factor
    }
  }
  const s = servings || 1
  const round1 = (v: number | null) => (v != null ? Math.round((v / s) * 10) / 10 : null)
  return Object.fromEntries(MACROS.map((m) => [m, round1(totals[m])])) as unknown as api.RecipeMacros
}

const fmt = (n: number | null) => (n != null ? String(Math.round(n)) : '—')

// "125 cal · 13P / 20C / 9F" per serving, skipping any macro nothing supplied.
function macroSummary(m: api.RecipeMacros): string {
  const parts: string[] = []
  if (m.calories != null) parts.push(`${Math.round(m.calories)} cal`)
  const macros = [
    m.protein_g != null ? `${Math.round(m.protein_g)}P` : null,
    m.carbs_g != null ? `${Math.round(m.carbs_g)}C` : null,
    m.fat_g != null ? `${Math.round(m.fat_g)}F` : null,
  ].filter(Boolean)
  if (macros.length) parts.push(macros.join(' / '))
  return parts.join(' · ')
}

// The modal shell shared by the view and the editor. Rendered through a portal
// to <body>: the Kitchen page's frosted `.glass` cards use backdrop-filter,
// which makes position:fixed anchor to the card instead of the viewport — so a
// modal nested under one only covers a band (and on iOS the page shows through).
// The portal lifts it out to the top of the DOM where `fixed inset-0` fills the
// screen. Body scroll is locked while it's open so the page can't drift behind.
function Sheet({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [])
  return createPortal(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 40 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        className="sheet-card max-h-[90svh] w-full max-w-sm overflow-y-auto p-6"
        role="dialog"
        aria-modal="true"
      >
        {children}
      </motion.div>
    </motion.div>,
    document.body,
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center rounded-xl bg-fg/5 px-1.5 py-2">
      <span className="font-display text-lg font-semibold leading-none">{value}</span>
      <span className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-fg/45">{label}</span>
    </div>
  )
}

// Per-serving nutrition: the five headline numbers (calories, the macros, and
// sugar) always shown, with the rest of the Nutrition Facts label a tap away.
const MORE_NUTRIENTS: { key: keyof api.RecipeMacros; label: string; unit: string }[] = [
  { key: 'saturated_fat_g', label: 'Saturated fat', unit: 'g' },
  { key: 'trans_fat_g', label: 'Trans fat', unit: 'g' },
  { key: 'cholesterol_mg', label: 'Cholesterol', unit: 'mg' },
  { key: 'sodium_mg', label: 'Sodium', unit: 'mg' },
  { key: 'fiber_g', label: 'Fiber', unit: 'g' },
]

function NutritionPanel({ m }: { m: api.RecipeMacros }) {
  const [open, setOpen] = useState(false)
  const hasMore = MORE_NUTRIENTS.some((r) => m[r.key] != null)
  return (
    <div>
      <div className="grid grid-cols-5 gap-1.5">
        <Stat label="Cal" value={fmt(m.calories)} />
        <Stat label="Protein" value={fmt(m.protein_g)} />
        <Stat label="Carbs" value={fmt(m.carbs_g)} />
        <Stat label="Fat" value={fmt(m.fat_g)} />
        <Stat label="Sugar" value={fmt(m.sugar_g)} />
      </div>
      {hasMore && (
        <>
          <button type="button" onClick={() => setOpen((o) => !o)}
            className="mt-2 flex items-center gap-1 text-xs font-semibold text-accent-bright hover:opacity-80">
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
            {open ? 'Hide nutrition' : 'More nutrition'}
          </button>
          {open && (
            <div className="mt-2 flex flex-col divide-y divide-fg/5 rounded-xl bg-fg/5 px-3">
              {MORE_NUTRIENTS.map((r) => (
                <div key={r.key} className="flex items-center justify-between py-1.5 text-sm">
                  <span className="text-fg/65">{r.label}</span>
                  <span className="tabular-nums text-fg/85">
                    {m[r.key] != null ? `${Math.round(m[r.key] as number)} ${r.unit}` : '—'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// Read-only view of one recipe: computed nutrition per serving, its ingredient
// lines, and steps.
function RecipeDetail({
  recipe,
  canEdit,
  onEdit,
  onDelete,
  onClose,
}: {
  recipe: api.Recipe
  canEdit: boolean
  onEdit: () => void
  onDelete: () => Promise<void>
  onClose: () => void
}) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const m = recipe.per_serving

  return (
    <Sheet onClose={onClose}>
      <div className="mb-3 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-accent-bright">
          <BookOpen className="h-3.5 w-3.5" /> Recipe
        </span>
        <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>

      <h2 className="font-display text-2xl font-semibold tracking-[-0.01em]">{recipe.name}</h2>
      <p className="mt-1 text-xs text-fg/45">
        Makes {recipe.servings} {recipe.servings === 1 ? 'serving' : 'servings'} · per serving
      </p>

      <div className="mt-4">
        <NutritionPanel m={m} />
      </div>

      {recipe.ingredients.length > 0 && (
        <div className="mt-5">
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/40">Ingredients</span>
          <ul className="flex flex-col gap-1">
            {recipe.ingredients.map((ing) => (
              <li key={ing.id} className="flex items-baseline justify-between gap-3 text-sm">
                <span className="text-fg/85">{ing.name}</span>
                <span className="shrink-0 tabular-nums text-fg/45">
                  {+ing.amount.toFixed(2)} {ing.unit}
                  {ing.calories != null && ` · ${Math.round(ing.calories)} cal`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {recipe.steps.trim() && (
        <div className="mt-4">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-fg/40">Steps</span>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-fg/80">{recipe.steps}</p>
        </div>
      )}

      {canEdit && (
        <div className="mt-6 flex flex-col gap-2.5">
          <Button type="button" variant="ghost" onClick={onEdit} className="flex items-center justify-center gap-1.5">
            <Pencil className="h-4 w-4" /> Edit recipe
          </Button>
          <Button
            type="button"
            variant="danger"
            disabled={busy}
            onClick={async () => {
              if (!armed) {
                setArmed(true)
                return
              }
              setBusy(true)
              try {
                await onDelete()
              } finally {
                setBusy(false)
              }
            }}
            className="flex items-center justify-center gap-1.5"
          >
            <Trash2 className="h-4 w-4" />
            {armed ? 'Tap again to delete' : 'Delete recipe'}
          </Button>
        </div>
      )}
    </Sheet>
  )
}

const SOURCE_LABEL: Record<api.FoodSource, string> = { usda: 'USDA', off: 'OFF', custom: 'Custom' }

// The food picker: search the USDA database (server-proxied) and the family's
// own custom foods, tap one to add it as an ingredient. Barcode scanning is a
// later step; this covers search + custom for now.
function FoodPicker({ onPick, onBack }: { onPick: (food: api.Food) => void; onBack: () => void }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<api.Food[]>([])
  const [custom, setCustom] = useState<api.Food[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // The family's custom foods are always shown (they're a short list); load once.
  useEffect(() => {
    api.getCustomFoods().then(setCustom).catch(() => {})
  }, [])

  // Debounce search so we don't hit the server on every keystroke.
  useEffect(() => {
    const query = q.trim()
    if (query.length < 2) {
      setResults([])
      setSearching(false)
      return
    }
    setSearching(true)
    const id = setTimeout(async () => {
      try {
        setResults(await api.searchFoods(query))
        setError(null)
      } catch (err) {
        setError(err instanceof api.ApiError ? err.message : 'Search failed.')
        setResults([])
      } finally {
        setSearching(false)
      }
    }, 350)
    return () => clearTimeout(id)
  }, [q])

  const shownCustom = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return needle ? custom.filter((f) => f.name.toLowerCase().includes(needle)) : custom
  }, [custom, q])

  function Row({ food }: { food: api.Food }) {
    // Cronometer-style: name on top, the brand + label serving beneath, and the
    // source database as a badge on the right.
    const sub = [food.brand, food.serving].filter(Boolean).join(' · ')
    return (
      <button
        type="button"
        onClick={() => onPick(food)}
        className="flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-fg/10"
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{food.name}</span>
          {sub && <span className="block truncate text-xs text-fg/45">{sub}</span>}
        </span>
        <span className="shrink-0 rounded-md border border-fg/10 bg-fg/5 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-fg/50">
          {SOURCE_LABEL[food.source]}
        </span>
      </button>
    )
  }

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <button onClick={onBack} aria-label="Back" className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <ChevronLeft className="h-5 w-5" />
        </button>
        <span className="text-xs font-semibold uppercase tracking-wide text-accent-bright">Add ingredient</span>
      </div>

      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg/40" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search foods (e.g. chicken breast)"
          className="field"
          // Inline pad-left clears the search icon; a `pl-9` utility loses to
          // `.field`'s own padding (same specificity, .field defined later).
          style={{ paddingLeft: '2.25rem' }}
          autoFocus
        />
      </div>

      <FormError message={error} />

      <div className="mt-3 flex flex-col gap-3">
        {shownCustom.length > 0 && (
          <div>
            <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-fg/40">Your foods</span>
            <div className="flex flex-col">
              {shownCustom.map((f) => (
                <Row key={`c${f.id}`} food={f} />
              ))}
            </div>
          </div>
        )}

        {q.trim().length >= 2 && (
          <div>
            <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-fg/40">
              Food database
            </span>
            {searching ? (
              <p className="px-2.5 py-3 text-sm text-fg/45">Searching…</p>
            ) : results.length === 0 ? (
              <p className="px-2.5 py-3 text-sm text-fg/45">No matches.</p>
            ) : (
              <div className="flex flex-col">
                {results.map((f) => (
                  <Row key={`${f.source}:${f.source_id}`} food={f} />
                ))}
              </div>
            )}
          </div>
        )}

        {q.trim().length < 2 && shownCustom.length === 0 && (
          <p className="px-2.5 py-6 text-center text-sm text-fg/45">
            Type to search the food database, or add custom foods first.
          </p>
        )}
      </div>
    </div>
  )
}

// One editable ingredient line: amount + unit, its live contribution, remove.
function LineRow({
  line,
  onChange,
  onRemove,
}: {
  line: EditLine
  onChange: (l: EditLine) => void
  onRemove: () => void
}) {
  const cals = line.calories != null ? Math.round((line.calories * gramsOf(line)) / 100) : null
  return (
    <div className="flex items-center gap-2 rounded-xl bg-fg/5 px-3 py-2">
      <div className="min-w-0 flex-1">
        <span className="block truncate text-sm">{line.name}</span>
        {cals != null && <span className="block text-xs text-fg/45">{cals} cal</span>}
      </div>
      {/* `.field` is width:100%, so size these by a fixed-width parent (like the
          servings field does) rather than a width utility it would override. */}
      <div className="w-16 shrink-0">
        <input
          inputMode="decimal"
          value={line.amount === 0 ? '' : String(line.amount)}
          onChange={(e) => {
            const v = e.target.value.replace(/[^0-9.]/g, '')
            onChange({ ...line, amount: v === '' ? 0 : Number(v) })
          }}
          className="field px-2 text-center"
          aria-label={`Amount of ${line.name}`}
        />
      </div>
      <div className="w-16 shrink-0">
        <select
          value={line.unit}
          onChange={(e) => onChange({ ...line, unit: e.target.value as api.MassUnit })}
          className="field px-2"
          aria-label={`Unit for ${line.name}`}
        >
          {UNITS.map((u) => (
            <option key={u} value={u}>
              {u}
            </option>
          ))}
        </select>
      </div>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${line.name}`}
        className="rounded-lg p-1.5 text-fg/40 hover:bg-fg/10 hover:text-danger"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  )
}

// Create or edit a recipe: name, servings, ingredient lines (with a food
// picker), live per-serving nutrition, and steps.
function RecipeSheet({
  recipe,
  onClose,
  onSaved,
}: {
  recipe: api.Recipe | null
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState(recipe?.name ?? '')
  const [servings, setServings] = useState<number | null>(recipe?.servings ?? 1)
  const [lines, setLines] = useState<EditLine[]>(() => (recipe?.ingredients ?? []).map(lineFromSaved))
  const [steps, setSteps] = useState(recipe?.steps ?? '')
  const [picking, setPicking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const totals = useMemo(() => perServing(lines, servings ?? 1), [lines, servings])

  const setLine = (key: string, next: EditLine) =>
    setLines((ls) => ls.map((l) => (l.key === key ? next : l)))
  const removeLine = (key: string) => setLines((ls) => ls.filter((l) => l.key !== key))

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    setBusy(true)
    setError(null)
    const payload: api.RecipePayload = {
      name: trimmed,
      servings: servings ?? 1,
      steps,
      ingredients: lines
        .filter((l) => l.amount > 0)
        .map((l) => ({
          food_id: l.food_id,
          source: l.source,
          source_id: l.source_id,
          name: l.name,
          brand: l.brand,
          calories: l.calories,
          protein_g: l.protein_g,
          carbs_g: l.carbs_g,
          fat_g: l.fat_g,
          saturated_fat_g: l.saturated_fat_g,
          trans_fat_g: l.trans_fat_g,
          cholesterol_mg: l.cholesterol_mg,
          sodium_mg: l.sodium_mg,
          fiber_g: l.fiber_g,
          sugar_g: l.sugar_g,
          amount: l.amount,
          unit: l.unit,
        })),
    }
    try {
      if (recipe) await api.updateRecipe(recipe.id, payload)
      else await api.createRecipe(payload)
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not save the recipe.')
    } finally {
      setBusy(false)
    }
  }

  if (picking) {
    return (
      <Sheet onClose={onClose}>
        <FoodPicker
          onBack={() => setPicking(false)}
          onPick={(food) => {
            setLines((ls) => [...ls, lineFromFood(food)])
            setPicking(false)
          }}
        />
      </Sheet>
    )
  }

  return (
    <Sheet onClose={onClose}>
      <div className="mb-4 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-accent-bright">
          {recipe ? 'Edit recipe' : 'New recipe'}
        </span>
        <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>

      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">Name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={120}
            placeholder="Taco bowls"
            className="field"
            autoFocus
          />
        </label>

        <label className="flex w-28 flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-fg/45">Servings</span>
          <input
            inputMode="numeric"
            value={servings ?? ''}
            onChange={(e) => {
              const d = e.target.value.replace(/[^0-9]/g, '')
              setServings(d === '' ? null : Number(d))
            }}
            className="field text-center"
          />
        </label>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">Ingredients</span>
            <button
              type="button"
              onClick={() => setPicking(true)}
              className="flex items-center gap-1 rounded-full border border-accent-bright/40 bg-accent-bright/15 px-2.5 py-1 text-xs font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
            >
              <Plus className="h-3.5 w-3.5" strokeWidth={2.5} /> Add
            </button>
          </div>
          {lines.length === 0 ? (
            <p className="rounded-xl bg-fg/5 px-3 py-4 text-center text-sm text-fg/45">
              Add foods and their amounts — nutrition adds up as you go.
            </p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {lines.map((l) => (
                <LineRow key={l.key} line={l} onChange={(n) => setLine(l.key, n)} onRemove={() => removeLine(l.key)} />
              ))}
            </div>
          )}
        </div>

        {lines.length > 0 && (
          <div>
            <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-fg/45">
              Per serving
            </span>
            <NutritionPanel m={totals} />
          </div>
        )}

        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">Steps (optional)</span>
          <textarea
            value={steps}
            onChange={(e) => setSteps(e.target.value)}
            rows={3}
            maxLength={10000}
            placeholder="How to make it"
            className="field resize-y leading-relaxed"
          />
        </label>

        <FormError message={error} />
        <Button type="submit" disabled={busy || !name.trim()} className="w-full">
          {busy ? 'Saving' : recipe ? 'Save changes' : 'Save recipe'}
        </Button>
      </form>
    </Sheet>
  )
}

type View = { mode: 'closed' } | { mode: 'detail'; recipe: api.Recipe } | { mode: 'edit'; recipe: api.Recipe | null }

// The family recipe box: saved recipes with computed per-serving nutrition.
// Everyone can browse; only parents add, edit, or delete. Self-contained like
// GroceryPanel.
export function RecipeBox() {
  const { user } = useAuth()
  const canEdit = user?.role === 'parent'

  const [recipes, setRecipes] = useState<api.Recipe[]>([])
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<View>({ mode: 'closed' })
  const mounted = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const box = await api.getRecipes()
      if (mounted.current) {
        setRecipes(box)
        setError(null)
      }
    } catch (err) {
      if (mounted.current) setError(err instanceof api.ApiError ? err.message : 'Could not load recipes.')
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    refresh()
    return () => {
      mounted.current = false
    }
  }, [refresh])

  async function onDelete(id: number) {
    await api.deleteRecipe(id)
    setView({ mode: 'closed' })
    refresh()
  }

  return (
    <section className="glass p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-bold">Recipes</h2>
        {canEdit && (
          <button
            type="button"
            onClick={() => setView({ mode: 'edit', recipe: null })}
            className="flex items-center gap-1 rounded-full border border-accent-bright/40 bg-accent-bright/15 px-2.5 py-1 text-xs font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
          >
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} /> New recipe
          </button>
        )}
      </div>

      <FormError message={error} />

      {recipes.length === 0 ? (
        <p className="py-6 text-center text-sm text-fg/50">
          {canEdit ? 'No recipes yet. Add your family favorites so planning dinner is one tap.' : 'No recipes yet.'}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {recipes.map((r) => {
            const summary = macroSummary(r.per_serving)
            return (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => setView({ mode: 'detail', recipe: r })}
                  className="flex w-full items-center justify-between gap-3 rounded-xl bg-fg/5 px-3 py-2.5 text-left transition-colors hover:bg-fg/10"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-display text-base font-semibold">{r.name}</span>
                    {summary && <span className="block truncate text-xs text-fg/50">{summary}</span>}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {view.mode === 'detail' && (
        <RecipeDetail
          recipe={view.recipe}
          canEdit={canEdit}
          onEdit={() => setView({ mode: 'edit', recipe: view.recipe })}
          onDelete={() => onDelete(view.recipe.id)}
          onClose={() => setView({ mode: 'closed' })}
        />
      )}
      {view.mode === 'edit' && (
        <RecipeSheet
          recipe={view.recipe}
          onClose={() => setView({ mode: 'closed' })}
          onSaved={() => {
            setView({ mode: 'closed' })
            refresh()
          }}
        />
      )}
    </section>
  )
}

// ---- custom foods -------------------------------------------------------------

type NutriKey =
  | 'calories'
  | 'fat_g'
  | 'saturated_fat_g'
  | 'trans_fat_g'
  | 'cholesterol_mg'
  | 'sodium_mg'
  | 'carbs_g'
  | 'fiber_g'
  | 'sugar_g'
  | 'protein_g'

// The Nutrition Facts label, in the order a package prints it; sub-nutrients
// (saturated/trans under fat, fiber/sugar under carbs) are indented.
const NUTRIENT_ROWS: { key: NutriKey; label: string; unit: string; indent?: boolean }[] = [
  { key: 'calories', label: 'Energy', unit: 'kcal' },
  { key: 'fat_g', label: 'Fat', unit: 'g' },
  { key: 'saturated_fat_g', label: 'Saturated', unit: 'g', indent: true },
  { key: 'trans_fat_g', label: 'Trans', unit: 'g', indent: true },
  { key: 'cholesterol_mg', label: 'Cholesterol', unit: 'mg' },
  { key: 'sodium_mg', label: 'Sodium', unit: 'mg' },
  { key: 'carbs_g', label: 'Carbs', unit: 'g' },
  { key: 'fiber_g', label: 'Fiber', unit: 'g', indent: true },
  { key: 'sugar_g', label: 'Sugar', unit: 'g', indent: true },
  { key: 'protein_g', label: 'Protein', unit: 'g' },
]

const NUTRI_KEYS = NUTRIENT_ROWS.map((r) => r.key)
const emptyNutri = () => Object.fromEntries(NUTRI_KEYS.map((k) => [k, ''])) as Record<NutriKey, string>

interface ServingDraft {
  name: string
  grams: string
}

const round2 = (n: number) => Math.round(n * 100) / 100
const numOrNull = (s: string) => (s.trim() === '' ? null : Number(s))
const decimal = (s: string) => s.replace(/[^0-9.]/g, '')

// A one-line summary for a custom-food row: its first serving and that serving's
// calories, backed out of the per-100g figure we store.
function foodSummary(f: api.Food): string {
  const s = f.servings[0]
  const cal = (grams: number) => (f.calories != null ? `${Math.round((f.calories * grams) / 100)} cal` : '')
  const parts = [f.brand]
  if (s) parts.push([s.name, cal(s.grams)].filter(Boolean).join(' · '))
  else if (f.calories != null) parts.push(`${Math.round(f.calories)} cal / 100 g`)
  return parts.filter(Boolean).join(' · ')
}

// Create or edit a custom food, Cronometer-style: a name, one or more named
// servings, and the Nutrition Facts as printed for one chosen serving. The
// values on screen are always "per" the selected serving; switching that serving
// rescales them so they describe the same food. The server stores per-100g.
function FoodSheet({
  food,
  onClose,
  onSaved,
}: {
  food: api.Food | null
  onClose: () => void
  onSaved: () => void
}) {
  const editing = food !== null
  const [name, setName] = useState(food?.name ?? '')
  const [brand, setBrand] = useState(food?.brand ?? '')
  const [servings, setServings] = useState<ServingDraft[]>(() =>
    editing && food.servings.length
      ? food.servings.map((s) => ({ name: s.name, grams: String(s.grams) }))
      : [{ name: '100 g', grams: '100' }],
  )
  const [basis, setBasis] = useState(0)
  // Nutrition shown per the basis serving. Seed an edit from the stored per-100g
  // figures scaled to the first serving's grams.
  const [nutri, setNutri] = useState<Record<NutriKey, string>>(() => {
    if (!editing) return emptyNutri()
    const g = food.servings[0]?.grams ?? 100
    const out = emptyNutri()
    for (const k of NUTRI_KEYS) {
      const v = food[k]
      if (v != null) out[k] = String(round2((v * g) / 100))
    }
    return out
  })
  const [busy, setBusy] = useState(false)
  const [armed, setArmed] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const setServing = (i: number, s: ServingDraft) =>
    setServings((ls) => ls.map((l, j) => (j === i ? s : l)))
  const addServing = () => setServings((ls) => [...ls, { name: '', grams: '' }])
  const removeServing = (i: number) =>
    setServings((ls) => {
      const next = ls.filter((_, j) => j !== i)
      setBasis((b) => (i < b ? b - 1 : Math.min(b, next.length - 1)))
      return next
    })

  // Switching which serving the numbers are "per" rescales them by the gram
  // ratio, so they keep describing the same food.
  function changeBasis(next: number) {
    const oldG = Number(servings[basis]?.grams) || 0
    const newG = Number(servings[next]?.grams) || 0
    if (oldG > 0 && newG > 0 && oldG !== newG) {
      setNutri((prev) => {
        const out = { ...prev }
        for (const k of NUTRI_KEYS) if (out[k] !== '') out[k] = String(round2((Number(out[k]) * newG) / oldG))
        return out
      })
    }
    setBasis(next)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const cleaned = servings.map((s) => ({ name: s.name.trim(), grams: Number(s.grams) }))
    if (!name.trim()) return setError('Give the food a name.')
    if (!cleaned.every((s) => s.name && s.grams > 0))
      return setError('Every serving needs a name and a weight in grams.')

    setBusy(true)
    setError(null)
    const payload: api.CustomFoodPayload = {
      name: name.trim(),
      brand: brand.trim(),
      servings: cleaned,
      basis_index: basis,
      ...(Object.fromEntries(NUTRI_KEYS.map((k) => [k, numOrNull(nutri[k])])) as Record<NutriKey, number | null>),
    }
    try {
      if (editing) await api.updateCustomFood(food.id!, payload)
      else await api.createCustomFood(payload)
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not save the food.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet onClose={onClose}>
      <div className="mb-4 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-accent-bright">
          {editing ? 'Edit food' : 'New food'}
        </span>
        <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>

      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={200}
            placeholder="e.g. Clif Bar, Peanut Butter" className="field" autoFocus />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">Brand (optional)</span>
          <input value={brand} onChange={(e) => setBrand(e.target.value)} maxLength={120}
            placeholder="e.g. Clif" className="field" />
        </label>

        <div>
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/45">Serving sizes</span>
          <p className="mb-2 text-xs text-fg/45">As printed on the package. The weight in grams is what lets a serving
            add up in recipes.</p>
          <div className="flex flex-col gap-1.5">
            {servings.map((s, i) => (
              <div key={i} className="flex items-center gap-2">
                <input value={s.name} onChange={(e) => setServing(i, { ...s, name: e.target.value })}
                  maxLength={60} placeholder="1 bar" className="field min-w-0 flex-1" aria-label={`Serving ${i + 1} name`} />
                <div className="flex w-24 shrink-0 items-center gap-1">
                  <input inputMode="decimal" value={s.grams}
                    onChange={(e) => setServing(i, { ...s, grams: decimal(e.target.value) })}
                    placeholder="0" className="field px-2 text-right" aria-label={`Serving ${i + 1} grams`} />
                  <span className="text-xs text-fg/45">g</span>
                </div>
                <button type="button" onClick={() => removeServing(i)} disabled={servings.length === 1}
                  aria-label={`Remove serving ${i + 1}`}
                  className="rounded-lg p-1.5 text-fg/40 hover:bg-fg/10 hover:text-danger disabled:opacity-30">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
          <button type="button" onClick={addServing}
            className="mt-2 flex items-center gap-1 text-xs font-semibold text-accent-bright hover:opacity-80">
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} /> Add serving size
          </button>
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">Nutrition facts</span>
            {servings.length > 1 && (
              <label className="flex items-center gap-1.5 text-xs text-fg/45">
                per
                <select value={basis} onChange={(e) => changeBasis(Number(e.target.value))}
                  className="field w-auto px-2 py-1 text-xs" aria-label="Nutrition displayed per serving">
                  {servings.map((s, i) => (
                    <option key={i} value={i}>{s.name.trim() || `Serving ${i + 1}`}</option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <div className="flex flex-col divide-y divide-fg/5 rounded-xl bg-fg/5 px-3">
            {NUTRIENT_ROWS.map((row) => (
              <div key={row.key} className="flex items-center justify-between gap-3 py-2">
                <span className={`text-sm ${row.indent ? 'pl-4 text-fg/60' : 'text-fg/85'}`}>{row.label}</span>
                <div className="flex w-24 shrink-0 items-center gap-1">
                  <input inputMode="decimal" value={nutri[row.key]}
                    onChange={(e) => setNutri((n) => ({ ...n, [row.key]: decimal(e.target.value) }))}
                    placeholder="0" className="field px-2 py-1 text-right" aria-label={row.label} />
                  <span className="w-6 text-xs text-fg/45">{row.unit}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <FormError message={error} />
        <Button type="submit" disabled={busy || !name.trim()} className="w-full">
          {busy ? 'Saving' : editing ? 'Save changes' : 'Save food'}
        </Button>

        {editing && (
          <Button type="button" variant="danger" disabled={busy}
            onClick={async () => {
              if (!armed) return setArmed(true)
              setBusy(true)
              try {
                await api.deleteCustomFood(food.id!)
                onSaved()
              } catch (err) {
                setError(err instanceof api.ApiError ? err.message : 'Could not delete the food.')
                setBusy(false)
              }
            }}
            className="flex items-center justify-center gap-1.5">
            <Trash2 className="h-4 w-4" />
            {armed ? 'Tap again to delete' : 'Delete food'}
          </Button>
        )}
      </form>
    </Sheet>
  )
}

// The Custom Foods box: a family's own foods for anything USDA/Open Food Facts
// lacks. They show up as pickable ingredients in the recipe builder too. Sits
// under Recipes on the Kitchen page. Everyone browses; only parents add/edit.
export function CustomFoodBox() {
  const { user } = useAuth()
  const canEdit = user?.role === 'parent'
  const [foods, setFoods] = useState<api.Food[]>([])
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<{ food: api.Food | null } | null>(null)
  const mounted = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const list = await api.getCustomFoods()
      if (mounted.current) {
        setFoods(list)
        setError(null)
      }
    } catch (err) {
      if (mounted.current) setError(err instanceof api.ApiError ? err.message : 'Could not load custom foods.')
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    refresh()
    return () => {
      mounted.current = false
    }
  }, [refresh])

  return (
    <section className="glass p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-bold">Custom foods</h2>
        {canEdit && (
          <button type="button" onClick={() => setEditing({ food: null })}
            className="flex items-center gap-1 rounded-full border border-accent-bright/40 bg-accent-bright/15 px-2.5 py-1 text-xs font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25">
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} /> New food
          </button>
        )}
      </div>

      <FormError message={error} />

      {foods.length === 0 ? (
        <p className="py-6 text-center text-sm text-fg/50">
          {canEdit
            ? 'Add anything the food database is missing — a homemade dish, a local brand — and use it in recipes.'
            : 'No custom foods yet.'}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {foods.map((f) => {
            const summary = foodSummary(f)
            const inner = (
              <>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{f.name}</span>
                  {summary && <span className="block truncate text-xs text-fg/45">{summary}</span>}
                </span>
                {canEdit && <Pencil className="h-4 w-4 shrink-0 text-fg/35" />}
              </>
            )
            return (
              <li key={f.id}>
                {canEdit ? (
                  <button type="button" onClick={() => setEditing({ food: f })}
                    className="flex w-full items-center gap-3 rounded-xl bg-fg/5 px-3 py-2.5 text-left transition-colors hover:bg-fg/10">
                    {inner}
                  </button>
                ) : (
                  <div className="flex w-full items-center gap-3 rounded-xl bg-fg/5 px-3 py-2.5">{inner}</div>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {editing && (
        <FoodSheet
          food={editing.food}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            refresh()
          }}
        />
      )}
    </section>
  )
}
