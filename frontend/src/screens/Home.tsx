import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { VerdictBadge } from '../components/VerdictBadge'
import { ApiError, createCheck, getHistory, getQuota } from '../lib/api'
import { useAuth } from '../lib/auth'
import { config } from '../lib/config'
import type { HistoryItem, Quota } from '../lib/types'
import { Limit } from './Limit'
import { enablePush } from '../lib/push'
import { Icon, type IconName } from '../components/Icon'
import { rememberCheck } from '../lib/lastCheck'

const ALL_MEDIA = 'image/*,video/*,audio/*,.opus,.ogg'
const TILES: { key: string; icon: IconName; accept?: string }[] = [
  { key: 'text', icon: 'text' },
  { key: 'photo', icon: 'image', accept: 'image/*' },
  { key: 'video', icon: 'video', accept: 'video/*' },
  { key: 'audio', icon: 'mic', accept: 'audio/*,.opus,.ogg' },
  { key: 'link', icon: 'link' },
]

interface InstallPrompt extends Event {
  prompt: () => Promise<void>
}

export function Home() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [limitAt, setLimitAt] = useState<string | null>(null)
  const [quota, setQuota] = useState<Quota | null>(null)
  const [recent, setRecent] = useState<HistoryItem[]>([])
  const [install, setInstall] = useState<InstallPrompt | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const pasteBox = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!user) return
    getQuota(user).then(setQuota).catch(() => undefined)
    getHistory(user).then((h) => setRecent(h.items.slice(0, 3))).catch(() => undefined)
  }, [user])

  useEffect(() => {
    const onPrompt = (e: Event) => {
      e.preventDefault()
      setInstall(e as InstallPrompt)
    }
    window.addEventListener('beforeinstallprompt', onPrompt)
    return () => window.removeEventListener('beforeinstallprompt', onPrompt)
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!user) return
    setError(null)
    const size = files.reduce((n, f) => n + f.size, 0)
    if (!text.trim() && !files.length) return setError(t('errors.EMPTY'))
    if (size > config.limits.maxShareBytes) return setError(t('errors.TOO_LARGE'))
    setBusy(true)
    try {
      const res = await createCheck(user, { text: text.trim(), files, clientLang: i18n.language })
      if (res.status !== 'DONE') void enablePush(user) // tell them when it is ready if they leave
      const initial =
        res.status === 'DONE'
          ? { check_id: res.check_id, status: 'DONE', stage: 'done', progress: 100, result: res.result }
          : undefined
      rememberCheck(res.check_id)
      navigate(`/check/${res.check_id}`, { state: { initial } })
    } catch (err) {
      if (err instanceof ApiError && err.code === 'DAILY_LIMIT') setLimitAt(String(err.body.resets_at ?? ''))
      else if (err instanceof ApiError) setError(t(`errors.${err.code}`, { defaultValue: t('errors.generic') }))
      else setError(t('errors.generic'))
    } finally {
      setBusy(false)
    }
  }

  // A tile opens the file picker for that kind of media, or puts the cursor in the paste box.
  const pick = (accept?: string) => {
    if (!accept) return pasteBox.current?.focus()
    if (fileInput.current) {
      fileInput.current.accept = accept
      fileInput.current.click()
    }
  }

  const left = quota ? Math.max(0, quota.limit - quota.used) : null

  return (
    <main className="screen">
      {limitAt !== null && <Limit resetsAt={limitAt || undefined} />}
      {left !== null && quota && (
        <div className="banner" role="status">
          <b>{left}</b>
          <span>{t('home.quota', { left, limit: quota.limit })}</span>
        </div>
      )}
      <form className="card" onSubmit={submit}>
        <label htmlFor="paste" className="label">
          {t('home.pasteLabel')}
        </label>
        <textarea
          ref={pasteBox}
          id="paste"
          rows={6}
          maxLength={config.limits.maxTextChars}
          placeholder={t('home.pastePlaceholder')}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <input
          ref={fileInput}
          type="file"
          hidden
          multiple
          accept={ALL_MEDIA}
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
        <div className="tiles" role="group" aria-label={t('home.whatCheck')}>
          {TILES.map((x) => (
            <button key={x.key} type="button" className="tile" onClick={() => pick(x.accept)}>
              <Icon name={x.icon} />
              {t(`home.tiles.${x.key}`)}
            </button>
          ))}
        </div>
        <div className="row">
          <button type="button" className="secondary" onClick={() => pick(ALL_MEDIA)}>
            {t('home.upload')}
          </button>
          {files.length > 0 && (
            <span className="muted">
              {t('home.filesSelected', { count: files.length })}{' '}
              <button type="button" className="link" onClick={() => setFiles([])}>
                {t('home.clearFiles')}
              </button>
            </span>
          )}
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button className="primary" type="submit" disabled={busy}>
          {busy ? t('check.sending') : t('home.check')}
        </button>
      </form>

      {recent.length > 0 && (
        <section className="card">
          <h3>{t('home.recent')}</h3>
          <ul className="history">
            {recent.map((h) => (
              <li key={h.check_id}>
                <Link to={`/check/${h.check_id}`}>
                  <VerdictBadge label={h.label} /> <span lang={h.content_language ?? undefined}>{h.headline}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card">
        <h3>{t('home.howToShare')}</h3>
        <ol className="howto">
          <li>{t('home.step1')}</li>
          <li>{t('home.step2')}</li>
          <li>{t('home.step3')}</li>
        </ol>
        {install && (
          <button className="secondary" onClick={() => void install.prompt()}>
            {t('home.install')}
          </button>
        )}
      </section>
    </main>
  )
}
