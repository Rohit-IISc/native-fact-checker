import { useTranslation } from 'react-i18next'
import type { CheckDoc, Stage } from '../lib/types'
import { Icon, type IconName } from './Icon'

const ORDER: Stage[] = [
  'received',
  'cache_lookup',
  'fetching_link',
  'extracting',
  'searching',
  'packaging',
  'judging',
  'reviewing',
  'composing',
  'speaking',
]
const AGENTS: { key: string; icon: IconName }[] = [
  { key: 'web_search', icon: 'globe' },
  { key: 'factcheck_sites', icon: 'shield' },
  { key: 'source_credibility', icon: 'link' },
  { key: 'media_provenance', icon: 'image' },
]

/** Live progress from the check's Firestore document: ring (stage progress), one tile per sub-agent, step list. */
export function ProgressSteps({ check, preview }: { check: CheckDoc | undefined; preview?: string }) {
  const { t } = useTranslation()
  const stage = check?.stage ?? 'received'
  const hasLink = check?.input_types?.includes('link') ?? false
  const steps = ORDER.filter((s) => s !== 'fetching_link' || hasLink)
  const current = stage === 'done' ? steps.length : Math.max(0, steps.indexOf(stage))
  const agents = check?.agents ?? {}
  const progress = Math.max(0, Math.min(100, Math.round(check?.progress ?? 0)))
  const started = Object.keys(agents).length > 0

  return (
    <>
      <section className="card checking">
        <div className="ring-row">
          <div className="ring" style={{ ['--p' as string]: `${progress}%` }} role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} aria-label={t('check.title')}>
            <i>{progress}%</i>
          </div>
          <div>
            <h1>{t('check.title')}</h1>
            <p className="muted small" role="status">
              {t(`stage.${stage}`, { defaultValue: '' })}
            </p>
          </div>
        </div>
        {preview && (
          <p className="quote" lang={check?.content_language ?? undefined}>
            {preview}
          </p>
        )}
        <ul className="agent-tiles" aria-label={t('check.agents')}>
          {AGENTS.map(({ key, icon }) => {
            const s = agents[key] ?? (started ? 'skipped' : 'waiting')
            const state = s === 'done' ? 'done' : s === 'pending' ? 'running' : s === 'skipped' ? 'skipped' : s === 'waiting' ? 'waiting' : 'missed'
            return (
              <li key={key} className={`atile a-${state}`}>
                <Icon name={icon} />
                <span>{t(`agentShort.${key}`)}</span>
                <small>{t(`check.agentState.${state}`)}</small>
              </li>
            )
          })}
        </ul>
      </section>
      <section className="card">
        <ol className="steps">
          {steps.map((s, i) => {
            const state = i < current ? 'done' : i === current ? 'active' : 'todo'
            return (
              <li key={s} className={`step step-${state}`} aria-current={state === 'active' ? 'step' : undefined}>
                <span className="step-dot" aria-hidden>
                  {state === 'done' ? '✓' : ''}
                </span>
                <span>{t(`stage.${s}`)}</span>
              </li>
            )
          })}
        </ol>
      </section>
    </>
  )
}
