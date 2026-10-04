import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AnswerText, CheckResult, ClaimResult, Evidence } from '../lib/types'
import { VerdictBadge } from './VerdictBadge'

const TIER_ORDER = { TIER_1: 0, TIER_2: 1, TIER_3: 2, NOT_A_SOURCE: 3 } as const

function Sources({ evidence }: { evidence: Pick<Evidence, 'evidence_id' | 'url' | 'domain' | 'publisher' | 'title' | 'tier'>[] }) {
  const { t } = useTranslation()
  const items = evidence.filter((e) => e.url && e.tier !== 'NOT_A_SOURCE').sort((a, b) => TIER_ORDER[a.tier] - TIER_ORDER[b.tier])
  if (!items.length) return null
  return (
    <section>
      <h3>{t('result.sources')}</h3>
      <ul className="sources">
        {items.map((e) => (
          <li key={e.evidence_id}>
            <a href={e.url ?? undefined} target="_blank" rel="noopener noreferrer">
              {e.publisher || e.domain || e.url}
            </a>
            {e.title && <div className="muted small">{e.title}</div>}
          </li>
        ))}
      </ul>
    </section>
  )
}

function List({ title, items }: { title: string; items: string[] }) {
  const { t } = useTranslation()
  return (
    <section>
      <h3>{title}</h3>
      {items.length ? (
        <ul>
          {items.map((x, i) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">{t('result.none')}</p>
      )}
    </section>
  )
}

export function ClaimCard({
  claim,
  answer,
  answerEn,
  audioUrl,
  sources,
  aiGeneration,
}: {
  claim: Pick<ClaimResult, 'label' | 'confidence' | 'result_url'>
  answer: AnswerText
  answerEn: AnswerText
  audioUrl?: string | null
  sources: Pick<Evidence, 'evidence_id' | 'url' | 'domain' | 'publisher' | 'title' | 'tier'>[]
  aiGeneration?: ClaimResult['ai_generation']
}) {
  const { t } = useTranslation()
  const [english, setEnglish] = useState(false)
  const [copied, setCopied] = useState(false)
  const sameLanguage = answer.language.split('-')[0] === answerEn.language.split('-')[0]
  const a = english ? answerEn : answer

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(claim.result_url)
      setCopied(true)
    } catch {
      window.prompt(t('result.copyLink'), claim.result_url)
    }
  }

  return (
    <article className="card claim">
      {audioUrl && <audio className="audio" controls src={audioUrl} preload="none" />}
      <div className="claim-head">
        <VerdictBadge label={claim.label} large />
        <span className="muted">{t('result.confidence', { n: claim.confidence })}</span>
      </div>
      <h2 lang={a.language}>{a.headline}</h2>
      <p lang={a.language} className="lead">
        {a.summary}
      </p>
      <section lang={a.language}>
        <h3>{t('result.whatPostClaims')}</h3>
        <p>{a.what_post_claims}</p>
        <h3>{t('result.whatIsTrue')}</h3>
        <p>{a.what_is_true}</p>
      </section>
      <div lang={a.language}>
        <List title={t('result.evidenceFor')} items={a.evidence_for} />
        <List title={t('result.evidenceAgainst')} items={a.evidence_against} />
      </div>
      {aiGeneration && (
        <section>
          <h3>{t('result.aiTitle')}</h3>
          <p>{t('result.aiLikelihood', { n: aiGeneration.likelihood_ai })}</p>
          <List title={t('result.aiSignalsAi')} items={aiGeneration.signals_ai} />
          <List title={t('result.aiSignalsReal')} items={aiGeneration.signals_real} />
        </section>
      )}
      <Sources evidence={sources} />
      <div className="actions">
        {!sameLanguage && (
          <button className="secondary" onClick={() => setEnglish((v) => !v)}>
            {english ? t('result.showNative') : t('result.showEnglish')}
          </button>
        )}
        <button className="secondary" onClick={copy}>
          {copied ? t('result.copied') : t('result.copyLink')}
        </button>
      </div>
    </article>
  )
}

export function ResultView({ result, onFeedback }: { result: CheckResult; onFeedback?: (helpful: boolean) => void }) {
  const { t } = useTranslation()
  const [sent, setSent] = useState(false)

  return (
    <div className="result">
      {result.cache_tier_hit !== 'NONE' && <p className="pill">{t('result.cached')}</p>}
      {result.non_checkable_type && (
        <article className="card">
          <VerdictBadge label="NOT_CHECKABLE" large />
          <p className="lead">{result.non_checkable_message}</p>
        </article>
      )}
      {result.claims.map((c) => (
        <ClaimCard
          key={c.verdict_id}
          claim={c}
          answer={c.answer}
          answerEn={c.answer_en}
          audioUrl={c.audio_url}
          sources={c.evidence}
          aiGeneration={c.ai_generation}
        />
      ))}
      {result.extra_claims_not_checked.length > 0 && (
        <section className="card">
          <h3>{t('result.extraClaims')}</h3>
          <ul>
            {result.extra_claims_not_checked.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        </section>
      )}
      {onFeedback && (
        <div className="feedback">
          {sent ? (
            <span>{t('result.thanks')}</span>
          ) : (
            <>
              <span>{t('result.helpful')}</span>
              {[true, false].map((v) => (
                <button
                  key={String(v)}
                  className="secondary"
                  onClick={() => {
                    setSent(true)
                    onFeedback(v)
                  }}
                >
                  {v ? t('result.yes') : t('result.no')}
                </button>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  )
}
