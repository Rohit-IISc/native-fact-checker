import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { VerdictBadge } from '../components/VerdictBadge'
import { getHistory } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { HistoryItem, Label } from '../lib/types'

const FILTERS: (Label | 'ALL')[] = ['ALL', 'FALSE', 'MISLEADING', 'SCAM', 'TRUE', 'NOT_ENOUGH_EVIDENCE']

export function History() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const [items, setItems] = useState<HistoryItem[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [filter, setFilter] = useState<Label | 'ALL'>('ALL')

  const load = async (after?: string) => {
    if (!user) return
    const page = await getHistory(user, after)
    setItems((prev) => (after ? [...prev, ...page.items] : page.items))
    setCursor(page.next_cursor)
    setLoaded(true)
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user])

  const shown = filter === 'ALL' ? items : items.filter((h) => h.label === filter)

  return (
    <main className="screen">
      <h1>{t('history.title')}</h1>
      {items.length > 0 && (
        <div className="chips" role="group" aria-label={t('history.filter')}>
          {FILTERS.map((f) => (
            <button key={f} type="button" className={`chip${filter === f ? ' on' : ''}`} aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {f === 'ALL' ? t('history.all') : t(`label.${f}`)}
            </button>
          ))}
        </div>
      )}
      {loaded && !items.length && <p className="muted">{t('history.empty')}</p>}
      <ul className="history card">
        {shown.map((h) => (
          <li key={h.check_id}>
            <Link to={`/check/${h.check_id}`}>
              <VerdictBadge label={h.label} />
              <span lang={h.content_language ?? undefined}>{h.headline}</span>
              <span className="muted small">{new Date(h.created_at).toLocaleDateString(i18n.language)}</span>
            </Link>
          </li>
        ))}
      </ul>
      {cursor && (
        <button className="secondary" onClick={() => void load(cursor)}>
          {t('history.more')}
        </button>
      )}
    </main>
  )
}
