import type { AppUser } from './auth'
import { config } from './config'
import { appCheckToken } from './firebase'
import type { CheckDoc, CheckResult, HistoryItem, PublicResult, Quota } from './types'

export class ApiError extends Error {
  status: number
  code: string
  body: Record<string, unknown>
  constructor(status: number, body: Record<string, unknown>) {
    super(String(body.message ?? body.error_code ?? status))
    this.status = status
    this.code = String(body.error_code ?? 'ERROR')
    this.body = body
  }
}

async function headers(user: AppUser | null): Promise<Record<string, string>> {
  const h: Record<string, string> = {}
  if (user) h.Authorization = `Bearer ${await user.getIdToken()}`
  if (user && !config.devAuth) {
    const token = await appCheckToken()
    if (token) h['X-Firebase-AppCheck'] = token
  }
  return h
}

async function request<T>(user: AppUser | null, path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${config.apiBaseUrl}${path}`, { ...init, headers: { ...(await headers(user)), ...(init.headers ?? {}) } })
  if (res.status === 204) return undefined as T
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>
  if (!res.ok) throw new ApiError(res.status, body)
  return body as T
}

export interface ShareInput {
  text?: string
  url?: string
  files?: File[]
  clientLang: string
}

export type CreateCheckResponse =
  | { check_id: string; status: 'RUNNING' }
  | { check_id: string; status: 'DONE'; cache_tier_hit: 'T1'; result: CheckResult }

// Cloud Run refuses request bodies over 32 MB. Above this, files go straight to Cloud Storage with a signed
// URL (POST /v1/uploads) and the check carries their upload ids (backend/app/intake/uploads.py).
const DIRECT_UPLOAD_OVER_BYTES = 24 * 1024 * 1024

interface SignedUpload {
  upload_id: string
  url: string
  headers: Record<string, string>
}

async function uploadDirect(user: AppUser, file: File): Promise<string | null> {
  try {
    const signed = await request<SignedUpload>(user, '/v1/uploads', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_type: file.type || 'application/octet-stream', size: file.size }),
    })
    const put = await fetch(signed.url, { method: 'PUT', headers: signed.headers, body: file })
    if (!put.ok) throw new ApiError(put.status, { error_code: 'UPLOAD_FAILED' })
    return signed.upload_id
  } catch (e) {
    // Local dev cannot sign URLs (501): send the file with the check as before.
    if (e instanceof ApiError && e.code === 'DIRECT_UPLOAD_UNAVAILABLE') return null
    throw e
  }
}

export async function createCheck(user: AppUser, input: ShareInput): Promise<CreateCheckResponse> {
  const form = new FormData()
  if (input.text) form.append('text', input.text)
  if (input.url) form.append('url', input.url)
  const files = input.files ?? []
  const total = files.reduce((n, f) => n + f.size, 0)
  for (const f of files) {
    const id = total > DIRECT_UPLOAD_OVER_BYTES ? await uploadDirect(user, f) : null
    if (id) form.append('upload_ids', id)
    else form.append('files', f, f.name)
  }
  form.append('client_lang', input.clientLang)
  return request(user, '/v1/checks', { method: 'POST', body: form })
}

export const getCheck = (user: AppUser, id: string) => request<CheckDoc>(user, `/v1/checks/${encodeURIComponent(id)}`)
export const getQuota = (user: AppUser) => request<Quota>(user, '/v1/me/quota')
export const getMe = (user: AppUser) =>
  request<{ uid: string; consent_at: string | null; ui_language: string | null }>(user, '/v1/me')
export const getHistory = (user: AppUser, cursor?: string) =>
  request<{ items: HistoryItem[]; next_cursor: string | null }>(
    user,
    `/v1/me/history${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`,
  )
export const giveConsent = (user: AppUser, uiLanguage: string) =>
  request<void>(user, '/v1/me/consent', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ui_language: uiLanguage }),
  })
export const sendFeedback = (user: AppUser, checkId: string, helpful: boolean) =>
  request<void>(user, `/v1/checks/${encodeURIComponent(checkId)}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ helpful }),
  })
export const getPublicResult = (id: string, lang?: string) =>
  request<PublicResult>(null, `/v1/results/${encodeURIComponent(id)}${lang ? `?lang=${encodeURIComponent(lang)}` : ''}`)
export const registerFcmToken = (user: AppUser, token: string) =>
  request<void>(user, '/v1/me/fcm-token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
