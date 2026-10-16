import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { FeedList } from '../components/FeedList'
import { getQuota, getRecent, getTrending } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { FeedItem, Quota } from '../lib/types'

/** Daily limit reached: when checks come back (real reset time), used and left, then shared checks to read. */
export function Limit({ resetsAt }: { resetsAt?: string }) {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const [quota, setQuota] = useState<Quota | null>(null)
  const [trending, setTrending] = useState<FeedItem[]>([])
  const [recent, setRecent] = useState<FeedItem[]>([])

  useEffect(() => {
    if (!user) return
    getQuota(user).then(setQuota).catch(() => undefined)
    getTrending(user).then((r) => setTrending(r.items.slice(0, 3))).catch(() => undefined)
    getRecent(user).then((r) => setRecent(r.items.slice(0, 5))).catch(() => undefined)
  }, [user])

  const reset = quota?.resets_at || resetsAt
  const when = reset
    ? new Date(reset).toLocaleString(i18n.resolvedLanguage, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
    : ''
  const hours = reset ? Math.max(1, Math.ceil((new Date(reset).getTime() - Date.now()) / 3_600_000)) : null
  const used = quota ? Math.min(quota.used, quota.limit) : null

  return (
    <div className="limit-screen">
      <section className="limit-banner" role="alert">
        <div>
          <b>{t('limit.title')}</b>
          <span>{t('limit.sub')}</span>
        </div>
        {when && (
          <span className="back">
            {t('limit.back')}
            <br />
            {when}
          </span>
        )}
      </section>
      <section className="card">
        {when && <p>{t('limit.body', { time: when })}</p>}
        {quota && used !== null && (
          <div className="stat3">
            <div className="stat">
              <b>{used}</b>
              {t('limit.used')}
            </div>
            <div className="stat">
              <b>{Math.max(0, quota.limit - quota.used)}</b>
              {t('limit.left')}
            </div>
            <div className="stat">
              <b>{t('limit.hours', { n: hours })}</b>
              {t('limit.toReset')}
            </div>
          </div>
        )}
      </section>
      {(trending.length > 0 || recent.length > 0) && <h2 className="sech">{t('limit.whileYouWait')}</h2>}
      {trending.length > 0 && (
        <>
          <div className="sech-row">
            <h3>{t('trending.title')}</h3>
            <Link to="/trending">{t('limit.seeAll')}</Link>
          </div>
          <FeedList items={trending} counts />
        </>
      )}
      {recent.length > 0 && (
        <>
          <h3>{t('home.recent')}</h3>
          <FeedList items={recent} />
        </>
      )}
    </div>
  )
}
