const env = import.meta.env

export const config = {
  devAuth: env.VITE_AUTH_MODE === 'dev',
  apiBaseUrl: ((env.VITE_API_BASE_URL as string | undefined) || '/api').replace(/\/$/, ''),
  // Local dev only: App Check prints a debug token to the console; register it in the Firebase console.
  appCheckDebug: env.VITE_APPCHECK_DEBUG === 'true',
  firestoreDb: (env.VITE_FIRESTORE_DB as string | undefined) || '(default)',
  firebase: {
    apiKey: env.VITE_FIREBASE_API_KEY as string | undefined,
    authDomain: env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined,
    projectId: env.VITE_FIREBASE_PROJECT_ID as string | undefined,
    storageBucket: env.VITE_FIREBASE_STORAGE_BUCKET as string | undefined,
    appId: env.VITE_FIREBASE_APP_ID as string | undefined,
    messagingSenderId: env.VITE_FIREBASE_MESSAGING_SENDER_ID as string | undefined,
  },
  vapidKey: env.VITE_FIREBASE_VAPID_KEY as string | undefined,
  recaptchaSiteKey: env.VITE_RECAPTCHA_ENTERPRISE_SITE_KEY as string | undefined,
  limits: {
    maxShareBytes: 50 * 1024 * 1024,
    maxImages: 10,
    maxTextChars: 10000,
  },
}
