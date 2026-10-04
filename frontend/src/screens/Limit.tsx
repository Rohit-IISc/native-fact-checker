import { useTranslation } from 'react-i18next'

export function Limit({ resetsAt }: { resetsAt?: string }) {
  const { t, i18n } = useTranslation()
  const time = resetsAt
    ? new Date(resetsAt).toLocaleString(i18n.language, { hour: 'numeric', minute: '2-digit', weekday: 'short' })
    : ''
  return (
    <section className="card limit" role="alert">
      <h2>{t('limit.title')}</h2>
      <p>{t('limit.body', { time })}</p>
    </section>
  )
}
