import * as api from '../../lib/api'

// How many base units (g for a solid, mL for a liquid) one of each unit is.
// Mirrors the backend UNIT_TO_BASE — nutrition is computed live here as the cook
// edits. A food is measured in only one family; the two never mix on a line.
export const UNIT_TO_BASE: Record<api.AmountUnit, number> = {
  g: 1, oz: 28.3495, lb: 453.592,
  ml: 1, floz: 29.5735, cup: 236.588, tbsp: 14.7868, tsp: 4.92892,
}
const MASS_UNITS: api.MassUnit[] = ['g', 'oz', 'lb']
const VOLUME_UNITS: api.VolumeUnit[] = ['ml', 'floz', 'cup', 'tbsp', 'tsp']
export const unitsForBase = (base: api.BaseUnit): api.AmountUnit[] => (base === 'ml' ? VOLUME_UNITS : MASS_UNITS)
const baseUnitOf = (unit: string): api.BaseUnit =>
  (VOLUME_UNITS as string[]).includes(unit) ? 'ml' : 'g'
// How each unit reads on screen (only "floz" differs from its token).
export const UNIT_LABEL: Record<string, string> = {
  g: 'g', oz: 'oz', lb: 'lb', ml: 'mL', floz: 'fl oz', cup: 'cup', tbsp: 'tbsp', tsp: 'tsp',
}
export const r2 = (n: number) => Math.round(n * 100) / 100

// A serving selection is encoded as the pseudo-unit "serving:<index>", so one
// dropdown can offer both a food's named servings and its raw units.
export const servingIndex = (unit: string): number | null =>
  unit.startsWith('serving:') ? Number(unit.slice(8)) : null

// An ingredient line while editing: the food's per-100(base) macros travel with
// it so totals recompute instantly, without a round-trip, when the amount
// changes. `base_unit` is the food's measure family; `servings` its named
// portions (for the by-serving picker) — both empty/"g" for a database food.
export interface EditLine {
  key: string
  food_id: number | null
  source: api.FoodSource
  source_id: string | null
  name: string
  brand: string
  base_unit: api.BaseUnit
  servings: api.FoodServing[]
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
  unit: string // an AmountUnit, or "serving:<index>"
}

let _keySeq = 0
export const nextKey = () => `l${_keySeq++}`

export function lineFromFood(food: api.Food): EditLine {
  // Default to the label serving when the food has named portions ("1 scoop"),
  // else to 100 of its base unit — the amount you'd tweak from.
  const hasServings = food.servings.length > 0
  return {
    key: nextKey(),
    food_id: food.id,
    source: food.source,
    source_id: food.source_id,
    name: food.name,
    brand: food.brand,
    base_unit: food.base_unit,
    servings: food.servings,
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
    amount: hasServings ? 1 : 100,
    unit: hasServings ? 'serving:0' : food.base_unit,
  }
}

// Rebuild an editor line from a saved recipe line. The API sends each macro
// already scaled to the line's base amount, so back out the per-100 figure the
// editor works in (base amount is always > 0 for a saved line). A saved line
// carries no named servings, so it redisplays in its stored unit.
export function lineFromSaved(ing: api.RecipeIngredient): EditLine {
  const per100 = (v: number | null) => (v != null && ing.grams > 0 ? (v * 100) / ing.grams : null)
  const unit = ing.unit in UNIT_TO_BASE ? ing.unit : 'g'
  return {
    key: nextKey(),
    food_id: ing.food_id,
    source: ing.source,
    source_id: ing.source_id,
    name: ing.name,
    brand: ing.brand,
    base_unit: baseUnitOf(unit),
    servings: [],
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
    unit,
  }
}

// The line's amount expressed in the food's base unit (grams or millilitres),
// resolving a by-serving selection to its base size.
export function baseAmountOf(l: EditLine): number {
  const si = servingIndex(l.unit)
  if (si != null) return l.amount * (l.servings[si]?.grams ?? 0)
  return l.amount * (UNIT_TO_BASE[l.unit as api.AmountUnit] ?? 1)
}
const gramsOf = baseAmountOf

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
export function perServing(lines: EditLine[], servings: number): api.RecipeMacros {
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

export const fmt = (n: number | null) => (n != null ? String(Math.round(n)) : '—')

// "125 cal · 13P / 20C / 9F" per serving, skipping any macro nothing supplied.
export function macroSummary(m: api.RecipeMacros): string {
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

export const SOURCE_LABEL: Record<api.FoodSource, string> = { usda: 'USDA', off: 'OFF', custom: 'Custom' }

export const round2 = (n: number) => Math.round(n * 100) / 100
export const numOrNull = (s: string) => (s.trim() === '' ? null : Number(s))
export const decimal = (s: string) => s.replace(/[^0-9.]/g, '')

// A one-line summary for a custom-food row: its first serving and that serving's
// calories, backed out of the per-100-base figure we store. Kid mode drops the
// calorie figure (showCal false) and keeps the serving name.
export function foodSummary(f: api.Food, showCal = true): string {
  const s = f.servings[0]
  const cal = (grams: number) =>
    showCal && f.calories != null ? `${Math.round((f.calories * grams) / 100)} cal` : ''
  const parts = [f.brand]
  if (s) parts.push([s.name, cal(s.grams)].filter(Boolean).join(' · '))
  else if (showCal && f.calories != null)
    parts.push(`${Math.round(f.calories)} cal / 100 ${UNIT_LABEL[f.base_unit]}`)
  return parts.filter(Boolean).join(' · ')
}

// A custom food's stored nutrition is per-100-base; people think in servings, so
// the detail view shows it per the food's first (label) serving, backed out the
// same way `foodSummary` backs out its calories. Falls back to per-100 when a
// food has no named serving. Nulls stay null so "unknown" reads as "—".
export function servingNutrition(f: api.Food): { macros: api.RecipeMacros; per: string } {
  const s = f.servings[0]
  const factor = s && s.grams > 0 ? s.grams / 100 : 1
  const scale = (v: number | null | undefined) => (v == null ? null : r2(v * factor))
  const macros = {
    calories: scale(f.calories),
    protein_g: scale(f.protein_g),
    carbs_g: scale(f.carbs_g),
    fat_g: scale(f.fat_g),
    saturated_fat_g: scale(f.saturated_fat_g),
    trans_fat_g: scale(f.trans_fat_g),
    cholesterol_mg: scale(f.cholesterol_mg),
    sodium_mg: scale(f.sodium_mg),
    fiber_g: scale(f.fiber_g),
    sugar_g: scale(f.sugar_g),
  } as api.RecipeMacros
  const per = s ? `Per ${s.name}` : `Per 100 ${UNIT_LABEL[f.base_unit]}`
  return { macros, per }
}

// The folder names in use across a family's foods, unique and alphabetical, for
// the folder picker's suggestions and the grouped custom-food view.
export const foldersOf = (foods: api.Food[]): string[] =>
  [...new Set(foods.map((f) => f.folder).filter((f): f is string => !!f))].sort((a, b) =>
    a.localeCompare(b),
  )
