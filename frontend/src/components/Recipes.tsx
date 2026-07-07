import { motion } from 'framer-motion'
import { BookOpen, Pencil, Plus, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Button, FormError } from './ui'

// "520 cal · 31P / 45C / 22F", skipping any macro that isn't filled in.
function macroSummary(r: api.Recipe): string {
  const parts: string[] = []
  if (r.calories != null) parts.push(`${r.calories} cal`)
  const macros = [
    r.protein_g != null ? `${r.protein_g}P` : null,
    r.carbs_g != null ? `${r.carbs_g}C` : null,
    r.fat_g != null ? `${r.fat_g}F` : null,
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
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 40 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        className="glass max-h-[90svh] w-full max-w-sm overflow-y-auto p-6"
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
    <div className="flex flex-1 flex-col items-center rounded-xl bg-fg/5 px-2 py-2">
      <span className="font-display text-lg font-semibold leading-none">{value}</span>
      <span className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-fg/45">{label}</span>
    </div>
  )
}

// Read-only view of one recipe: nutrition per serving, ingredients, steps.
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
  const dash = (n: number | null) => (n != null ? String(n) : '—')

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

      <div className="mt-4 flex gap-2">
        <Stat label="Cal" value={dash(recipe.calories)} />
        <Stat label="Protein" value={dash(recipe.protein_g)} />
        <Stat label="Carbs" value={dash(recipe.carbs_g)} />
        <Stat label="Fat" value={dash(recipe.fat_g)} />
      </div>

      {recipe.ingredients.trim() && (
        <div className="mt-5">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-fg/40">Ingredients</span>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-fg/80">{recipe.ingredients}</p>
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

// A macro number field: empty means "not filled in" (null).
function NumField({
  label,
  value,
  onChange,
}: {
  label: string
  value: number | null
  onChange: (v: number | null) => void
}) {
  return (
    <label className="flex flex-1 flex-col gap-1">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-fg/45">{label}</span>
      <input
        inputMode="numeric"
        value={value ?? ''}
        onChange={(e) => {
          const digits = e.target.value.replace(/[^0-9]/g, '')
          onChange(digits === '' ? null : Number(digits))
        }}
        className="field text-center"
      />
    </label>
  )
}

// Create or edit a recipe.
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
  const [calories, setCalories] = useState<number | null>(recipe?.calories ?? null)
  const [protein, setProtein] = useState<number | null>(recipe?.protein_g ?? null)
  const [carbs, setCarbs] = useState<number | null>(recipe?.carbs_g ?? null)
  const [fat, setFat] = useState<number | null>(recipe?.fat_g ?? null)
  const [ingredients, setIngredients] = useState(recipe?.ingredients ?? '')
  const [steps, setSteps] = useState(recipe?.steps ?? '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    setBusy(true)
    setError(null)
    const payload: api.RecipePayload = {
      name: trimmed,
      servings: servings ?? 1,
      calories,
      protein_g: protein,
      carbs_g: carbs,
      fat_g: fat,
      ingredients,
      steps,
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

        <div className="flex items-end gap-3">
          <label className="flex w-24 flex-col gap-1">
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
          <p className="pb-2 text-xs text-fg/40">Nutrition below is per serving.</p>
        </div>

        <div className="flex gap-2">
          <NumField label="Cal" value={calories} onChange={setCalories} />
          <NumField label="Protein" value={protein} onChange={setProtein} />
          <NumField label="Carbs" value={carbs} onChange={setCarbs} />
          <NumField label="Fat" value={fat} onChange={setFat} />
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">Ingredients</span>
          <textarea
            value={ingredients}
            onChange={(e) => setIngredients(e.target.value)}
            rows={4}
            maxLength={5000}
            placeholder={'One per line\nGround beef\nRice'}
            className="field resize-y leading-relaxed"
          />
        </label>

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

// The family recipe box: saved recipes with per-serving nutrition. Everyone can
// browse; only parents add, edit, or delete. Self-contained like GroceryPanel.
export function RecipeBox() {
  const { user } = useAuth()
  const canEdit = user?.role === 'parent'

  const [recipes, setRecipes] = useState<api.Recipe[]>([])
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<View>({ mode: 'closed' })

  const refresh = useCallback(async () => {
    try {
      setRecipes(await api.getRecipes())
      setError(null)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load recipes.')
    }
  }, [])

  useEffect(() => {
    refresh()
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
            const summary = macroSummary(r)
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
