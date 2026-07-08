import { DinnerPlanner } from '../components/Meals'
import { GroceryPanel } from '../components/Grocery'
import { CustomFoodBox, RecipeBox } from '../components/Recipes'

// The Kitchen tab, top to bottom: tonight's dinner and the week's menu (the
// hero), the grocery list you act on, then the recipe box and custom foods
// that feed both.
export function Kitchen() {
  return (
    <div className="flex flex-col gap-4">
      <DinnerPlanner />
      <GroceryPanel />
      <RecipeBox />
      <CustomFoodBox />
    </div>
  )
}
