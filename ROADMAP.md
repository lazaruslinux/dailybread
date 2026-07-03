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
- **Ship-ready packaging** — the frontend is containerized behind nginx, so
  `docker compose up` serves the whole app on one port; sliding sessions
  (60-day idle expiry instead of a fixed weekly logout); real PWA icon set.

## Next

1. **First real deployment** — a family living in the app day to day, behind
   an HTTPS reverse proxy. Real usage feedback drives everything after this.
2. **Multi-household tenancy.** Every account belongs to exactly one family;
   all data is family-scoped; zero cross-family visibility. New "household"
   accounts get a create-your-family wizard on first login and become that
   family's head. Isolation is enforced by tests on every endpoint, written
   before the feature. Lands before any feature that adds new tables, so
   everything after it is born scoped.
3. **Themes** — selectable color schemes built on CSS variables.
4. **Nutrition (Food tab)** — manual food log, then daily macro summary,
   then a barcode scanner (BarcodeDetector API with a WASM fallback) backed by
   Open Food Facts / USDA FoodData Central, importable into local Postgres so
   lookups never have to leave the server.
5. **Meals (Kitchen tab)** — tonight's dinner card and a week strip.
6. **Family chat** — messaging, then topic channels, then photo attachments.
7. **Fitness sync** — workouts flowing into the app and auto-completing
   matching board routines. Strava first (watch → Strava → server polling);
   direct Apple Health export as a self-hosted alternative path.

## Ongoing polish

- Optimistic updates (no full refetch per tap), undo toast for deletes,
  loading skeletons, pull-to-refresh.
