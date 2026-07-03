# Roadmap

Where dailybread is headed, in order. Done items stay for history.

## Done

- **Auth + first-run setup** — bootstrap wizard creates the first parent/admin;
  admin-created accounts only, no public signup; Argon2 + httpOnly JWT cookie.
- **Admin dashboard** — family member management (roles, admin flag, password
  resets) with lockout guards so an install always keeps a working admin.
- **Live board** — routines, to-dos, and scheduled cards; streaks; a "Now"
  divider; assignees; tap to check off, visible edit affordance for parents.
- **Moods** — five-level daily mood rendered as weather, per-day, with a
  "keep it to myself" option that is indistinguishable from no mood at all.
- **Profiles** — bio, mood picker, and each member's slice of the board.
- **Four-tab shell** — Today / Food / Kitchen / Me with bottom navigation.
- **Grocery lists** — shared checklists, one per store plus a built-in General
  list; per-store clear; removing a store folds its items back into General.
- **Test suite + CI** — permission-matrix and privacy-rule tests (pytest,
  in-memory SQLite) plus typecheck/build, run on every push.

## Next

1. **Multi-household tenancy.** Every account belongs to exactly one family;
   all data is family-scoped; zero cross-family visibility. New "household"
   accounts get a create-your-family wizard on first login and become that
   family's head. Isolation is enforced by tests on every endpoint. This lands
   before any further features so everything after it is born scoped.
2. **First real deployment** — containerized frontend, PWA icons, HTTPS.
3. **Nutrition (Food tab)** — manual food log, then daily macro summary,
   then a barcode scanner (BarcodeDetector API with a WASM fallback) backed by
   Open Food Facts / USDA FoodData Central, importable into local Postgres so
   lookups never have to leave the server.
4. **Meals (Kitchen tab)** — tonight's dinner card and a week strip.
5. **Family chat** — messaging, then topic channels, then photo attachments.
6. **Fitness sync** — workouts flowing into the app and auto-completing
   matching board routines. Strava first (watch → Strava → server polling);
   direct Apple Health export as a self-hosted alternative path.

## Ongoing polish

- Optimistic updates (no full refetch per tap), undo toast for deletes,
  loading skeletons, longer sliding sessions, pull-to-refresh.
