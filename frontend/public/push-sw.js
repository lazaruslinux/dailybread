// Web Push handlers, imported into the generated service worker. The server
// sends a small JSON payload ({title, body, tag, url}); showing a
// notification for every push is also what keeps the subscription alive -
// browsers revoke pushes that arrive silently.

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    // an unparseable payload still shows something rather than nothing
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'dailybread', {
      body: data.body || '',
      tag: data.tag,
      icon: '/pwa-192.png',
      badge: '/pwa-192.png',
      data: { url: data.url || '/' },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || '/'
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      for (const win of wins) {
        if ('focus' in win) return win.focus()
      }
      return clients.openWindow(url)
    }),
  )
})
