import { Bell, BellOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import * as api from '../lib/api'

// The You-tab "Notifications" card: turn card reminders on or off for THIS
// device, and ring it once to prove the pipe works. One subscription per
// device per member; the server pushes ~15 minutes before a timed card.

// The applicationServerKey the browser wants is raw bytes, not base64url.
function keyBytes(b64url: string): Uint8Array {
  const pad = '='.repeat((4 - (b64url.length % 4)) % 4)
  const raw = atob((b64url + pad).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

// Why this device can't do push (or null when it can). Checked lazily so an
// unsupported browser just gets a quiet explanation, never an error.
function unsupportedReason(): string | null {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    // The one mainstream holdout is an iPhone browser tab: iOS allows push
    // only for web apps installed to the Home Screen.
    if (/iPhone|iPad/.test(navigator.userAgent)) {
      return 'On an iPhone or iPad, first add dailybread to your Home Screen (Share → Add to Home Screen), then open it from that icon and enable notifications here.'
    }
    return "This browser doesn't support notifications."
  }
  if (!window.isSecureContext) {
    return 'Notifications need the HTTPS address of the app.'
  }
  return null
}

type State =
  | { kind: 'checking' }
  | { kind: 'unsupported'; reason: string }
  | { kind: 'unconfigured' }
  | { kind: 'denied' }
  | { kind: 'off' }
  | { kind: 'on'; endpoint: string }

export function NotificationsCard() {
  const [state, setState] = useState<State>({ kind: 'checking' })
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const reason = unsupportedReason()
    if (reason) {
      setState({ kind: 'unsupported', reason })
      return
    }
    if (Notification.permission === 'denied') {
      setState({ kind: 'denied' })
      return
    }
    navigator.serviceWorker.getRegistration().then(async (reg) => {
      const sub = reg && (await reg.pushManager.getSubscription())
      setState(sub ? { kind: 'on', endpoint: sub.endpoint } : { kind: 'off' })
    })
  }, [])

  async function enable() {
    setBusy(true)
    setError(null)
    setNote(null)
    try {
      const { key } = await api.getPushKey()
      if ((await Notification.requestPermission()) !== 'granted') {
        setState({ kind: 'denied' })
        return
      }
      const reg = await navigator.serviceWorker.getRegistration()
      if (!reg) throw new Error('no service worker')
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(key) as BufferSource,
      })
      const json = sub.toJSON()
      await api.subscribePush(sub.endpoint, {
        p256dh: json.keys?.p256dh ?? '',
        auth: json.keys?.auth ?? '',
      })
      setState({ kind: 'on', endpoint: sub.endpoint })
      setNote('This device will get reminders shortly before timed cards.')
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 503) {
        setState({ kind: 'unconfigured' })
      } else {
        setError('Could not turn notifications on. Try again in a moment.')
      }
    } finally {
      setBusy(false)
    }
  }

  async function disable() {
    setBusy(true)
    setError(null)
    setNote(null)
    try {
      const reg = await navigator.serviceWorker.getRegistration()
      const sub = reg && (await reg.pushManager.getSubscription())
      if (sub) {
        await api.unsubscribePush(sub.endpoint)
        await sub.unsubscribe()
      }
      setState({ kind: 'off' })
    } catch {
      setError('Could not turn notifications off here; you can also revoke them in your browser settings.')
    } finally {
      setBusy(false)
    }
  }

  async function test() {
    setBusy(true)
    setError(null)
    setNote(null)
    try {
      const { sent } = await api.sendTestPush()
      setNote(
        sent > 0
          ? `Sent. ${sent === 1 ? 'This device' : `${sent} devices`} should ring in a few seconds.`
          : 'No registered devices found for you. Turn notifications on first.',
      )
    } catch {
      setError('The test could not be sent.')
    } finally {
      setBusy(false)
    }
  }

  const on = state.kind === 'on'

  return (
    <div className="glass p-4" data-notifications>
      <span className="mb-3 block text-xs font-semibold uppercase tracking-wide text-fg/50">
        Notifications
      </span>

      {state.kind === 'unsupported' && (
        <p className="text-xs leading-relaxed text-fg/50">{state.reason}</p>
      )}
      {state.kind === 'unconfigured' && (
        <p className="text-xs leading-relaxed text-fg/50">
          This server doesn't have push notifications set up.
        </p>
      )}
      {state.kind === 'denied' && (
        <p className="text-xs leading-relaxed text-fg/50">
          Notifications are blocked for dailybread in this browser. Allow them in your
          browser/site settings, then come back here.
        </p>
      )}

      {(state.kind === 'off' || on) && (
        <>
          <p className="mb-3 text-xs leading-relaxed text-fg/50">
            {on
              ? 'Reminders are on for this device: a ping shortly before anything with a time on your board.'
              : 'Get a ping on this device shortly before anything with a time on your board. Each person turns this on per device.'}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={on ? disable : enable}
              className={`flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition-colors ${
                on
                  ? 'border-fg/15 bg-fg/5 text-fg/70 hover:bg-fg/10'
                  : 'border-accent-bright/40 bg-accent-bright/15 text-accent-bright hover:bg-accent-bright/25'
              }`}
            >
              {on ? (
                <>
                  <BellOff className="h-3.5 w-3.5" /> Turn off
                </>
              ) : (
                <>
                  <Bell className="h-3.5 w-3.5" /> Turn on
                </>
              )}
            </button>
            {on && (
              <button
                type="button"
                disabled={busy}
                onClick={test}
                className="rounded-xl border border-fg/15 bg-fg/5 px-3 py-2 text-xs font-semibold text-fg/70 transition-colors hover:bg-fg/10"
                data-test-push
              >
                Send a test
              </button>
            )}
          </div>
        </>
      )}

      {note && <p className="mt-2.5 text-xs text-emerald-300">{note}</p>}
      {error && <p className="mt-2.5 text-xs text-rose-300">{error}</p>}
    </div>
  )
}
