# Roadmap

Where dailybread is headed, in order. Done items stay for history.

## Done

- **Auth + first-run setup** — bootstrap wizard creates the first parent/admin;
  admin-created accounts only, no public signup; Argon2 + httpOnly JWT cookie.
- **Admin dashboard** — family member management (roles, admin flag, password
  resets) with lockout guards so an install always keeps a working admin.
- **Live board** — routines, tasks, and scheduled cards; streaks; a "Now"
  divider; assignees; a checkbox completes a card (optimistic, with an undo
  toast) and tapping the card body opens a detail sheet with the full info
  plus edit/delete for parents.
- **Daily verse** — a verse of the day at the bottom of the board, rotating
  through a bundled NKJV set (quoted under the publisher's gratis use
  policy) keyed to the calendar day, weighted toward the New Testament and
  the words of Jesus, so it needs no network and phones home to no one;
  tapping it opens the passage on Bible.com.
- **Done stays visible** — checked cards stay on the board, crossed out,
  until the day rolls over; scheduled cards show on the board no matter how
  far out they are.
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

- **First real deployment** — a family living in the app day to day, behind
  an HTTPS reverse proxy. Real usage feedback drives everything after this.
- **Multi-household tenancy (backend)** — every account belongs to exactly
  one family; all data is family-scoped; zero cross-family visibility,
  enforced by isolation tests on every endpoint, written before the feature.
  Landed before any feature that adds new tables, so everything after it is
  born scoped.

## Next

1. **Board v2, remaining slices** — four card kinds (Routine / Task /
   Activity / Appointment), "Up next" / "Later" sections, member colors with
   a mine/family filter, multi-assignee cards with per-person routine
   check-off, and a do-not-disturb dot.
2. **Calendar + day history** — an Outlook-style calendar view of scheduled
   cards, and every past day saved and revisitable, with the day rolling
   over at midnight in the household's timezone.
3. **Family-creation wizard (frontend)** — the UI for "new household"
   accounts to create their family on first login (the backend is done).
4. **Themes** — selectable color schemes built on CSS variables.
5. **Nutrition (Food tab)** — manual food log, then daily macro summary,
   then a barcode scanner (BarcodeDetector API with a WASM fallback) backed by
   Open Food Facts / USDA FoodData Central, importable into local Postgres so
   lookups never have to leave the server.
6. **Meals (Kitchen tab)** — tonight's dinner card and a week strip.
7. **Family chat** — messaging, then topic channels, then photo attachments.
8. **Fitness sync** — workouts flowing into the app and auto-completing
   matching board routines. Strava first (watch → Strava → server polling);
   direct Apple Health export as a self-hosted alternative path.

## Ongoing polish

- Undo toast for deletes, loading skeletons, pull-to-refresh.
