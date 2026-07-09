# dailybread

A self-hosted life-planning app for families. Daily routines, to-dos, a shared
schedule, and food tracking in one place, running entirely on hardware you
control.

## Status

In daily use by a real family. See [ROADMAP.md](ROADMAP.md) for what exists
and what's next.

## What it does

- A family board that knows what time it is: routines, tasks, activities, and
  appointments (one-off or repeating, like a weekly work meeting), with
  recurrence, multiple assignees, streaks, a member filter, and a List or
  Timeline view of the day. A calendar keeps honest day-by-day history.
- Real phone notifications: reminders shortly before anything timed, plus an
  optional morning digest, mid-day food check, and evening check-in. Standard
  Web Push with encrypted payloads; the server needs no inbound exposure.
- Nutrition: a private per-member food diary (search, barcodes, custom foods),
  recipes with computed per-serving nutrition, a weight log and health profile
  that auto-adjust a daily calorie target, and an exercise log that earns
  calories back.
- The Kitchen: per-store grocery lists, a recipe box, and a week of planned
  dinners that surface on the board.
- Family accounts with parent and child roles. Child accounts are simplified
  and parent-supervised: no nutrition area, a narrowed board, check-offs that
  wait for approval, and a mood, status, and journal only parents see.
- Villages: private circles of linked families, invitation-only and
  undiscoverable, for sharing across households without any social-media
  mechanics. No feed, no likes, ever.
- Onboarding by invite code: the server admin mints a short-lived code; the
  invitee picks their own username and password and founds their own family.
- Per-member themes, daily moods rendered as weather, and a private journal.

## Privacy

Your data stays on your server. The app keeps no cloud account, sends no
telemetry, and makes no third-party calls except for features you turn on
yourself (Strava, and optional online food lookups). See [PRIVACY.md](PRIVACY.md).

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

## Repository layout

```
backend/    FastAPI service
frontend/   React PWA
docs/       architecture and decisions
```

## Development

```
cp .env.example .env     # then edit values
docker compose up        # starts database, backend, and frontend on one port
```

Backend tests: `cd backend && python -m pytest`. Frontend build:
`cd frontend && npm run build`. Both run in CI on every push.

## Built with AI assistance

I build this project with the help of Claude, Anthropic's AI assistant. It
contributes to the code, architecture, and documentation. I direct the work,
review it, and decide what ships.

## License

MIT. See [LICENSE](LICENSE).

One carve-out: the daily verse text in `frontend/src/lib/verses.ts` is quoted
from the New King James Version and is not covered by the MIT license.
Scripture taken from the New King James Version&reg;. Copyright &copy; 1982 by
Thomas Nelson. Used by permission. All rights reserved. Quoted under the
publisher's gratis use policy (fewer than 500 verses, comprising a small
fraction of this work).
