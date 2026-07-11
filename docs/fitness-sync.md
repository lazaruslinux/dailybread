# Syncing health and fitness data

The Fitness tab fills itself from your phone. Nothing polls a cloud API and
no third-party service ever sees the numbers: an app **on the phone** reads
the health store and POSTs the data straight to your own server on a
schedule. Each family member mints their own sync key in the app
(Fitness → Connect), and everything imported is visible only to them.

Both platforms use the same endpoint and the same kind of key. The server
tells the two payload shapes apart on its own.

| | iPhone / Apple Watch | Android / Pixel Watch, Fitbit, Samsung |
|---|---|---|
| Health store | Apple Health | Health Connect |
| Bridge app | [Health Auto Export](https://www.healthyapps.dev/) | HC Webhook (free, open source, on Google Play) |
| Route maps | Yes (enable route data) | Not yet — the bridge doesn't send GPS |
| Per-workout calories | Yes | Not yet — the bridge doesn't send session energy |

## Getting your key

1. In the app, open **Fitness** and tap **Connect** at the bottom.
2. The app detects what phone you're holding and shows the right path
   (there's a link to switch if it guessed wrong).
3. Tap **Make my sync key**. You get two things, shown only once:
   - a **Send to** address (your server's ingest URL)
   - an **Authorization header** (`Bearer` plus your key)

Re-minting later replaces the old key, so a lost key is a ten-second fix,
not a problem.

## iPhone: Health Auto Export

1. Install Health Auto Export from the App Store and grant it the Apple
   Health permissions you want to share.
2. Create a **REST API automation**. Paste the **Send to** address as the
   URL and add the **Authorization** header exactly as shown.
3. Pick the metrics to send (steps, active energy, exercise minutes, resting
   heart rate, weight, body fat percentage) and set the schedule.
4. Create a **second automation for workouts**, same URL and header, and
   turn on **route data** if you want the little route maps on run cards.
5. Trigger a manual sync once; the Fitness tab should fill within moments.

Notes:
- Times arrive as your phone's local wall clock and are stored that way.
- Weigh-ins with body fat fill the weight log's body-fat column, but never
  overwrite a value you typed yourself.

## Android: HC Webhook

Pixel Watch, Fitbit, and Samsung Health data all land in **Health Connect**
on the phone; HC Webhook reads it and forwards it.

1. Make sure your watch's companion app is writing to Health Connect
   (Settings → Health Connect → App permissions).
2. Install **HC Webhook** from Google Play.
3. Add a webhook: paste the **Send to** address as the URL, and add the
   **Authorization** header as a custom header, exactly as shown.
4. Grant HC Webhook read access to what you want to share: steps, active
   calories, exercise, heart rate, weight.
5. Pick a schedule and run a manual send once to confirm.

Notes:
- Payload times are UTC; the server converts them onto the family's
  timezone before bucketing days, so an evening walk never files under
  tomorrow.
- Known v1 gaps: no GPS routes and no per-session calories (the bridge app
  doesn't expose them yet). Workout cards render without the map, and the
  watch-calories opt-in earns 0 on Android for now.

## Either platform

- Syncs only need to reach the server, so a phone that leaves the house
  catches up when it's back on the home network (or however you route to
  your instance). Imports are idempotent — re-sending a whole window never
  duplicates anything.
- If the sync goes quiet for a couple of days, the member gets a push
  notification about it (You → Notifications → "Sync gone quiet").
