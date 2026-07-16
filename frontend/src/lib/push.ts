import * as api from './api'

// The applicationServerKey the browser wants is raw bytes, not base64url.
export function keyBytes(b64url: string): Uint8Array {
  const pad = '='.repeat((4 - (b64url.length % 4)) % 4)
  const raw = atob((b64url + pad).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

// The per-device "I turned push off on purpose" marker. Notification.permission
// stays 'granted' after a disable in You > Notifications, so without recorded
// intent an intentional disable is indistinguishable from a push-service drop —
// and the resync below would silently re-enable it on the next app open. The
// Notifications card sets this on disable and clears it on enable.
export const PUSH_OFF_KEY = 'db_push_off'

// Once per boot: a push service (or the browser) can silently drop a
// subscription without telling the server, so any push after that vanishes.
// This heals it on app open by rebuilding a missing subscription and re-upserting
// it. The Notifications card stays the ONLY place that ever asks for permission —
// this NEVER prompts, so a member who never enabled push is untouched.
let attempted = false

export async function resyncPushSubscription(): Promise<void> {
  if (attempted) return
  attempted = true
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return
  if (!window.isSecureContext) return
  if (Notification.permission !== 'granted') return
  // Turned off on purpose on this device: the missing subscription is the
  // member's choice, never a drop to heal.
  try {
    if (localStorage.getItem(PUSH_OFF_KEY) === '1') return
  } catch {
    return // storage unreadable: intent unknown, so never resurrect
  }
  try {
    const reg = await navigator.serviceWorker.ready
    let sub = await reg.pushManager.getSubscription()
    if (!sub) {
      // Browser side dropped: rebuild the subscription from scratch.
      const { key } = await api.getPushKey()
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(key) as BufferSource,
      })
    }
    // ALWAYS re-PUT, even when the browser still holds a subscription: the
    // server deletes its row on any 404/410 from the push service, transient
    // ones included, so a perfectly valid browser subscription can be missing
    // server-side. The upsert-by-endpoint makes this idempotent — one cheap
    // PUT per app boot is the heal.
    const json = sub.toJSON()
    await api.subscribePush(sub.endpoint, {
      p256dh: json.keys?.p256dh ?? '',
      auth: json.keys?.auth ?? '',
    })
  } catch {
    // Silent: a dev build with no SW never resolves `ready`, an unconfigured
    // server 503s the key. Either way the manual card is still the real path.
  }
}
