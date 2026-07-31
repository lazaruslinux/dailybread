import { Plus, Trash2, X } from 'lucide-react'
import { useMemo, useRef, useState, type FormEvent } from 'react'
import * as api from '../../lib/api'
import { useAuth } from '../../auth/AuthContext'
import { Button, FormError } from '../ui'
import { DiscardGuard, Sheet, useFormDraft } from './Sheet'
import { FoodConfirm, FoodPicker } from './FoodPicker'
import { NutritionPanel } from './ui'
import {
  UNIT_LABEL,
  UNIT_TO_BASE,
  baseAmountOf,
  lineFromSaved,
  nextKey,
  perServing,
  r2,
  servingIndex,
  unitsForBase,
  type EditLine,
} from './shared'

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
  const base = baseAmountOf(line)
  const cals = line.calories != null ? Math.round((line.calories * base) / 100) : null
  // Show the resolved weight/volume when the amount isn't already in the base
  // unit (a serving, or oz/cup/fl oz), so "1 scoop" reads its "32 g" too.
  const showBase = servingIndex(line.unit) != null || line.unit !== line.base_unit
  const baseLabel = `${+base.toFixed(base < 10 ? 1 : 0)} ${UNIT_LABEL[line.base_unit]}`
  const sub = [showBase ? baseLabel : null, cals != null ? `${cals} cal` : null].filter(Boolean).join(' · ')

  // Switching units keeps the physical quantity: convert the amount so the base
  // stays put (2 scoops -> 64 g -> 2.26 oz).
  function changeUnit(next: string) {
    const nsi = servingIndex(next)
    const per = nsi != null ? line.servings[nsi]?.grams || 1 : UNIT_TO_BASE[next as api.AmountUnit] || 1
    onChange({ ...line, unit: next, amount: r2(base / per) })
  }

  // Two rows: the name gets the full card width (long product names were
  // truncated to a few letters beside the controls), and the amount + unit
  // get room beneath — three digits and a "1 pita (60 g)" both fit.
  return (
    <div className="rounded-xl bg-fg/5 px-3 py-2">
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <span className="block truncate text-sm">{line.name}</span>
          {sub && <span className="block text-xs text-fg/45">{sub}</span>}
        </div>
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${line.name}`}
          className="shrink-0 rounded-lg p-1.5 text-fg/40 hover:bg-fg/10 hover:text-danger"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        {/* `.field` is width:100%, so size these by their parents (like the
            servings field does) rather than a width utility it would override. */}
        <div className="w-20 shrink-0">
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
        <div className="min-w-0 flex-1">
          <select
            value={line.unit}
            onChange={(e) => changeUnit(e.target.value)}
            className="field px-2"
            aria-label={`Unit for ${line.name}`}
          >
            {line.servings.length > 0 && (
              <optgroup label="Servings">
                {line.servings.map((s, i) => (
                  <option key={`s${i}`} value={`serving:${i}`}>
                    {s.name}
                  </option>
                ))}
              </optgroup>
            )}
            <optgroup label={line.base_unit === 'ml' ? 'Volume' : 'Weight'}>
              {unitsForBase(line.base_unit).map((u) => (
                <option key={u} value={u}>
                  {UNIT_LABEL[u]}
                </option>
              ))}
            </optgroup>
          </select>
        </div>
      </div>
    </div>
  )
}

// Create or edit a recipe: name, servings, ingredient lines (with a food
// picker), live per-serving nutrition, and steps.
export function RecipeSheet({
  recipe,
  onClose,
  onSaved,
}: {
  recipe: api.Recipe | null
  onClose: () => void
  onSaved: () => void
}) {
  const { user } = useAuth()
  const [name, setName] = useState(recipe?.name ?? '')
  const [servings, setServings] = useState<number | null>(recipe?.servings ?? 1)
  const [lines, setLines] = useState<EditLine[]>(() => (recipe?.ingredients ?? []).map(lineFromSaved))
  const [steps, setSteps] = useState(recipe?.steps ?? '')
  const [picking, setPicking] = useState(false)
  const [pending, setPending] = useState<api.Food | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)

  // Draft + dirty tracking. Only a NEW recipe autosaves (keyed per user); an edit
  // just guards against losing changes. `snapshot` is the whole editable form;
  // dirty = it differs from what we opened with.
  const draftKey = recipe ? null : `db:draft:recipe:${user?.id ?? 0}`
  const snapshot = useMemo(() => JSON.stringify({ name, servings, lines, steps }), [name, servings, lines, steps])
  const initial = useRef(snapshot)
  const dirty = snapshot !== initial.current
  const { restored, clear: clearDraft } = useFormDraft(draftKey, snapshot, dirty, (raw) => {
    try {
      const d = JSON.parse(raw)
      if (typeof d.name === 'string') setName(d.name)
      if (d.servings === null || typeof d.servings === 'number') setServings(d.servings)
      // Re-key restored lines so a fresh session's key sequence can't collide.
      if (Array.isArray(d.lines)) setLines(d.lines.map((l: EditLine) => ({ ...l, key: nextKey() })))
      if (typeof d.steps === 'string') setSteps(d.steps)
    } catch {
      // ignore corrupt draft
    }
  })
  const attemptClose = () => (dirty ? setConfirming(true) : onClose())
  const startFresh = () => {
    setName('')
    setServings(1)
    setLines([])
    setSteps('')
    clearDraft()
  }

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
        .filter((l) => baseAmountOf(l) > 0)
        .map((l) => {
          // A by-serving line is persisted as its resolved base amount + unit
          // (the API stores atomic units, not "2 scoops").
          const bySrv = servingIndex(l.unit) != null
          const amount = bySrv ? r2(baseAmountOf(l)) : l.amount
          const unit = (bySrv ? l.base_unit : l.unit) as api.AmountUnit
          return {
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
            amount,
            unit,
          }
        }),
    }
    try {
      if (recipe) await api.updateRecipe(recipe.id, payload)
      else await api.createRecipe(payload)
      clearDraft()
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not save the recipe.')
    } finally {
      setBusy(false)
    }
  }

  if (picking) {
    // Tapping outside the picker returns to the form, never discards the
    // recipe. A picked/scanned food goes through FoodConfirm (swapped inside
    // this same open Sheet — stacked sheets fight over the body lock) so
    // nothing is appended before it's been read and portioned.
    return (
      <Sheet onClose={() => setPicking(false)}>
        {pending ? (
          <FoodConfirm
            food={pending}
            onBack={() => setPending(null)}
            onAdd={(l) => {
              setLines((ls) => [...ls, l])
              setPending(null)
              setPicking(false)
            }}
          />
        ) : (
          <FoodPicker onBack={() => setPicking(false)} onPick={setPending} />
        )}
      </Sheet>
    )
  }

  return (
    <Sheet onClose={attemptClose}>
      {confirming && (
        <DiscardGuard
          onKeep={() => setConfirming(false)}
          onDiscard={() => {
            clearDraft()
            onClose()
          }}
        />
      )}
      <div className="mb-4 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-accent-bright">
          {recipe ? 'Edit recipe' : 'New recipe'}
        </span>
        <button onClick={attemptClose} aria-label="Close" className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>

      {restored && (
        <div className="mb-3 flex items-center justify-between gap-2 rounded-xl bg-accent-bright/10 px-3 py-2 text-xs">
          <span className="text-fg/70">Picked up your unsaved draft.</span>
          <button type="button" onClick={startFresh} className="shrink-0 font-semibold text-accent-bright hover:opacity-80">
            Start fresh
          </button>
        </div>
      )}

      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">Name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={120}
            placeholder="Taco bowls"
            className="field"
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
              Add foods and their amounts. Nutrition adds up as you go.
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
