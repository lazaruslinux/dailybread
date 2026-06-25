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

- Strava: if you connect a Strava account, the server contacts Strava's API to
  read your activities. That is a per-account choice, and you can skip it.
- Food data: looking up foods can query a public nutrition database. You can
  also import that database once and keep every lookup fully local, so nothing
  leaves at all.

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
