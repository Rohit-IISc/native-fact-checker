import { registerFcmToken } from './api'
import type { AppUser } from './auth'
import { config } from './config'
import { firebaseApp } from './firebase'

let asked = false

/**
 * Ask for notification permission once a check has started (docs/07: not on first load), then register
 * this device's FCM token. Our own service worker (sw.ts) shows the push, so the token is bound to it.
 * Best effort: a refusal or an unsupported browser just means no push; the live screen still works.
 */
export async function enablePush(user: AppUser): Promise<void> {
  if (asked || config.devAuth || !config.vapidKey || !('Notification' in window)) return
  asked = true
  try {
    const { getMessaging, getToken, isSupported } = await import('firebase/messaging') // loaded only when needed
    if (!(await isSupported())) return
    const permission = Notification.permission === 'default' ? await Notification.requestPermission() : Notification.permission
    if (permission !== 'granted') return
    const token = await getToken(getMessaging(firebaseApp()), {
      vapidKey: config.vapidKey,
      serviceWorkerRegistration: await navigator.serviceWorker.ready,
    })
    if (token) await registerFcmToken(user, token)
  } catch (e) {
    console.warn('Push notifications are not available', e)
  }
}
