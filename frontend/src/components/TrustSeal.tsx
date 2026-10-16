import { useTranslation } from 'react-i18next'
import { contentLng } from '../i18n'
import { monogram } from '../lib/monogram'
import type { Evidence } from '../lib/types'

type Source = Pick<Evidence, 'evidence_id' | 'url' | 'domain' | 'publisher' | 'tier'>

// Only a verdict both reviewers signed off on earns the seal. A split, a policy downgrade or an
// unknown outcome shows nothing, so the seal always means what it says.
const SIGNED_OFF = new Set(['AGREED', 'AGREED_AFTER_REVISION'])

export function TrustSeal({ outcome, evidence, lang }: { outcome?: string; evidence: Source[]; lang: string }) {
  const { t } = useTranslation(undefined, { lng: contentLng(lang) })
  if (!outcome || !SIGNED_OFF.has(outcome)) return null
  const tier1 = evidence.filter((e) => e.tier === 'TIER_1' && e.url)
  if (!tier1.length) return null
  const names = [...new Set(tier1.map((e) => e.publisher || e.domain || ''))].filter(Boolean).slice(0, 3)
  return (
    <div className="trust" lang={lang}>
      <svg className="seal" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path
          d="M12 2.5l2.2 1.6 2.7-.1 1 2.5 2.2 1.6-.8 2.6.8 2.6-2.2 1.6-1 2.5-2.7-.1L12 21.5l-2.2-1.6-2.7.1-1-2.5-2.2-1.6.8-2.6-.8-2.6 2.2-1.6 1-2.5 2.7.1z"
          fill="currentColor"
        />
        <path d="M8.5 12.2l2.4 2.4 4.6-4.8" fill="none" stroke="var(--seal-tick)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div>
        <b>{t('result.verifiedBy')}</b>
        <span>{t('result.verifiedNote', { count: tier1.length })}</span>
        <div className="logos">
          {names.map((n) => (
            <span key={n} className="slogo" title={n}>
              {monogram(n)}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
