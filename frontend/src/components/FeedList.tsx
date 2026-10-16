import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { languageName, timeAgo } from '../lib/format'
import type { FeedItem } from '../lib/types'
import { VerdictBadge } from './VerdictBadge'

/** Shared verdicts (Recent checks, Trending). Only verdict text: never anyone's post, media or name. */
export function FeedList({ items, counts = false }: { items: FeedItem[]; counts?: boolean }) {
  const { t, i18n } = useTranslation()
  const ui = i18n.resolvedLanguage ?? 'en'
  return (
    <ul className="feed">
      {items.map((it, n) => (
        <li key={it.verdict_id}>
          <Link to={`/r/${it.verdict_id}`}>
            {counts ? <span className="rank">{n + 1}</span> : <span className={`swatch sw-${it.label.toLowerCase()}`} aria-hidden="true" />}
            <span className="feed-body">
              <span className="feed-head" lang={it.language ?? undefined}>{it.headline || it.claim}</span>
              <span className="muted small">
                {counts && it.checks ? `${t('trending.checks', { count: it.checks })} · ` : ''}
                {timeAgo(counts && it.last_checked_at ? it.last_checked_at : it.created_at, ui)} · {languageName(it.language, ui)}
              </span>
            </span>
            <VerdictBadge label={it.label} lang={it.language} />
          </Link>
        </li>
      ))}
    </ul>
  )
}
