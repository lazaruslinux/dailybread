import { Bookmark, BookmarkCheck, ChevronLeft, ScanBarcode, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import * as api from '../../lib/api'
import { Button, FormError } from '../ui'
import { BarcodeScanner } from '../BarcodeScanner'
import { FoodSheet } from './FoodSheet'
import { FoodIdentity } from './ui'
import {
  SOURCE_LABEL,
  UNIT_LABEL,
  UNIT_TO_BASE,
  baseAmountOf,
  foldersOf,
  lineFromFood,
  r2,
  servingIndex,
  unitsForBase,
  type EditLine,
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

  function changeUnit(next: string) {
    const nsi = servingIndex(next)
    const per = nsi != null ? line.servings[nsi]?.grams || 1 : UNIT_TO_BASE[next as api.AmountUnit] || 1
    setLine({ ...line, unit: next, amount: r2(base / per) })
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
      <p className="mt-1.5 px-1 text-xs text-fg/45">{[baseLabel, cals != null ? `${cals} cal` : null].filter(Boolean).join(' · ')}</p>

      <Button type="button" onClick={() => onAdd(line)} disabled={line.amount <= 0} className="mt-4 w-full">
        Add to recipe
      </Button>
    </div>
  )
}
