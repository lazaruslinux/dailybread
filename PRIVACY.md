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
- Backups, if you set them up, are written wherever you choose, on your own
  storage.

## What leaves the server, and only if you opt in

- Food data: searching for a food or scanning a barcode queries a public
  nutrition database (USDA FoodData Central or Open Food Facts). Only the
  search text or barcode number is sent, and once a food has been used it is
  cached on your server, so repeat lookups stay local. Skip search and scanning
  and enter foods by hand, and nothing leaves at all.
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

- Traffic between your device and the server is encrypted with TLS.
- Passwords are stored hashed with Argon2, never in plain text.
- Accounts are created by an administrator. There is no public sign-up.
- On the private family instance, the database is meant to sit on an encrypted
  disk, so the stored data is unreadable without the key.

## The public demo is different

The public demo (URL to be decided) is a sandbox filled with fake data so
people can try the app. It is wiped and reset on a schedule. Do not put real
personal information into the demo.
