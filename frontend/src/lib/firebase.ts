import { type FirebaseApp, initializeApp } from 'firebase/app'
import { type AppCheck, getToken as getAppCheckToken, initializeAppCheck, ReCaptchaEnterpriseProvider } from 'firebase/app-check'
import { type Auth, getAuth } from 'firebase/auth'
import { type Firestore, getFirestore } from 'firebase/firestore'
import { config } from './config'

let app: FirebaseApp | null = null
let appCheck: AppCheck | null = null

export function firebaseApp(): FirebaseApp {
  if (!app) {
    if (!config.firebase.apiKey) throw new Error('Firebase is not configured (see frontend/.env.example)')
    app = initializeApp(config.firebase)
    if (config.recaptchaSiteKey) {
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

export function db(): Firestore {
  return getFirestore(firebaseApp(), config.firestoreDb)
}

export async function appCheckToken(): Promise<string | null> {
  firebaseApp()
  if (!appCheck) return null
  const { token } = await getAppCheckToken(appCheck, false)
  return token
}
