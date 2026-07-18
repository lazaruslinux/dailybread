# dailybread

A self-hosted life-planning app for families. Daily routines, to-dos, a shared
schedule, and food tracking in one place, running entirely on hardware you
control.

<p>
  <img src="docs/screenshots/home-light.png" alt="Home board in the light theme: the day's routines, tasks, and appointments" width="200">
  <img src="docs/screenshots/home-dark.png" alt="The same board in the dark theme" width="200">
  <img src="docs/screenshots/kitchen-light.png" alt="Kitchen tab: tonight's dinner plan and per-store grocery lists" width="200">
  <img src="docs/screenshots/health-light.png" alt="Health tab: steps, active calories, distance, exercise, and resting heart rate" width="200">
</p>

The screens show a fictional demo family; none of it is real data.

## Status

In daily use by a real family. See [ROADMAP.md](ROADMAP.md) for what exists
and what's next.

## What it does

- A family board that knows what time it is: routines, tasks, activities, and
  appointments (one-off or repeating, like a weekly work meeting), with
  recurrence, multiple assignees, streaks, a member filter, and a List or
  Timeline view of the day. A calendar keeps honest day-by-day history.
- Real phone notifications: reminders shortly before anything timed (with a
  configurable lead, and a longer runway for appointments), an optional morning
  digest and evening check-in, and family-activity pushes you tune per kind. A
  reminder that would have fired while the server was down still catches up for
  a short window. Standard Web Push with encrypted payloads, so the server
  needs no inbound exposure. An in-app Inbox keeps a history of family activity
  even when pushes are off.
- Nutrition: a private per-member food diary (search, barcodes, custom foods),
  recipes with computed per-serving nutrition, a weight log and health profile
  that auto-adjust a daily calorie target, and an exercise log that earns
  calories back. A finished day can be locked, and any food can be pinned to a
  saved-foods shelf for quick logging.
- Health: your own phone pushes fitness data to your server (Apple Health or
  Health Connect), and nothing is ever fetched from a cloud service. The Health
  tab shows daily steps, active calories, and distance with time-of-day
  charts, exercise minutes, workouts with route maps, resting heart rate, and
  weight and body-fat trends. Each member tunes their own daily targets for
  steps, active energy, and exercise minutes.
- The Kitchen: per-store grocery lists, a recipe box, and a week of planned
  dinners that surface on the board. Each night takes one of four standing modes
  (self-serve, homemade, go out, delivery); the family votes, kids included, and
  a parent locks in the pick.
- Breadcrumbs: light gamification for showing up. Members earn crumbs for daily
  verses, locked diary days, workouts, and kids' completed cards, climbing
  levels and bread-themed tiers. There are deliberately no purchases and no
  public leaderboard.
- Daily verses: an opt-in verse of the day (bundled NKJV text, so it phones home
  to no one) with reading streaks worn as a small badge beside the avatar.
- Family accounts with parent and child roles. Child accounts are simplified
  and parent-supervised: no nutrition or calorie data at all, a narrowed board,
  check-offs that wait for approval, and a mood, status, and journal only
  parents see. Kids can still cast their dinner vote.
- Villages: private circles of linked families, invitation-only and
  undiscoverable, for sharing across households without any social-media
  mechanics. Families share recipes and share events with per-family RSVPs that
  land on each attending family's board in their own timezone. No feed, no
  likes, ever.
- Onboarding by invite code: the server admin mints a short-lived code; the
  invitee picks their own username and password and founds their own family.
- Per-member themes, daily moods rendered as weather, and a private journal.

## Privacy

Your data stays on your server. The app keeps no cloud account, sends no
telemetry, and makes no third-party calls except optional online food lookups
you turn on yourself. Health and fitness data arrives because your own phone
pushes it to your server; nothing fitness-related is fetched from an outside
service (see [docs/fitness-sync.md](docs/fitness-sync.md)). See
[PRIVACY.md](PRIVACY.md).

## Tech

- Backend: FastAPI (Python) and PostgreSQL.
- Frontend: React (Vite, TypeScript), Tailwind CSS, and Framer Motion, built as
  a Progressive Web App.
- Runs with Docker Compose.

## How it is meant to be run

There are three separate things, and they share only this source code. No real
data or secrets move between them.

1. This repository: the code.
2. A public demo: a throwaway sandbox with fake data, for trying the app.
3. Your own private instance: where you and your family actually use it, on your
   own network.

Step-by-step instructions for standing up your own instance are in
[docs/self-hosting.md](docs/self-hosting.md).

## Repository layout

```
backend/    FastAPI service
frontend/   React PWA
docs/       architecture and decisions
```

## Development

```
cp .env.example .env     # then edit values
docker compose up        # starts database, backend, and frontend
```

Compose publishes the app at `127.0.0.1:8080` (the nginx frontend, which
proxies `/api` to the backend) and the backend separately at `127.0.0.1:8000`
for development. You use the app through `8080` alone.

Backend tests: `cd backend && python -m pytest`. Frontend build:
`cd frontend && npm run build`. Both run in CI on every push.

## Built with AI assistance

I build this project with the help of Claude, Anthropic's AI assistant. It
contributes to the code, architecture, and documentation. I direct the work,
review it, and decide what ships.

## License

GNU AGPL-3.0. See [LICENSE](LICENSE). Copyright (c) 2026 lazaruslinux.

In plain terms: run it, modify it, and self-host it freely. If you host a
modified version for other people, you must share your modifications under
the same license.

One carve-out: the daily verse text in `frontend/src/lib/verses.ts` is quoted
from the New King James Version and is not covered by the AGPL.
Scripture taken from the New King James Version&reg;. Copyright &copy; 1982 by
Thomas Nelson. Used by permission. All rights reserved. Quoted under the
publisher's gratis use policy (fewer than 500 verses, comprising a small
fraction of this work).
