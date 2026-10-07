import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { contentLng } from '../i18n'
import type { AnswerText, CheckResult, ClaimResult, Evidence } from '../lib/types'
import { VerdictBadge } from './VerdictBadge'

const TIER_ORDER = { TIER_1: 0, TIER_2: 1, TIER_3: 2, NOT_A_SOURCE: 3 } as const

function Sources({ evidence, lang }: { evidence: Pick<Evidence, 'evidence_id' | 'url' | 'domain' | 'publisher' | 'title' | 'tier'>[]; lang: string }) {
  const { t } = useTranslation(undefined, { lng: contentLng(lang) })
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

function List({ title, items, lang }: { title: string; items: string[]; lang: string }) {
  const { t } = useTranslation(undefined, { lng: contentLng(lang) })
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
  audioPending,
  sources,
  aiGeneration,
}: {
  claim: Pick<ClaimResult, 'label' | 'confidence' | 'result_url'> & Partial<Pick<ClaimResult, 'panel_outcome'>>
  answer: AnswerText
  answerEn: AnswerText
  audioUrl?: string | null
  audioPending?: boolean
  sources: Pick<Evidence, 'evidence_id' | 'url' | 'domain' | 'publisher' | 'title' | 'tier'>[]
  aiGeneration?: ClaimResult['ai_generation']
}) {
  // t: UI chrome in the display language. tc: the answer itself, in the language of the post
  // (decision 15), so headings match the text under them whatever the display language is.
  const { t } = useTranslation()
  const [english, setEnglish] = useState(false)
  const [copied, setCopied] = useState(false)
  const sameLanguage = answer.language.split('-')[0] === answerEn.language.split('-')[0]
  const a = english ? answerEn : answer
  const { t: tc } = useTranslation(undefined, { lng: contentLng(a.language) })

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
      {audioUrl ? (
        <audio className="audio" controls src={audioUrl} preload="none" />
      ) : (
        audioPending && (
          <p className="muted small" role="status" lang={answer.language}>
            {tc('result.audioSoon')}
          </p>
        )
      )}
      <div className="claim-head">
        <VerdictBadge label={claim.label} large lang={a.language} />
        <span className="muted" lang={a.language}>
          {tc('result.confidence', { n: claim.confidence })}
        </span>
      </div>
      <h2 lang={a.language}>{a.headline}</h2>
      <p lang={a.language} className="lead">
        {a.summary}
      </p>
      <section lang={a.language}>
        <h3>{tc('result.whatPostClaims')}</h3>
        <p>{a.what_post_claims}</p>
        <h3>{tc('result.whatIsTrue')}</h3>
        <p>{a.what_is_true}</p>
      </section>
      {claim.panel_outcome === 'SPLIT' && (a.panel_readings?.length ?? 0) > 0 && (
        <section lang={a.language} className="split">
          <h3>{tc('result.splitTitle')}</h3>
          <p className="muted">{tc('result.splitNote')}</p>
          <ul>
            {a.panel_readings?.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </section>
      )}
      <div lang={a.language}>
        <List title={tc('result.evidenceFor')} items={a.evidence_for} lang={a.language} />
        <List title={tc('result.evidenceAgainst')} items={a.evidence_against} lang={a.language} />
      </div>
      {aiGeneration && (
        <section lang={a.language}>
          <h3>{tc('result.aiTitle')}</h3>
          <p>{tc('result.aiLikelihood', { n: aiGeneration.likelihood_ai })}</p>
          <List title={tc('result.aiSignalsAi')} items={aiGeneration.signals_ai} lang={a.language} />
          <List title={tc('result.aiSignalsReal')} items={aiGeneration.signals_real} lang={a.language} />
        </section>
      )}
      <Sources evidence={sources} lang={a.language} />
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
  // Part of the answer, so in the post's language; the display language if we could not read the post.
  const { t: tc } = useTranslation(undefined, { lng: contentLng(result.content_language) })
  const [sent, setSent] = useState(false)

  return (
    <div className="result">
      {result.cache_tier_hit !== 'NONE' && <p className="pill">{t('result.cached')}</p>}
      {result.media_missing_prompt && (
        <p className="card notice" role="status" lang={result.content_language ?? undefined}>
          {tc('result.mediaMissing')}
        </p>
      )}
      {result.non_checkable_type && (
        <article className="card">
          <VerdictBadge label="NOT_CHECKABLE" large lang={result.content_language} />
          <p className="lead" lang={result.content_language ?? undefined}>
            {result.non_checkable_message}
          </p>
        </article>
      )}
      {result.claims.map((c) => (
        <ClaimCard
          key={c.verdict_id}
          claim={c}
          answer={c.answer}
          answerEn={c.answer_en}
          audioUrl={c.audio_url}
          audioPending={result.audio_pending}
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
