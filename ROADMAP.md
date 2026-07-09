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

- **Exercise log** — running and walking with three effort levels; the burn
  is MET-based off the latest weigh-in (calibrated to match Cronometer) and
  is added onto that day's energy target, so a workout earns calories back.
  Goal rates above 1.5 lb/week now carry a warning, with a read-and-confirm
  step at 2 lb.
- **Health profile and auto targets** — an optional per-member health
  profile (birthdate, sex, height, activity) plus a weight log; together
  they compute a daily calorie target (lean-mass formula when body fat is
  known), shifted for a lose/maintain/gain goal at a capped healthy rate,
  floored at safe minimums, flipping to maintenance at the goal weight, and
  adjusting with every weigh-in. Diary targets gain an Auto mode; the macro
  split stays each member's own. Children's goals are set by a parent.
  An optional goal body fat % sits beside the goal weight (informational;
  the math stays weight-driven).

- **Daily greeting** — the first open of the day says good morning and offers
  to set the day's mood and status in one small sheet; saving quiets it for
  the day, "maybe later" only for that visit.
- **Day timeline** — the board gains a List / Timeline toggle: an hour-gutter
  day view with cards laid onto their time slots (height matches duration,
  overlapping cards share the lane side by side, attendees' faces ride on
  the card), a line marking now, and its own scroll panel that opens at the
  current hour without moving the page. Cards and calendar rows now show the
  full slot ("3:00 – 4:30 PM") rather than just the start.

- **Push reminders** — real phone notifications, shortly before anything with
  a time on the board: each member turns them on per device from the You tab
  (with a send-a-test button), routines only nag the people who haven't done
  theirs, and a device that revokes permission cleans itself up. Standard Web
  Push — works in any browser on Android, and on iOS through the
  Home-Screen-installed app — delivered outbound through the platform push
  relays with end-to-end encrypted payloads, so the server stays
  private-network-only with no inbound exposure.

- **Kid accounts** — a birthdate on each member marks minors (unlocking
  automatically at 18). Minors see a simplified app: no nutrition, health,
  or diary (hidden in the UI and refused by the server), and a board limited
  to their own cards plus read-only family-wide ones. A minor's check-off
  waits as pending until a parent approves it — parents get a push and a
  "Waiting on you" section on Home; the kid can withdraw a pending tick but
  can't undo an approved one. A minor's mood, status, and journal are
  visible only to their parents (a parent can read a minor's journal;
  adults' journals stay readable by no one). Kids receive no notifications
  of any kind. All of it is passive: in a household where kids don't sign
  in, nothing changes for the parents.
- **Timeline day nav** — chevrons on the timeline step to the previous or
  next day as a read-only peek fed by the calendar, with a jump back to
  today.
- **Scheduled check-ins** — three optional daily pushes, hours configurable:
  a morning digest (a personal good-morning with the day's card count and
  what's next), a mid-day check with calories left (only for members who
  log food), and an evening check-in for every adult. Each fires at most
  once per day per member, quietly skipping anyone it doesn't apply to.

## Next

1. **Villages** — private circles of linked families on the same install.
   Invitation-only (one-time codes, hashed at rest, throttled), nothing
   discoverable, and deliberately anti-social-media: no feed, no likes, no
   comments, ever. Exactly two things cross the family wall: recipes shared
   onto a village shelf in the Kitchen (browse, then save an independent
   copy), and each member's mood/status, visible across families only if
   that member opts in — minors never. Membership shipped; shelf and
   presence follow.
2. **Fitness sync** — workouts flowing into the app and auto-completing
   matching board routines. Strava first (watch → Strava → server polling);
   direct Apple Health export as a self-hosted alternative path.

## Ongoing polish

- Member colors, a do-not-disturb dot, loading skeletons, pull-to-refresh,
  an in-app "How to use" / FAQ section.
- Health layer: a weight trend chart, a parent-facing UI for setting a
  child's goals (the endpoints exist), net carbs on the diary, more
  exercise types (the catalog is data-driven), and a projected
  goal-arrival date.

## Parked

- **Dinner voting** — a parent posts a few candidate meals for a night and
  the family votes from the Kitchen tab (the one Kitchen write kids would
  get); the parent sees the tally and sets the plan. Not scheduled.

## Shelved

- **Calendar subscription feed** — a read-only per-member iCal feed. Parked:
  phone calendar apps refresh subscriptions lazily (hours), which reads as
  stale on a LAN-only server; push reminders cover the real need. Cheap to
  revive if wanted.
- **Kid-mode extensions** (rewards, allowance, chore scoring) — paused; in
  practice parents manage the family board directly and kids rarely sign
  in, so the approval flow above already covers the need.
- **Family chat** — cut in favor of Villages. Real-time messaging competes
  with the phone's own messenger and drags in the social-media dynamics
  this app deliberately refuses; the cross-household need it was meant to
  serve is covered by village sharing instead.
