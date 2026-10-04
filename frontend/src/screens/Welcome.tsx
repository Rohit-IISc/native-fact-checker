import { useTranslation } from 'react-i18next'

export function Welcome({ signedIn, onSignIn, onAgree, busy }: {
  signedIn: boolean
  onSignIn: () => void
  onAgree: () => void
  busy: boolean
}) {
  const { t } = useTranslation()
  return (
    <main className="screen welcome">
      <h1>{t('welcome.title')}</h1>
      <ol className="points">
        <li>{t('welcome.point1')}</li>
        <li>{t('welcome.point2')}</li>
        <li>{t('welcome.point3')}</li>
      </ol>
      <p className="privacy">{t('welcome.privacy')}</p>
      {signedIn ? (
        <button className="primary" onClick={onAgree} disabled={busy}>
          {t('welcome.agree')}
        </button>
      ) : (
        <button className="primary" onClick={onSignIn} disabled={busy}>
          {t('welcome.signin')}
        </button>
      )}
    </main>
  )
}
