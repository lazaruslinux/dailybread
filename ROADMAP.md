# Roadmap

Where dailybread is headed, in order. Done items stay for history.

## Done

- **Auth + first-run setup** — bootstrap wizard creates the first parent/admin;
  admin-created accounts only, no public signup; Argon2 + httpOnly JWT cookie.
- **Admin dashboard** — family member management (roles, admin flag, password
  resets) with lockout guards so an install always keeps a working admin.
- **Live board** — routines, tasks, and scheduled cards; streaks; assignees; a
  checkbox completes a card (optimistic, with an undo toast) and tapping the
  card body opens a detail sheet with the full info plus edit/delete for
  parents.
- **Daily verse** — a verse of the day at the bottom of the board, rotating
  through a bundled NKJV set (quoted under the publisher's gratis use
  policy) keyed to the calendar day, so it needs no network and phones home
  to no one; tapping it opens the passage on Bible.com.
- **Moods + profiles** — five-level daily mood rendered as weather; profile
  pages with a daily status, avatar photos, and each member's slice of the
  board.
- **Four-tab shell** — Home / Nutrition / Kitchen / You with bottom navigation.
- **Grocery lists** — shared checklists per store with a combined "All" view;
  items move between stores; per-store clear.
- **Test suite + CI** — permission-matrix and privacy-rule tests (pytest,
  in-memory SQLite) plus typecheck/build, run on every push.
- **Ship-ready packaging** — the frontend is containerized behind nginx, so
  `docker compose up` serves the whole app on one port; sliding sessions;
  real PWA icon set.
- **First real deployment** — a family living in the app day to day, behind
  an HTTPS reverse proxy. Real usage feedback drives everything after this.
- **Multi-household tenancy** — every account belongs to exactly one family;
  all data is family-scoped with zero cross-family visibility, enforced by
  isolation tests written before the feature; first-login wizard for new
  households.
- **Board v2** — four card kinds (Routine / Task / Activity / Appointment)
  with per-kind schedule rules, recurrence (weekly / every-N-weeks /
  monthly), multi-assignee cards with per-person routine check-off, a
  see-vs-do split (private or family visibility), and a member filter.
- **Temporal board** — Past due / Now / Coming up / Anytime / Next 7 days /
  Done sections driven by the live clock; one-off cards carry forward until
  checked; completing a past-due card archives it to its own day.
- **Calendar + day history** — two-week and month views with a whole-period
  overview (open cards first, completed settle to the bottom), day agendas
  with past-day marking so missed items are recorded on the day they
  actually were, and add/edit from any day.
- **Themes** — selectable color schemes on CSS variables (a warm light
  default and a dark forest), per-member.
- **Private daily journal** — one page per member per day, archived nightly;
  readable by no one else, ever.
- **Food layer + recipe builder** — recipes built from ingredient lines of
  real foods (server-proxied USDA search and Open Food Facts barcodes, plus
  the family's own custom foods with multi-serving Nutrition Facts entry);
  full-label nutrition computed per serving; weight- and volume-based
  amounts without density guesswork.
- **Hardening + performance pass** — password changes end the account's
  existing sessions everywhere; repeated login failures throttle per
  username; feed and calendar fetch completions in one query; food searches
  cached briefly server-side.
- **Barcode scanning** — a camera scanner in the recipe ingredient picker
  (WASM decoder bundled locally, loaded only when it opens, with a
  type-the-digits fallback); codes resolve against the family's own foods
  first, then the shared cache, then Open Food Facts; an unknown code opens
  the New Food form prefilled, so one entry teaches the app the product for
  good. Reusable wherever a barcode is wanted next.

- **Dinner planner** — the family menu: each night takes a saved recipe or a
  typed one-off, with its per-serving nutrition alongside; the week is
  planned in the Kitchen and tonight's pick surfaces on the Home board.
- **Recipe → grocery** — one tap sends a recipe's ingredient lines onto a
  chosen store's grocery list.
- **Password management** — any member changes their own password from the
  You tab (their other sessions end, the one making the change stays);
  admins reset a member's forgotten password to a generated one, handed
  over once, with a forced choose-your-own step at the next sign-in.

- **Nutrition diary** — a personal food diary per member: entries grouped by
  meal with consumed-vs-target bars on top; log foods by serving, weight, or
  volume (search, barcode, custom foods) or a recipe by servings; each member
  sets their own calorie budget and macro split. Entries snapshot their
  nutrition at log time, so editing a recipe later never rewrites history.

- **Health profile and auto targets** — an optional per-member health
  profile (birthdate, sex, height, activity) plus a weight log; together
  they compute a daily calorie target (lean-mass formula when body fat is
  known), shifted for a lose/maintain/gain goal at a capped healthy rate,
  floored at safe minimums, flipping to maintenance at the goal weight, and
  adjusting with every weigh-in. Diary targets gain an Auto mode; the macro
  split stays each member's own. Children's goals are set by a parent.

## Next

1. **Push reminders** — Web Push for card reminders and a morning digest.
2. **Family chat** — messaging, then topic channels, then photo attachments;
   channels carry explicit member lists from day one so a channel can later
   span households.
3. **Fitness sync** — workouts flowing into the app and auto-completing
   matching board routines. Strava first (watch → Strava → server polling);
   direct Apple Health export as a self-hosted alternative path.

## Ongoing polish

- Member colors, a do-not-disturb dot, loading skeletons, pull-to-refresh,
  an in-app "How to use" / FAQ section.

## Shelved

- **Calendar subscription feed** — a read-only per-member iCal feed. Parked:
  phone calendar apps refresh subscriptions lazily (hours), which reads as
  stale on a LAN-only server; push reminders cover the real need. Cheap to
  revive if wanted.
