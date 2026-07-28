# Self-hosting dailybread

This is a plain, step-by-step guide to running your own private instance. You do
not need to be a server expert. Budget about 15 minutes.

## 1. What you need

- A computer that stays on: an old PC, a mini PC, a Raspberry-Pi-class box, or a
  small VPS all work.
- Docker with the Compose plugin. Install it from the official docs at
  https://docs.docker.com/engine/install/ (that page also sets up `docker
  compose`).
- The 15 minutes.

## 2. Get the code

Clone this repository onto that machine:

```
git clone https://github.com/lazaruslinux/dailybread.git
cd dailybread
```

## 3. Configure

Copy the example settings file and open it in an editor:

```
cp .env.example .env
```

The first two values below are secrets and must be changed; the app refuses to
start while they still hold the example file's placeholders, because those
placeholders are public knowledge (they are in this repository). The rest
enable optional features:

- `SECRET_KEY`: a long random string that signs login sessions. Generate one
  with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `POSTGRES_PASSWORD`: the database password. Pick anything, then make sure the
  same value appears in `DATABASE_URL` right below it. Set it before the first
  start: Postgres locks in whatever password its data volume was first created
  with, so editing `.env` later does not change the real password (if you need
  to change it after the fact, wipe the volume with `docker compose down -v`,
  which deletes your data, or change it inside Postgres with `ALTER USER`).
- `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY`: needed only for push notifications.
  The one-line generator command is in the comments of `.env.example`. Leave
  them blank to skip notifications.
- `USDA_API_KEY`: a free key from https://fdc.nal.usda.gov/api-key-signup.
  Get one if anybody will search foods by name, because that search has no
  other source: leave the key blank and searching returns an error. Barcode
  scanning uses Open Food Facts and needs no key, and custom foods and recipes
  work regardless.
- `COOKIE_SECURE`: leave `false` for now. Set it to `true` once you serve the
  app over HTTPS (see step 7), or logins misbehave.

## 4. Start it

```
docker compose up -d
```

The database schema is created and updated automatically the first time the
backend starts, so there is no separate migration step.

If the app does not come up, run `docker compose logs backend`. A backend that
exits immediately with "refused to start" is telling you a placeholder value in
`.env` still needs filling in; fix the value it names and run
`docker compose up -d` again.

## 5. Reach it

By default the app binds to `127.0.0.1:8080`, meaning it answers only on the
machine itself. On that machine, open http://localhost:8080.

To reach it from phones and other devices, either put a reverse proxy in front
of it (step 7, the right long-term answer and the only way to get HTTPS), or for
a quick trusted-LAN setup edit `docker-compose.yml`, change the frontend port
line `"127.0.0.1:8080:80"` to `"8080:80"`, and run `docker compose up -d` again.
Then http://YOUR-MACHINE-LAN-IP:8080 works from any device on the network. The
caveat: that is plain HTTP with no encryption, fine on a private home network
but not for the internet, and push notifications and iPhone home-screen install
still need HTTPS.

Before you widen access beyond the machine it runs on, finish the setup wizard
in step 6. Until that wizard has been completed the install has no accounts and
no way to tell who you are, so it belongs to whoever loads the page first: that
visitor picks the username and password and becomes the server admin. The
window closes for good the moment the first account exists, and the wizard
never appears again. If someone else claims the install there is no way to take
it back short of wiping the database with `docker compose down -v` and starting
over.

## 6. First login

The first time you open the app on an empty database, it shows a short setup
wizard. It creates your family and your first account, and that account becomes
both the family admin and the server admin. After that, the wizard never appears
again.

- Add your family: from that account, open the Admin area in the app and add
  each member (adults and children).
- Invite another household: the server admin (the account the setup wizard
  created) mints a short invite code from the Admin area. The invitee uses it
  to pick their own username and password and found their own family. Codes
  are valid for 48 hours, and you get a notification when the household is
  actually set up.
- Keep an eye on the install: the server admin's Admin area also has a server
  overview listing every family, village and member on the server. From there
  you can rename or dissolve a village, remove a member, remove an entire
  household, and reset any account's password.

  Two of those deserve care. Removing a household deletes that family and
  everything in it: every member, board, kitchen and food diary. And resetting
  a password gives you a working credential for someone else's account, which
  means the server admin can reach any household's data on the install if they
  choose to. That is unavoidable for whoever holds the database anyway, but it
  is worth knowing before you hand the role to anyone. Every other account in
  the app is family-scoped and cannot see another household at all.

## 7. HTTPS with a reverse proxy

Push notifications and installing the app to an iPhone home screen both require
HTTPS. The simplest way is a small reverse proxy such as Caddy, which fetches
and renews certificates for you. A minimal `Caddyfile`:

```
dailybread.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

Point that domain at your server, run Caddy, then set `COOKIE_SECURE=true` in
`.env` and restart with `docker compose up -d`.

## 8. Phone health sync

To fill the Health tab from a phone (Apple Health or Android Health Connect),
follow [fitness-sync.md](fitness-sync.md).

## 9. Backups

Two things hold your data: the Postgres database and the uploaded avatar images.
Back both up:

```
docker compose exec -T db pg_dump -U dailybread dailybread > dailybread-backup.sql
docker compose cp backend:/app/media ./media-backup
```

To restore, start only the database first so the schema comes from your backup
rather than a fresh install. Restoring over an already-initialized database
fails with "already exists" errors; if you have one, wipe it first with
`docker compose down -v` (careful: `-v` deletes the current data for good).

```
docker compose up -d --wait db
docker compose exec -T db psql -U dailybread dailybread < dailybread-backup.sql
docker compose up -d
docker compose cp ./media-backup/. backend:/app/media
```

## 10. Updating

```
git pull
docker compose build
docker compose up -d
```

Schema migrations run automatically when the new backend starts.
