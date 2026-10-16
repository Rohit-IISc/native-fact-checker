import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

/** Privacy and Terms links: landing footer, consent screen and the language sheet. */
export function LegalLinks() {
  const { t } = useTranslation()
  return (
    <p className="legal-links">
      <Link to="/privacy">{t('privacy.title')}</Link>
      <Link to="/terms">{t('terms.title')}</Link>
    </p>
  )
}
