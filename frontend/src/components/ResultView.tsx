import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { contentLng } from '../i18n'
import type { AnswerText, CheckResult, ClaimResult, Evidence } from '../lib/types'
import { AudioPlayer } from './AudioPlayer'
import { Icon } from './Icon'
import { VerdictBadge } from './VerdictBadge'
import { monogram } from '../lib/monogram'
import { TrustSeal } from './TrustSeal'

const TIER_ORDER = { TIER_1: 0, TIER_2: 1, TIER_3: 2, NOT_A_SOURCE: 3 } as const
const TIER_KEY = { TIER_1: 'tier1', TIER_2: 'tier2', TIER_3: 'tier3', NOT_A_SOURCE: 'tier3' } as const
// Outcomes where both the Judge and the Critic read the evidence (a downgrade can follow a failed stage).
const TWO_REVIEWERS = new Set(['AGREED', 'AGREED_AFTER_REVISION', 'SPLIT'])

type Source = Pick<Evidence, 'evidence_id' | 'url' | 'domain' | 'publisher' | 'title' | 'tier'>
type Tab = 'answer' | 'evidence' | 'sources' | 'english'

/** The sources we show and count: with a link, credible tiers first. */
export function listedSources(evidence: Source[]): Source[] {
  return evidence.filter((e) => e.url && e.tier !== 'NOT_A_SOURCE').sort((a, b) => TIER_ORDER[a.tier] - TIER_ORDER[b.tier])
}

function Sources({ items, lang }: { items: Source[]; lang: string }) {
  const { t } = useTranslation(undefined, { lng: contentLng(lang) })
  if (!items.length) return <p className="muted">{t('result.none')}</p>
  return (
    <ul className="sources">
      {items.map((e) => (
        <li key={e.evidence_id} className="source">
          <span className="slogo" aria-hidden="true">
            {monogram(e.publisher || e.domain || '?')}
          </span>
          <div>
            <a href={e.url ?? undefined} target="_blank" rel="noopener noreferrer">
              {e.publisher || e.domain || e.url}
            </a>
            <span className={`tier tier-${TIER_KEY[e.tier]}`}>{t(`result.${TIER_KEY[e.tier]}`)}</span>
            {e.title && <div className="muted small">{e.title}</div>}
          </div>
        </li>
      ))}
    </ul>
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

function AiSection({ a, ai }: { a: AnswerText; ai: NonNullable<ClaimResult['ai_generation']> }) {
  const { t: tc } = useTranslation(undefined, { lng: contentLng(a.language) })
  // The answer carries the signals in its own language (composer-1.4). Older verdicts have only the English
  // list: shown in an English answer, left out of other languages rather than mixing English in.
  const english = a.language.split('-')[0] === 'en'
  const sigAi = a.ai_signals_ai?.length ? a.ai_signals_ai : english ? ai.signals_ai : []
  const sigReal = a.ai_signals_real?.length ? a.ai_signals_real : english ? ai.signals_real : []
  return (
    <section lang={a.language} className="ai">
      <h3>{tc('result.aiTitle')}</h3>
      <p>{tc('result.aiLikelihood', { n: ai.likelihood_ai })}</p>
      {(sigAi.length > 0 || sigReal.length > 0) && (
        <>
          <List title={tc('result.aiSignalsAi')} items={sigAi} lang={a.language} />
          <List title={tc('result.aiSignalsReal')} items={sigReal} lang={a.language} />
        </>
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
  cardUrl,
  sources,
  aiGeneration,
}: {
  claim: Pick<ClaimResult, 'label' | 'confidence' | 'result_url'> &
    Partial<Pick<ClaimResult, 'panel_outcome' | 'evidence_for_ids' | 'evidence_against_ids'>>
  answer: AnswerText
  answerEn: AnswerText
  audioUrl?: string | null
  audioPending?: boolean
  cardUrl?: string | null
  sources: Source[]
  aiGeneration?: ClaimResult['ai_generation']
}) {
  // t: UI chrome in the display language. tc / te: the answer itself, in the language of the post
  // (decision 15) or in English, so headings match the text under them whatever the display language is.
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('answer')
  const [copied, setCopied] = useState(false)
  const sameLanguage = answer.language.split('-')[0] === answerEn.language.split('-')[0]
  const a = tab === 'english' ? answerEn : answer
  const { t: tc } = useTranslation(undefined, { lng: contentLng(answer.language) })
  const { t: ta } = useTranslation(undefined, { lng: contentLng(a.language) })
  const listed = listedSources(sources)
  const reviewers = Boolean(claim.panel_outcome && TWO_REVIEWERS.has(claim.panel_outcome))
  const tabs: Tab[] = sameLanguage ? ['answer', 'evidence', 'sources'] : ['answer', 'evidence', 'sources', 'english']

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(claim.result_url)
      setCopied(true)
    } catch {
      window.prompt(t('result.copyLink'), claim.result_url)
    }
  }

  // The card in the language on screen (the API draws any language the verdict has an answer in).
  const shareCard = async () => {
    if (!cardUrl) return
    const url = new URL(cardUrl)
    url.searchParams.set('lang', a.language)
    try {
      const blob = await (await fetch(url)).blob()
      const file = new File([blob], 'chckr.png', { type: 'image/png' })
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], text: claim.result_url })
        return
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return // the user closed the share sheet
    }
    window.open(url, '_blank', 'noopener')
  }

  const whatsapp = `https://wa.me/?text=${encodeURIComponent(`${a.headline}\n${claim.result_url}`)}`

  return (
    <article className="claim">
      <div className={`vbanner vb-${claim.label.toLowerCase()}`}>
        <div className="vmain">
          <b lang={answer.language}>{tc(`label.${claim.label}`)}</b>
          {/* A "not confirmed" verdict has no meaningful confidence: "0/100" there only confused people (Oct 16). */}
          {claim.label !== 'NOT_ENOUGH_EVIDENCE' && (
            <span lang={answer.language}>{tc('result.confidence', { n: claim.confidence })}</span>
          )}
        </div>
        <span className="vmeta" lang={answer.language}>
          {reviewers && <span>{tc('result.reviewers')}</span>}
          <span>{tc('result.sourceCount', { count: listed.length })}</span>
        </span>
      </div>
      <TrustSeal outcome={claim.panel_outcome} evidence={sources} lang={answer.language} />
      {audioUrl && tab !== 'english' ? (
        <AudioPlayer src={audioUrl} lang={answer.language} />
      ) : (
        audioPending &&
        tab !== 'english' && (
          <p className="muted small" role="status" lang={answer.language}>
            {tc('result.audioSoon')}
          </p>
        )
      )}
      <h2 className="headline" lang={a.language}>
        {a.headline}
      </h2>
      <p lang={a.language} className="lead">
        {a.summary}
      </p>
      <div className="stat3" lang={a.language}>
        <div className="stat">
          <b>{claim.evidence_for_ids?.length ?? a.evidence_for.length}</b>
          {ta('result.statFor')}
        </div>
        <div className="stat">
          <b>{claim.evidence_against_ids?.length ?? a.evidence_against.length}</b>
          {ta('result.statAgainst')}
        </div>
        <div className="stat">
          <b>{listed.length}</b>
          {ta('result.statSources')}
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label={t('result.sections')}>
        {tabs.map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            id={`tab-${k}`}
            aria-selected={tab === k}
            aria-controls="tabpanel"
            className={tab === k ? 'on' : undefined}
            onClick={() => setTab(k)}
          >
            {k === 'english' ? 'English' : t(`result.tab.${k}`)}
          </button>
        ))}
      </div>

      <div id="tabpanel" role="tabpanel" aria-labelledby={`tab-${tab}`} className="card tabpanel" lang={a.language}>
        {(tab === 'answer' || tab === 'english') && (
          <>
            <section>
              <h3>{ta('result.whatPostClaims')}</h3>
              <p>{a.what_post_claims}</p>
              <h3>{ta('result.whatIsTrue')}</h3>
              <p>{a.what_is_true}</p>
            </section>
            {claim.panel_outcome === 'SPLIT' && (a.panel_readings?.length ?? 0) > 0 && (
              <section className="split">
                <h3>{ta('result.splitTitle')}</h3>
                <p className="muted">{ta('result.splitNote')}</p>
                <ul>
                  {a.panel_readings?.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </section>
            )}
            {aiGeneration && <AiSection a={a} ai={aiGeneration} />}
          </>
        )}
        {tab === 'evidence' && (
          <>
            <List title={ta('result.evidenceFor')} items={a.evidence_for} lang={a.language} />
            <List title={ta('result.evidenceAgainst')} items={a.evidence_against} lang={a.language} />
          </>
        )}
        {tab === 'sources' && (
          <section>
            <h3>{ta('result.sources')}</h3>
            <Sources items={listed} lang={a.language} />
          </section>
        )}
      </div>

      <div className="share" role="group" aria-label={t('result.shareTitle')}>
        <a href={whatsapp} target="_blank" rel="noopener noreferrer">
          <Icon name="chat" />
          {t('result.shareWhatsApp')}
        </a>
        {cardUrl && (
          <button type="button" onClick={shareCard}>
            <Icon name="image" />
            {t('result.shareCardShort')}
          </button>
        )}
        <button type="button" onClick={copy}>
          <Icon name="link" />
          {copied ? t('result.copied') : t('result.copyLinkShort')}
        </button>
        {!sameLanguage && (
          <button type="button" onClick={() => setTab(tab === 'english' ? 'answer' : 'english')} aria-pressed={tab === 'english'}>
            <Icon name="globe" />
            {tab === 'english' ? t('result.showNativeShort') : 'English'}
          </button>
        )}
      </div>
    </article>
  )
}

export function ResultView({ result, onFeedback }: { result: CheckResult; onFeedback?: (helpful: boolean) => void }) {
  const { t, i18n } = useTranslation()
  // Part of the answer, so in the post's language; the display language if we could not read the post.
  const { t: tc } = useTranslation(undefined, { lng: contentLng(result.content_language) })
  const [sent, setSent] = useState(false)

  return (
    <div className="result">
      {result.cache_tier_hit !== 'NONE' && (
        <p className="pill">
          {result.claims[0]?.checked_at
            ? t('result.cachedOn', {
                date: new Date(result.claims[0].checked_at).toLocaleDateString(i18n.resolvedLanguage, {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                }),
              })
            : t('result.cached')}
        </p>
      )}
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
          cardUrl={c.card_url}
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
                  className="link"
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
