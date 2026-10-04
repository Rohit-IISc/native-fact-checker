import { GoogleAuthProvider, onAuthStateChanged, signInWithPopup, signOut as fbSignOut } from 'firebase/auth'
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { config } from './config'
import { auth } from './firebase'

export interface AppUser {
  uid: string
  name: string | null
  email: string | null
  photoURL: string | null
  getIdToken: () => Promise<string>
}

interface AuthState {
  user: AppUser | null
  loading: boolean
  signIn: () => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)
const DEV_KEY = 'devUid'

function devUser(uid: string): AppUser {
  return { uid, name: uid, email: `${uid}@dev.local`, photoURL: null, getIdToken: async () => `dev:${uid}` }
}

function readDevUid(): string | null {
  try {
    return localStorage.getItem(DEV_KEY)
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AppUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (config.devAuth) {
      const uid = readDevUid()
      setUser(uid ? devUser(uid) : null)
      setLoading(false)
      return
    }
    return onAuthStateChanged(auth(), (u) => {
      setUser(
        u
          ? { uid: u.uid, name: u.displayName, email: u.email, photoURL: u.photoURL, getIdToken: () => u.getIdToken() }
          : null,
      )
      setLoading(false)
    })
  }, [])

  const signIn = useCallback(async () => {
    if (config.devAuth) {
      const uid = 'dev-user'
      try {
        localStorage.setItem(DEV_KEY, uid)
      } catch {
        /* private mode: session-only sign-in */
      }
      setUser(devUser(uid))
      return
    }
    await signInWithPopup(auth(), new GoogleAuthProvider())
  }, [])

  const signOut = useCallback(async () => {
    if (config.devAuth) {
      try {
        localStorage.removeItem(DEV_KEY)
      } catch {
        /* ignore */
      }
      setUser(null)
      return
    }
    await fbSignOut(auth())
  }, [])

  const value = useMemo(() => ({ user, loading, signIn, signOut }), [user, loading, signIn, signOut])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
