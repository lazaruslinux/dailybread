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
- **Multi-family server hardening** — per-family clocks (reminders and
  digests fire on each household's own timezone, set silently from the
  browser at signup, adjustable in the admin sheet); a server-admin rescue
  reset for a household that locked itself out; and family offboarding that
  removes a household and everything it owns while saved recipe copies stay
  with their new owners.
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

- **Fitness tab (Apple Health import)** — a fifth tab with the day's steps,
  active calories, exercise minutes, and resting heart rate, a week of step
  bars, and imported workouts. Data arrives from the member's own phone: an
  exporter app POSTs Apple Health JSON to an ingest endpoint authenticated
  by a per-member bearer token (shown once, hash-stored, re-mintable,
  revocable) — no cloud middleman, no cookies, no CSRF surface. Imports are
  idempotent (daily metrics upsert per day, workouts on the exporter's
  stable id), weigh-ins flow into the existing weight log without ever
  overriding a deliberate in-app entry, and everything imported is
  self-only: invisible to other members, absent for child accounts.

- **Fitness metric detail views + personal goals** — every metric card
  opens into its own story: the last 30 days as tappable bars (tap a day,
  read its number), a goal line, 7- and 30-day averages, and the best day
  (lowest, for resting heart rate). Each member can tune their own daily
  targets for steps, active energy, and exercise minutes right in the
  detail view — the rings follow — or put one back on the recommended
  default with a tap.

- **Repeating appointments** — an appointment can carry the same weekly or
  monthly schedule a routine does (the standing work meeting), keeping its
  start and end times and its shared check-off, completed per occurrence; a
  missed one is never "overdue", the next simply comes around.
- **Kid accounts** — the Child role is the switch (birthdate is optional,
  informational only). Child accounts see a simplified app: no nutrition,
  health, or diary (hidden in the UI and refused by the server), and a board
  limited to their own cards plus read-only family-wide ones. A minor's check-off
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

- **Village recipe sharing** — parents share recipes to their villages
  straight from the recipe box (a Shared chip marks them; edits show live on
  the other side with a last-updated stamp); other families browse the full
  recipe through an id-free projection and save independent copies, each
  stamped "Copy of X shared by <name> from <family> on <date>". A family
  joins any number of villages but founds at most one, and each member may
  opt their daily mood and status onto the village card (children never
  appear).
- **Dinner Plan** — the nightly "are we cooking at all": four standing modes
  (Self-Serve, Homemade, Go Out, Delivery) always on for today and behind
  every day of the week planner. Adults pick one with a short note or a
  recipe; picks show as the voter's face with their own text, kid avatars
  ride the leading choice, the first pick of the day nudges the other
  adults, and Lock it in crowns dinner reversibly.
- **Family identity** — the family's name is asked for at setup (with a nudge
  toward a fun custom name, since several families can share a last name),
  shown atop the member dashboard, and renameable by an admin anytime.
- **Invite onboarding** — the server admin invites a new household by minting
  a one-time code (15-minute expiry, stored hashed, attempts throttled)
  instead of typing a temporary password. The invitee taps "Enter invite
  code" on the sign-in screen, is greeted by name, chooses their own
  password, gets a four-step tour, and founds their own family — invites
  never join an existing one. Pre-sign-in screens default to the dark theme.

## Next

1. **Fitness follow-through** — trends (weight chart, with body fat
   percentage synced from the health exporter as a second line), imported
   workouts auto-completing matching board routines, and an opt-in for
   counting watch calories toward the day's energy target. Strava as an
   optional secondary connector if ever wanted. Intraday (hourly) metric
   detail would need a finer-grained table and a chattier exporter
   setting — deliberately deferred to keep the sync light.

## Ongoing polish

- Member colors, a do-not-disturb dot, loading skeletons, pull-to-refresh,
  an in-app "How to use" / FAQ section.
- Health layer: a weight trend chart, a parent-facing UI for setting a
  child's goals (the endpoints exist), net carbs on the diary, more
  exercise types (the catalog is data-driven), and a projected
  goal-arrival date.

## Parked

- **Android fitness adapter (future release)** — Health Connect is Android's
  HealthKit, and community bridge apps can POST it to a webhook. The ingest
  endpoint, tokens, and all the Fitness UI are already platform-neutral; the
  work is a second payload parser for whichever bridge gets blessed, after
  vetting one for background-sync reliability. Deliberately after the Apple
  path is polished with a real household on it.
- **Adult member role** — parent permissions without admin, for grown members
  who aren't heads of household. Today the roles are Parent and Child only.

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
