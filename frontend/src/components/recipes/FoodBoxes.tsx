import { BookmarkCheck, ChevronRight, FolderOpen, Pencil, Plus, Share2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../../lib/api'
import { useAuth } from '../../auth/AuthContext'
import { Button, FormError } from '../ui'
import { CollapsibleCard } from '../CollapsibleCard'
import { ShareFoodToVillage } from '../SharedRecipes'
import { Sheet } from './Sheet'
import { FoodSheet } from './FoodSheet'
import { LibraryFoldButton, NutritionPanel, useLibraryPreview } from './ui'
import { UNIT_LABEL, foldersOf, foodSummary, servingNutrition } from './shared'

// The family's Saved Foods: search or barcode results pinned for quick
// re-use. Unpinning never deletes the food itself.
export function SavedFoodBox() {
  const { user } = useAuth()
  const canEdit = user?.role === 'parent'
  const [foods, setFoods] = useState<api.Food[]>([])
  const [error, setError] = useState<string | null>(null)
  const preview = useLibraryPreview(foods)

  const refresh = useCallback(async () => {
    try {
      setFoods(await api.getSavedFoods())
      setError(null)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load saved foods.')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  async function unpin(food: api.Food) {
    if (food.id == null) return
    setFoods((list) => list.filter((f) => f.id !== food.id))
    try {
      await api.unsaveFood(food.id)
    } catch {
      refresh() // the pin stays; the next tap tries again
    }
  }

  return (
    <CollapsibleCard
      title="Saved foods"
      summary={foods.length ? String(foods.length) : undefined}
      storageKey="saved-foods"
      flush
    >
      <div className="px-3.5">
        <FormError message={error} />
      </div>
      {foods.length === 0 ? (
        <p className="db-emptyline">
          Tap the bookmark on any food you search or scan to keep it here for quick re-use.
        </p>
      ) : (
        <ul>
          {preview.shown.map((f) => {
            const summary = foodSummary(f, canEdit)
            return (
              <li key={f.id} className="db-row">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[0.90625rem] font-medium">
                    {f.brand ? `${f.brand}, ${f.name}` : f.name}
                  </span>
                  {summary && <span className="block truncate text-[0.78125rem] text-fg/45">{summary}</span>}
                </span>
                {canEdit && (
                  <button
                    type="button"
                    onClick={() => unpin(f)}
                    aria-label={`Remove ${f.name} from saved foods`}
                    className="-m-2.5 shrink-0 rounded-lg p-3.5 text-gold transition-colors hover:bg-fg/10"
                  >
                    <BookmarkCheck className="h-4 w-4" strokeWidth={2.5} />
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
      <LibraryFoldButton
        total={foods.length}
        showAll={preview.showAll}
        onToggle={() => preview.setShowAll((v) => !v)}
        noun="foods"
      />
    </CollapsibleCard>
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
  // Tapping a food opens a read-only detail first (what's inside + Edit/Share),
  // rather than dropping straight into the editor.
  const [detail, setDetail] = useState<api.Food | null>(null)
  const preview = useLibraryPreview(foods)
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
    // A copy saved off the Village Shelf lands in this list without a tab
    // round-trip.
    window.addEventListener('db:foods-changed', refresh)
    return () => {
      mounted.current = false
      window.removeEventListener('db:foods-changed', refresh)
    }
  }, [refresh])

  const renderFood = (f: api.Food) => {
    const summary = foodSummary(f, canEdit)
    const inner = (
      <>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[0.90625rem] font-medium">{f.name}</span>
          {summary && <span className="block truncate text-[0.78125rem] text-fg/45">{summary}</span>}
        </span>
        {f.shared_to.length > 0 && (
          <span className="db-chip db-chip-gold flex items-center gap-1">
            <Share2 className="h-3 w-3" /> Shared
          </span>
        )}
        {canEdit && <ChevronRight className="h-4 w-4 shrink-0 text-fg/35" />}
      </>
    )
    return (
      <li key={f.id} className={`db-row ${canEdit ? 'transition-colors hover:bg-fg/5' : ''}`}>
        {canEdit ? (
          <button type="button" onClick={() => setDetail(f)}
            className="-my-2 flex min-h-11 w-full items-center gap-3 py-2 text-left">
            {inner}
          </button>
        ) : (
          inner
        )}
      </li>
    )
  }

  // Expanded, the list groups by folder (alphabetical headers, unfiled last);
  // the folded preview stays a flat recency glance.
  const byName = (a: api.Food, b: api.Food) => a.name.localeCompare(b.name)
  const folderGroups = foldersOf(foods).map((name) => ({
    name,
    items: foods.filter((f) => f.folder === name).sort(byName),
  }))
  const unfiled = foods.filter((f) => !f.folder).sort(byName)

  return (
    <>
      <CollapsibleCard
        title="Custom foods"
        summary={foods.length ? String(foods.length) : undefined}
        storageKey="custom-foods"
        flush
        action={
          canEdit && (
            <button type="button" onClick={() => setEditing({ food: null })}
              className="db-tap44 -my-2 flex min-h-8 shrink-0 items-center gap-1 rounded-full border border-accent-bright/40 bg-accent-bright/15 px-2.5 text-xs font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25">
              <Plus className="h-3.5 w-3.5" strokeWidth={2.5} /> New food
            </button>
          )
        }
      >
        <div className="px-3.5">
          <FormError message={error} />
        </div>

        {foods.length === 0 ? (
          <p className="db-emptyline">
            {canEdit
              ? 'Add anything the food database is missing (a homemade dish, a local brand) and use it in recipes.'
              : 'No custom foods yet.'}
          </p>
        ) : !preview.folded && folderGroups.length > 0 ? (
          <div>
            {folderGroups.map((g) => (
              <div key={g.name}>
                <div className="db-sect">
                  <span>{g.name}</span>
                </div>
                <ul>{g.items.map(renderFood)}</ul>
              </div>
            ))}
            {unfiled.length > 0 && <ul>{unfiled.map(renderFood)}</ul>}
          </div>
        ) : (
          <ul>{preview.shown.map(renderFood)}</ul>
        )}
        <LibraryFoldButton
          total={foods.length}
          showAll={preview.showAll}
          onToggle={() => preview.setShowAll((v) => !v)}
          noun="foods"
        />
      </CollapsibleCard>

      {detail && (
        <Sheet onClose={() => setDetail(null)}>
          <div className="mb-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-lg font-bold leading-snug">{detail.name}</h3>
              {detail.brand && <p className="mt-0.5 text-sm text-fg/55">{detail.brand}</p>}
              {detail.folder && (
                <p className="mt-1 flex items-center gap-1 text-xs text-fg/45">
                  <FolderOpen className="h-3 w-3 shrink-0" /> {detail.folder}
                </p>
              )}
            </div>
            {detail.shared_to.length > 0 && (
              <span className="db-chip db-chip-gold flex items-center gap-1">
                <Share2 className="h-3 w-3" /> Shared
              </span>
            )}
          </div>
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-fg/35">
            {servingNutrition(detail).per}
          </p>
          <div className="mb-3">
            <NutritionPanel m={servingNutrition(detail).macros} />
          </div>
          {detail.servings.length > 0 && (
            <div className="mb-3 flex flex-col gap-1">
              {detail.servings.map((s, i) => (
                <p key={i} className="flex justify-between gap-3 text-sm text-fg/75">
                  <span className="min-w-0 truncate">{s.name}</span>
                  <span className="shrink-0 text-fg/50">
                    {s.grams} {UNIT_LABEL[detail.base_unit]}
                  </span>
                </p>
              ))}
            </div>
          )}
          <Button
            type="button"
            className="mb-2 min-h-11 w-full"
            onClick={() => {
              setEditing({ food: detail })
              setDetail(null)
            }}
          >
            <Pencil className="mr-1.5 inline h-4 w-4" /> Edit
          </Button>
          {/* Share/unshare right here, per the family's ask, so a food can be
              shared without stepping into the editor. */}
          <ShareFoodToVillage food={detail} />
        </Sheet>
      )}

      {editing && (
        <FoodSheet
          food={editing.food}
          folders={foldersOf(foods)}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            refresh()
          }}
        />
      )}
    </>
  )
}
