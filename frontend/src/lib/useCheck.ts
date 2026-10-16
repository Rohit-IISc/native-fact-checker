import { doc, onSnapshot } from 'firebase/firestore'
import { useEffect, useState } from 'react'
import { getCheck } from './api'
import type { AppUser } from './auth'
import { config } from './config'
import { db } from './firestore'
import type { CheckDoc } from './types'

const TERMINAL = new Set(['DONE', 'FAILED', 'LIMIT'])

/** Live check document: Firestore onSnapshot, or polling GET /v1/checks/{id} in dev mode. */
export function useCheck(user: AppUser | null, checkId: string | undefined, initial?: CheckDoc) {
  const [check, setCheck] = useState<CheckDoc | undefined>(initial)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!user || !checkId) return
    if (initial && TERMINAL.has(initial.status)) return

    if (!config.devAuth) {
      return onSnapshot(
        doc(db(), 'checks', checkId),
        (snap) => snap.exists() && setCheck(snap.data() as CheckDoc),
        (e) => setError(e.message),
      )
    }

    let stopped = false
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const d = await getCheck(user, checkId)
        if (stopped) return
        setCheck(d)
        if (TERMINAL.has(d.status)) return
      } catch (e) {
        if (!stopped) setError(e instanceof Error ? e.message : String(e))
      }
      if (!stopped) timer = setTimeout(poll, 1000)
    }
    void poll()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [user, checkId, initial])

  return { check, error }
}
