"""Persist verdicts and build CheckResult / ClaimResult objects from stored docs."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.ids import ulid
from app.models import (
    AnswerText,
    Claim,
    ClaimResult,
    Evidence,
    JudgeVerdict,
    Label,
    PanelOutcome,
    TimeSensitivity,
    band_for,
)
from app.settings import get_config, get_settings
from app.store import Store

VERDICTS = "verdicts"
CLAIMS = "claims"


def result_url(verdict_id: str) -> str:
    return f"{get_settings().public_base_url}/r/{verdict_id}"


def lang_key(language: str) -> str:
    """answers.{lang} key: the primary subtag (hi-IN -> hi). Code-mixed scripts keep a suffix (hi-Latn)."""
    return language.replace("_", "-")


def expires_at(label: Label, sensitivity: TimeSensitivity, now: datetime) -> str | None:
    cache = get_config().limits["cache"]
    if label == Label.NOT_ENOUGH_EVIDENCE:
        return (now + timedelta(days=int(cache["not_enough_evidence_ttl_days"]))).isoformat()
    if sensitivity == TimeSensitivity.LIVE_EVENT:
        # Archived (not deleted) after this; ARCHIVED verdicts become context evidence.
        return (now + timedelta(days=int(cache["live_event_active_days"]))).isoformat()
    return None


async def persist_verdict(
    store: Store,
    *,
    check_id: str,
    claim: Claim,
    verdict: JudgeVerdict,
    outcome: PanelOutcome,
    evidence: list[Evidence],
    answer: AnswerText,
    answer_en: AnswerText,
    prompt_versions: dict[str, str],
    model_versions: dict[str, str],
    policy_reason: str | None = None,
    split_readings: list[str] | None = None,
    is_stub: bool = False,
) -> str:
    now = datetime.now(UTC)
    verdict_id = ulid()
    used_ids = set(verdict.evidence_for_ids) | set(verdict.evidence_against_ids) | set(verdict.cited_ids)
    max_items = int(get_config().limits["evidence"]["max_items_per_claim"])
    kept = [e for e in evidence if e.claim_id == claim.claim_id]
    kept.sort(key=lambda e: (e.evidence_id not in used_ids,))
    answers = {lang_key(answer.language): answer.model_dump(mode="json")}
    answers.setdefault(lang_key(answer_en.language), answer_en.model_dump(mode="json"))
    doc: dict[str, Any] = {
        "verdict_id": verdict_id,
        "check_id": check_id,
        "claim_original": claim.claim_original,
        "claim_en": claim.claim_en,
        "claim_type": claim.claim_type.value,
        "label": verdict.label.value,
        "confidence": verdict.confidence,
        "band": band_for(verdict.confidence),
        "panel_outcome": outcome.value,
        "policy_reason": policy_reason,
        "split_readings": split_readings or [],
        "what_is_true_en": verdict.what_is_true_en,
        "reasoning_en": verdict.reasoning_en,
        "evidence": [e.model_dump(mode="json") for e in kept[:max_items]],
        "evidence_for_ids": verdict.evidence_for_ids,
        "evidence_against_ids": verdict.evidence_against_ids,
        "ai_generation": verdict.ai_generation.model_dump(mode="json") if verdict.ai_generation else None,
        "event_date": verdict.event_date.isoformat() if verdict.event_date else None,
        "claimed_date": claim.claimed_date.isoformat() if claim.claimed_date else None,
        "time_sensitivity": claim.time_sensitivity.value,
        "content_language": answer.language,
        "status": "ACTIVE",
        "superseded_by": None,
        "answers": answers,
        "answer_en_key": lang_key(answer_en.language),
        "created_at": now.isoformat(),
        "expires_at": expires_at(verdict.label, claim.time_sensitivity, now),
        "model_versions": model_versions,
        "prompt_versions": prompt_versions,
        "is_stub": is_stub,
    }
    await store.set(VERDICTS, verdict_id, doc)
    await store.set(CLAIMS, f"{verdict_id}_{claim.claim_id}", {
        "verdict_id": verdict_id,
        "claim_en": claim.claim_en,
        "status": "ACTIVE",
        "time_sensitivity": claim.time_sensitivity.value,
        "created_at": now.isoformat(),
        # "embedding" (Vector 768) is written by the tier 2 cache on Day 3.
    })
    return verdict_id


def pick_answer(doc: dict[str, Any], language: str | None) -> dict[str, Any] | None:
    answers = doc.get("answers") or {}
    if language:
        if language in answers:
            return answers[language]
        base = language.split("-")[0]
        for k, v in answers.items():
            if k.split("-")[0] == base:
                return v
    return answers.get(doc.get("content_language") or "") or next(iter(answers.values()), None)


def claim_result_from_doc(doc: dict[str, Any], language: str | None = None) -> ClaimResult:
    answer = pick_answer(doc, language or doc.get("content_language"))
    answer_en = (doc.get("answers") or {}).get(doc.get("answer_en_key") or "en") or answer
    return ClaimResult(
        verdict_id=doc["verdict_id"],
        claim_original=doc["claim_original"],
        claim_en=doc["claim_en"],
        label=doc["label"],
        confidence=doc["confidence"],
        band=doc["band"],
        panel_outcome=doc["panel_outcome"],
        evidence=doc.get("evidence") or [],
        evidence_for_ids=doc.get("evidence_for_ids") or [],
        evidence_against_ids=doc.get("evidence_against_ids") or [],
        ai_generation=doc.get("ai_generation"),
        answer=answer,
        answer_en=answer_en,
        audio_url=(answer or {}).get("audio_url"),
        card_url=(answer or {}).get("card_url"),
        result_url=result_url(doc["verdict_id"]),
    )


def public_result(doc: dict[str, Any], language: str | None) -> dict[str, Any]:
    """Whitelisted fields for the public result page. No user data."""
    cr = claim_result_from_doc(doc, language)
    return {
        "verdict_id": cr.verdict_id,
        "claim_original": cr.claim_original,
        "claim_en": cr.claim_en,
        "label": cr.label.value,
        "confidence": cr.confidence,
        "band": cr.band,
        "what_is_true": cr.answer.what_is_true,
        "answer": cr.answer.model_dump(mode="json"),
        "answer_en": cr.answer_en.model_dump(mode="json"),
        "sources": [
            {"evidence_id": e.evidence_id, "url": e.url, "domain": e.domain, "publisher": e.publisher,
             "title": e.title, "tier": e.tier.value, "stance": e.stance.value}
            for e in cr.evidence if e.url and e.tier.value != "NOT_A_SOURCE"
        ],
        "evidence_for_ids": cr.evidence_for_ids,
        "evidence_against_ids": cr.evidence_against_ids,
        "audio_url": cr.audio_url,
        "card_url": cr.card_url,
        "created_at": doc.get("created_at"),
    }
