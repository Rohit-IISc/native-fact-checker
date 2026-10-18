import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { FeedList } from '../components/FeedList'
import { ApiError, createCheck, getExamples, getQuota, getRecent } from '../lib/api'
import { useAuth } from '../lib/auth'
import { config } from '../lib/config'
import type { FeedItem, Quota } from '../lib/types'
import { Limit } from './Limit'
import { enablePush } from '../lib/push'
import { Icon, type IconName } from '../components/Icon'
import { rememberCheck } from '../lib/lastCheck'

const ALL_MEDIA = 'image/*,video/*,audio/*,.opus,.ogg'
// Only inputs the pipeline supports, two rows of three. Screenshot opens the photo picker.
const TILES: { key: string; icon: IconName; accept?: string }[] = [
  { key: 'text', icon: 'text' },
  { key: 'photo', icon: 'image', accept: 'image/*' },
  { key: 'video', icon: 'video', accept: 'video/*' },
  { key: 'link', icon: 'link' },
  { key: 'screenshot', icon: 'camera', accept: 'image/*' },
  { key: 'audio', icon: 'mic', accept: 'audio/*,.opus,.ogg' },
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
  const [recent, setRecent] = useState<FeedItem[] | null>(null)
  const [examples, setExamples] = useState<string[]>([])
  const [install, setInstall] = useState<InstallPrompt | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const pasteBox = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!user) return
    getQuota(user).then(setQuota).catch(() => undefined)
    getRecent(user).then((r) => setRecent(r.items)).catch(() => setRecent([]))
    getExamples(user).then((r) => setExamples(r.items.map((i) => i.key))).catch(() => undefined)
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

  // Out of checks (the API said so, or today's real count is used up): the limit screen instead of the form.
  if (limitAt !== null || left === 0) {
    return (
      <main className="screen home">
        <Limit resetsAt={limitAt || quota?.resets_at || undefined} />
      </main>
    )
  }

  return (
    <main className="screen home">
      <form className="paste" onSubmit={submit}>
        <label htmlFor="paste" className="sr-only">
          {t('home.pasteLabel')}
        </label>
        <textarea
          ref={pasteBox}
          id="paste"
          rows={2}
          maxLength={config.limits.maxTextChars}
          placeholder={t('home.pastePlaceholder')}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button className="go" type="submit" disabled={busy}>
          {busy ? t('check.sending') : t('home.check')}
        </button>
      </form>
      <input
        ref={fileInput}
        type="file"
        hidden
        multiple
        accept={ALL_MEDIA}
        onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
      />
      {files.length > 0 && (
        <p className="files" role="status">
          {t('home.filesSelected', { count: files.length })}{' '}
          <button type="button" className="link" onClick={() => setFiles([])}>
            {t('home.clearFiles')}
          </button>
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {left !== null && quota && (
        <div className="banner" role="status">
          <span>{t('home.quotaTitle')}</span>
          <b className="go-pill">{t('home.quotaPill', { left, limit: quota.limit })}</b>
        </div>
      )}
      <h2 className="sech">{t('home.whatCheck')}</h2>
      <div className="grid3" role="group" aria-label={t('home.whatCheck')}>
        {TILES.map((x) => (
          <button key={x.key} type="button" className="tile" onClick={() => pick(x.accept)}>
            <Icon name={x.icon} />
            {t(`home.tiles.${x.key}`)}
          </button>
        ))}
      </div>
      <p className="guide">
        <Icon name="chat" />
        <span>{t('home.shareLine')}</span>
      </p>
      {install && (
        <button className="secondary install" onClick={() => void install.prompt()}>
          {t('home.install')}
        </button>
      )}
      {examples.length > 0 && (
        <section aria-labelledby="examples-title">
          <h2 className="sech" id="examples-title">
            {t('examples.title')}
          </h2>
          <p className="muted small">{t('examples.note')}</p>
          <div className="examples">
            {examples.map((k) => (
              <Link key={k} to={`/example/${k}`} className="example-btn">
                {t(`examples.items.${k}`)}
              </Link>
            ))}
          </div>
        </section>
      )}
      <h2 className="sech">{t('home.recent')}</h2>
      {recent === null && <p className="muted">…</p>}
      {recent !== null && recent.length === 0 && <p className="muted">{t('home.recentEmpty')}</p>}
      {recent !== null && recent.length > 0 && <FeedList items={recent} />}
    </main>
  )
}
