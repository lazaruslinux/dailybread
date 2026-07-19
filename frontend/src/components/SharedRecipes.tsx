import { AnimatePresence, motion } from 'framer-motion'
import { ArrowDownToLine, Share2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useAuth } from '../auth/AuthContext'
import * as api from '../lib/api'
import { CollapsibleCard } from './CollapsibleCard'
import { NutritionPanel, Sheet } from './Recipes'
import { Button, FormError } from './ui'

function compactStamp(iso: string): string {
  const d = new Date(iso)
  const sameYear = d.getFullYear() === new Date().getFullYear()
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' }),
  }) + ', ' + d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

const baseLabel = (base: api.BaseUnit) => (base === 'ml' ? 'mL' : 'g')

// A one-question confirm over the sheet, so sharing to or removing from a
// village is always a deliberate second tap (the family asked for this on
// every share/unshare, recipes and foods alike). Mirrors DiscardGuard.
function ConfirmDialog({
  title,
  confirmLabel,
  danger,
  onConfirm,
  onCancel,
}: {
  title: string
  confirmLabel: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return createPortal(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-6"
      onClick={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div className="sheet-card w-full max-w-xs p-5 text-center" role="alertdialog" aria-modal="true">
        <p className="font-display text-lg font-semibold">{title}</p>
        <div className="mt-4 flex flex-col gap-2">
          <Button type="button" variant={danger ? 'danger' : 'primary'} onClick={onConfirm} className="min-h-11 w-full">
            {confirmLabel}
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel} className="min-h-11 w-full">
            Cancel
          </Button>
        </div>
      </div>
    </motion.div>,
    document.body,
  )
}

// The village shelf, in the Kitchen: recipes AND custom foods other families
// shared, with attribution, browseable in full and one tap from becoming your
// own independent copy. The card only renders when the family is in a village
// (or, for kids who can't read the roster, when the shelf has anything on it).

function ShareSheet({
  villages,
  onClose,
  onShared,
}: {
  villages: api.Village[]
  onClose: () => void
  onShared: () => void
}) {
  const [mode, setMode] = useState<'recipes' | 'foods'>('recipes')
  const [recipes, setRecipes] = useState<api.Recipe[] | null>(null)
  const [foods, setFoods] = useState<api.Food[] | null>(null)
  const [villageId, setVillageId] = useState<number>(villages[0]?.id)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [confirm, setConfirm] = useState<{ title: string; run: () => void } | null>(null)
  const villageName = villages.find((v) => v.id === villageId)?.name ?? 'your village'

  useEffect(() => {
    api.getRecipes().then(setRecipes).catch(() => setError('Could not load your recipes.'))
    api.getCustomFoods().then(setFoods).catch(() => setError('Could not load your foods.'))
  }, [])

  async function shareRecipeIt(id: number) {
    setBusyId(id)
    setError(null)
    try {
      await api.shareRecipe(villageId, id)
      // The recipe box's row grows its "Shared" chip immediately.
      window.dispatchEvent(new Event('db:recipes-changed'))
      onShared()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
      setBusyId(null)
    }
  }

  async function shareFoodIt(id: number) {
    setBusyId(id)
    setError(null)
    try {
      await api.shareFood(villageId, id)
      // The Custom foods row grows its "Shared" chip immediately.
      window.dispatchEvent(new Event('db:foods-changed'))
      onShared()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
      setBusyId(null)
    }
  }

  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-2 text-lg font-bold">Share to your village</h3>
      <div className="mb-3 flex rounded-full border border-fg/10 bg-fg/5 p-0.5 text-xs font-semibold">
        {(['recipes', 'foods'] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`min-h-11 flex-1 rounded-full px-3 py-1.5 transition-colors ${
              mode === m ? 'bg-accent-bright/25 text-fg' : 'text-fg/55 hover:text-fg'
            }`}
          >
            {m === 'recipes' ? 'Recipes' : 'Foods'}
          </button>
        ))}
      </div>
      {villages.length > 1 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {villages.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => setVillageId(v.id)}
              className={`rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors ${
                villageId === v.id
                  ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
                  : 'border-fg/10 bg-fg/5 text-fg/70 hover:bg-fg/10'
              }`}
            >
              {v.name}
            </button>
          ))}
        </div>
      )}
      <p className="mb-4 text-sm text-fg/60">
        It appears on the village shelf for other families to browse and copy. You can take it
        back off anytime; copies they saved stay theirs.
      </p>
      <FormError message={error} />
      <div className="flex max-h-72 flex-col gap-1.5 overflow-y-auto">
        {mode === 'recipes' ? (
          <>
            {recipes?.map((r) => (
              <button
                key={r.id}
                type="button"
                disabled={busyId !== null}
                onClick={() =>
                  setConfirm({ title: `Share "${r.name}" to ${villageName}?`, run: () => shareRecipeIt(r.id) })
                }
                className="flex min-h-11 items-center justify-between rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left text-sm font-semibold text-fg/85 transition-colors hover:bg-fg/10 disabled:opacity-50"
              >
                {r.name}
                <Share2 className="h-4 w-4 shrink-0 text-accent-bright" />
              </button>
            ))}
            {recipes?.length === 0 && (
              <p className="py-4 text-center text-sm text-fg/40">No recipes yet. Build one first.</p>
            )}
          </>
        ) : (
          <>
            {foods?.map((f) => (
              <button
                key={f.id}
                type="button"
                disabled={busyId !== null || f.id == null}
                onClick={() =>
                  f.id != null &&
                  setConfirm({ title: `Share "${f.name}" to ${villageName}?`, run: () => shareFoodIt(f.id!) })
                }
                className="flex min-h-11 items-center justify-between rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left text-sm font-semibold text-fg/85 transition-colors hover:bg-fg/10 disabled:opacity-50"
              >
                <span className="min-w-0 truncate">
                  {f.name}
                  {f.brand && <span className="text-fg/40"> · {f.brand}</span>}
                </span>
                <Share2 className="h-4 w-4 shrink-0 text-accent-bright" />
              </button>
            ))}
            {foods?.length === 0 && (
              <p className="py-4 text-center text-sm text-fg/40">
                No custom foods yet. Add one first.
              </p>
            )}
          </>
        )}
      </div>
      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          confirmLabel="Share"
          onConfirm={() => {
            confirm.run()
            setConfirm(null)
          }}
          onCancel={() => setConfirm(null)}
        />
      )}
    </Sheet>
  )
}

// "Share to village" inside a recipe's or custom food's own detail sheet:
// renders nothing when the family isn't in a village; one village shares on
// tap, several offer chips; existing shares list with an Unshare action. The
// two wrappers below feed it the right API calls and change event; everything
// here is type="button" because FoodSheet mounts it inside a form.
function VillageShareSection({
  initialShares,
  doShare,
  doUnshare,
  changeEvent,
}: {
  initialShares: api.RecipeShare[]
  // Resolves to the new share's id (the unshare handle).
  doShare: (villageId: number) => Promise<number>
  doUnshare: (shareId: number) => Promise<void>
  changeEvent: string
}) {
  const { user } = useAuth()
  const [villages, setVillages] = useState<api.Village[]>([])
  const [shares, setShares] = useState<api.RecipeShare[]>(initialShares)
  const [picking, setPicking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<
    { title: string; label: string; danger?: boolean; run: () => void } | null
  >(null)

  useEffect(() => {
    api.listVillages().then(setVillages).catch(() => {})
  }, [])

  if (user?.role !== 'parent' || villages.length === 0) return null
  const remaining = villages.filter((v) => !shares.some((s) => s.village_id === v.id))

  async function shareTo(v: api.Village) {
    setError(null)
    try {
      const shareId = await doShare(v.id)
      setShares((prev) => [
        ...prev,
        { share_id: shareId, village_id: v.id, village_name: v.name },
      ])
      setPicking(false)
      window.dispatchEvent(new Event(changeEvent))
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
    }
  }

  async function unshare(share: api.RecipeShare) {
    setError(null)
    try {
      await doUnshare(share.share_id)
      setShares((prev) => prev.filter((s) => s.share_id !== share.share_id))
      window.dispatchEvent(new Event(changeEvent))
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
    }
  }

  return (
    <div className="mt-2.5 flex flex-col gap-1.5">
      {shares.map((sh) => (
        <div
          key={sh.share_id}
          className="flex items-center justify-between rounded-xl border border-accent-bright/30 bg-accent-bright/10 px-3 py-2 text-xs font-semibold text-fg/75"
        >
          <span className="flex min-w-0 items-center gap-1.5">
            <Share2 className="h-3.5 w-3.5 shrink-0 text-accent-bright" />
            {/* No truncate: the live-pointer clause is the part worth reading,
                so the label wraps instead of hiding it at phone width. */}
            <span>
              Shared to {sh.village_name}. Your edits show there live
            </span>
          </span>
          <button
            type="button"
            onClick={() =>
              setConfirm({
                title: `Remove from ${sh.village_name}?`,
                label: 'Remove',
                danger: true,
                run: () => unshare(sh),
              })
            }
            className="-my-2 -mr-3 flex min-h-11 shrink-0 items-center px-3 font-semibold text-fg/45 hover:text-fg/70"
          >
            Unshare
          </button>
        </div>
      ))}
      {remaining.length > 0 &&
        (picking && remaining.length > 1 ? (
          <div className="flex flex-wrap gap-1.5">
            {remaining.map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() =>
                  setConfirm({ title: `Share to ${v.name}?`, label: 'Share', run: () => shareTo(v) })
                }
                className="min-h-11 rounded-full border border-fg/10 bg-fg/5 px-3 py-1 text-xs font-semibold text-fg/70 transition-colors hover:bg-fg/10"
              >
                {v.name}
              </button>
            ))}
          </div>
        ) : (
          <Button
            type="button"
            variant="ghost"
            className="flex min-h-11 w-full items-center justify-center gap-1.5"
            onClick={() =>
              remaining.length === 1
                ? setConfirm({
                    title: `Share to ${remaining[0].name}?`,
                    label: 'Share',
                    run: () => shareTo(remaining[0]),
                  })
                : setPicking(true)
            }
          >
            <Share2 className="h-4 w-4" /> Share to village
          </Button>
        ))}
      <FormError message={error} />
      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          confirmLabel={confirm.label}
          danger={confirm.danger}
          onConfirm={() => {
            confirm.run()
            setConfirm(null)
          }}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  )
}

export function ShareToVillage({ recipe }: { recipe: api.Recipe }) {
  return (
    <VillageShareSection
      initialShares={recipe.shared_to}
      doShare={async (villageId) => (await api.shareRecipe(villageId, recipe.id)).share_id}
      doUnshare={(shareId) => api.unshareRecipe(shareId)}
      changeEvent="db:recipes-changed"
    />
  )
}

export function ShareFoodToVillage({ food }: { food: api.Food }) {
  // A brand-new unsaved food has no id to share yet.
  if (food.id == null) return null
  const foodId = food.id
  return (
    <VillageShareSection
      initialShares={food.shared_to}
      doShare={async (villageId) => (await api.shareFood(villageId, foodId)).share_id}
      doUnshare={(shareId) => api.unshareFood(shareId)}
      changeEvent="db:foods-changed"
    />
  )
}

export function SharedRecipesBox() {
  const { user } = useAuth()
  const [villages, setVillages] = useState<api.Village[]>([])
  const [shelf, setShelf] = useState<api.SharedRecipe[]>([])
  const [foodShelf, setFoodShelf] = useState<api.SharedFood[]>([])
  const [detail, setDetail] = useState<api.SharedRecipeDetail | null>(null)
  const [foodDetail, setFoodDetail] = useState<api.SharedFoodDetail | null>(null)
  const [sharing, setSharing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)
  const [savedFood, setSavedFood] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<{ title: string; run: () => void } | null>(null)
  // Like the recipe library: show the newest couple, fold the rest.
  const [showAll, setShowAll] = useState(false)
  const [showAllFoods, setShowAllFoods] = useState(false)

  const isParent = user?.role === 'parent'
  const isMinor = user?.is_minor ?? false

  const refresh = useCallback(() => {
    // Minors can't read the village roster (it carries other households' moods
    // and levels), but the shelves are theirs to browse - go straight to them
    // and let the contents decide rendering.
    if (isMinor) {
      api.villageShelf().then(setShelf).catch(() => {})
      api.villageFoodShelf().then(setFoodShelf).catch(() => {})
      return
    }
    api
      .listVillages()
      .then((v) => {
        setVillages(v)
        if (v.length > 0) {
          api.villageShelf().then(setShelf).catch(() => {})
          api.villageFoodShelf().then(setFoodShelf).catch(() => {})
        } else {
          setShelf([])
          setFoodShelf([])
        }
      })
      .catch(() => {})
  }, [isMinor])

  useEffect(() => {
    refresh()
    // Village membership changes AND shares made elsewhere (a recipe's or
    // food's own detail sheet) both land here without a tab-away round trip.
    window.addEventListener('db:villages', refresh)
    window.addEventListener('db:recipes-changed', refresh)
    window.addEventListener('db:foods-changed', refresh)
    return () => {
      window.removeEventListener('db:villages', refresh)
      window.removeEventListener('db:recipes-changed', refresh)
      window.removeEventListener('db:foods-changed', refresh)
    }
  }, [refresh])

  // Adults: the box exists whenever the family has a village, even before
  // anything is shared. Kids can't see the roster, so for them the shelves'
  // own contents are the signal.
  if (isMinor ? shelf.length === 0 && foodShelf.length === 0 : villages.length === 0) return null
  const theirs = shelf.filter((s) => !s.is_own)
  const mine = shelf.filter((s) => s.is_own)
  const theirsFoods = foodShelf.filter((s) => !s.is_own)
  const mineFoods = foodShelf.filter((s) => s.is_own)

  async function unshareMine(entry: api.SharedRecipe) {
    setError(null)
    try {
      await api.unshareRecipe(entry.share_id)
      window.dispatchEvent(new Event('db:recipes-changed'))
      refresh()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
    }
  }

  async function unshareMyFood(entry: api.SharedFood) {
    setError(null)
    try {
      await api.unshareFood(entry.share_id)
      // The Custom foods row drops its "Shared" chip immediately.
      window.dispatchEvent(new Event('db:foods-changed'))
      refresh()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
    }
  }

  async function openDetail(shareId: number) {
    setError(null)
    setSaved(null)
    try {
      setDetail(await api.sharedRecipeDetail(shareId))
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not open that recipe.')
    }
  }

  async function openFoodDetail(shareId: number) {
    setError(null)
    setSavedFood(null)
    try {
      setFoodDetail(await api.sharedFoodDetail(shareId))
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not open that food.')
    }
  }

  async function saveCopy() {
    if (!detail) return
    setBusy(true)
    setError(null)
    try {
      const copy = await api.saveSharedCopy(detail.share_id)
      window.dispatchEvent(new Event('db:recipes-changed'))
      setSaved(copy.name)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
    }
    setBusy(false)
  }

  async function saveFoodCopy() {
    if (!foodDetail) return
    setBusy(true)
    setError(null)
    try {
      const copy = await api.saveSharedFoodCopy(foodDetail.share_id)
      window.dispatchEvent(new Event('db:foods-changed'))
      setSavedFood(copy.name)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
    }
    setBusy(false)
  }

  const shownCount = shelf.length + foodShelf.length

  return (
    <CollapsibleCard
      title="Village Shelf"
      summary={shownCount ? `${shownCount} shared` : villages.map((v) => v.name).join(' · ')}
      storageKey="village-recipes"
      defaultOpen
      action={
        isParent ? (
          <button
            type="button"
            onClick={() => setSharing(true)}
            className="flex items-center gap-1.5 rounded-full border border-accent-bright/40 bg-accent-bright/15 px-3 py-1.5 text-sm font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
          >
            <Share2 className="h-4 w-4" /> Share
          </button>
        ) : undefined
      }
    >
      <FormError message={error} />
      {theirs.length === 0 && theirsFoods.length === 0 ? (
        <p className="text-sm text-fg/50">
          Nothing shared yet. Recipes and foods shared by your village families appear here for
          everyone to browse and copy.
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          {theirs.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-fg/45">
                Shared recipes
              </p>
              <div className="flex flex-col gap-1.5">
                {(showAll ? theirs : theirs.slice(0, 2)).map((s) => (
                  <button
                    key={s.share_id}
                    type="button"
                    onClick={() => openDetail(s.share_id)}
                    className="flex min-h-11 items-center justify-between gap-3 rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left transition-colors hover:bg-fg/10"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-fg/90">{s.name}</span>
                      <span className="block truncate text-xs text-fg/45">
                        Shared by {s.shared_by ?? s.family_name} from {s.family_name}
                        {villages.length > 1 && ` · ${s.village_name}`}
                      </span>
                      <span className="block truncate text-[10px] text-fg/35">
                        Last updated {compactStamp(s.updated_at)}
                      </span>
                    </span>
                    {!isMinor && s.per_serving.calories != null && (
                      <span className="shrink-0 text-xs font-semibold text-fg/50">
                        {Math.round(s.per_serving.calories)} kcal
                      </span>
                    )}
                  </button>
                ))}
                {theirs.length > 2 && (
                  <button
                    type="button"
                    onClick={() => setShowAll((v) => !v)}
                    className="mt-0.5 w-full rounded-xl border border-fg/10 bg-fg/5 py-2 text-center text-xs font-semibold text-fg/60 transition-colors hover:bg-fg/10 hover:text-fg"
                  >
                    {showAll ? 'Show fewer' : `Show all ${theirs.length} recipes`}
                  </button>
                )}
              </div>
            </div>
          )}

          {theirsFoods.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-fg/45">
                Shared foods
              </p>
              <div className="flex flex-col gap-1.5">
                {(showAllFoods ? theirsFoods : theirsFoods.slice(0, 2)).map((s) => (
                  <button
                    key={s.share_id}
                    type="button"
                    onClick={() => openFoodDetail(s.share_id)}
                    className="flex min-h-11 items-center justify-between gap-3 rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left transition-colors hover:bg-fg/10"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-fg/90">
                        {s.name}
                        {s.brand && <span className="font-normal text-fg/40"> · {s.brand}</span>}
                      </span>
                      <span className="block truncate text-xs text-fg/45">
                        Shared by {s.shared_by ?? s.family_name} from {s.family_name}
                        {villages.length > 1 && ` · ${s.village_name}`}
                      </span>
                      {s.serving && (
                        <span className="block truncate text-[10px] text-fg/35">{s.serving}</span>
                      )}
                    </span>
                    {!isMinor && s.calories != null && (
                      <span className="shrink-0 text-xs font-semibold text-fg/50">
                        {Math.round(s.calories)} kcal/100 {baseLabel(s.base_unit)}
                      </span>
                    )}
                  </button>
                ))}
                {theirsFoods.length > 2 && (
                  <button
                    type="button"
                    onClick={() => setShowAllFoods((v) => !v)}
                    className="mt-0.5 w-full rounded-xl border border-fg/10 bg-fg/5 py-2 text-center text-xs font-semibold text-fg/60 transition-colors hover:bg-fg/10 hover:text-fg"
                  >
                    {showAllFoods ? 'Show fewer' : `Show all ${theirsFoods.length} foods`}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {(mine.length > 0 || mineFoods.length > 0) && (
        <div className="mt-4">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-fg/45">
            Shared by you
          </p>
          <div className="flex flex-col gap-1.5">
            {mine.map((s) => (
              <div
                key={`r${s.share_id}`}
                className="flex items-center gap-3 rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-fg/80">{s.name}</span>
                  <span className="block truncate text-xs text-fg/40">
                    Recipe · Shared by {s.shared_by ?? s.family_name}
                    {villages.length > 1 && ` · ${s.village_name}`} · Last updated{' '}
                    {compactStamp(s.updated_at)}
                  </span>
                </span>
                {isParent && (
                  <button
                    type="button"
                    onClick={() =>
                      setConfirm({ title: `Remove "${s.name}" from shared?`, run: () => unshareMine(s) })
                    }
                    aria-label={`Unshare ${s.name}`}
                    className="btn-danger -my-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-base font-bold leading-none"
                  >
                    −
                  </button>
                )}
              </div>
            ))}
            {mineFoods.map((s) => (
              <div
                key={`f${s.share_id}`}
                className="flex items-center gap-3 rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-fg/80">
                    {s.name}
                    {s.brand && <span className="font-normal text-fg/40"> · {s.brand}</span>}
                  </span>
                  <span className="block truncate text-xs text-fg/40">
                    Food · Shared by {s.shared_by ?? s.family_name}
                    {villages.length > 1 && ` · ${s.village_name}`}
                  </span>
                </span>
                {isParent && (
                  <button
                    type="button"
                    onClick={() =>
                      setConfirm({ title: `Remove "${s.name}" from shared?`, run: () => unshareMyFood(s) })
                    }
                    aria-label={`Unshare ${s.name}`}
                    className="btn-danger -my-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-base font-bold leading-none"
                  >
                    −
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <AnimatePresence>
        {detail && (
          <Sheet onClose={() => setDetail(null)}>
            <h3 className="mb-0.5 text-lg font-bold">{detail.name}</h3>
            <p className="mb-0.5 text-xs text-fg/45">
              Shared by {detail.shared_by ?? detail.family_name} from {detail.family_name} ·{' '}
              {detail.servings} servings
            </p>
            <p className="mb-3 text-[10px] text-fg/35">
              Last updated {compactStamp(detail.updated_at)}
            </p>
            <div className="mb-3">
              <NutritionPanel m={detail.per_serving} />
            </div>
            <div className="mb-3 flex flex-col gap-1">
              {detail.ingredients.map((line, i) => (
                <p key={i} className="flex justify-between gap-3 text-sm text-fg/75">
                  <span className="min-w-0 truncate">
                    {line.name}
                    {line.brand && <span className="text-fg/40"> · {line.brand}</span>}
                  </span>
                  <span className="shrink-0 text-fg/50">
                    {line.amount} {line.unit}
                  </span>
                </p>
              ))}
            </div>
            {detail.steps && (
              <p className="mb-4 whitespace-pre-wrap text-sm leading-relaxed text-fg/65">
                {detail.steps}
              </p>
            )}
            <FormError message={error} />
            {saved ? (
              <p className="mb-2 rounded-xl border border-accent-bright/30 bg-accent-bright/10 p-3 text-center text-sm font-semibold text-fg/80">
                Saved to your recipes as "{saved}"
              </p>
            ) : (
              isParent && (
                <Button type="button" className="mb-2 min-h-11 w-full" disabled={busy} onClick={saveCopy}>
                  <ArrowDownToLine className="mr-1.5 inline h-4 w-4" />
                  {busy ? 'Saving…' : 'Save a copy'}
                </Button>
              )
            )}
          </Sheet>
        )}
        {foodDetail && (
          <Sheet onClose={() => setFoodDetail(null)}>
            <h3 className="mb-0.5 text-lg font-bold">{foodDetail.name}</h3>
            {foodDetail.brand && <p className="mb-0.5 text-sm text-fg/55">{foodDetail.brand}</p>}
            <p className="mb-3 text-xs text-fg/45">
              Shared by {foodDetail.shared_by ?? foodDetail.family_name} from{' '}
              {foodDetail.family_name}
            </p>
            {!isMinor && (
              <>
                <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-fg/35">
                  Per 100 {baseLabel(foodDetail.base_unit)}
                </p>
                <div className="mb-3">
                  <NutritionPanel m={foodDetail} />
                </div>
              </>
            )}
            {foodDetail.servings.length > 0 && (
              <div className="mb-3 flex flex-col gap-1">
                {foodDetail.servings.map((s, i) => (
                  <p key={i} className="flex justify-between gap-3 text-sm text-fg/75">
                    <span className="min-w-0 truncate">{s.name}</span>
                    <span className="shrink-0 text-fg/50">
                      {s.grams} {baseLabel(foodDetail.base_unit)}
                    </span>
                  </p>
                ))}
              </div>
            )}
            <FormError message={error} />
            {savedFood ? (
              <p className="mb-2 rounded-xl border border-accent-bright/30 bg-accent-bright/10 p-3 text-center text-sm font-semibold text-fg/80">
                Saved to your custom foods as "{savedFood}"
              </p>
            ) : (
              isParent &&
              !foodDetail.is_own && (
                <Button type="button" className="mb-2 min-h-11 w-full" disabled={busy} onClick={saveFoodCopy}>
                  <ArrowDownToLine className="mr-1.5 inline h-4 w-4" />
                  {busy ? 'Saving…' : 'Save a copy'}
                </Button>
              )
            )}
          </Sheet>
        )}
        {sharing && (
          <ShareSheet
            villages={villages}
            onClose={() => setSharing(false)}
            onShared={() => {
              setSharing(false)
              refresh()
            }}
          />
        )}
        {confirm && (
          <ConfirmDialog
            title={confirm.title}
            confirmLabel="Remove"
            danger
            onConfirm={() => {
              confirm.run()
              setConfirm(null)
            }}
            onCancel={() => setConfirm(null)}
          />
        )}
      </AnimatePresence>
    </CollapsibleCard>
  )
}
