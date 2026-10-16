import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { VerdictBadge } from '../components/VerdictBadge'
import { getHistory, getHistoryStats } from '../lib/api'
import { useAuth } from '../lib/auth'
import { languageName } from '../lib/format'
import type { HistoryItem, HistoryStats, Label } from '../lib/types'

const FILTERS: (Label | 'ALL')[] = ['ALL', 'FALSE', 'MISLEADING', 'SCAM', 'TRUE', 'NOT_ENOUGH_EVIDENCE']

/** The user's own checks: real counts from the whole history, filter chips, newest first. */
export function History() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const ui = i18n.resolvedLanguage ?? 'en'
  const [items, setItems] = useState<HistoryItem[]>([])
  const [stats, setStats] = useState<HistoryStats | null>(null)
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
    if (!user) return
    void load()
    getHistoryStats(user).then(setStats).catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user])

  const shown = filter === 'ALL' ? items : items.filter((h) => h.label === filter)

  return (
    <main className="screen history-screen">
      <h1>{t('history.title')}</h1>
      {stats && stats.checked > 0 && (
        <div className="stat3">
          <div className="stat">
            <b>{stats.checked}</b>
            {t('history.checked')}
          </div>
          <div className="stat">
            <b>{stats.by_label.FALSE ?? 0}</b>
            {t('history.false')}
          </div>
          <div className="stat">
            <b>{stats.by_label.SCAM ?? 0}</b>
            {t('history.scams')}
          </div>
        </div>
      )}
      {items.length > 0 && (
        <div className="chips" role="group" aria-label={t('history.filter')}>
          {FILTERS.map((f) => (
            <button key={f} type="button" className={`chip${filter === f ? ' on' : ''}`} aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {f === 'ALL' ? t('history.all') : t(`label.${f}`)}
            </button>
          ))}
        </div>
      )}
      {loaded && !items.length && <p className="card muted">{t('history.empty')}</p>}
      {loaded && items.length > 0 && !shown.length && <p className="muted">{t('history.noneForFilter')}</p>}
      <ul className="feed">
        {shown.map((h) => (
          <li key={h.check_id}>
            <Link to={`/check/${h.check_id}`}>
              <span className={`swatch sw-${h.label.toLowerCase()}`} aria-hidden="true" />
              <span className="feed-body">
                <span className="feed-head" lang={h.content_language ?? undefined}>{h.headline}</span>
                <span className="muted small">
                  {new Date(h.created_at).toLocaleDateString(ui, { day: 'numeric', month: 'short' })}
                  {h.content_language ? ` · ${languageName(h.content_language, ui)}` : ''}
                </span>
              </span>
              <VerdictBadge label={h.label} lang={h.content_language} />
            </Link>
          </li>
        ))}
      </ul>
      {cursor && (
        <button className="secondary more" onClick={() => void load(cursor)}>
          {t('history.more')}
        </button>
      )}
    </main>
  )
}
