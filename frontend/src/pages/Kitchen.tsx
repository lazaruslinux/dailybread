import { GroceryPanel } from '../components/Grocery'
import { RecipeBox } from '../components/Recipes'

// The Kitchen tab: the family's recipe box and shared grocery lists. The week
// dinner planner (which picks from these recipes) lands here next.
export function Kitchen() {
  return (
    <div className="flex flex-col gap-4">
      <RecipeBox />
      <GroceryPanel />
    </div>
  )
}
