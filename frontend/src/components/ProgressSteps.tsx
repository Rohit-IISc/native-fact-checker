import { useTranslation } from 'react-i18next'
import type { CheckDoc, Stage } from '../lib/types'

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
const AGENTS = ['web_search', 'factcheck_sites', 'source_credibility', 'media_provenance']

export function ProgressSteps({ check }: { check: CheckDoc | undefined }) {
  const { t } = useTranslation()
  const stage = check?.stage ?? 'received'
  const hasLink = check?.input_types?.includes('link') ?? false
  const steps = ORDER.filter((s) => s !== 'fetching_link' || hasLink)
  const current = stage === 'done' ? steps.length : Math.max(0, steps.indexOf(stage))
  const agents = check?.agents ?? {}

  return (
    <div>
      <div className="progress-bar" role="progressbar" aria-valuenow={check?.progress ?? 0} aria-valuemin={0} aria-valuemax={100}>
        <div style={{ width: `${check?.progress ?? 3}%` }} />
      </div>
      <ol className="steps">
        {steps.map((s, i) => {
          const state = i < current ? 'done' : i === current ? 'active' : 'todo'
          return (
            <li key={s} className={`step step-${state}`}>
              <span className="step-dot" aria-hidden>
                {state === 'done' ? '✓' : ''}
              </span>
              <span>{t(`stage.${s}`)}</span>
              {s === 'searching' && Object.keys(agents).length > 0 && (
                <ul className="agents">
                  {AGENTS.filter((a) => agents[a] && agents[a] !== 'skipped').map((a) => (
                    <li key={a} className={`agent agent-${agents[a]}`}>
                      {agents[a] === 'done' ? '✓ ' : '… '}
                      {t(`agent.${a}`)}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
