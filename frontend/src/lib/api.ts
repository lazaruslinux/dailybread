// Tiny API client. All requests go through the /api prefix, which the Vite dev
// server proxies to the FastAPI backend (see vite.config.ts). In production the
// same /api path is routed to the backend by whatever reverse proxy fronts the
// app.
//
// Security notes:
// - The session lives in an httpOnly cookie the browser attaches by itself.
//   This file never sees, stores, or logs a token, so a script injection has
//   nothing to steal from JS-land.
// - `credentials: 'same-origin'` sends the cookie only to our own origin.

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: 'same-origin',
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
  if (!res.ok) {
    // FastAPI errors carry a {"detail": "..."} body; fall back to the status.
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* non-JSON error body; keep the fallback message */
    }
    throw new ApiError(res.status, detail)
  }
  // 204 No Content has no body to parse.
  if (res.status === 204) return undefined as T
  return res.json()
}

// ---- health ----------------------------------------------------------------

export interface Health {
  status: string
  mode: string
  demo: boolean
}

export const getHealth = () => request<Health>('/health')

// ---- auth ------------------------------------------------------------------

export type Role = 'parent' | 'child'

export interface User {
  id: number
  username: string
  display_name: string
  role: Role
  is_admin: boolean
  // The instance "server admin": the only account that can invite new
  // households. Distinct from is_admin, which is family board management.
  is_owner: boolean
  // null only for a fresh "new household" account that hasn't run its
  // create-your-family wizard yet. The app uses this to route them there.
  family_id: number | null
  // ISO timestamp of the member's last avatar upload, or null if they have no
  // photo (the UI then draws generated initials). Doubles as a cache-busting
  // version for the avatar image URL.
  avatar_updated_at: string | null
  // True after an admin reset this account to a generated password. The app
  // routes to a choose-your-own-password screen (and the backend refuses
  // everything else) until they set one.
  must_change_password: boolean
}

export interface SetupState {
  initialized: boolean
}

export const getSetup = () => request<SetupState>('/auth/setup')

export const getMe = () => request<User>('/auth/me')

export const login = (username: string, password: string) =>
  request<User>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })

export const bootstrap = (username: string, display_name: string, password: string) =>
  request<User>('/auth/bootstrap', {
    method: 'POST',
    body: JSON.stringify({ username, display_name, password }),
  })

export const logout = () => request<void>('/auth/logout', { method: 'POST' })

export const changePassword = (current_password: string, new_password: string) =>
  request<User>('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password, new_password }),
  })

// ---- admin: family member management ----------------------------------------

export interface CreateUserPayload {
  username: string
  display_name: string
  password: string
  role: Role
  is_admin?: boolean
  // True creates a family-less parent account: whoever signs in with it
  // founds their own separate household via the create-family wizard. Used
  // only by "Invite another household", never by "Add family member".
  new_household?: boolean
}

export interface UpdateUserPayload {
  display_name?: string
  role?: Role
  is_admin?: boolean
  password?: string
}

export const listUsers = () => request<User[]>('/auth/users')

export const createUser = (payload: CreateUserPayload) =>
  request<User>('/auth/users', { method: 'POST', body: JSON.stringify(payload) })

export const updateUser = (id: number, payload: UpdateUserPayload) =>
  request<User>(`/auth/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })

export const deleteUser = (id: number) =>
  request<void>(`/auth/users/${id}`, { method: 'DELETE' })

// The generated password comes back exactly once, for the admin to hand over;
// the member's account is then locked to choosing their own until they do.
export interface PasswordReset {
  password: string
  user: User
}

export const resetPassword = (id: number) =>
  request<PasswordReset>(`/auth/users/${id}/reset-password`, { method: 'POST' })

// ---- families ----------------------------------------------------------------

export interface Family {
  id: number
  name: string
}

// The create-your-family wizard: a family-less account names its household and
// becomes its head (parent + admin). One family per account, ever.
export const createFamily = (name: string) =>
  request<Family>('/families', { method: 'POST', body: JSON.stringify({ name }) })

// ---- items and the home feed --------------------------------------------------

// The phone's local calendar date, YYYY-MM-DD. Sent with every "today"
// request because the server may live in a different timezone.
export function localDate(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export type ItemKind = 'routine' | 'task' | 'activity' | 'appointment'

// Who can SEE a card, separate from who is assigned to DO it. private = the
// owner plus anyone assigned; family = shown on the whole household's board.
export type Visibility = 'private' | 'family'

export type RepeatType = 'weekly' | 'monthly'

// A routine's recurrence. days are weekday numbers, 0 = Monday .. 6 = Sunday
// (weekly); month_day is a day of the month, 1-31 (monthly). interval is
// "every N weeks/months".
export interface Repeat {
  type: RepeatType
  days: number[]
  interval: number
  month_day: number | null
}

// One participant's own state on a routine, since routines are per-person.
export interface AssigneeCompletion {
  user_id: number
  completed: boolean
  streak: number
}

export interface FeedItem {
  id: number
  owner_id: number | null
  kind: ItemKind
  title: string
  notes: string
  visibility: Visibility
  assignees: User[]
  shared_to_feed: boolean
  time_of_day: string | null // start / "From", "HH:MM:SS"
  end_time: string | null // end / "To", "HH:MM:SS"
  all_day: boolean // all-day appointment
  date_for: string | null // "YYYY-MM-DD"
  repeat: Repeat | null // routines only
  // The requesting member's own view: for a routine, their own check and
  // streak (or, for a non-participant, whether everyone is done). For other
  // kinds, the single shared check.
  completed: boolean
  streak: number | null
  // Per-participant state for routines; null for every other kind.
  assignee_completions: AssigneeCompletion[] | null
}

export interface Feed {
  date: string
  // One-off cards past their date and still open (or checked off today). Never
  // routines. The client shows these under "Past due".
  overdue: FeedItem[]
  // Everything happening today: routines landing today, cards dated today, and
  // undated tasks. The client slices this by the clock into now / coming up /
  // anytime, and moves anything completed into "Done".
  today: FeedItem[]
  // One-off cards dated in the next seven days.
  next7: FeedItem[]
}

// The repeat object sent when creating/editing a routine. days/month_day are
// filled per type; the server ignores the ones the type doesn't use.
export interface RepeatInput {
  type: RepeatType
  days?: number[]
  interval?: number
  month_day?: number | null
}

export interface ItemPayload {
  kind: ItemKind
  title: string
  notes?: string
  // Who the card is shared with. Empty on a personal card means the owner
  // alone; set visibility to 'family' for Everyone.
  assignee_ids?: number[]
  visibility?: Visibility
  time_of_day?: string | null // start / "From"
  end_time?: string | null // end / "To"
  all_day?: boolean
  date_for?: string | null
  repeat?: RepeatInput | null // required for routines, ignored otherwise
  shared_to_feed?: boolean
}

export const getFeed = () => request<Feed>(`/items/feed?date=${localDate()}`)

export interface CalendarDay {
  date: string
  items: FeedItem[]
}
export interface Calendar {
  start: string
  end: string
  days: CalendarDay[]
}

// Scheduled cards across a date range, grouped by day (routines expanded onto
// each day they fall on). start/end are YYYY-MM-DD; the span is capped server-side.
export const getCalendar = (start: string, end: string) =>
  request<Calendar>(`/items/calendar?start=${start}&end=${end}`)

export const createItem = (payload: ItemPayload) =>
  request<FeedItem>('/items', { method: 'POST', body: JSON.stringify(payload) })

export const updateItem = (id: number, payload: Partial<ItemPayload>) =>
  request<FeedItem>(`/items/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })

export const deleteItem = (id: number) => request<void>(`/items/${id}`, { method: 'DELETE' })

// forUserId lets a parent check a routine off on another member's behalf. date
// defaults to today (the board); the calendar passes the day being viewed so a
// missed item is marked on its actual day.
const completePath = (id: number, forUserId?: number, date?: string) =>
  `/items/${id}/complete?date=${date ?? localDate()}${forUserId != null ? `&for=${forUserId}` : ''}`

export const completeItem = (id: number, forUserId?: number, date?: string) =>
  request<FeedItem>(completePath(id, forUserId, date), { method: 'POST' })

export const uncompleteItem = (id: number, forUserId?: number, date?: string) =>
  request<FeedItem>(completePath(id, forUserId, date), { method: 'DELETE' })

// ---- grocery list -----------------------------------------------------------

export interface GroceryItem {
  id: number
  title: string
  checked: boolean
  list_id: number | null // null = the General list
}

export interface GroceryList {
  id: number
  name: string
}

export interface GroceryState {
  lists: GroceryList[]
  items: GroceryItem[]
}

export const getGrocery = () => request<GroceryState>('/grocery')

export const addGroceryStore = (name: string) =>
  request<GroceryList>('/grocery/lists', { method: 'POST', body: JSON.stringify({ name }) })

export const removeGroceryStore = (id: number) =>
  request<void>(`/grocery/lists/${id}`, { method: 'DELETE' })

export const addGrocery = (title: string, listId: number | null) =>
  request<GroceryItem>('/grocery', {
    method: 'POST',
    body: JSON.stringify({ title, list_id: listId }),
  })

export const updateGrocery = (
  id: number,
  payload: { title?: string; checked?: boolean; list_id?: number | null },
) => request<GroceryItem>(`/grocery/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })

export const deleteGrocery = (id: number) =>
  request<void>(`/grocery/${id}`, { method: 'DELETE' })

export const clearCheckedGrocery = (listId: number | null) =>
  request<GroceryState>(`/grocery/clear-checked${listId !== null ? `?list_id=${listId}` : ''}`, {
    method: 'POST',
  })

// ---- foods --------------------------------------------------------------------

export type FoodSource = 'usda' | 'off' | 'custom'

// The measure family a food is portioned in: "g" (mass) or "ml" (volume, for a
// liquid). Nutrition is stored per 100 of this unit; amounts never cross between
// families (that needs a density we don't have).
export type BaseUnit = 'g' | 'ml'

// A named portion of a food (e.g. "1 slice" = 21 g, or "1 tbsp" = 15 mL). The
// `grams` field is the size in the food's base unit — grams for a solid,
// millilitres for a liquid. Custom foods carry these.
export interface FoodServing {
  name: string
  grams: number
}

// A food with per-100-base-unit nutrition. `id` is null for an un-saved
// search/barcode result (the server saves it when it's first used in a recipe);
// set for a stored custom food. Nutrient fields are null when a source didn't
// supply them; cholesterol/sodium are in mg (as labels print), the rest in grams.
export interface Food {
  id: number | null
  source: FoodSource
  source_id: string | null
  name: string
  brand: string
  base_unit: BaseUnit
  serving: string // display label for the source's serving, e.g. "1 slice (21 g)"; "" when unknown
  servings: FoodServing[]
  calories: number | null
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  saturated_fat_g: number | null
  trans_fat_g: number | null
  cholesterol_mg: number | null
  sodium_mg: number | null
  fiber_g: number | null
  sugar_g: number | null
}

// Creating/editing a custom food: the parent enters one or more named servings
// and the Nutrition Facts as printed for one chosen serving (`basis_index`); the
// server converts to per-100g.
export interface CustomFoodPayload {
  name: string
  brand?: string
  // Product barcode digits, so a later scan resolves straight to this food.
  barcode?: string | null
  base_unit?: BaseUnit
  servings: FoodServing[]
  basis_index: number
  calories?: number | null
  protein_g?: number | null
  carbs_g?: number | null
  fat_g?: number | null
  saturated_fat_g?: number | null
  trans_fat_g?: number | null
  cholesterol_mg?: number | null
  sodium_mg?: number | null
  fiber_g?: number | null
  sugar_g?: number | null
}

export const searchFoods = (q: string) =>
  request<Food[]>(`/foods/search?q=${encodeURIComponent(q)}`)

export const lookupBarcode = (code: string) => request<Food>(`/foods/barcode/${code}`)

export const getCustomFoods = () => request<Food[]>('/foods')

export const createCustomFood = (payload: CustomFoodPayload) =>
  request<Food>('/foods', { method: 'POST', body: JSON.stringify(payload) })

export const updateCustomFood = (id: number, payload: CustomFoodPayload) =>
  request<Food>(`/foods/${id}`, { method: 'PUT', body: JSON.stringify(payload) })

export const deleteCustomFood = (id: number) =>
  request<void>(`/foods/${id}`, { method: 'DELETE' })

// ---- meals (the family menu) ----------------------------------------------------

export type MealSlot = 'breakfast' | 'lunch' | 'dinner'

export interface Meal {
  date_for: string
  slot: MealSlot
  recipe_id: number | null
  recipe_name: string | null
  custom_title: string | null
  per_serving: RecipeMacros | null
}

export const getMeals = (start: string, end: string) =>
  request<Meal[]>(`/meals?start=${start}&end=${end}`)

export const setMeal = (payload: {
  date_for: string
  slot?: MealSlot
  recipe_id?: number | null
  custom_title?: string | null
}) => request<Meal>('/meals', { method: 'PUT', body: JSON.stringify(payload) })

export const clearMeal = (date: string) =>
  request<void>(`/meals?date=${date}`, { method: 'DELETE' })

export const pushRecipeToGrocery = (recipeId: number, listId: number | null) =>
  request<{ added: number }>(`/recipes/${recipeId}/grocery`, {
    method: 'POST',
    body: JSON.stringify({ list_id: listId }),
  })

// ---- recipes ------------------------------------------------------------------

// Mass units (a solid) and volume units (a liquid). An ingredient's unit must
// match its food's base measure; the two never mix on one line.
export type MassUnit = 'g' | 'oz' | 'lb'
export type VolumeUnit = 'ml' | 'floz' | 'cup' | 'tbsp' | 'tsp'
export type AmountUnit = MassUnit | VolumeUnit

// One saved ingredient line: what food, how much, and the macros that amount
// contributes (per-100g scaled by grams), so the client totals without redoing
// the math. `grams` is the canonical amount those contributions are based on.
export interface RecipeIngredient {
  id: number
  food_id: number
  source: FoodSource
  source_id: string | null
  name: string
  brand: string
  amount: number
  unit: string
  grams: number
  calories: number | null
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  saturated_fat_g: number | null
  trans_fat_g: number | null
  cholesterol_mg: number | null
  sodium_mg: number | null
  fiber_g: number | null
  sugar_g: number | null
}

// Per-serving nutrition, computed from the lines — the whole Nutrition Facts
// label. A field is null when no ingredient supplied that nutrient (so it reads
// "—", not a misleading 0).
export interface RecipeMacros {
  calories: number | null
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  saturated_fat_g: number | null
  trans_fat_g: number | null
  cholesterol_mg: number | null
  sodium_mg: number | null
  fiber_g: number | null
  sugar_g: number | null
}

export interface Recipe {
  id: number
  name: string
  servings: number
  steps: string
  ingredients: RecipeIngredient[]
  per_serving: RecipeMacros
}

// An ingredient line being saved. It carries the whole food (not just an id):
// a search/barcode food isn't in our database until it's used, so saving the
// recipe is what persists it. `food_id` is set only when reusing a food that's
// already saved (a custom food, or one a prior recipe cached).
export interface RecipeIngredientPayload {
  food_id?: number | null
  source: FoodSource
  source_id?: string | null
  name: string
  brand?: string
  calories?: number | null
  protein_g?: number | null
  carbs_g?: number | null
  fat_g?: number | null
  saturated_fat_g?: number | null
  trans_fat_g?: number | null
  cholesterol_mg?: number | null
  sodium_mg?: number | null
  fiber_g?: number | null
  sugar_g?: number | null
  amount: number
  unit: AmountUnit
}

// Create/edit payload. On edit, omitting `ingredients` leaves them; sending the
// array replaces the whole list.
export interface RecipePayload {
  name: string
  servings?: number
  steps?: string
  ingredients?: RecipeIngredientPayload[]
}

export const getRecipes = () => request<Recipe[]>('/recipes')

export const createRecipe = (payload: RecipePayload) =>
  request<Recipe>('/recipes', { method: 'POST', body: JSON.stringify(payload) })

export const updateRecipe = (id: number, payload: RecipePayload) =>
  request<Recipe>(`/recipes/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })

export const deleteRecipe = (id: number) =>
  request<void>(`/recipes/${id}`, { method: 'DELETE' })

// ---- profiles and moods ---------------------------------------------------------

export type MoodLevel = 'sunny' | 'partly' | 'cloudy' | 'rainy' | 'stormy'

export interface Mood {
  level: MoodLevel
  hidden: boolean
}

export interface FamilyMember extends User {
  mood: Mood | null
}

export interface Profile extends FamilyMember {
  bio: string
  created_at: string
}

export const getFamily = () => request<FamilyMember[]>(`/users?date=${localDate()}`)

export const getProfile = (id: number) =>
  request<Profile>(`/users/${id}/profile?date=${localDate()}`)

export const updateMyProfile = (payload: { display_name?: string; bio?: string }) =>
  request<Profile>('/me/profile', { method: 'PATCH', body: JSON.stringify(payload) })

// The image URL for a member's avatar, or null when they have no photo. The
// avatar_updated_at value is appended so the browser refetches after a change
// but caches hard otherwise (the server sends an immutable cache header).
export const avatarUrl = (u: { id: number; avatar_updated_at: string | null }): string | null =>
  u.avatar_updated_at
    ? `/api/users/${u.id}/avatar?v=${encodeURIComponent(u.avatar_updated_at)}`
    : null

// Multipart upload can't go through request(): the browser must set its own
// multipart Content-Type with the boundary, so we call fetch directly here.
export async function uploadAvatar(userId: number, file: File): Promise<Profile> {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(`/api/users/${userId}/avatar`, {
    method: 'POST',
    credentials: 'same-origin',
    body,
  })
  if (!res.ok) {
    let detail = `Upload failed (${res.status})`
    try {
      const b = await res.json()
      if (typeof b?.detail === 'string') detail = b.detail
    } catch {
      /* keep the fallback */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json()
}

export const removeAvatar = (userId: number) =>
  request<void>(`/users/${userId}/avatar`, { method: 'DELETE' })

export const setMyMood = (level: MoodLevel, hidden: boolean) =>
  request<Mood>('/me/mood', {
    method: 'PUT',
    body: JSON.stringify({ date_for: localDate(), level, hidden }),
  })

export const clearMyMood = () =>
  request<void>(`/me/mood?date=${localDate()}`, { method: 'DELETE' })

// ---- journal (private daily entries) ------------------------------------------

export interface JournalEntry {
  date_for: string
  body: string
  updated_at: string
}

// Today's entry, or null when nothing is written yet.
export const getJournal = (date = localDate()) =>
  request<JournalEntry | null>(`/me/journal?date=${date}`)

export const getJournalHistory = () => request<JournalEntry[]>('/me/journal/history')

// Upsert a day's entry. A blank body clears it (returned body is "").
export const saveJournal = (body: string, date = localDate()) =>
  request<JournalEntry>('/me/journal', {
    method: 'PUT',
    body: JSON.stringify({ date_for: date, body }),
  })

// ---- the nutrition diary -------------------------------------------------------

// A member's personal food log. Entries snapshot their nutrition at log time
// (server-computed), so editing recipes or foods later never rewrites history.

export type DiarySlot = 'breakfast' | 'lunch' | 'dinner' | 'snack'

export interface DiaryEntry {
  id: number
  date_for: string
  slot: DiarySlot
  time_of_day: string | null // "HH:MM:SS"
  name: string
  brand: string
  food_id: number | null
  recipe_id: number | null
  amount: number
  unit: string // an AmountUnit, or "srv" for a recipe entry
  label: string | null // human phrasing of the portion ("2 slice")
  calories: number | null
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  saturated_fat_g: number | null
  trans_fat_g: number | null
  cholesterol_mg: number | null
  sodium_mg: number | null
  fiber_g: number | null
  sugar_g: number | null
}

// Daily targets: each member sets their own calorie budget and macro split
// (the percentages must sum to 100). The *_g fields are derived server-side.
export interface NutritionTargets {
  mode: TargetMode
  // Includes the day's exercise burn when served for a specific day.
  calories: number
  exercise_kcal: number
  protein_pct: number
  carbs_pct: number
  fat_pct: number
  protein_g: number
  carbs_g: number
  fat_g: number
}

export interface DiaryDay {
  date: string
  targets: NutritionTargets
  consumed: RecipeMacros
  entries: DiaryEntry[]
  exercise: ExerciseEntry[]
  burned: number
}

// Logging something eaten: a recipe by servings (recipe_id + amount), or a
// food carried whole like a recipe ingredient line (id when saved, else
// source/name/nutrition to find-or-create). The server computes totals.
export interface DiaryEntryPayload extends Partial<Omit<RecipeIngredientPayload, 'amount' | 'unit'>> {
  date_for: string
  slot: DiarySlot
  time_of_day?: string | null
  amount: number
  unit?: AmountUnit
  label?: string | null
  recipe_id?: number
}

export interface DiaryEntryPatch {
  amount?: number
  unit?: AmountUnit
  label?: string | null
  slot?: DiarySlot
  time_of_day?: string | null
  date_for?: string
}

export const getDiary = (date: string) => request<DiaryDay>(`/diary?date=${date}`)

export const createDiaryEntry = (payload: DiaryEntryPayload) =>
  request<DiaryEntry>('/diary', { method: 'POST', body: JSON.stringify(payload) })

export const updateDiaryEntry = (id: number, patch: DiaryEntryPatch) =>
  request<DiaryEntry>(`/diary/${id}`, { method: 'PATCH', body: JSON.stringify(patch) })

export const deleteDiaryEntry = (id: number) =>
  request<void>(`/diary/${id}`, { method: 'DELETE' })

export const setNutritionTargets = (t: {
  calories: number
  protein_pct: number
  carbs_pct: number
  fat_pct: number
  mode?: TargetMode
}) => request<NutritionTargets>('/diary/targets', { method: 'PUT', body: JSON.stringify(t) })

// ---- health profile, weigh-ins, and the computed target -------------------------

// Health data is as private as the diary, with one exception: parents see and
// manage a CHILD's health section (children never set their own goals).

export type Sex = 'male' | 'female'
export type ActivityLevel = 'sedentary' | 'light' | 'moderate' | 'active' | 'very_active'
export type GoalType = 'lose' | 'maintain' | 'gain'
export type TargetMode = 'manual' | 'auto'

export interface HealthProfile {
  birthdate: string | null
  sex: Sex | null
  height_cm: number | null
  activity_level: ActivityLevel | null
  goal: GoalType | null
  rate_lbs_per_week: number | null
  goal_weight_kg: number | null
  goal_body_fat_pct: number | null
}

export interface WeightEntry {
  date_for: string
  weight_kg: number
  body_fat_pct: number | null
}

// Estimates from the profile + latest weigh-in; null until both are complete.
export interface ComputedHealth {
  bmr: number
  tdee: number
  maintenance_calories: number
  auto_calories: number
  at_goal: boolean
}

export interface Health {
  profile: HealthProfile | null
  latest_weight: WeightEntry | null
  weights: WeightEntry[] // recent first
  computed: ComputedHealth | null
}

export const getHealthProfile = () => request<Health>('/me/health')

export const updateHealthProfile = (
  p: Partial<Pick<HealthProfile, 'birthdate' | 'sex' | 'height_cm' | 'activity_level'>>,
) => request<Health>('/me/health/profile', { method: 'PUT', body: JSON.stringify(p) })

export const logWeight = (date_for: string, weight_kg: number, body_fat_pct?: number | null) =>
  request<Health>('/me/health/weight', {
    method: 'PUT',
    body: JSON.stringify({ date_for, weight_kg, body_fat_pct: body_fat_pct ?? null }),
  })

export interface GoalPayload {
  goal: GoalType
  rate_lbs_per_week?: number | null
  goal_weight_kg?: number | null
  goal_body_fat_pct?: number | null
}

export const setHealthGoal = (g: GoalPayload) =>
  request<Health>('/me/health/goal', { method: 'PUT', body: JSON.stringify(g) })

// Parent-managed: a child's health section.
export const getMemberHealth = (id: number) => request<Health>(`/members/${id}/health`)

export const setMemberGoal = (id: number, g: GoalPayload) =>
  request<Health>(`/members/${id}/health/goal`, { method: 'PUT', body: JSON.stringify(g) })

// ---- exercise log ----------------------------------------------------------------

export type ExerciseActivity = 'running' | 'walking'
export type ExerciseEffort = 'light' | 'moderate' | 'vigorous'

export interface ExerciseEntry {
  id: number
  date_for: string
  time_of_day: string | null
  activity: ExerciseActivity
  label: string
  effort: ExerciseEffort
  minutes: number
  kcal: number
}

export const logExercise = (payload: {
  date_for: string
  activity: ExerciseActivity
  effort: ExerciseEffort
  minutes: number
  time_of_day?: string | null
}) => request<ExerciseEntry>('/me/exercise', { method: 'POST', body: JSON.stringify(payload) })

export const updateExercise = (
  id: number,
  patch: { minutes?: number; effort?: ExerciseEffort; time_of_day?: string | null },
) => request<ExerciseEntry>(`/me/exercise/${id}`, { method: 'PATCH', body: JSON.stringify(patch) })

export const deleteExercise = (id: number) =>
  request<void>(`/me/exercise/${id}`, { method: 'DELETE' })

// ---- web push (reminders) -------------------------------------------------------

export const getPushKey = () => request<{ key: string }>('/push/key')

export const subscribePush = (endpoint: string, keys: { p256dh: string; auth: string }) =>
  request<void>('/push/subscription', {
    method: 'PUT',
    body: JSON.stringify({ endpoint, keys }),
  })

export const unsubscribePush = (endpoint: string) =>
  request<void>('/push/subscription', {
    method: 'DELETE',
    body: JSON.stringify({ endpoint }),
  })

export const sendTestPush = () => request<{ sent: number }>('/push/test', { method: 'POST' })
