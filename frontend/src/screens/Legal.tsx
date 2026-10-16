import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { config } from '../lib/config'

interface Section {
  h: string
  items: string[]
}

/** /privacy and /terms: public, no sign-in. Every statement is checked against the code (docs/08). */
export function Legal({ kind }: { kind: 'privacy' | 'terms' }) {
  const { t, i18n } = useTranslation()
  const vars = { email: config.contactEmail, limit: config.limits.dailyChecks }
  const sections = t(`${kind}.sections`, { returnObjects: true, ...vars }) as Section[]
  const updated = new Date(`${config.legalUpdated}T00:00:00`).toLocaleDateString(i18n.resolvedLanguage, {
    day: 'numeric', month: 'long', year: 'numeric',
  })
  return (
    <main className="screen legal">
      <h1>{t(`${kind}.title`)}</h1>
      <p className="muted">{t('legal.updated', { date: updated })}</p>
      <p className="lead">{t(`${kind}.intro`, vars)}</p>
      {Array.isArray(sections) &&
        sections.map((s) => (
          <section key={s.h} className="card">
            <h2>{s.h}</h2>
            <ul>
              {s.items.map((it) => (
                <li key={it}>{it}</li>
              ))}
            </ul>
          </section>
        ))}
      <section className="card">
        <h2>{t('legal.contact')}</h2>
        <p>
          <a href={`mailto:${config.contactEmail}`}>{config.contactEmail}</a>
        </p>
      </section>
      <p className="muted small">{t('legal.prototype')}</p>
      <Link className="button primary" to="/">
        {t('legal.back')}
      </Link>
    </main>
  )
}
