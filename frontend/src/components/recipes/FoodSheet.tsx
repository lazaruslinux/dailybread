import { Plus, ScanBarcode, Trash2, X } from 'lucide-react'
import { useMemo, useRef, useState, type FormEvent } from 'react'
import * as api from '../../lib/api'
import { useAuth } from '../../auth/AuthContext'
import { Button, FormError } from '../ui'
import { ShareFoodToVillage } from '../SharedRecipes'
import { DiscardGuard, Sheet, useFormDraft } from './Sheet'
import { UNIT_LABEL, UNIT_TO_BASE, decimal, numOrNull, round2, unitsForBase } from './shared'

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

// Create or edit a custom food, Cronometer-style: a name, one or more named
// servings, and the Nutrition Facts as printed for one chosen serving. The
// values on screen are always "per" the selected serving; switching that serving
// rescales them so they describe the same food. The server stores per-100g.
// A serving size can be typed in the food's base unit or a friendlier one that
// converts to it: grams or ounces for a solid, millilitres or fluid ounces for
// a liquid. It is only an ENTRY unit — storage stays g/mL. Form-wide, not
// per-serving: per-serving units would break changeBasis's gram-ratio rescale.
// The serving-size entry units are just the app's mass/volume units
// (unitsForBase): grams/ounces/pounds for a solid, millilitres/fl-oz/cups/
// tablespoons/teaspoons for a liquid. Storage stays g/mL.
type SizeUnit = api.AmountUnit

export function FoodSheet({
  food,
  prefill = null,
  folders,
  barcode: barcodeProp = null,
  onClose,
  onSaved,
}: {
  food: api.Food | null
  // A source food (barcode/search result) to seed a NEW custom food from — the
  // health-check "save as custom food" path. Ignored when `food` is set (an
  // edit); seeds name/brand/measure/servings/nutrition but stays a create, so
  // submit posts a new food instead of trying to PUT the un-saved cache row.
  prefill?: api.Food | null
  // Existing folder names across the family's foods, for the picker's datalist.
  folders: string[]
  // Prefilled product code when the sheet opens off an unknown barcode scan.
  barcode?: string | null
  onClose: () => void
  onSaved: (saved?: api.Food) => void
}) {
  const editing = food !== null
  // The row whose values seed the fields: the edited food, or a prefill source
  // for a fresh food. `editing` still keys off `food` alone, so a prefill never
  // becomes an update.
  const seed = food ?? prefill
  // A custom food's source_id is its barcode; keep it across edits so a food
  // scanned-and-entered once stays findable by its code.
  const barcode = food?.source_id ?? barcodeProp
  const { user } = useAuth()
  const [name, setName] = useState(seed?.name ?? '')
  const [brand, setBrand] = useState(seed?.brand ?? '')
  const [folder, setFolder] = useState(food?.folder ?? '')
  // Weight (g) or Volume (mL). A liquid's label serving is a volume, so its
  // sizes and nutrition are entered and stored against millilitres.
  const [baseUnit, setBaseUnit] = useState<api.BaseUnit>(seed?.base_unit ?? 'g')
  // The entry unit for serving sizes. An edited food ALWAYS opens in its base
  // unit (a food entered as 1 oz reopens as 28.35 g): lossless and honest,
  // where converting back to oz would only guess intent. Storage is always the
  // base unit; this just softens data entry.
  const [sizeUnit, setSizeUnit] = useState<SizeUnit>(seed?.base_unit ?? 'g')
  const [servings, setServings] = useState<ServingDraft[]>(() =>
    seed && seed.servings.length
      ? seed.servings.map((s) => ({ name: s.name, grams: String(s.grams) }))
      : [{ name: '', grams: '' }],
  )
  const [basis, setBasis] = useState(0)
  // Nutrition shown per the basis serving. Seed from the stored per-100g figures
  // scaled to the first serving's grams (an edit, or a prefill source food).
  const [nutri, setNutri] = useState<Record<NutriKey, string>>(() => {
    if (!seed) return emptyNutri()
    const g = seed.servings[0]?.grams ?? 100
    const out = emptyNutri()
    for (const k of NUTRI_KEYS) {
      const v = seed[k]
      if (v != null) out[k] = String(round2((v * g) / 100))
    }
    return out
  })
  const [busy, setBusy] = useState(false)
  const [armed, setArmed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  // Draft + dirty tracking, mirroring RecipeSheet: only a NEW food autosaves.
  const draftKey = editing ? null : `db:draft:food:${user?.id ?? 0}`
  const snapshot = useMemo(
    () => JSON.stringify({ name, brand, folder, baseUnit, sizeUnit, servings, basis, nutri }),
    [name, brand, folder, baseUnit, sizeUnit, servings, basis, nutri],
  )
  const initialSnap = useRef(snapshot)
  const dirty = snapshot !== initialSnap.current
  const { restored, clear: clearDraft } = useFormDraft(draftKey, snapshot, dirty, (raw) => {
    try {
      const d = JSON.parse(raw)
      if (typeof d.name === 'string') setName(d.name)
      if (typeof d.brand === 'string') setBrand(d.brand)
      if (typeof d.folder === 'string') setFolder(d.folder)
      if (d.baseUnit === 'g' || d.baseUnit === 'ml') setBaseUnit(d.baseUnit)
      if (d.sizeUnit in UNIT_TO_BASE) setSizeUnit(d.sizeUnit)
      if (Array.isArray(d.servings)) setServings(d.servings)
      if (typeof d.basis === 'number') setBasis(d.basis)
      if (d.nutri && typeof d.nutri === 'object') setNutri({ ...emptyNutri(), ...d.nutri })
    } catch {
      // ignore corrupt draft
    }
  })
  const attemptClose = () => (dirty ? setConfirming(true) : onClose())
  const startFresh = () => {
    setName('')
    setBrand('')
    setFolder('')
    setBaseUnit('g')
    setSizeUnit('g')
    setServings([{ name: '', grams: '' }])
    setBasis(0)
    setNutri(emptyNutri())
    clearDraft()
  }

  // Flip weight <-> volume. Serving names are the user's own words now (no
  // "100 g" default to retitle); entered numbers stay put (we can't convert a
  // weight to a volume without a density).
  function changeBase(next: api.BaseUnit) {
    setBaseUnit(next)
    // The entry unit follows the measure family; numbers stay put (no density).
    setSizeUnit(next)
  }

  // Retype the serving sizes in a friendlier unit, converting the non-empty
  // values in place so the physical size is preserved (100 g -> 3.53 oz).
  function changeSizeUnit(next: SizeUnit) {
    const ratio = UNIT_TO_BASE[sizeUnit] / UNIT_TO_BASE[next]
    setServings((ls) =>
      ls.map((s) => {
        const v = Number(s.grams)
        return s.grams === '' || !Number.isFinite(v) ? s : { ...s, grams: String(round2(v * ratio)) }
      }),
    )
    setSizeUnit(next)
  }

  const setServing = (i: number, s: ServingDraft) =>
    setServings((ls) => ls.map((l, j) => (j === i ? s : l)))
  const addServing = () => setServings((ls) => [...ls, { name: '', grams: '' }])
  const removeServing = (i: number) => {
    // Two sibling updates, never one inside the other's updater: an impure
    // updater double-fires under StrictMode and mis-shifts the basis in dev.
    setServings((ls) => ls.filter((_, j) => j !== i))
    setBasis((b) => (i < b ? b - 1 : Math.min(b, servings.length - 2)))
  }

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
    // The typed size is in sizeUnit; store it in the base unit (g or mL).
    const cleaned = servings.map((s) => ({
      name: s.name.trim(),
      grams: round2(Number(s.grams) * UNIT_TO_BASE[sizeUnit]),
    }))
    if (!name.trim()) return setError('Give the food a name.')
    if (!cleaned.every((s) => s.name && s.grams > 0))
      return setError(`Every serving needs a name and a size in ${UNIT_LABEL[sizeUnit]}.`)

    setBusy(true)
    setError(null)
    const payload: api.CustomFoodPayload = {
      name: name.trim(),
      brand: brand.trim(),
      folder: folder.trim() || null,
      barcode,
      base_unit: baseUnit,
      // Straight from the scanned source, like the health-check fields below:
      // a saved copy converts between weight and volume the way its cache row
      // did. Nothing here derives one from the serving sizes typed above.
      density_g_per_ml: seed?.density_g_per_ml ?? null,
      servings: cleaned,
      basis_index: basis,
      // Carry the source's health-check label data straight through (already
      // per-100), so a food saved from a scan still judges its real ingredients
      // when its barcode is scanned again. Null for hand-made foods. Sliced to
      // the FoodIn caps: source strings are uncapped and an over-long OFF
      // ingredient list must not 422 a field the member can't see.
      ingredients_text: seed?.ingredients_text?.slice(0, 4000) ?? null,
      added_sugar_g: seed?.added_sugar_g ?? null,
      additives: seed?.additives?.slice(0, 1000) ?? null,
      nova_group: seed?.nova_group ?? null,
      ...(Object.fromEntries(NUTRI_KEYS.map((k) => [k, numOrNull(nutri[k])])) as Record<NutriKey, number | null>),
    }
    try {
      const saved = editing
        ? await api.updateCustomFood(food.id!, payload)
        : await api.createCustomFood(payload)
      clearDraft()
      onSaved(saved)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not save the food.')
    } finally {
      setBusy(false)
    }
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
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-accent-bright">
          {editing ? 'Edit food' : 'New food'}
        </span>
        <button onClick={attemptClose} aria-label="Close" className="-m-1.5 rounded-lg p-3 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>

      {barcode && (
        <p className="-mt-2 mb-3 flex items-center gap-1.5 text-xs text-fg/50" data-barcode-chip>
          <ScanBarcode className="h-3.5 w-3.5" /> Barcode {barcode}
          {!editing && ' · enter its label once and future scans find it instantly'}
        </p>
      )}

      {restored && (
        <div className="mb-3 flex items-center justify-between gap-2 rounded-xl bg-accent-bright/10 px-3 py-2 text-xs">
          <span className="text-fg/70">Picked up your unsaved draft.</span>
          <button type="button" onClick={startFresh} className="shrink-0 font-semibold text-accent-bright hover:opacity-80">
            Start fresh
          </button>
        </div>
      )}

      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={200}
            placeholder="e.g. Clif Bar, Peanut Butter" className="field" />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">Brand (optional)</span>
          <input value={brand} onChange={(e) => setBrand(e.target.value)} maxLength={120}
            placeholder="e.g. Clif" className="field" />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">Folder (optional)</span>
          <input value={folder} onChange={(e) => setFolder(e.target.value)} maxLength={60}
            list="db-food-folders" placeholder="e.g. Panda Express" className="field" />
          <datalist id="db-food-folders">
            {folders.map((f) => (
              <option key={f} value={f} />
            ))}
          </datalist>
        </label>

        <div>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">Serving sizes</span>
            {/* Weight vs volume: a liquid (syrup, milk) is labelled by mL, not g. */}
            <div className="flex rounded-full border border-fg/10 bg-fg/5 p-0.5 text-[11px] font-semibold">
              {(['g', 'ml'] as api.BaseUnit[]).map((b) => (
                <button key={b} type="button" onClick={() => changeBase(b)} aria-pressed={baseUnit === b}
                  className={`rounded-full px-2.5 py-0.5 transition-colors ${
                    baseUnit === b ? 'bg-accent-bright/25 text-fg' : 'text-fg/55 hover:text-fg'
                  }`}>
                  {b === 'g' ? 'Weight' : 'Volume'}
                </button>
              ))}
            </div>
          </div>
          <p className="mb-2 text-xs text-fg/45">
            As printed on the package. The {baseUnit === 'ml' ? 'volume' : 'weight'} in{' '}
            {UNIT_LABEL[sizeUnit]} is what lets a serving add up in recipes.
          </p>
          <div className="flex flex-col gap-1.5">
            {servings.map((s, i) => (
              <div key={i} className="flex items-center gap-2">
                <input value={s.name} onChange={(e) => setServing(i, { ...s, name: e.target.value })}
                  maxLength={60} placeholder={baseUnit === 'ml' ? '1 cup, 2 tbsp' : '1 bar, 17 chips'}
                  className="field min-w-0 flex-1" aria-label={`Serving ${i + 1} name`} />
                <div className="flex shrink-0 items-center gap-1">
                  <input inputMode="decimal" value={s.grams}
                    onChange={(e) => setServing(i, { ...s, grams: decimal(e.target.value) })}
                    placeholder="100" style={{ width: '3.75rem' }}
                    className="field shrink-0 px-2 text-right"
                    aria-label={`Serving ${i + 1} size in ${UNIT_LABEL[sizeUnit]}`} />
                  {/* Inline width like the grams input beside it: .field sets
                      its own width, so a w-* utility loses to it, and desktop
                      renders native selects far wider than iOS — without this
                      the select swallows the delete button and the row
                      overflows the sheet. */}
                  <select value={sizeUnit} onChange={(e) => changeSizeUnit(e.target.value as SizeUnit)}
                    style={{ width: '4rem' }}
                    className="field min-h-11 shrink-0 px-1.5 text-xs" aria-label={`Serving ${i + 1} unit`}>
                    {unitsForBase(baseUnit).map((u) => (
                      <option key={u} value={u}>{UNIT_LABEL[u]}</option>
                    ))}
                  </select>
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

        {/* Share/unshare from the food itself, the recipe sheet's treatment.
            A new food has no id to share yet, so only edits show it. */}
        {editing && <ShareFoodToVillage food={food} />}

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
