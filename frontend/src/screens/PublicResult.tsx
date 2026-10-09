import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ClaimCard } from '../components/ResultView'
import { getPublicResult } from '../lib/api'
import type { PublicResult as PR } from '../lib/types'

/** /r/:verdictId opens without sign-in and shows no user data. */
export function PublicResult() {
  const { t } = useTranslation()
  const { verdictId } = useParams()
  const [params] = useSearchParams()
  const [result, setResult] = useState<PR | null>(null)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    if (!verdictId) return
    getPublicResult(verdictId, params.get('lang') ?? undefined)
      .then(setResult)
      .catch(() => setMissing(true))
  }, [verdictId, params])

  return (
    <main className="screen">
      {missing && <p className="card">{t('public.notFound')}</p>}
      {result && (
        <ClaimCard
          claim={{ label: result.label, confidence: result.confidence, result_url: window.location.href,
                   panel_outcome: result.panel_outcome }}
          answer={result.answer}
          answerEn={result.answer_en}
          audioUrl={result.audio_url}
          cardUrl={result.card_url}
          sources={result.sources}
        />
      )}
      <Link className="button primary" to="/">
        {t('public.cta')}
      </Link>
    </main>
  )
}
