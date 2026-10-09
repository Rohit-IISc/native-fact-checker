"""Correction-card samples in the five demo languages, from recorded composer outputs of our own
acceptance inputs (never samples/). Used by test_card.py and `python -m app.output.card`."""
from __future__ import annotations

import json
from pathlib import Path

from app.models import AnswerText, ClaimResult, Evidence, Label, PanelOutcome, SourceTier, Stance

FIXTURES = Path(__file__).parent / "fixtures"
BY_LANGUAGE = {"hi": "06-hi-free-recharge-scheme", "ta": "05-ta-health-remedy", "kn": "15-kn-thin-local-claim",
               "id": "07-id-vaccine-microchip", "en": "08-en-chandrayaan3-landing"}


def sample_answer(language: str) -> AnswerText:
    case = BY_LANGUAGE[language.split("-")[0]]
    outputs = json.loads((FIXTURES / case / "composer.json").read_text(encoding="utf-8"))["outputs"]
    return AnswerText.model_validate(next(o for o in outputs if o["language"].startswith(language[:2])))


def sample_claim(language: str, label: Label = Label.MISLEADING) -> ClaimResult:
    a = sample_answer(language)
    evidence = [
        Evidence(evidence_id="fc-1", agent="factcheck_sites", claim_id="c1", url="https://www.boomlive.in/x",
                 publisher="BOOM", snippet_en="s", stance=Stance.CONTRADICTS, tier=SourceTier.TIER_1),
        Evidence(evidence_id="ws-1", agent="web_search", claim_id="c1", url="https://x.com/someone/1",
                 publisher="X user", snippet_en="s", stance=Stance.CONTRADICTS, tier=SourceTier.NOT_A_SOURCE),
        Evidence(evidence_id="ws-2", agent="web_search", claim_id="c1", url="https://www.thehindu.com/y",
                 publisher="The Hindu", snippet_en="s", stance=Stance.CONTEXT, tier=SourceTier.TIER_2),
    ]
    return ClaimResult(
        verdict_id="01SAMPLE", claim_original=a.what_post_claims, claim_en="sample", label=label, confidence=80,
        band="HIGH", panel_outcome=PanelOutcome.AGREED, evidence=evidence,
        evidence_for_ids=[], evidence_against_ids=["fc-1", "ws-1", "ws-2"], answer=a, answer_en=a,
        result_url="https://ai-builder-2026.web.app/r/01SAMPLE")
