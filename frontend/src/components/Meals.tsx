import { AnimatePresence, motion } from 'framer-motion'
import { Check, ChevronLeft, ChevronRight, UtensilsCrossed, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Button, FormError } from './ui'

// The Kitchen's hero: tonight's dinner, with the week's menu underneath.
// Parents plan a night from the recipe box or type a one-off ("Pizza out");
// kids see the menu read-only. Dinner-only for now — the API already carries
// a slot, so breakfast/lunch are a UI change later.

function toISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
// Sunday-first, matching the calendar grid.
function weekStartOf(d: Date): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  x.setDate(x.getDate() - x.getDay())
  return x
}
function addDays(d: Date, n: number): Date {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

const mealTitle = (m: api.Meal | undefined) => m?.recipe_name ?? m?.custom_title ?? null

// Pick a night's dinner: one of the saved recipes, or a typed title.
function MealSheet({
  dayISO,
  current,
  onClose,
  onSaved,
}: {
  dayISO: string
  current: api.Meal | undefined
  onClose: () => void
  onSaved: () => void
}) {
  const [recipes, setRecipes] = useState<api.Recipe[]>([])
  const [custom, setCustom] = useState(current?.custom_title ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getRecipes().then(setRecipes).catch(() => {})
  }, [])

  async function choose(recipeId: number) {
    setBusy(true)
    setError(null)
    try {
      await api.setMeal({ date_for: dayISO, recipe_id: recipeId })
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not plan the night.')
      setBusy(false)
    }
  }

  async function submitCustom(e: FormEvent) {
    e.preventDefault()
    if (!custom.trim()) return
    setBusy(true)
    setError(null)
    try {
      await api.setMeal({ date_for: dayISO, custom_title: custom.trim() })
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not plan the night.')
      setBusy(false)
    }
  }

  async function clear() {
    setBusy(true)
    try {
      await api.clearMeal(dayISO)
      onSaved()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not clear the night.')
      setBusy(false)
    }
  }

  const heading = new Date(`${dayISO}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })

  return createPortal(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        className="sheet-card max-h-[90svh] w-full max-w-sm overflow-y-auto p-6"
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-1 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wide text-accent-bright">
            Dinner
          </span>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-fg/50 hover:bg-fg/10 hover:text-fg">
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="mb-4 font-display text-lg font-semibold tracking-[-0.01em]">{heading}</p>

        <FormError message={error} />

        {recipes.length > 0 && (
          <div className="mb-4">
            <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-fg/40">
              Your recipes
            </span>
            <div className="flex flex-col">
              {recipes.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  disabled={busy}
                  onClick={() => choose(r.id)}
                  className="flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-fg/10"
                >
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{r.name}</span>
                  {current?.recipe_id === r.id && (
                    <Check className="h-4 w-4 shrink-0 text-emerald-400" strokeWidth={3} />
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        <form onSubmit={submitCustom} className="flex items-center gap-2">
          <input
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            maxLength={120}
            placeholder={recipes.length > 0 ? 'Or type it (Pizza out)' : 'Type it (Pizza out)'}
            className="field"
          />
          <Button type="submit" disabled={busy || !custom.trim()} className="shrink-0">
            Set
          </Button>
        </form>

        {mealTitle(current) && (
          <button
            type="button"
            disabled={busy}
            onClick={clear}
            className="mt-3 w-full text-center text-sm font-semibold text-danger hover:opacity-80"
          >
            Clear this night
          </button>
        )}
      </motion.div>
    </motion.div>,
    document.body,
  )
}

export function DinnerPlanner() {
  const { user } = useAuth()
  const isParent = user?.role === 'parent'
  const todayISO = toISO(new Date())
  const [weekStart, setWeekStart] = useState(() => weekStartOf(new Date()))
  const [meals, setMeals] = useState<api.Meal[]>([])
  const [error, setError] = useState<string | null>(null)
  const [planning, setPlanning] = useState<string | null>(null) // dayISO in the sheet
  const [showWeek, setShowWeek] = useState(false)

  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)),
    [weekStart],
  )

  const refresh = useCallback(async () => {
    try {
      // The week on screen plus today, which can sit outside a paged-away week.
      const [week, tonight] = await Promise.all([
        api.getMeals(toISO(days[0]), toISO(days[6])),
        api.getMeals(todayISO, todayISO),
      ])
      const seen = new Set(week.map((m) => `${m.date_for}:${m.slot}`))
      setMeals([...week, ...tonight.filter((m) => !seen.has(`${m.date_for}:${m.slot}`))])
      setError(null)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not load the menu.')
    }
  }, [days, todayISO])

  useEffect(() => {
    refresh()
  }, [refresh])

  const dinnerOn = (iso: string) =>
    meals.find((m) => m.date_for === iso && m.slot === 'dinner')

  const tonight = dinnerOn(todayISO)
  const tonightLabel = new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
  const weekLabel =
    weekStartOf(new Date()).getTime() === weekStart.getTime()
      ? 'This week'
      : days[0].toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) +
        ' – ' +
        days[6].toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

  return (
    <section className="glass p-5" data-dinner-planner>
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-bright/15 text-accent-bright">
          <UtensilsCrossed className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-fg/40">
            Tonight · {tonightLabel}
          </p>
          <h2 className="truncate font-display text-xl font-semibold tracking-[-0.01em]">
            {mealTitle(tonight) ?? "What's for dinner?"}
          </h2>
        </div>
        {isParent && (
          <button
            type="button"
            onClick={() => setPlanning(todayISO)}
            className="shrink-0 rounded-full border border-accent-bright/40 bg-accent-bright/15 px-3 py-1.5 text-xs font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
          >
            {mealTitle(tonight) ? 'Change' : 'Plan'}
          </button>
        )}
      </div>

      <FormError message={error} />

      <button
        type="button"
        onClick={() => setShowWeek((v) => !v)}
        className="mt-3 text-xs font-semibold text-accent-bright hover:underline"
      >
        {showWeek ? 'Hide the week' : "Plan the week"}
      </button>

      {showWeek && (
        <div className="mt-2">
          <div className="mb-1.5 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setWeekStart((s) => addDays(s, -7))}
              aria-label="Previous week"
              className="rounded-lg p-1 text-fg/50 hover:bg-fg/10 hover:text-fg"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-xs font-semibold uppercase tracking-wide text-fg/45">{weekLabel}</span>
            <button
              type="button"
              onClick={() => setWeekStart((s) => addDays(s, 7))}
              aria-label="Next week"
              className="rounded-lg p-1 text-fg/50 hover:bg-fg/10 hover:text-fg"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <div className="flex flex-col">
            {days.map((d) => {
              const iso = toISO(d)
              const title = mealTitle(dinnerOn(iso))
              const isToday = iso === todayISO
              const row = (
                <>
                  <span
                    className={`w-10 shrink-0 text-xs font-semibold uppercase ${
                      isToday ? 'text-accent-bright' : 'text-fg/45'
                    }`}
                  >
                    {d.toLocaleDateString(undefined, { weekday: 'short' })}
                  </span>
                  <span className={`min-w-0 flex-1 truncate text-sm ${title ? 'text-fg/90' : 'text-fg/35'}`}>
                    {title ?? '—'}
                  </span>
                </>
              )
              return isParent ? (
                <button
                  key={iso}
                  type="button"
                  onClick={() => setPlanning(iso)}
                  className="flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-fg/10"
                >
                  {row}
                </button>
              ) : (
                <div key={iso} className="flex items-center gap-3 px-2 py-1.5">
                  {row}
                </div>
              )
            })}
          </div>
        </div>
      )}

      <AnimatePresence>
        {planning && (
          <MealSheet
            dayISO={planning}
            current={dinnerOn(planning)}
            onClose={() => setPlanning(null)}
            onSaved={() => {
              setPlanning(null)
              refresh()
            }}
          />
        )}
      </AnimatePresence>
    </section>
  )
}

// The slim Home strip: tonight's dinner when one is planned, tapping through
// to the Kitchen. Renders nothing on unplanned days — the board shouldn't nag.
export function TonightCard({ onOpenKitchen }: { onOpenKitchen: () => void }) {
  const [title, setTitle] = useState<string | null>(null)

  useEffect(() => {
    const today = toISO(new Date())
    api
      .getMeals(today, today)
      .then((ms) => setTitle(mealTitle(ms.find((m) => m.slot === 'dinner'))))
      .catch(() => {})
  }, [])

  if (!title) return null
  return (
    <button
      type="button"
      onClick={onOpenKitchen}
      data-tonight-card
      className="glass mb-4 flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-fg/5"
    >
      <UtensilsCrossed className="h-4 w-4 shrink-0 text-accent-bright" />
      <span className="min-w-0 flex-1 truncate text-sm">
        <span className="mr-2 text-[11px] font-semibold uppercase tracking-widest text-fg/40">
          Tonight
        </span>
        <span className="font-semibold text-fg/90">{title}</span>
      </span>
    </button>
  )
}
