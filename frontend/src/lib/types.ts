// Mirrors backend/app/models.py (CheckResult, ClaimResult, Evidence, AnswerText).

export type Label = 'TRUE' | 'FALSE' | 'MISLEADING' | 'SCAM' | 'NOT_ENOUGH_EVIDENCE'
export type Band = 'LOW' | 'MEDIUM' | 'HIGH'
export type Tier = 'TIER_1' | 'TIER_2' | 'TIER_3' | 'NOT_A_SOURCE'
export type Stance = 'SUPPORTS' | 'CONTRADICTS' | 'CONTEXT' | 'UNRELATED'

export interface Evidence {
  evidence_id: string
  agent: string
  claim_id: string
  url?: string | null
  domain?: string | null
  publisher?: string | null
  title?: string | null
  published_at?: string | null
  snippet_en: string
  stance: Stance
  rating_text?: string | null
  tier: Tier
}

export interface AnswerText {
  language: string
  headline: string
  summary: string
  what_post_claims: string
  what_is_true: string
  evidence_for: string[]
  evidence_against: string[]
  confidence_phrase: string
  sources_spoken: string
  audio_script: string
  card_lines: string[]
  /** Only when the reviewers disagreed (panel_outcome SPLIT): one item per reading. */
  panel_readings?: string[]
  /** The AI-generation signals in this answer's language (composer-1.4); older verdicts lack them. */
  ai_signals_ai?: string[]
  ai_signals_real?: string[]
}

export interface AIGeneration {
  likelihood_ai: number
  signals_ai: string[]
  signals_real: string[]
}

export interface ClaimResult {
  verdict_id: string
  claim_original: string
  claim_en: string
  label: Label
  confidence: number
  band: Band
  panel_outcome: string
  evidence: Evidence[]
  evidence_for_ids: string[]
  evidence_against_ids: string[]
  ai_generation?: AIGeneration | null
  answer: AnswerText
  answer_en: AnswerText
  audio_url?: string | null
  card_url?: string | null
  result_url: string
}

export interface CheckResult {
  check_id: string
  status: 'RUNNING' | 'DONE' | 'FAILED' | 'LIMIT'
  content_language?: string | null
  non_checkable_type?: string | null
  non_checkable_message?: string | null
  claims: ClaimResult[]
  extra_claims_not_checked: string[]
  cache_tier_hit: 'NONE' | 'T1' | 'T2'
  degraded: boolean
  media_missing_prompt: boolean
  /** Text is final; the spoken answers are still being generated. */
  audio_pending?: boolean
  latency_ms?: number | null
}

export type Stage =
  | 'received'
  | 'cache_lookup'
  | 'fetching_link'
  | 'extracting'
  | 'searching'
  | 'packaging'
  | 'judging'
  | 'reviewing'
  | 'composing'
  | 'speaking'
  | 'done'
  | 'failed'
  | 'limit'

export interface CheckDoc {
  check_id: string
  status: CheckResult['status']
  stage: Stage
  progress: number
  input_types?: string[]
  agents?: Record<string, string>
  content_language?: string | null
  claims_preview?: string[]
  error_code?: string | null
  cache_tier_hit?: string
  result?: CheckResult
}

export interface Quota {
  used: number
  limit: number
  resets_at: string
}

export interface HistoryItem {
  check_id: string
  created_at: string
  headline: string
  label: Label | 'NOT_CHECKABLE'
  labels: string[]
  content_language?: string | null
  status: string
}

export interface PublicResult {
  verdict_id: string
  claim_original: string
  claim_en: string
  label: Label
  confidence: number
  panel_outcome?: string
  band: Band
  answer: AnswerText
  answer_en: AnswerText
  sources: Pick<Evidence, 'evidence_id' | 'url' | 'domain' | 'publisher' | 'title' | 'tier' | 'stance'>[]
  evidence_for_ids?: string[]
  evidence_against_ids?: string[]
  ai_generation?: AIGeneration | null
  audio_url?: string | null
  card_url?: string | null
  created_at?: string
}

export interface HistoryStats {
  checked: number
  by_label: Partial<Record<Label | 'NOT_CHECKABLE', number>>
}

/** A shared verdict on Home (Recent checks) and Trending: verdict text only, nothing about who checked it. */
export interface FeedItem {
  verdict_id: string
  label: Label
  headline: string
  claim: string
  language: string | null
  created_at: string
  checks?: number
  last_checked_at?: string
}
