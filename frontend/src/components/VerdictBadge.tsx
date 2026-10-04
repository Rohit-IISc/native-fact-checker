import { useTranslation } from 'react-i18next'
import { contentLng } from '../i18n'
import type { Label } from '../lib/types'

/** `lang` is the content language (BCP-47): verdicts read in the language of the post, not the UI. */
export function VerdictBadge({ label, large = false, lang }: { label: Label | 'NOT_CHECKABLE'; large?: boolean; lang?: string | null }) {
  const { t } = useTranslation(undefined, { lng: contentLng(lang) })
  return <span className={`badge badge-${label.toLowerCase()}${large ? ' badge-large' : ''}`}>{t(`label.${label}`)}</span>
}
