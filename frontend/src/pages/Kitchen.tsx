import { DinnerPlanner } from '../components/Meals'
import { GroceryPanel } from '../components/Grocery'
import { CustomFoodBox, RecipeBox, SavedFoodBox } from '../components/recipes'
import { SharedRecipesBox } from '../components/SharedRecipes'

// The Kitchen tab, top to bottom: tonight's dinner and the week's menu (the
// hero), the grocery list you act on, then the recipe box and custom foods
// that feed both.
export function Kitchen() {
  return (
    <div className="flex flex-col gap-3">
      <DinnerPlanner />
      <GroceryPanel />
      <RecipeBox />
      <SharedRecipesBox />
      <SavedFoodBox />
      <CustomFoodBox />
    </div>
  )
}
