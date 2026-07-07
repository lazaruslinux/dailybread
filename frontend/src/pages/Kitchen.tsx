import { UtensilsCrossed } from 'lucide-react'
import { GroceryPanel } from '../components/Grocery'
import { CustomFoodBox, RecipeBox } from '../components/Recipes'

// Placeholder for the dinner planner (KF4). It sits at the very top of the
// Kitchen as the page's hero — the most-important, always-open thing — so the
// order reads: what's for dinner → what to buy → the recipe/food library
// underneath. Kept a clear stub until the real planner replaces it.
function TonightHero() {
  const today = new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
  return (
    <section className="glass p-5">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-bright/15 text-accent-bright">
          <UtensilsCrossed className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-fg/40">Tonight · {today}</p>
          <h2 className="font-display text-xl font-semibold tracking-[-0.01em]">What's for dinner?</h2>
        </div>
      </div>
      <p className="mt-3 rounded-xl bg-fg/5 px-3 py-3 text-sm text-fg/50">
        The dinner planner lands here next. Pick the night's meal from your recipes below, and its
        ingredients flow straight to the grocery list.
      </p>
    </section>
  )
}

// The Kitchen tab, top to bottom: tonight's dinner (the hero), the grocery list
// you act on, then the recipe box and custom foods that feed both.
export function Kitchen() {
  return (
    <div className="flex flex-col gap-4">
      <TonightHero />
      <GroceryPanel />
      <RecipeBox />
      <CustomFoodBox />
    </div>
  )
}
