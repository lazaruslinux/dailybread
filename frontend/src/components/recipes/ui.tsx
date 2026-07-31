import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import * as api from '../../lib/api'
import { useAuth } from '../../auth/AuthContext'
import { SOURCE_LABEL, fmt } from './shared'

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

export function NutritionPanel({ m }: { m: api.RecipeMacros }) {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  // Kid mode: recipes are ingredients and steps, not calorie counts.
  if (user?.is_minor) return null
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

// The identity subline + database badge shown wherever a picked or scanned
// food needs read-and-confirm: the brand and label serving are what you check
// against the package in your hand.
export function FoodIdentity({ food }: { food: Pick<api.Food, 'brand' | 'serving' | 'source'> }) {
  const sub = [food.brand, food.serving].filter(Boolean).join(' · ')
  return (
    <div className="flex items-center gap-2" data-portion-food>
      {sub && <span className="min-w-0 truncate text-xs text-fg/45">{sub}</span>}
      <span className="shrink-0 rounded-md border border-fg/10 bg-fg/5 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-fg/50">
        {SOURCE_LABEL[food.source]}
      </span>
    </div>
  )
}

// A growing library shows its newest couple of entries and folds the rest,
// so the Kitchen stays glanceable however many recipes the family collects.
const LIBRARY_PREVIEW = 2

export function useLibraryPreview<T extends { id: number | null }>(items: T[]) {
  const [showAll, setShowAll] = useState(false)
  const folded = !showAll && items.length > LIBRARY_PREVIEW
  const shown = folded
    ? [...items].sort((a, b) => (b.id ?? 0) - (a.id ?? 0)).slice(0, LIBRARY_PREVIEW)
    : items
  return { shown, folded, showAll, setShowAll }
}

export function LibraryFoldButton({
  total,
  showAll,
  onToggle,
  noun,
}: {
  total: number
  showAll: boolean
  onToggle: () => void
  noun: string
}) {
  if (total <= LIBRARY_PREVIEW) return null
  return (
    <button
      type="button"
      onClick={onToggle}
      className="mt-2 w-full rounded-xl border border-fg/10 bg-fg/5 py-2 text-center text-xs font-semibold text-fg/60 transition-colors hover:bg-fg/10 hover:text-fg"
    >
      {showAll ? 'Show fewer' : `Show all ${total} ${noun}`}
    </button>
  )
}
