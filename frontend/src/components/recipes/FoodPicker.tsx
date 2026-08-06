import { Bookmark, BookmarkCheck, ChevronLeft, Pencil, ScanBarcode, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import * as api from '../../lib/api'
import { Button, FormError } from '../ui'
import { BarcodeScanner } from '../BarcodeScanner'
import { FoodSheet } from './FoodSheet'
import { FoodIdentity } from './ui'
import {
  EDIT_MACROS,
  SOURCE_LABEL,
  WATER_ASSUMED_HINT,
  UNIT_GROUPS,
  UNIT_LABEL,
  baseAmountOf,
  decimalOnly,
  foldersOf,
  implausibleMacros,
  assumesWater,
  lineFromFood,
  r2,
  servingIndex,
  toBase,
  type EditLine,
  type MacroValues,
} from './shared'

// The food picker: search the USDA database (server-proxied), the family's
// own custom foods, or scan a product barcode — tap a result to add it as an
// ingredient. An unknown barcode opens the New Food form prefilled with the
// code, so entering it once teaches the app the product for good.
export function FoodPicker({ onPick, onBack }: { onPick: (food: api.Food) => void; onBack: () => void }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<api.Food[]>([])
  const [custom, setCustom] = useState<api.Food[]>([])
  const [recent, setRecent] = useState<api.Food[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [scanning, setScanning] = useState(false)
  const [looking, setLooking] = useState(false)
  const [unknownCode, setUnknownCode] = useState<string | null>(null)

  async function scanned(code: string) {
    setScanning(false)
    setLooking(true)
    setError(null)
    try {
      onPick(await api.lookupBarcode(code))
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 404) setUnknownCode(code)
      else setError(err instanceof api.ApiError ? err.message : 'Barcode lookup failed.')
    } finally {
      setLooking(false)
    }
  }

  const [saved, setSaved] = useState<api.Food[]>([])

  // The family's custom foods are always shown (they're a short list); load
  // once, with the recently-used and saved shelves alongside.
  useEffect(() => {
    api.getCustomFoods().then(setCustom).catch(() => {})
    api.getRecentFoods().then(setRecent).catch(() => {})
    api.getSavedFoods().then(setSaved).catch(() => {})
  }, [])

  // A food's saved-state matches by id when it has one, else by its source
  // identity (a fresh search result has no id until something stores it).
  const savedKey = (f: api.Food) => (f.id != null ? `#${f.id}` : `${f.source}:${f.source_id}`)
  const savedKeys = useMemo(() => {
    const keys = new Set<string>()
    for (const f of saved) {
      keys.add(`#${f.id}`)
      if (f.source_id) keys.add(`${f.source}:${f.source_id}`)
    }
    return keys
  }, [saved])

  async function toggleSaved(food: api.Food) {
    if (savedKeys.has(savedKey(food))) {
      const pin = saved.find(
        (f) => f.id === food.id || (food.source_id != null && f.source === food.source && f.source_id === food.source_id),
      )
      if (pin?.id == null) return
      setSaved((list) => list.filter((f) => f.id !== pin.id))
      try {
        await api.unsaveFood(pin.id)
      } catch {
        api.getSavedFoods().then(setSaved).catch(() => {})
      }
    } else {
      try {
        const stored = await api.saveFood({
          food_id: food.id,
          source: food.source,
          source_id: food.source_id,
          name: food.name,
          brand: food.brand,
          base_unit: food.base_unit,
          density_g_per_ml: food.density_g_per_ml,
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
        })
        setSaved((list) => [stored, ...list])
      } catch {
        // the bookmark stays hollow; the next tap tries again
      }
    }
  }

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
    // Cronometer-style: name on top, the brand + label serving beneath, the
    // source database as a badge, and a bookmark to pin database foods to
    // the family's Saved Foods (custom foods are already kept).
    const sub = [food.brand, food.serving].filter(Boolean).join(' · ')
    const pinned = savedKeys.has(savedKey(food))
    return (
      <div className="flex w-full items-center gap-1">
        <button
          type="button"
          onClick={() => onPick(food)}
          className="flex min-w-0 flex-1 items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-fg/10"
        >
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{food.name}</span>
            {sub && <span className="block truncate text-xs text-fg/45">{sub}</span>}
          </span>
          <span className="shrink-0 rounded-md border border-fg/10 bg-fg/5 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-fg/50">
            {SOURCE_LABEL[food.source]}
          </span>
        </button>
        {food.source !== 'custom' && (
          <button
            type="button"
            onClick={() => void toggleSaved(food)}
            aria-label={pinned ? `Remove ${food.name} from saved foods` : `Save ${food.name}`}
            className={`shrink-0 rounded-lg p-1.5 transition-colors hover:bg-fg/10 ${pinned ? 'text-gold' : 'text-fg/35'}`}
          >
            {pinned ? (
              <BookmarkCheck className="h-4 w-4" strokeWidth={2.5} />
            ) : (
              <Bookmark className="h-4 w-4" strokeWidth={2} />
            )}
          </button>
        )}
      </div>
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

      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg/40" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search foods (e.g. chicken breast)"
            className="field"
            // Inline pad-left clears the search icon; a `pl-9` utility loses to
            // `.field`'s own padding (same specificity, .field defined later).
            // No autoFocus: the sheet opens calm, the keyboard comes when asked.
            style={{ paddingLeft: '2.25rem' }}
          />
        </div>
        <button
          type="button"
          onClick={() => setScanning(true)}
          aria-label="Scan a barcode"
          className="shrink-0 rounded-xl border border-fg/10 bg-fg/5 p-2.5 text-fg/70 transition-colors hover:bg-fg/10 hover:text-fg"
          data-scan
        >
          <ScanBarcode className="h-5 w-5" />
        </button>
      </div>

      <FormError message={error} />
      {looking && <p className="mt-2 px-1 text-sm text-fg/50">Looking up the barcode…</p>}

      <div className="mt-3 flex flex-col gap-3">
        {q.trim().length < 2 && saved.length > 0 && (
          <div>
            <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-fg/40">
              Saved foods
            </span>
            <div className="flex flex-col">
              {saved.map((f) => (
                <Row key={`s${f.id}`} food={f} />
              ))}
            </div>
          </div>
        )}

        {q.trim().length < 2 && recent.length > 0 && (
          <div>
            <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-fg/40">
              Recently used
            </span>
            <div className="flex flex-col">
              {recent.map((f) => (
                <Row key={`r${f.id}`} food={f} />
              ))}
            </div>
          </div>
        )}

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

        {q.trim().length < 2 && shownCustom.length === 0 && recent.length === 0 && (
          <p className="px-2.5 py-6 text-center text-sm text-fg/45">
            Type to search the food database, scan a barcode, or add custom foods first.
          </p>
        )}
      </div>

      {scanning && <BarcodeScanner onCode={scanned} onClose={() => setScanning(false)} />}
      {unknownCode && (
        // Nothing knows this product yet: enter its label once (barcode kept),
        // and it lands straight into the recipe as the picked ingredient.
        <FoodSheet
          food={null}
          folders={foldersOf(custom)}
          barcode={unknownCode}
          onClose={() => setUnknownCode(null)}
          onSaved={(saved) => {
            setUnknownCode(null)
            if (saved) onPick(saved)
          }}
        />
      )}
    </div>
  )
}

// Confirm a picked or scanned food before it joins the recipe: read the name
// against the package, set the portion, then Add. Nothing lands silently.
export function FoodConfirm({
  food,
  onAdd,
  onBack,
}: {
  food: api.Food
  onAdd: (l: EditLine) => void
  onBack: () => void
}) {
  const [line, setLine] = useState<EditLine>(() => lineFromFood(food))
  const base = baseAmountOf(line)
  const cals = line.calories != null ? Math.round((line.calories * base) / 100) : null
  const baseLabel = `${+base.toFixed(base < 10 ? 1 : 0)} ${UNIT_LABEL[line.base_unit]}`
  const assumed = assumesWater(line, line.unit)

  function changeUnit(next: string) {
    const nsi = servingIndex(next)
    // What ONE of the new unit is worth in base units, density included, so the
    // physical quantity survives the switch (2 scoops -> 64 g -> 2.26 oz).
    const per = nsi != null ? line.servings[nsi]?.grams || 1 : toBase(line, 1, next) || 1
    setLine({ ...line, unit: next, amount: r2(base / per) })
  }

  // The label editor, the same offer the diary's portion sheet makes: scanned
  // data is often incomplete (Open Food Facts frequently has no carbs) or
  // self-contradictory, and this is the last look before it becomes a recipe's
  // nutrition. Always reachable by the pencil; opens by itself when the numbers
  // are missing or don't add up.
  const portion = (v: number | null) => (v != null ? (v * base) / 100 : null)
  const shown = {
    calories: portion(line.calories),
    protein_g: portion(line.protein_g),
    carbs_g: portion(line.carbs_g),
    fat_g: portion(line.fat_g),
    // Not shown, but the plausibility check is built on sugars.
    sugar_g: portion(line.sugar_g),
  }
  const missing = EDIT_MACROS.some((f) => shown[f.key] == null)
  const dontAddUp = !missing && implausibleMacros(shown)
  const [editing, setEditing] = useState(() => missing || dontAddUp)
  const seedValues = (): MacroValues => ({
    calories: shown.calories != null ? String(Math.round(shown.calories)) : '',
    protein_g: shown.protein_g != null ? String(Math.round(shown.protein_g)) : '',
    carbs_g: shown.carbs_g != null ? String(Math.round(shown.carbs_g)) : '',
    fat_g: shown.fat_g != null ? String(Math.round(shown.fat_g)) : '',
  })
  const [values, setValues] = useState<MacroValues>(seedValues)

  // Changing the amount or the unit rescales the portion, so the fields re-seed
  // to the freshly scaled numbers: an edit sits on top of a settled portion,
  // never beside a stale one. (The diary's portion sheet does the same.)
  useEffect(() => {
    setValues(seedValues())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base])

  // The line stores per-100 figures, so an edited portion is divided back out.
  // A zero-size portion has nothing to divide by, so the field is only recorded.
  function editMacro(key: keyof MacroValues, raw: string) {
    const next = decimalOnly(raw)
    setValues((prev) => ({ ...prev, [key]: next }))
    if (base <= 0) return
    const typed = next.trim() === '' ? null : Number(next)
    setLine((l) => ({
      ...l,
      [key]: typed != null && Number.isFinite(typed) ? r2((typed * 100) / base) : null,
    }))
  }

  return (
    <div data-food-confirm>
      <div className="mb-3 flex items-center gap-2">
        <button onClick={onBack} aria-label="Back" className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <ChevronLeft className="h-5 w-5" />
        </button>
        <span className="text-xs font-semibold uppercase tracking-wide text-accent-bright">Add ingredient</span>
      </div>

      <h2 className="text-lg font-bold leading-snug">{food.name}</h2>
      <div className="mt-1">
        <FoodIdentity food={food} />
      </div>

      <div className="mt-4 flex items-center gap-2">
        <div className="w-20 shrink-0">
          <input
            inputMode="decimal"
            value={line.amount === 0 ? '' : String(line.amount)}
            onChange={(e) => {
              const v = e.target.value.replace(/[^0-9.]/g, '')
              setLine({ ...line, amount: v === '' ? 0 : Number(v) })
            }}
            className="field px-2 text-center"
            aria-label={`Amount of ${food.name}`}
          />
        </div>
        <div className="min-w-0 flex-1">
          <select value={line.unit} onChange={(e) => changeUnit(e.target.value)} className="field px-2" aria-label={`Unit for ${food.name}`}>
            {line.servings.length > 0 && (
              <optgroup label="Servings">
                {line.servings.map((s, i) => (
                  <option key={`s${i}`} value={`serving:${i}`}>
                    {s.name}
                  </option>
                ))}
              </optgroup>
            )}
            {/* Both families: a cross-family amount converts through the
                food's density (or water, which the hint below names). */}
            {UNIT_GROUPS.map((g) => (
              <optgroup key={g.label} label={g.label}>
                {g.units.map((u) => (
                  <option key={u} value={u}>
                    {UNIT_LABEL[u]}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
      </div>
      <p className="mt-1.5 px-1 text-xs text-fg/45">{[baseLabel, cals != null ? `${cals} cal` : null].filter(Boolean).join(' · ')}</p>
      {assumed && <p className="px-1 text-xs text-fg/45">{WATER_ASSUMED_HINT}</p>}

      <div className="mt-3 rounded-xl border border-fg/10 bg-fg/5 px-3.5 py-2.5">
        {editing ? (
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <span className="db-micro">This ingredient</span>
              <button
                type="button"
                onClick={() => setEditing(false)}
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
                    value={values[f.key]}
                    placeholder="Add"
                    onChange={(e) => editMacro(f.key, e.target.value)}
                    className={`field ${values[f.key] === '' ? 'ring-1 ring-amber-400/60' : ''}`}
                  />
                </label>
              ))}
            </div>
            {dontAddUp && (
              <p className="text-[11px] leading-snug text-amber-500">
                These numbers don't add up; check them against the label.
              </p>
            )}
            {missing && (
              <p className="text-[11px] leading-snug text-amber-500">
                The highlighted macros weren't in the scan. Add them from the package label if you have it.
              </p>
            )}
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="-my-2.5 flex min-h-11 w-full items-center justify-between gap-2 py-2.5 text-left"
          >
            <span className="text-sm font-semibold text-accent-bright">
              {[
                cals != null ? `${cals} cal` : '— cal',
                shown.protein_g != null ? `${Math.round(shown.protein_g)}g protein` : null,
                shown.carbs_g != null ? `${Math.round(shown.carbs_g)}g carbs` : null,
                shown.fat_g != null ? `${Math.round(shown.fat_g)}g fat` : null,
              ]
                .filter(Boolean)
                .join(' · ')}
            </span>
            <Pencil className="h-4 w-4 shrink-0 text-fg/40" />
          </button>
        )}
      </div>

      <Button type="button" onClick={() => onAdd(line)} disabled={line.amount <= 0} className="mt-4 w-full">
        Add to recipe
      </Button>
    </div>
  )
}
