import { type FirebaseApp, initializeApp } from 'firebase/app'
import { type AppCheck, getToken as getAppCheckToken, initializeAppCheck, ReCaptchaEnterpriseProvider } from 'firebase/app-check'
import { type Auth, getAuth } from 'firebase/auth'
import { config } from './config'

let app: FirebaseApp | null = null
let appCheck: AppCheck | null = null

export function firebaseApp(): FirebaseApp {
  if (!app) {
    if (!config.firebase.apiKey) throw new Error('Firebase is not configured (see frontend/.env.example)')
    app = initializeApp(config.firebase)
    if (config.recaptchaSiteKey) {
      if (config.appCheckDebug) {
        ;(self as unknown as { FIREBASE_APPCHECK_DEBUG_TOKEN?: boolean }).FIREBASE_APPCHECK_DEBUG_TOKEN = true
      }
      appCheck = initializeAppCheck(app, {
        provider: new ReCaptchaEnterpriseProvider(config.recaptchaSiteKey),
        isTokenAutoRefreshEnabled: true,
      })
    }
  }
  return app
}

export function auth(): Auth {
  return getAuth(firebaseApp())
}

/**
 * App Check token for API calls, or null if none could be obtained. Never throws: the backend
 * decides whether a missing token is acceptable (APP_CHECK_ENFORCE), and answers 403
 * APP_CHECK_REQUIRED if not, which the UI can show. Throwing here would silently block every call.
 */
export async function appCheckToken(): Promise<string | null> {
  firebaseApp()
  if (!appCheck) return null
  try {
    const { token } = await getAppCheckToken(appCheck, false)
    return token
  } catch (e) {
    console.warn(
      config.appCheckDebug
        ? 'App Check failed. Register the debug token printed above in Firebase console > App Check > Apps > Manage debug tokens.'
        : 'App Check failed; sending the request without a token.',
      e,
    )
    return null
  }
}
