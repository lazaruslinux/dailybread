# dailybread

A self-hosted life-planning app for families. Daily routines, to-dos, a shared
schedule, and food tracking in one place, running entirely on hardware you
control.

## Status

Early development. Not yet usable. See `docs/` for the plan.

## What it does (planned)

- A home screen where today's routines, pending to-dos, and scheduled blocks
  appear as cards at the top.
- Routines: recurring daily tasks (exercise, brush teeth, breakfast) that you
  check off each day.
- To-dos: one-off items (call the dentist, pick up groceries).
- Schedule: time blocks for meetings and focused work.
- Nutrition: calorie, macro, and micronutrient tracking.
- Strava: pull in your workouts.
- Multiple family members, each with their own login and view. Parents can
  manage accounts and see their kids' day.

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

A real quickstart will go here once the stack runs. Planned shape:

```
cp .env.example .env     # then edit values
docker compose up        # starts database, backend, and frontend
```

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
