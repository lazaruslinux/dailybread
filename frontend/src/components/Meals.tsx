import { AnimatePresence, motion } from 'framer-motion'
import { Check, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Pencil, Plus, UtensilsCrossed, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import * as api from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { Sheet } from './Recipes'
import { Button, Field, FormError } from './ui'

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

// The night's per-serving figures as readable pills. Only nutrients the
// recipe actually knows are shown — never a misleading zero.
function MacroPills({ ps }: { ps: api.RecipeMacros }) {
  const pills = [
    ps.calories != null ? `${Math.round(ps.calories)} cal` : null,
    ps.protein_g != null ? `${Math.round(ps.protein_g)}g protein` : null,
    ps.carbs_g != null ? `${Math.round(ps.carbs_g)}g carbs` : null,
    ps.fat_g != null ? `${Math.round(ps.fat_g)}g fat` : null,
    ps.sugar_g != null ? `${Math.round(ps.sugar_g)}g sugar` : null,
  ].filter((x): x is string => x !== null)
  if (pills.length === 0) return null
  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-1.5" data-tonight-macros>
      <span className="text-[10px] font-semibold uppercase tracking-widest text-fg/40">
        Per serving
      </span>
      {pills.map((text) => (
        <span key={text} className="rounded-md bg-fg/5 px-1.5 py-0.5 text-xs font-semibold text-fg/75">
          {text}
        </span>
      ))}
    </div>
  )
}

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

// "What should we have?" — the two-person-friendly face of dinner voting: a
// parent poses 2-3 choices, the others get a push and tap a pick, names (not
// tallies) show who wants what, and one tap crowns the winner as dinner.
function AskSheet({
  dayISO,
  onClose,
  onAsked,
}: {
  dayISO: string
  onClose: () => void
  onAsked: () => void
}) {
  const [choices, setChoices] = useState<{ title: string; recipe_id: number | null }[]>([
    { title: '', recipe_id: null },
    { title: '', recipe_id: null },
    { title: '', recipe_id: null },
  ])
  const [recipes, setRecipes] = useState<api.Recipe[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.getRecipes().then(setRecipes).catch(() => {})
  }, [])

  function setChoice(i: number, title: string, recipeId: number | null = null) {
    setChoices((prev) => prev.map((c, j) => (j === i ? { title, recipe_id: recipeId } : c)))
  }

  function addRecipe(r: api.Recipe) {
    const slot = choices.findIndex((c) => !c.title.trim())
    if (slot === -1) return
    setChoice(slot, r.name, r.id)
  }

  const filled = choices.filter((c) => c.title.trim())

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.openBallot(
        dayISO,
        filled.map((c) => ({ title: c.title.trim(), recipe_id: c.recipe_id })),
      )
      onAsked()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 text-lg font-bold">Ask about dinner</h3>
      <p className="mb-4 text-sm text-fg/60">
        Give the family two or three choices. Everyone gets a nudge and taps a pick; you set
        the winner.
      </p>
      <form onSubmit={submit} noValidate className="flex flex-col gap-3">
        {choices.map((c, i) => (
          <Field
            key={i}
            label={`Choice ${i + 1}${i === 2 ? ' (optional)' : ''}`}
            value={c.title}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setChoice(i, e.target.value)}
            maxLength={120}
          />
        ))}
        {recipes.length > 0 && (
          <div>
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              From your recipes
            </span>
            <div className="flex max-h-24 flex-wrap gap-1.5 overflow-y-auto">
              {recipes.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => addRecipe(r)}
                  className="rounded-full border border-fg/10 bg-fg/5 px-2.5 py-1 text-xs font-semibold text-fg/70 transition-colors hover:bg-fg/10"
                >
                  {r.name}
                </button>
              ))}
            </div>
          </div>
        )}
        <FormError message={error} />
        <Button type="submit" disabled={busy || filled.length < 2}>
          {busy ? 'Asking…' : 'Ask the family'}
        </Button>
      </form>
    </Sheet>
  )
}

function DinnerQuestion({
  ballot,
  isParent,
  dayISO,
  onChanged,
}: {
  ballot: api.DinnerBallot
  isParent: boolean
  dayISO: string
  onChanged: () => void
}) {
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  async function pick(o: api.DinnerOption) {
    setBusyId(o.id)
    setError(null)
    try {
      await api.castVote(o.id)
      onChanged()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
    }
    setBusyId(null)
  }

  async function crown(o: api.DinnerOption) {
    setBusyId(o.id)
    setError(null)
    try {
      await api.setMeal(
        o.recipe_id != null
          ? { date_for: dayISO, recipe_id: o.recipe_id }
          : { date_for: dayISO, custom_title: o.title },
      )
      await api.closeBallot(dayISO)
      onChanged()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusyId(null)
    }
  }

  async function drop() {
    try {
      await api.closeBallot(dayISO)
      onChanged()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
    }
  }

  return (
    <div className="mt-3 rounded-xl border border-accent-bright/25 bg-accent-bright/5 p-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-accent-bright">
        What should we have?
      </p>
      <div className="flex flex-col gap-1.5">
        {ballot.options.map((o) => (
          <div
            key={o.id}
            className={`flex items-center gap-2 rounded-xl border px-3 py-2 ${
              o.my_vote ? 'border-accent-bright/60 bg-accent-bright/15' : 'border-fg/10 bg-fg/5'
            }`}
          >
            <button
              type="button"
              disabled={busyId !== null}
              onClick={() => pick(o)}
              className="min-w-0 flex-1 text-left"
            >
              <span className="block truncate text-sm font-semibold text-fg/90">{o.title}</span>
              <span className="block truncate text-xs italic text-fg/45">
                {o.voters.length ? o.voters.join(', ') : 'No picks yet'}
              </span>
            </button>
            {isParent && (
              <button
                type="button"
                disabled={busyId !== null}
                onClick={() => crown(o)}
                className="shrink-0 rounded-full border border-accent-bright/40 bg-accent-bright/15 px-2.5 py-1 text-[11px] font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
              >
                Set as dinner
              </button>
            )}
          </div>
        ))}
      </div>
      <FormError message={error} />
      {isParent && (
        <button
          type="button"
          onClick={drop}
          className="mt-2 w-full text-center text-xs font-semibold text-fg/40 hover:text-fg/60"
        >
          Drop the question
        </button>
      )}
    </div>
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
  const [asking, setAsking] = useState(false)
  const [ballot, setBallot] = useState<api.DinnerBallot | null>(null)

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
      setBallot(await api.getBallot(todayISO))
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
          <span className="flex shrink-0 gap-1.5">
            {!mealTitle(tonight) && !(ballot && ballot.options.length > 0) && (
              <button
                type="button"
                onClick={() => setAsking(true)}
                className="rounded-full border border-accent-bright/40 bg-accent-bright/15 px-3 py-1.5 text-xs font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
              >
                Ask
              </button>
            )}
            <button
              type="button"
              onClick={() => setPlanning(todayISO)}
              className="rounded-full border border-accent-bright/40 bg-accent-bright/15 px-3 py-1.5 text-xs font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
            >
              {mealTitle(tonight) ? 'Change' : 'Plan'}
            </button>
          </span>
        )}
      </div>

      {tonight?.per_serving && <MacroPills ps={tonight.per_serving} />}

      {!mealTitle(tonight) && ballot && ballot.options.length > 0 && (
        <DinnerQuestion ballot={ballot} isParent={!!isParent} dayISO={todayISO} onChanged={refresh} />
      )}

      <FormError message={error} />

      <button
        type="button"
        onClick={() => setShowWeek((v) => !v)}
        aria-expanded={showWeek}
        className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-xl border border-accent-bright/30 bg-accent-bright/10 py-2 text-sm font-semibold text-accent-bright transition-colors hover:bg-accent-bright/20"
      >
        {showWeek ? 'Hide the week' : 'Plan the week'}
        {showWeek ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
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
          <div className="flex flex-col gap-1.5">
            {days.map((d) => {
              const iso = toISO(d)
              const meal = dinnerOn(iso)
              const title = mealTitle(meal)
              const cal = meal?.per_serving?.calories
              const isToday = iso === todayISO
              const dayLabel = (
                <span
                  className={`w-10 shrink-0 text-xs font-semibold uppercase ${
                    isToday ? 'text-accent-bright' : 'text-fg/45'
                  }`}
                >
                  {d.toLocaleDateString(undefined, { weekday: 'short' })}
                </span>
              )
              if (!isParent) {
                return (
                  <div key={iso} className="flex items-center gap-3 rounded-lg bg-fg/5 px-2.5 py-2">
                    {dayLabel}
                    <span className={`min-w-0 flex-1 truncate text-sm ${title ? 'text-fg/90' : 'text-fg/35'}`}>
                      {title ?? '—'}
                    </span>
                  </div>
                )
              }
              // Parents: a planned night reads as editable (pencil), an empty
              // one invites a pick — filling the week ahead should feel easy.
              return title ? (
                <button
                  key={iso}
                  type="button"
                  onClick={() => setPlanning(iso)}
                  className="flex w-full items-center gap-3 rounded-lg bg-fg/5 px-2.5 py-2 text-left transition-colors hover:bg-fg/10"
                >
                  {dayLabel}
                  <span className="min-w-0 flex-1 truncate text-sm text-fg/90">{title}</span>
                  {cal != null && (
                    <span className="shrink-0 text-xs text-fg/40">{Math.round(cal)} cal</span>
                  )}
                  <Pencil className="h-3.5 w-3.5 shrink-0 text-fg/40" />
                </button>
              ) : (
                <button
                  key={iso}
                  type="button"
                  onClick={() => setPlanning(iso)}
                  className="flex w-full items-center gap-3 rounded-lg border border-dashed border-fg/20 px-2.5 py-2 text-left transition-colors hover:border-accent-bright/40 hover:bg-fg/5"
                >
                  {dayLabel}
                  <span className="flex min-w-0 flex-1 items-center gap-1 truncate text-sm font-semibold text-accent-bright">
                    <Plus className="h-3.5 w-3.5" /> Add dinner
                  </span>
                </button>
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

      <AnimatePresence>
        {asking && (
          <AskSheet
            dayISO={todayISO}
            onClose={() => setAsking(false)}
            onAsked={() => {
              setAsking(false)
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
