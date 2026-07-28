# Privacy

dailybread is built so the people using it keep their own data. This file
explains exactly what that means, and where the limits are, in plain terms.

## The short version

Your data lives in a database on the server you run. The app has no cloud
backend, no account owned by anyone else, and no analytics. It does not send
your information anywhere unless you explicitly connect an outside service.

## Where your data is

- Everything you enter (routines, to-dos, schedule, food logs, family accounts)
  is stored in your own PostgreSQL database, on your own hardware.
- Profile photos are files on the server's own disk, in a separate volume from
  the database. Back them up separately if you want to keep them.
- Backups, if you set them up, are written wherever you choose, on your own
  storage.

## What leaves the server, and only if you opt in

- Food data: searching for a food or scanning a barcode queries a public
  nutrition database (USDA FoodData Central or Open Food Facts). Only the
  search text or barcode number is sent, and once a food has been used it is
  cached on your server, so repeat lookups stay local. The barcode health check
  reads a bit more off that same label than the nutrition numbers alone, so the
  cache now also keeps the product's ingredient list text, its additive tags,
  its NOVA processing group, and its added-sugar figure, stored right next to
  the nutrition data in your own database. A product that was cached before the
  health check existed does not have those fields yet; the first time someone
  runs a health check on it, they are filled in by a single fresh lookup to the
  same two databases the barcode came from, and after that the check stays
  local. This is all still the same public sources you already opted into, with
  no new service in the mix, and none of the cached label data ever leaves your
  server. Skip search and scanning and enter foods by hand, and nothing leaves
  at all.
- Web push: if you turn on notifications, reminders are delivered through your
  browser vendor's push service (Apple, Google, or Mozilla, the same pipe every
  web app uses). That service relays an encrypted payload it cannot read. Leave
  notifications off and nothing goes out this way.

Health and fitness data moves the other direction. Your own phone pushes it to
your server, and the app never reaches out to any fitness service to fetch it.
See [docs/fitness-sync.md](docs/fitness-sync.md).

Nothing else is sent out. There is no telemetry, no third-party crash
reporting, no ads, and no tracking.

## Security

- Traffic between your device and the server is encrypted with TLS when the
  install serves HTTPS (the reverse-proxy step in the self-hosting guide; on a
  bare LAN install, traffic stays on your own network but is not encrypted).
- Passwords are stored hashed with Argon2, never in plain text.
- There is no public sign-up. The first account is created by whoever runs the
  first-run setup wizard, and every account after it needs either an admin or a
  short-lived invite code from the server admin. An invited person picks their
  own username and password.
- On the private family instance, the database is meant to sit on an encrypted
  disk, so the stored data is unreadable without the key.
