// The service worker stores a Web Share Target POST here (pages cannot read that FormData directly);
// the /check?shared=1 page picks it up. Plain IndexedDB, shared by the window and the worker.

export interface PendingShare {
  title?: string
  text?: string
  url?: string
  files: File[]
  received_at: number
}

const DB = 'share-target'
const STORE = 'pending'
const KEY = 'latest'

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest): Promise<T> {
  const db = await open()
  return new Promise<T>((resolve, reject) => {
    const t = db.transaction(STORE, mode)
    const req = fn(t.objectStore(STORE))
    t.oncomplete = () => {
      db.close()
      resolve(req.result as T)
    }
    t.onerror = () => reject(t.error)
  })
}

export function savePendingShare(share: PendingShare): Promise<void> {
  return tx('readwrite', (s) => s.put(share, KEY))
}

export async function takePendingShare(): Promise<PendingShare | null> {
  const share = await tx<PendingShare | undefined>('readonly', (s) => s.get(KEY))
  if (share) await tx('readwrite', (s) => s.delete(KEY))
  return share ?? null
}

export function shareFromFormData(form: FormData): PendingShare {
  const str = (k: string) => {
    const v = form.get(k)
    return typeof v === 'string' && v.trim() ? v : undefined
  }
  return {
    title: str('title'),
    text: str('text'),
    url: str('url'),
    files: form.getAll('files').filter((f): f is File => f instanceof File && f.size > 0),
    received_at: Date.now(),
  }
}
