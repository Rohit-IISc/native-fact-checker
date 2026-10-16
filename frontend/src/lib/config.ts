const env = import.meta.env

// Our Hosting site and its preview channels serve Firebase's sign-in handler at /__/auth/, so sign-in runs on
// the address the user is on (the account picker shows it) and can use a same-window redirect.
const host = typeof location === 'undefined' ? '' : location.hostname
const ownHost = host === 'chckr.web.app' || /^chckr--[a-z0-9-]+\.web\.app$/.test(host)

export const config = {
  devAuth: env.VITE_AUTH_MODE === 'dev',
  apiBaseUrl: ((env.VITE_API_BASE_URL as string | undefined) || '/api').replace(/\/$/, ''),
  // Local dev only: App Check prints a debug token to the console; register it in the Firebase console.
  appCheckDebug: env.VITE_APPCHECK_DEBUG === 'true',
  firestoreDb: (env.VITE_FIRESTORE_DB as string | undefined) || '(default)',
  firebase: {
    apiKey: env.VITE_FIREBASE_API_KEY as string | undefined,
    authDomain: ownHost ? host : (env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined),
    projectId: env.VITE_FIREBASE_PROJECT_ID as string | undefined,
    storageBucket: env.VITE_FIREBASE_STORAGE_BUCKET as string | undefined,
    appId: env.VITE_FIREBASE_APP_ID as string | undefined,
    messagingSenderId: env.VITE_FIREBASE_MESSAGING_SENDER_ID as string | undefined,
  },
  vapidKey: env.VITE_FIREBASE_VAPID_KEY as string | undefined,
  recaptchaSiteKey: env.VITE_RECAPTCHA_ENTERPRISE_SITE_KEY as string | undefined,
  contactEmail: 'rohitsainice@gmail.com',
  legalUpdated: '2026-10-16', // /privacy and /terms: change when the text changes
  limits: {
    maxShareBytes: 50 * 1024 * 1024,
    maxImages: 10,
    maxTextChars: 10000,
    dailyChecks: 10, // config/limits.yaml quota.checks_per_user_per_day; the signed-in screens read it from /v1/me/quota
  },
}
