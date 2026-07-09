import { AnimatePresence } from 'framer-motion'
import { ArrowDownToLine, Share2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import * as api from '../lib/api'
import { CollapsibleCard } from './CollapsibleCard'
import { NutritionPanel, Sheet } from './Recipes'
import { Button, FormError } from './ui'

// The village shelf, in the Kitchen: recipes other families shared, with
// attribution, browseable in full (steps + per-serving nutrition) and one tap
// from becoming your own independent copy. The card only renders when the
// family is in a village.

function ShareSheet({
  villageId,
  onClose,
  onShared,
}: {
  villageId: number
  onClose: () => void
  onShared: () => void
}) {
  const [recipes, setRecipes] = useState<api.Recipe[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  useEffect(() => {
    api
      .getRecipes()
      .then(setRecipes)
      .catch(() => setError('Could not load your recipes.'))
  }, [])

  async function shareIt(id: number) {
    setBusyId(id)
    setError(null)
    try {
      await api.shareRecipe(villageId, id)
      onShared()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
      setBusyId(null)
    }
  }

  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 text-lg font-bold">Share a recipe</h3>
      <p className="mb-4 text-sm text-fg/60">
        It appears on the village shelf for other families to browse and copy. You can take it
        back off anytime; copies they saved stay theirs.
      </p>
      <FormError message={error} />
      <div className="flex max-h-72 flex-col gap-1.5 overflow-y-auto">
        {recipes?.map((r) => (
          <button
            key={r.id}
            type="button"
            disabled={busyId !== null}
            onClick={() => shareIt(r.id)}
            className="flex items-center justify-between rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left text-sm font-semibold text-fg/85 transition-colors hover:bg-fg/10 disabled:opacity-50"
          >
            {r.name}
            <Share2 className="h-4 w-4 shrink-0 text-accent-bright" />
          </button>
        ))}
        {recipes?.length === 0 && (
          <p className="py-4 text-center text-sm text-fg/40">No recipes yet — build one first.</p>
        )}
      </div>
    </Sheet>
  )
}

export function SharedRecipesBox() {
  const { user } = useAuth()
  const [villages, setVillages] = useState<api.Village[]>([])
  const [shelf, setShelf] = useState<api.SharedRecipe[]>([])
  const [detail, setDetail] = useState<api.SharedRecipeDetail | null>(null)
  const [sharing, setSharing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)
  const [armedUnshare, setArmedUnshare] = useState(false)

  const isParent = user?.role === 'parent'

  const refresh = useCallback(() => {
    api
      .listVillages()
      .then((v) => {
        setVillages(v)
        if (v.length > 0) return api.villageShelf().then(setShelf)
        setShelf([])
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    refresh()
    window.addEventListener('db:villages', refresh)
    return () => window.removeEventListener('db:villages', refresh)
  }, [refresh])

  if (villages.length === 0) return null
  const village = villages[0]

  async function openDetail(shareId: number) {
    setError(null)
    setSaved(null)
    setArmedUnshare(false)
    try {
      setDetail(await api.sharedRecipeDetail(shareId))
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not open that recipe.')
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

  async function unshare() {
    if (!detail) return
    if (!armedUnshare) {
      setArmedUnshare(true)
      setTimeout(() => setArmedUnshare(false), 4000)
      return
    }
    setBusy(true)
    try {
      await api.unshareRecipe(detail.share_id)
      setDetail(null)
      refresh()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong')
    }
    setBusy(false)
  }

  return (
    <CollapsibleCard
      title="Village shelf"
      summary={shelf.length ? `${shelf.length} shared` : village.name}
      storageKey="village-shelf"
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
      {shelf.length === 0 ? (
        <p className="text-sm text-fg/50">
          Nothing on the shelf yet. Recipes shared by {village.name}'s families appear here for
          everyone to browse and copy.
        </p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {shelf.map((s) => (
            <button
              key={s.share_id}
              type="button"
              onClick={() => openDetail(s.share_id)}
              className="flex items-center justify-between gap-3 rounded-xl border border-fg/10 bg-fg/5 px-3 py-2.5 text-left transition-colors hover:bg-fg/10"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold text-fg/90">{s.name}</span>
                <span className="block truncate text-xs text-fg/45">
                  from {s.family_name}
                  {s.is_own && ' (you)'}
                </span>
              </span>
              {s.per_serving.calories != null && (
                <span className="shrink-0 text-xs font-semibold text-fg/50">
                  {Math.round(s.per_serving.calories)} kcal
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      <AnimatePresence>
        {detail && (
          <Sheet onClose={() => setDetail(null)}>
            <h3 className="mb-0.5 text-lg font-bold">{detail.name}</h3>
            <p className="mb-3 text-xs text-fg/45">
              from {detail.family_name} · {detail.servings} servings
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
                <Button type="button" className="mb-2 w-full" disabled={busy} onClick={saveCopy}>
                  <ArrowDownToLine className="mr-1.5 inline h-4 w-4" />
                  {busy ? 'Saving…' : 'Save a copy'}
                </Button>
              )
            )}
            {isParent && detail.is_own && (
              <button
                type="button"
                onClick={unshare}
                className={`w-full text-center text-xs font-semibold ${armedUnshare ? 'text-danger' : 'text-fg/45'} hover:underline`}
              >
                {armedUnshare ? 'Tap again to take it off the shelf' : 'Unshare'}
              </button>
            )}
          </Sheet>
        )}
        {sharing && (
          <ShareSheet
            villageId={village.id}
            onClose={() => setSharing(false)}
            onShared={() => {
              setSharing(false)
              refresh()
            }}
          />
        )}
      </AnimatePresence>
    </CollapsibleCard>
  )
}
