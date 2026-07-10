# Architecture

How dailybread is put together, and the decisions that shaped it. Written for
someone reading the code for the first time.

## Three containers, one port

`docker compose up` builds and starts:

- **db**: stock Postgres 16 with a named volume.
- **backend**: FastAPI (Python). The container entrypoint runs
  `alembic upgrade head` before the server starts, so the schema is always
  current by the time the app answers. Avatar photos live in a named volume
  mounted at `/app/media`, never in the database.
- **frontend**: the built React PWA served by nginx, which also forwards
  `/api/*` to the backend. The browser only ever talks to this one origin, so
  there is no CORS in production and the session cookie stays first-party.

Both published ports bind to `127.0.0.1`: the compose file assumes a reverse
proxy (or SSH tunnel) in front, and exposes nothing to the network by itself.

## Request path

Browser → nginx → FastAPI → Postgres. nginx strips the `/api` prefix, serves
the fingerprinted static assets with immutable cache headers, and keeps
`index.html` and the service worker uncacheable so phones pick up new deploys.
The backend is plain synchronous SQLAlchemy behind FastAPI's threadpool; at
family scale that is the simple thing that works.

## Tenancy: families are the wall

Every account belongs to exactly one family, and every row of family data
carries a `family_id`. Queries filter by the requesting user's family, always;
there is no cross-family read path anywhere. The isolation tests
(`backend/tests/test_tenancy.py`) were written before the multi-family feature
itself, and the suite fails if a route ever leaks across the wall.

One deliberate exception: rows with `family_id = NULL` are the install's
shared food cache (products fetched from USDA or Open Food Facts). They hold
public catalog data, never anything a family typed in; custom foods are
family-scoped like everything else.

Villages are the only structure that spans families: private, invitation-only
circles for sharing between linked households. There is no discovery, no
feed, and no like button, by design.

## Roles and privacy

Two roles: parent and child. Children get a simplified, parent-supervised
app: no nutrition area, a narrowed board, and check-offs that wait for parent
approval. Some surfaces are self-only even among adults, with no parent
override: the journal, the food diary, and the fitness data. The permission
matrix is enforced in route dependencies (`app/deps.py`) and pinned down by
tests per surface.

## Food data

The server proxies all food lookups so phones never call a third party:

- **Search** goes to USDA FoodData Central (`app/foods_api.py`). Results are
  deduped (duplicate branded listings collapse on barcode or brand+name) and
  reranked by how well they match the typed words, since FDC's own relevance
  is poor. Good answers are cached in memory for a few minutes.
- **Barcodes** resolve in order: the family's own custom foods, then the
  shared cache, then USDA's branded dataset (label-accurate for US products),
  then Open Food Facts. A product scanned once is cached, so scanning it
  again never leaves the server. An unknown code opens the new-food form
  prefilled; one manual entry teaches the install that product for good.
- **Persist on use**: search and barcode results are transient until an
  ingredient line or diary entry actually uses one, which is when the food row
  is saved.

Nutrition is stored per 100 g (or 100 mL for liquids), whatever the source,
so recipe and diary math never cares where a food came from. Diary entries
snapshot their nutrition at log time; editing a recipe later never rewrites
anyone's history.

## Push notifications

Standard Web Push with VAPID (`app/push.py`). The server sends reminders
shortly before timed cards, plus optional daily digests; the browser's push
service does the delivery, so the server needs no inbound exposure and the
payloads are encrypted end to end. A `reminder_log` row per card per day makes
the loop idempotent across restarts. Card times are wall-clock local, and the
loop compares them against each family's own timezone, so households in
different zones on one install each get their mornings at their own hour.

## Fitness ingest

`POST /api/ingest/health` accepts the JSON that the Health Auto Export iOS
app sends on a schedule. It authenticates with a per-member bearer token
(stored hashed, mintable and revocable from the app) instead of the session
cookie, so the endpoint a phone automation hits has no CSRF surface. Imports
are idempotent: daily metrics upsert on (member, day, metric) and workouts on
the exporter's stable id, so re-sending a whole window is always safe.
Everything imported is self-only, like the diary.

## Auth and sessions

Argon2 password hashes; an httpOnly, SameSite=lax JWT cookie with sliding
expiry. Password changes and admin resets end the account's other sessions.
Login failures throttle per username. As CSRF defense-in-depth beyond
SameSite, a middleware refuses any state-changing request whose
`Sec-Fetch-Site` header says it came from another site. New households join
by a short-lived, hashed invite code minted by the server admin; there is no
open signup.

## Decisions worth knowing

- **Self-hosted first.** No cloud account, no telemetry, no third-party calls
  except the food lookups above and integrations you enable yourself.
- **No realtime chat.** It would compete with the phone's own messenger and
  drag in the social dynamics this app refuses; village sharing covers the
  cross-household need.
- **Alembic owns the schema.** Every change is a migration; the app never
  creates tables itself.
- **Tests are permission-first.** The bulk of the suite asserts who can see
  and touch what, because in a family app the privacy rules are the product.
