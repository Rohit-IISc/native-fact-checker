import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate } from 'react-router-dom'
import { getCheck } from '../lib/api'
import { useAuth } from '../lib/auth'
import { lastCheck } from '../lib/lastCheck'

/** Dock "Checks": the check now running on this device, if any. Finished checks live in History. */
export function LatestCheck() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [running, setRunning] = useState<string | null | undefined>(undefined)

  useEffect(() => {
    if (!user) return
    const started = lastCheck()
    if (!started) {
      setRunning(null)
      return
    }
    getCheck(user, started.id)
      .then((doc) => setRunning(doc.status === 'RUNNING' ? started.id : null))
      .catch(() => setRunning(null))
  }, [user])

  if (running) return <Navigate to={`/check/${running}`} replace />
  return (
    <main className="screen">
      <h1>{t('checks.title')}</h1>
      {running === null && (
        <section className="card">
          <p>{t('checks.empty')}</p>
          <div className="row">
            <Link className="button primary" to="/">
              {t('checks.start')}
            </Link>
            <Link className="button secondary" to="/history">
              {t('checks.history')}
            </Link>
          </div>
        </section>
      )}
    </main>
  )
}
