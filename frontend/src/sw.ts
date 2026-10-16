/// <reference lib="webworker" />
import { clientsClaim } from 'workbox-core'
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { savePendingShare, shareFromFormData } from './lib/shareStore'

declare let self: ServiceWorkerGlobalScope

self.skipWaiting()
clientsClaim()
cleanupOutdatedCaches()
precacheAndRoute(self.__WB_MANIFEST)

// Web Share Target: Android share sheet (WhatsApp included) POSTs multipart data here.
self.addEventListener('fetch', (event: FetchEvent) => {
  const url = new URL(event.request.url)
  if (event.request.method === 'POST' && url.pathname === '/share-target') {
    event.respondWith(
      (async () => {
        try {
          const form = await event.request.formData()
          await savePendingShare(shareFromFormData(form))
          return Response.redirect('/check?shared=1', 303)
        } catch {
          return Response.redirect('/?share_error=1', 303)
        }
      })(),
    )
  }
})

// SPA navigations fall back to the precached shell, except the API and Firebase's reserved /__/ paths:
// sign-in opens /__/auth/handler on this domain (authDomain chckr.web.app), and serving the app shell there
// opened the app inside the sign-in popup, again and again (Oct 16).
registerRoute(new NavigationRoute(createHandlerBoundToURL('/index.html'), { denylist: [/^\/api\//, /^\/__\//] }))

// Push (FCM data or notification messages). The page suppresses nothing; if a window is
// visible on the same check we skip the notification.
self.addEventListener('push', (event: PushEvent) => {
  const payload = (() => {
    try {
      return event.data?.json() as { notification?: { title?: string; body?: string }; data?: Record<string, string> }
    } catch {
      return undefined
    }
  })()
  const data = payload?.data ?? {}
  const title = payload?.notification?.title ?? data.title ?? 'Result ready'
  const body = payload?.notification?.body ?? data.body ?? ''
  const target = data.check_id ? `/check/${data.check_id}` : '/'
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      if (windows.some((w) => w.visibilityState === 'visible' && new URL(w.url).pathname === target)) return
      await self.registration.showNotification(title, { body, icon: '/icons/icon-192.png', data: { target } })
    })(),
  )
})

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close()
  const target = (event.notification.data as { target?: string } | undefined)?.target ?? '/'
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      const existing = windows[0]
      if (existing) {
        await existing.focus()
        await existing.navigate(target)
      } else {
        await self.clients.openWindow(target)
      }
    })(),
  )
})
