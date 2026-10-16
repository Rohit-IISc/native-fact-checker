import { useTranslation } from 'react-i18next'
import { Icon, type IconName } from '../components/Icon'
import { UI_LANGUAGES } from '../i18n'
import { config } from '../lib/config'
import { LegalLinks } from './Legal'

const FEATURES: { key: string; icon: IconName }[] = [
  { key: 'share', icon: 'share' },
  { key: 'sources', icon: 'shield' },
  { key: 'listen', icon: 'mic' },
  { key: 'deleted', icon: 'clock' },
]

/** Landing and consent. The language chips switch every word on this screen at once. */
export function Welcome({ signedIn, onSignIn, onAgree, onLanguage, busy, error }: {
  signedIn: boolean
  onSignIn: () => void
  onAgree: () => void
  onLanguage: (code: string) => void
  busy: boolean
  error?: string | null
}) {
  const { t, i18n } = useTranslation()
  return (
    <main className="welcome">
      <div className="hero">
        <img src="/brand/chckr-logo.png" alt={t('app.name')} width={200} height={200} />
      </div>
      <p className="tick">{t('welcome.ticker', { limit: config.limits.dailyChecks })}</p>
      <div className="screen-pad">
        <h1>{t('welcome.title')}</h1>
        <div className="chips lang-chips" role="group" aria-label={t('nav.chooseLanguage')}>
          {UI_LANGUAGES.map((l) => {
            const on = i18n.resolvedLanguage === l.code
            return (
              <button key={l.code} type="button" lang={l.code} className={`chip${on ? ' on' : ''}`} aria-pressed={on} onClick={() => onLanguage(l.code)}>
                {l.name}
              </button>
            )
          })}
        </div>
        <ul className="features">
          {FEATURES.map((f) => (
            <li key={f.key} className="tile">
              <Icon name={f.icon} />
              {t(`welcome.feature.${f.key}`)}
            </li>
          ))}
        </ul>
        <ol className="points">
          <li>{t('welcome.point1')}</li>
          <li>{t('welcome.point2')}</li>
          <li>{t('welcome.point3')}</li>
        </ol>
        <p className="privacy">{t('welcome.privacy')}</p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {signedIn ? (
          <button className="primary" onClick={onAgree} disabled={busy}>
            {t('welcome.agree')}
          </button>
        ) : (
          <button className="primary" onClick={onSignIn} disabled={busy}>
            {t('welcome.signin')}
          </button>
        )}
        <LegalLinks />
      </div>
    </main>
  )
}
