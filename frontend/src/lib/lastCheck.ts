/** The check this device started last, so dock "Checks" can reopen it while it is still running
 *  (history only lists finished checks). Per device and best effort: storage may be unavailable. */
const KEY = 'chckr.lastCheck'

export function rememberCheck(checkId: string) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ id: checkId, at: new Date().toISOString() }))
  } catch {
    /* private mode */
  }
}

export function lastCheck(): { id: string; at: string } | null {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? 'null') as { id?: unknown; at?: unknown } | null
    return v && typeof v.id === 'string' && typeof v.at === 'string' ? { id: v.id, at: v.at } : null
  } catch {
    return null
  }
}
