import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate } from 'react-router-dom'
import { getHistory } from '../lib/api'
import { useAuth } from '../lib/auth'
import { lastCheck } from '../lib/lastCheck'

/** Dock "Checks": the user's latest check (live progress while it runs, then the answer). */
export function LatestCheck() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [latest, setLatest] = useState<string | null | undefined>(undefined)

  useEffect(() => {
    if (!user) return
    getHistory(user)
      .then((page) => {
        const done = page.items[0]
        const started = lastCheck()
        setLatest(started && (!done || started.at > done.created_at) ? started.id : (done?.check_id ?? null))
      })
      .catch(() => setLatest(lastCheck()?.id ?? null))
  }, [user])

  if (latest) return <Navigate to={`/check/${latest}`} replace />
  return (
    <main className="screen">
      <h1>{t('checks.title')}</h1>
      {latest === null && (
        <section className="card">
          <p>{t('checks.empty')}</p>
          <Link className="button primary" to="/">
            {t('checks.start')}
          </Link>
        </section>
      )}
    </main>
  )
}
