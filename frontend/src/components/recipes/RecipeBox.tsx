import { BookOpen, Pencil, Plus, Share2, ShoppingBasket, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../../lib/api'
import { useAuth } from '../../auth/AuthContext'
import { announceChange } from '../../lib/changes'
import { Button, FormError } from '../ui'
import { CollapsibleCard } from '../CollapsibleCard'
import { ShareToVillage } from '../SharedRecipes'
import { Sheet } from './Sheet'
import { RecipeSheet } from './RecipeSheet'
import { LibraryFoldButton, NutritionPanel, useLibraryPreview } from './ui'
import { UNIT_LABEL, macroSummary } from './shared'

// One tap from a recipe to the store: pick which list its ingredient lines
// land on. Announces the change so the GroceryPanel refreshes in place.
function SendToGrocery({ recipe }: { recipe: api.Recipe }) {
  const [picking, setPicking] = useState(false)
  const [lists, setLists] = useState<api.GroceryList[]>([])
  const [busy, setBusy] = useState(false)
  const [added, setAdded] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function open() {
    setPicking(true)
    setAdded(null)
    try {
      setLists((await api.getGrocery()).lists)
    } catch {
      // The chips just show Unsorted; the push itself will surface errors.
    }
  }

  async function send(listId: number | null) {
    setBusy(true)
    setError(null)
    try {
      const res = await api.pushRecipeToGrocery(recipe.id, listId)
      setAdded(res.added)
      setPicking(false)
      // Via announceChange, not a raw dispatch: it retires the shared-read
      // generation first, so the listeners it wakes cannot join a /grocery
      // request that left before these ingredients landed and paint a list
      // without them.
      announceChange('db:grocery-changed')
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not add the ingredients.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-4" data-send-grocery>
      {added != null ? (
        <p className="rounded-xl bg-emerald-500/10 px-3 py-2.5 text-sm font-semibold text-emerald-500">
          Added {added} {added === 1 ? 'item' : 'items'} to the grocery list.
        </p>
      ) : picking ? (
        <div className="rounded-xl bg-fg/5 px-3 py-2.5">
          <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wide text-fg/40">
            Add to which list?
          </span>
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              disabled={busy}
              onClick={() => send(null)}
              className="rounded-full border border-fg/10 bg-fg/5 px-3 py-1 text-xs font-semibold text-fg/70 hover:bg-fg/10"
            >
              Unsorted
            </button>
            {lists.map((l) => (
              <button
                key={l.id}
                type="button"
                disabled={busy}
                onClick={() => send(l.id)}
                className="rounded-full border border-fg/10 bg-fg/5 px-3 py-1 text-xs font-semibold text-fg/70 hover:bg-fg/10"
              >
                {l.name}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <Button type="button" variant="ghost" onClick={open} className="flex w-full items-center justify-center gap-1.5">
          <ShoppingBasket className="h-4 w-4" /> Add ingredients to grocery list
        </Button>
      )}
      <FormError message={error} />
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
        <button onClick={onClose} aria-label="Close" className="-m-1.5 rounded-lg p-3 text-fg/50 hover:bg-fg/10 hover:text-fg">
          <X className="h-5 w-5" />
        </button>
      </div>

      <h2 className="font-display text-2xl font-semibold tracking-[-0.01em]">{recipe.name}</h2>
      <p className="mt-1 text-xs text-fg/45">
        Makes {recipe.servings} {recipe.servings === 1 ? 'serving' : 'servings'} · per serving
      </p>
      {recipe.provenance && (
        <p className="mb-2 text-[11px] italic leading-relaxed text-fg/40">{recipe.provenance}</p>
      )}

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
                  {+ing.amount.toFixed(2)} {UNIT_LABEL[ing.unit] ?? ing.unit}
                  {canEdit && ing.calories != null && ` · ${Math.round(ing.calories)} cal`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {canEdit && recipe.ingredients.length > 0 && <SendToGrocery recipe={recipe} />}
      {canEdit && <ShareToVillage recipe={recipe} />}

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
  const preview = useLibraryPreview(recipes)
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
    // A copy saved from the village shelf lands here without this box
    // knowing; the shelf announces it instead.
    window.addEventListener('db:recipes-changed', refresh)
    return () => {
      mounted.current = false
      window.removeEventListener('db:recipes-changed', refresh)
    }
  }, [refresh])

  async function onDelete(id: number) {
    await api.deleteRecipe(id)
    setView({ mode: 'closed' })
    refresh()
  }

  return (
    <>
      <CollapsibleCard
        title="Recipes"
        summary={recipes.length ? String(recipes.length) : undefined}
        storageKey="recipes"
        defaultOpen
        flush
        action={
          canEdit && (
            <button
              type="button"
              onClick={() => setView({ mode: 'edit', recipe: null })}
              className="-my-2 flex min-h-11 shrink-0 items-center gap-1 rounded-full border border-accent-bright/40 bg-accent-bright/15 px-2.5 text-xs font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
            >
              <Plus className="h-3.5 w-3.5" strokeWidth={2.5} /> New recipe
            </button>
          )
        }
      >
        <div className="px-3.5">
          <FormError message={error} />
        </div>

        {recipes.length === 0 ? (
          <p className="db-emptyline">
            {canEdit ? 'No recipes yet. Add your family favorites so planning dinner is one tap.' : 'No recipes yet.'}
          </p>
        ) : (
          <ul>
            {preview.shown.map((r) => {
              // Kid mode: the row is just the recipe's name - no macro line.
              const summary = canEdit ? macroSummary(r.per_serving) : ''
              return (
                <li key={r.id} className="db-row transition-colors hover:bg-fg/5">
                  <button
                    type="button"
                    onClick={() => setView({ mode: 'detail', recipe: r })}
                    className="-my-2 flex min-h-11 w-full items-center gap-3 py-2 text-left"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-display text-[0.90625rem] font-semibold">{r.name}</span>
                      {summary && <span className="block truncate text-[0.78125rem] text-fg/50">{summary}</span>}
                    </span>
                    {r.shared_to.length > 0 && (
                      <span className="db-chip db-chip-gold flex items-center gap-1">
                        <Share2 className="h-3 w-3" /> Shared
                      </span>
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
        <LibraryFoldButton
          total={recipes.length}
          showAll={preview.showAll}
          onToggle={() => preview.setShowAll((v) => !v)}
          noun="recipes"
        />
      </CollapsibleCard>

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
    </>
  )
}
