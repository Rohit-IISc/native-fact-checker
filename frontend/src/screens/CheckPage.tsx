import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ProgressSteps } from '../components/ProgressSteps'
import { ResultView } from '../components/ResultView'
import { ApiError, createCheck, sendFeedback } from '../lib/api'
import { useAuth } from '../lib/auth'
import { takePendingShare } from '../lib/shareStore'
import type { CheckDoc } from '../lib/types'
import { useCheck } from '../lib/useCheck'
import { Limit } from './Limit'
import { enablePush } from '../lib/push'
import { rememberCheck } from '../lib/lastCheck'

/** /check?shared=1 picks up a Web Share Target payload and submits it, then becomes /check/:id. */
export function SharedCheck() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [error, setError] = useState<string | null>(null)
  const [limitAt, setLimitAt] = useState<string | null>(null)
  const started = useRef(false)

  useEffect(() => {
    if (!user || started.current || params.get('shared') !== '1') return
    started.current = true
    void (async () => {
      const share = await takePendingShare()
      if (!share) return navigate('/', { replace: true })
      // WhatsApp often puts the link inside text; the server extracts URLs from text too.
      const text = [share.title, share.text].filter(Boolean).join('\n')
      try {
        const res = await createCheck(user, { text, url: share.url, files: share.files, clientLang: i18n.language })
        if (res.status !== 'DONE') void enablePush(user) // tell them when it is ready if they leave
        const initial =
          res.status === 'DONE'
            ? { check_id: res.check_id, status: 'DONE', stage: 'done', progress: 100, result: res.result }
            : undefined
        rememberCheck(res.check_id)
        navigate(`/check/${res.check_id}`, { replace: true, state: { initial } })
      } catch (err) {
        if (err instanceof ApiError && err.code === 'DAILY_LIMIT') setLimitAt(String(err.body.resets_at ?? ''))
        else if (err instanceof ApiError) setError(t(`errors.${err.code}`, { defaultValue: t('errors.generic') }))
        else setError(t('errors.generic'))
      }
    })()
  }, [user, params, navigate, i18n.language, t])

  return (
    <main className="screen">
      {limitAt !== null ? (
        <Limit resetsAt={limitAt || undefined} />
      ) : error ? (
        <p className="card error">{error}</p>
      ) : (
        <p className="card">{t('check.sending')}</p>
      )}
    </main>
  )
}

export function CheckPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { checkId } = useParams()
  const location = useLocation()
  const initial = (location.state as { initial?: CheckDoc } | null)?.initial
  const { check, error } = useCheck(user, checkId, initial)
  const [showLeave, setShowLeave] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setShowLeave(true), 10_000)
    return () => clearTimeout(timer)
  }, [])

  const done = check?.status === 'DONE' && check.result
  const failed = check?.status === 'FAILED'

  return (
    <main className="screen">
      {!done && !failed && (
        <>
          <ProgressSteps check={check} preview={check?.claims_preview?.[0]} />
          {showLeave && <p className="muted leave">{t('check.leaveNote')}</p>}
        </>
      )}
      {failed && (
        <section className="card" role="alert">
          <p>{t('check.failed')}</p>
          <Link className="button primary" to="/">
            {t('check.tryAgain')}
          </Link>
        </section>
      )}
      {error && <p className="error">{error}</p>}
      {done && check.result && (
        <ResultView
          result={check.result}
          onFeedback={user && checkId ? (helpful) => void sendFeedback(user, checkId, helpful).catch(() => undefined) : undefined}
        />
      )}
    </main>
  )
}
