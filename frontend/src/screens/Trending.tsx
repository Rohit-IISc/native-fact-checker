import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FeedList } from '../components/FeedList'
import { getTrending } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { FeedItem } from '../lib/types'

/** Most-checked verdicts across all users: last 24 hours, or 7 days when fewer than 3 (backend/app/feed.py). */
export function Trending() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [data, setData] = useState<{ window: string; items: FeedItem[] } | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!user) return
    getTrending(user).then(setData).catch(() => setFailed(true))
  }, [user])

  return (
    <main className="screen">
      <h1>{t('trending.title')}</h1>
      {data && <p className="muted">{t(data.window === '24h' ? 'trending.window24h' : 'trending.window7d')}</p>}
      {failed && <p className="error">{t('errors.generic')}</p>}
      {data && !data.items.length && <p className="card muted">{t('trending.empty')}</p>}
      {data && data.items.length > 0 && <FeedList items={data.items} counts />}
      {!data && !failed && <p className="muted">…</p>}
    </main>
  )
}
