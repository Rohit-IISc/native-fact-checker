"""Pydantic v2 models shared by the pipeline, API and eval.

Every model call's JSON output must validate against one of these. Keep field
names stable: they are stored in Firestore and BigQuery.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Label(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    MISLEADING = "MISLEADING"
    SCAM = "SCAM"
    NOT_ENOUGH_EVIDENCE = "NOT_ENOUGH_EVIDENCE"


class NonCheckableType(str, Enum):
    OPINION = "OPINION"
    SATIRE = "SATIRE"
    JOKE = "JOKE"
    GREETING = "GREETING"
    PROMOTION = "PROMOTION"
    DEVOTIONAL = "DEVOTIONAL"
    PERSONAL_MESSAGE = "PERSONAL_MESSAGE"
    OTHER = "OTHER"


class ClaimType(str, Enum):
    EVENT = "EVENT"
    STATISTIC = "STATISTIC"
    QUOTE = "QUOTE"
    HEALTH = "HEALTH"
    SCIENCE = "SCIENCE"
    GOVERNMENT_SCHEME = "GOVERNMENT_SCHEME"
    FINANCIAL_OFFER = "FINANCIAL_OFFER"
    MEDIA_AUTHENTICITY = "MEDIA_AUTHENTICITY"
    OTHER = "OTHER"


class TimeSensitivity(str, Enum):
    LIVE_EVENT = "LIVE_EVENT"
    EVERGREEN = "EVERGREEN"


class SourceTier(str, Enum):
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"
    NOT_A_SOURCE = "NOT_A_SOURCE"


class Stance(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    CONTEXT = "CONTEXT"
    UNRELATED = "UNRELATED"


class PanelOutcome(str, Enum):
    AGREED = "AGREED"
    AGREED_AFTER_REVISION = "AGREED_AFTER_REVISION"
    SPLIT = "SPLIT"
    POLICY_DOWNGRADE = "POLICY_DOWNGRADE"
    CACHED = "CACHED"


# ---------- Intake and extraction ----------

class FetchedPost(BaseModel):
    source_url: str
    platform: Literal["youtube", "x", "instagram", "facebook", "linkedin", "telegram", "news", "other"]
    title: str | None = None
    text: str | None = None
    author_handle: str | None = None
    published_at: datetime | None = None
    image_uris: list[str] = []          # gs:// URIs of downloaded images
    youtube_url: str | None = None
    media_missing: bool = False
    fetch_method: Literal["youtube", "x_oembed", "meta_oembed", "open_graph", "html", "failed"]


class Claim(BaseModel):
    claim_id: str
    claim_original: str = Field(description="Claim in the content's own language and script")
    claim_en: str = Field(description="Canonical English claim, one sentence, self-contained")
    claim_type: ClaimType
    entities: list[str] = []
    place: str | None = None
    claimed_date: date | None = Field(None, description="When the post says it happened")
    time_sensitivity: TimeSensitivity
    search_queries_original: list[str] = Field(default_factory=list, max_length=3)
    search_queries_en: list[str] = Field(default_factory=list, max_length=3)


class AIGenerationSignals(BaseModel):
    signals_ai: list[str] = []
    signals_real: list[str] = []


class Extraction(BaseModel):
    content_language: str = Field(description="BCP-47, for example hi-IN")
    content_script: str = Field(description="ISO 15924, for example Deva, Latn, Taml, Knda")
    summary_en: str
    checkable: bool
    non_checkable_type: NonCheckableType | None = None
    claims: list[Claim] = Field(default_factory=list, max_length=3)
    extra_claims_not_checked: list[str] = []
    ocr_text: str | None = None
    transcript: str | None = None
    visual_description_en: str | None = None
    ai_generation_signals: AIGenerationSignals | None = None
    origin_hints: list[str] = Field(
        default_factory=list, description="Handles, watermarks, logos, channel names seen in the media"
    )


class NearMatchResult(BaseModel):
    decision: Literal["SAME", "SAME_CLAIM_DIFFERENT_DATE", "DIFFERENT"]
    reason: str


# ---------- Evidence ----------

class Evidence(BaseModel):
    evidence_id: str                    # e.g. "ws-3", "fc-1"; assigned by code
    agent: Literal[
        "web_search", "factcheck_sites", "source_credibility", "media_provenance", "cache_archive", "satellite"
    ]
    claim_id: str
    url: str | None = None
    domain: str | None = None
    publisher: str | None = None
    title: str | None = None
    published_at: date | None = None
    language: str | None = None
    snippet_en: str = Field(description="What this source says, in English, max 60 words")
    stance: Stance
    rating_text: str | None = None   # ClaimReview rating, if any
    tier: SourceTier = SourceTier.TIER_3  # set by code, never by the model


class SourceAssessment(BaseModel):
    origin_type: Literal["KNOWN_OUTLET", "UNKNOWN_SITE", "SOCIAL_ACCOUNT", "UNKNOWN"]
    origin_name: str | None = None
    repeat_offender_count: int = 0
    repeat_offender_examples: list[str] = []
    domain_age_days: int | None = None
    red_flags: list[str] = []
    note_en: str


class AgentFindings(BaseModel):
    agent: str
    evidence: list[Evidence] = []
    source_assessment: SourceAssessment | None = None
    ai_generation_signals: AIGenerationSignals | None = None
    earliest_appearance: str | None = None   # media provenance: earliest date and URL found
    notes_en: str = ""
    timed_out: bool = False


class ClaimBrief(BaseModel):
    claim_id: str
    claim_en: str
    claimed_date: date | None = None
    place: str | None = None
    brief_en: str = Field(description="Neutral summary of what the evidence says. No verdict.")
    evidence_ids: list[str]
    gaps_en: list[str] = []


class EvidencePack(BaseModel):
    check_id: str
    briefs: list[ClaimBrief]
    evidence: list[Evidence]
    source_assessment: SourceAssessment | None = None
    ai_generation_signals: AIGenerationSignals | None = None
    missing_lanes: list[str] = []


# ---------- Panel ----------

class AIGenerationAssessment(BaseModel):
    likelihood_ai: int = Field(ge=0, le=100)
    signals_ai: list[str]
    signals_real: list[str]


class JudgeVerdict(BaseModel):
    claim_id: str
    label: Label
    confidence: int = Field(ge=0, le=100)
    what_is_true_en: str
    event_date: date | None = None
    evidence_for_ids: list[str] = Field(description="Evidence supporting the claim as stated")
    evidence_against_ids: list[str] = Field(description="Evidence contradicting or re-contextualising the claim")
    cited_ids: list[str] = Field(description="Ids the label relies on")
    reasoning_en: str
    ai_generation: AIGenerationAssessment | None = None


class JudgeOutput(BaseModel):
    verdicts: list[JudgeVerdict]


class CriticReview(BaseModel):
    claim_id: str
    decision: Literal["AGREE", "DISAGREE"]
    proposed_label: Label
    proposed_confidence: int = Field(ge=0, le=100)
    objections_en: list[str] = []


class CriticOutput(BaseModel):
    reviews: list[CriticReview]


# ---------- Answer ----------

class AnswerText(BaseModel):
    language: str
    headline: str = Field(description="Max 12 words")
    summary: str = Field(description="One sentence")
    what_post_claims: str
    what_is_true: str
    evidence_for: list[str]
    evidence_against: list[str]
    confidence_phrase: str
    sources_spoken: str
    audio_script: str = Field(description="75 to 110 words, fixed order, no URLs")
    card_lines: list[str] = Field(description="3 to 4 short lines for the correction card", max_length=4)


class ComposerOutput(BaseModel):
    native: AnswerText
    english: AnswerText


class ClaimResult(BaseModel):
    verdict_id: str
    claim_original: str
    claim_en: str
    label: Label
    confidence: int
    band: Literal["LOW", "MEDIUM", "HIGH"]
    panel_outcome: PanelOutcome
    evidence: list[Evidence]
    evidence_for_ids: list[str]
    evidence_against_ids: list[str]
    ai_generation: AIGenerationAssessment | None = None
    answer: AnswerText
    answer_en: AnswerText
    audio_url: str | None = None
    card_url: str | None = None
    result_url: str


class CheckResult(BaseModel):
    check_id: str
    status: Literal["RUNNING", "DONE", "FAILED", "LIMIT"]
    content_language: str | None = None
    non_checkable_type: NonCheckableType | None = None
    non_checkable_message: str | None = None
    claims: list[ClaimResult] = []
    extra_claims_not_checked: list[str] = []
    cache_tier_hit: Literal["NONE", "T1", "T2"] = "NONE"
    degraded: bool = False
    media_missing_prompt: bool = False
    latency_ms: int | None = None


# ---------- Check request and progress (no web-specific types, so a bot or B2B API can reuse) ----------

class InputType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    LINK = "link"


class MediaRef(BaseModel):
    kind: Literal["image", "video", "audio"]
    mime_type: str
    uri: str                            # gs:// URI, or local path in dev
    size_bytes: int
    sha256: str
    duration_s: float | None = None
    phash: str | None = None            # images: 64-bit pHash, 16 hex chars (tier 1 near match)
    frame_phashes: list[str] = []       # video: pHash of one keyframe every 5 s


class CheckRequest(BaseModel):
    check_id: str
    uid: str
    text: str | None = None
    url: str | None = None
    media: list[MediaRef] = []
    client_lang: str = "en"
    share_date: date


class Stage(str, Enum):
    RECEIVED = "received"
    CACHE_LOOKUP = "cache_lookup"
    FETCHING_LINK = "fetching_link"
    EXTRACTING = "extracting"
    SEARCHING = "searching"
    PACKAGING = "packaging"
    JUDGING = "judging"
    REVIEWING = "reviewing"
    COMPOSING = "composing"
    SPEAKING = "speaking"
    DONE = "done"
    FAILED = "failed"
    LIMIT = "limit"


def band_for(confidence: int) -> Literal["LOW", "MEDIUM", "HIGH"]:
    if confidence >= 85:
        return "HIGH"
    if confidence >= 60:
        return "MEDIUM"
    return "LOW"
