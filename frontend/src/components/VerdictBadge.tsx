import { useTranslation } from 'react-i18next'
import type { Label } from '../lib/types'

export function VerdictBadge({ label, large = false }: { label: Label | 'NOT_CHECKABLE'; large?: boolean }) {
  const { t } = useTranslation()
  return <span className={`badge badge-${label.toLowerCase()}${large ? ' badge-large' : ''}`}>{t(`label.${label}`)}</span>
}
