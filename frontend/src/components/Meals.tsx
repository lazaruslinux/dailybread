import { AnimatePresence } from 'framer-motion'
import { Bike, Car, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, CookingPot, Pencil, Plus, Utensils, UtensilsCrossed } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
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
// The Dinner Plan: four standing modes, always on for today until dinner is
// set, and the same four modes behind every day of the week planner — a pick
// made for Friday is simply Friday's vote, preselected when Friday arrives.
// Adults tap a pick; each voter's typed detail rides WITH their name, so two
// competing restaurants read as two people's picks. Kid-mode avatars ride the
// leading choice, faded — they eat whatever wins, they never vote.

const CHOICES: {
  id: api.DinnerChoice
  label: string
  hint: string
  Icon: typeof Utensils
}[] = [
  { id: 'self_serve', label: 'Self-Serve', hint: 'Everyone fends for themselves', Icon: Utensils },
  { id: 'homemade', label: 'Homemade', hint: 'Cooked at home', Icon: CookingPot },
  { id: 'go_out', label: 'Go Out', hint: 'Pick a restaurant', Icon: Car },
  { id: 'delivery', label: 'Delivery', hint: 'Order in', Icon: Bike },
]

const EMPTY_PLAN = (dayISO: string): api.DinnerPlan => ({
  date_for: dayISO,
  votes: [],
  kids: [],
})

function leaderOf(plan: api.DinnerPlan): api.DinnerChoice | null {
  const counts = new Map<api.DinnerChoice, number>()
  for (const v of plan.votes) counts.set(v.choice, (counts.get(v.choice) ?? 0) + 1)
  const max = Math.max(0, ...counts.values())
  return max > 0 ? (CHOICES.find((c) => (counts.get(c.id) ?? 0) === max)?.id ?? null) : null
}

function VoterBubble({ voter, faded }: { voter: api.DinnerVoter; faded?: boolean }) {
  const url = api.avatarUrl(voter)
  return url ? (
    <img
      src={url}
      alt=""
      title={voter.display_name}
      className={`h-5 w-5 rounded-full border border-fg/15 object-cover ${faded ? 'opacity-50' : ''}`}
    />
  ) : (
    <span
      title={voter.display_name}
      className={`flex h-5 w-5 items-center justify-center rounded-full bg-gradient-to-br from-accent-bright/60 to-accent-strong/60 text-[8px] font-bold text-fg ${faded ? 'opacity-50' : ''}`}
    >
      {voter.display_name
        .split(/\s+/)
        .slice(0, 2)
        .map((w) => w[0]?.toUpperCase() ?? '')
        .join('')}
    </span>
  )
}

// A voter with their own typed detail attached: "Alex · Chipotle". Two
// people, two restaurants, two chips — nobody's pick masquerades as the row's.
function VoterChip({ vote }: { vote: api.DinnerVote }) {
  const extra = vote.detail || vote.recipe_name
  return (
    <span className="flex items-center gap-1.5 rounded-full border border-fg/10 bg-fg/10 py-0.5 pl-0.5 pr-2">
      <VoterBubble voter={vote.user} />
      <span className="max-w-36 truncate text-[11px] font-semibold text-fg/70">
        {vote.user.display_name.split(/\s+/)[0]}
        {extra && <span className="font-normal text-fg/50"> · {extra}</span>}
      </span>
    </span>
  )
}

function DetailSheet({
  choice,
  current,
  onClose,
  onVote,
  onRetract,
}: {
  choice: (typeof CHOICES)[number]
  current: api.DinnerVote | null
  onClose: () => void
  onVote: (detail: string, recipeId: number | null) => Promise<void>
  onRetract: (() => Promise<void>) | null
}) {
  const [detail, setDetail] = useState(current?.detail ?? '')
  const [recipeId, setRecipeId] = useState<number | null>(current?.recipe_id ?? null)
  const [recipes, setRecipes] = useState<api.Recipe[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (choice.id === 'homemade') api.getRecipes().then(setRecipes).catch(() => {})
  }, [choice.id])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onVote(detail.trim(), recipeId)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 text-lg font-bold">{choice.label}</h3>
      <p className="mb-4 text-sm text-fg/60">{choice.hint}</p>
      <form onSubmit={submit} noValidate className="flex flex-col gap-3">
        <Field
          label={choice.id === 'homemade' ? 'What are we making? (optional)' : 'Where? (optional)'}
          value={detail}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
            setDetail(e.target.value)
            setRecipeId(null)
          }}
          maxLength={30}
        />
        {choice.id === 'homemade' && recipes.length > 0 && (
          <div>
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-fg/50">
              Or a recipe
            </span>
            <div className="flex max-h-24 flex-wrap gap-1.5 overflow-y-auto">
              {recipes.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => {
                    setRecipeId(r.id)
                    setDetail(r.name.slice(0, 30))
                  }}
                  className={`rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors ${
                    recipeId === r.id
                      ? 'border-accent-bright/60 bg-accent-bright/20 text-fg'
                      : 'border-fg/10 bg-fg/5 text-fg/70 hover:bg-fg/10'
                  }`}
                >
                  {r.name}
                </button>
              ))}
            </div>
          </div>
        )}
        <FormError message={error} />
        <Button type="submit" disabled={busy}>
          {busy ? 'Saving…' : current ? 'Change my pick' : 'This is my pick'}
        </Button>
        {onRetract && (
          <button
            type="button"
            onClick={onRetract}
            className="text-center text-xs font-semibold text-fg/40 hover:text-fg/60"
          >
            Remove my vote
          </button>
        )}
      </form>
    </Sheet>
  )
}

// One option card: header row (icon, label, hint, Lock it in), then the
// voters' chips on their own line so every pick sits beside its person.
function ChoiceRow({
  choice,
  plan,
  mine,
  isParent,
  leader,
  onTap,
  onLock,
}: {
  choice: (typeof CHOICES)[number]
  plan: api.DinnerPlan
  mine: boolean
  isParent: boolean
  leader: api.DinnerChoice | null
  onTap: () => void
  onLock: (() => void) | null
}) {
  const voters = plan.votes.filter((v) => v.choice === choice.id)
  return (
    <div
      className={`rounded-xl border px-3 py-2.5 ${
        mine ? 'border-accent-bright/60 bg-accent-bright/15' : 'border-fg/10 bg-fg/5'
      }`}
    >
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          onClick={onTap}
          className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
        >
          <choice.Icon className="h-4 w-4 shrink-0 text-accent-bright" />
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold text-fg/90">{choice.label}</span>
            <span className="block truncate text-xs italic text-fg/40">{choice.hint}</span>
          </span>
        </button>
        {isParent && onLock && voters.length > 0 && (
          <button
            type="button"
            onClick={onLock}
            className="shrink-0 rounded-full border border-accent-bright/40 bg-accent-bright/15 px-2.5 py-1 text-[11px] font-semibold text-accent-bright transition-colors hover:bg-accent-bright/25"
          >
            Lock it in
          </button>
        )}
      </div>
      {(voters.length > 0 || (leader === choice.id && plan.kids.length > 0)) && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {voters.map((v) => (
            <VoterChip key={v.user.id} vote={v} />
          ))}
          {leader === choice.id &&
            plan.kids.map((k) => <VoterBubble key={k.id} voter={k} faded />)}
        </div>
      )}
    </div>
  )
}

function DinnerPlanBlock({
  plan,
  isParent,
  me,
  dayISO,
  onChanged,
}: {
  plan: api.DinnerPlan
  isParent: boolean
  me: number | undefined
  dayISO: string
  onChanged: () => void
}) {
  const [detailFor, setDetailFor] = useState<(typeof CHOICES)[number] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const myVote = plan.votes.find((v) => v.user.id === me) ?? null
  const leader = leaderOf(plan)

  async function voteFor(choice: api.DinnerChoice, detail = '', recipeId: number | null = null) {
    setError(null)
    try {
      await api.castDinnerVote(dayISO, { choice, detail, recipe_id: recipeId })
      setDetailFor(null)
      onChanged()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      throw err
    }
  }

  async function retract() {
    setError(null)
    await api.retractDinnerVote(dayISO)
    setDetailFor(null)
    onChanged()
  }

  async function lockIn(c: (typeof CHOICES)[number]) {
    setError(null)
    try {
      const winners = plan.votes.filter((v) => v.choice === c.id)
      const withRecipe = winners.find((v) => v.recipe_id != null)
      if (c.id === 'homemade' && withRecipe?.recipe_id != null) {
        await api.setMeal({ date_for: dayISO, recipe_id: withRecipe.recipe_id })
      } else {
        const detail = winners.map((v) => v.detail).find(Boolean) ?? ''
        await api.setMeal({
          date_for: dayISO,
          custom_title: detail ? `${c.label} · ${detail}` : c.label,
        })
      }
      onChanged()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
    }
  }

  function tapped(c: (typeof CHOICES)[number]) {
    if (!isParent) return
    if (c.id === 'self_serve') {
      if (myVote?.choice === 'self_serve') retract()
      else voteFor('self_serve').catch(() => {})
      return
    }
    setDetailFor(c)
  }

  return (
    <div className="mt-3 rounded-xl border border-accent-bright/25 bg-accent-bright/5 p-3" data-dinner-plan>
      <div className="flex flex-col gap-1.5">
        {CHOICES.map((c) => (
          <ChoiceRow
            key={c.id}
            choice={c}
            plan={plan}
            mine={myVote?.choice === c.id}
            isParent={isParent}
            leader={leader}
            onTap={() => tapped(c)}
            onLock={() => lockIn(c)}
          />
        ))}
      </div>
      <FormError message={error} />

      <AnimatePresence>
        {detailFor && (
          <DetailSheet
            choice={detailFor}
            current={myVote?.choice === detailFor.id ? myVote : null}
            onClose={() => setDetailFor(null)}
            onVote={(detail, recipeId) => voteFor(detailFor.id, detail, recipeId)}
            onRetract={myVote?.choice === detailFor.id ? retract : null}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

// The week planner's +Set: the same four modes for a future day. A pick here
// is simply that day's vote; no locking from a distance, no typing dinners in.
function DayPlanSheet({
  dayISO,
  plan,
  lockedTitle,
  me,
  onClose,
  onChanged,
}: {
  dayISO: string
  plan: api.DinnerPlan
  lockedTitle: string | null
  me: number | undefined
  onClose: () => void
  onChanged: () => void
}) {
  const [detailFor, setDetailFor] = useState<(typeof CHOICES)[number] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const myVote = plan.votes.find((v) => v.user.id === me) ?? null
  const leader = leaderOf(plan)
  const dayLabel = new Date(dayISO + 'T12:00:00').toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  })

  async function voteFor(choice: api.DinnerChoice, detail = '', recipeId: number | null = null) {
    setError(null)
    try {
      await api.castDinnerVote(dayISO, { choice, detail, recipe_id: recipeId })
      setDetailFor(null)
      onChanged()
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
      throw err
    }
  }

  async function retract() {
    await api.retractDinnerVote(dayISO)
    setDetailFor(null)
    onChanged()
  }

  if (lockedTitle) {
    return (
      <Sheet onClose={onClose}>
        <h3 className="mb-1 text-lg font-bold">{dayLabel}</h3>
        <p className="mb-4 text-sm text-fg/70">
          Planned: <span className="font-semibold text-fg/90">{lockedTitle}</span>
        </p>
        <FormError message={error} />
        <Button
          type="button"
          variant="ghost"
          className="w-full"
          onClick={async () => {
            try {
              await api.clearMeal(dayISO)
              onChanged()
            } catch (err) {
              setError(err instanceof api.ApiError ? err.message : 'Something went wrong.')
            }
          }}
        >
          Unlock this day
        </Button>
      </Sheet>
    )
  }

  return (
    <Sheet onClose={onClose}>
      <h3 className="mb-1 text-lg font-bold">{dayLabel}</h3>
      <p className="mb-4 text-sm text-fg/60">
        Make your pick — it'll be waiting in the Dinner Plan when the day comes.
      </p>
      <div className="flex flex-col gap-1.5">
        {CHOICES.map((c) => (
          <ChoiceRow
            key={c.id}
            choice={c}
            plan={plan}
            mine={myVote?.choice === c.id}
            isParent
            leader={leader}
            onTap={() => {
              if (c.id === 'self_serve') {
                if (myVote?.choice === 'self_serve') retract()
                else voteFor('self_serve').catch(() => {})
              } else setDetailFor(c)
            }}
            onLock={null}
          />
        ))}
      </div>
      <FormError message={error} />
      {myVote && (
        <button
          type="button"
          onClick={retract}
          className="mt-2 w-full text-center text-xs font-semibold text-fg/40 hover:text-fg/60"
        >
          Remove my pick
        </button>
      )}

      <AnimatePresence>
        {detailFor && (
          <DetailSheet
            choice={detailFor}
            current={myVote?.choice === detailFor.id ? myVote : null}
            onClose={() => setDetailFor(null)}
            onVote={(detail, recipeId) => voteFor(detailFor.id, detail, recipeId)}
            onRetract={myVote?.choice === detailFor.id ? retract : null}
          />
        )}
      </AnimatePresence>
    </Sheet>
  )
}

export function DinnerPlanner() {
  const { user } = useAuth()
  const isParent = user?.role === 'parent'
  const todayISO = toISO(new Date())
  const [weekStart, setWeekStart] = useState(() => weekStartOf(new Date()))
  const [meals, setMeals] = useState<api.Meal[]>([])
  const [error, setError] = useState<string | null>(null)
  const [planning, setPlanning] = useState<string | null>(null) // dayISO in the DayPlanSheet
  const [weekPlans, setWeekPlans] = useState<Record<string, api.DinnerPlan>>({})
  const [showWeek, setShowWeek] = useState(false)
  const [plan, setPlan] = useState<api.DinnerPlan | null>(null)

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
      setPlan(await api.getDinnerPlan(todayISO))
      const ranged = await api.getDinnerPlanRange(toISO(days[0]), toISO(days[6]))
      setWeekPlans(Object.fromEntries(ranged.map((p) => [p.date_for, p])))
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
            {mealTitle(tonight) ?? 'Dinner Plan'}
          </h2>
        </div>
      </div>

      {tonight?.per_serving && <MacroPills ps={tonight.per_serving} />}

      {!mealTitle(tonight) && plan && (
        <DinnerPlanBlock
          plan={plan}
          isParent={!!isParent}
          me={user?.id}
          dayISO={todayISO}
          onChanged={refresh}
        />
      )}
      {mealTitle(tonight) && isParent && (
        <button
          type="button"
          onClick={async () => {
            await api.clearMeal(todayISO)
            refresh()
          }}
          className="mt-1.5 w-full text-center text-xs font-semibold text-fg/40 hover:text-fg/60"
        >
          Unlock tonight's plan
        </button>
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
              const dayPlan = weekPlans[iso]
              // Compact everyone-sees-everyone: YOUR pick spelled out when you
              // have one (else the leader's), plus how many other votes exist.
              const myDayVote = dayPlan?.votes.find((v) => v.user.id === user?.id) ?? null
              const dayLeader = dayPlan ? leaderOf(dayPlan) : null
              const shownVote =
                myDayVote ?? dayPlan?.votes.find((v) => v.choice === dayLeader) ?? null
              const shownChoice = CHOICES.find((c) => c.id === shownVote?.choice)
              const others = (dayPlan?.votes.length ?? 0) - (shownVote ? 1 : 0)
              const summary = shownChoice
                ? shownChoice.label +
                  (shownVote?.detail || shownVote?.recipe_name
                    ? ' · ' + (shownVote.detail || shownVote.recipe_name)
                    : '') +
                  (others > 0 ? ` + ${others} other vote${others > 1 ? 's' : ''}` : '')
                : null
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
                    <span className={`min-w-0 flex-1 truncate text-sm ${title ?? summary ? 'text-fg/90' : 'text-fg/35'}`}>
                      {title ?? summary ?? '—'}
                    </span>
                  </div>
                )
              }
              // Parents: a locked night reads as set (tap to unlock), a night
              // with picks shows where the wind is blowing, an empty one
              // invites the four choices.
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
                  className={`flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors ${
                    summary
                      ? 'bg-fg/5 hover:bg-fg/10'
                      : 'border border-dashed border-fg/20 hover:border-accent-bright/40 hover:bg-fg/5'
                  }`}
                >
                  {dayLabel}
                  {summary ? (
                    <>
                      <span className="min-w-0 flex-1 truncate text-sm text-fg/80">{summary}</span>
                      <span className="flex shrink-0 items-center -space-x-1">
                        {(dayPlan?.votes ?? []).map((v) => (
                          <VoterBubble key={v.user.id} voter={v.user} />
                        ))}
                      </span>
                    </>
                  ) : (
                    <span className="flex min-w-0 flex-1 items-center gap-1 truncate text-sm font-semibold text-accent-bright">
                      <Plus className="h-3.5 w-3.5" /> Set
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}

      <AnimatePresence>
        {planning && (
          <DayPlanSheet
            dayISO={planning}
            plan={weekPlans[planning] ?? (planning === todayISO && plan ? plan : EMPTY_PLAN(planning))}
            lockedTitle={mealTitle(dinnerOn(planning))}
            me={user?.id}
            onClose={() => setPlanning(null)}
            onChanged={refresh}
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
