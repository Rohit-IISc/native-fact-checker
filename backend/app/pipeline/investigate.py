"""Stages 4 to 7 for checkable claims: fan-out, packager, review panel, composer (docs/03).

Every stage has a deadline from config/limits.yaml, capped by what is left of the check's budget,
and degrades instead of failing the check:
  - an agent that fails or times out becomes a missing lane the packager and judge are told about
  - packager failure: the judge reads code-ranked evidence without briefs
  - judge failure: NOT_ENOUGH_EVIDENCE for every claim
  - critic failure or no time: judge verdict kept, confidence capped below HIGH (panel.merge)
  - no time for a revision after a disagreement: SPLIT, so NOT_ENOUGH_EVIDENCE with both readings
  - composer failure: an English answer built from the verdict
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents import (
    composer,
    factcheck_sites,
    media_provenance,
    packager,
    panel_agents,
    same_media,
    source_credibility,
    web_search,
)
from app.agents.tools import Tools
from app.llm import LLM, StageFailed
from app.models import (
    AgentFindings,
    AnswerText,
    CheckRequest,
    Claim,
    CriticOutput,
    CriticReview,
    Evidence,
    EvidencePack,
    Extraction,
    FetchedPost,
    JudgeOutput,
    JudgeVerdict,
    Label,
    PanelOutcome,
    SourceTier,
    Stage,
    Stance,
)
from app.observability.logging import log_event
from app.pipeline import panel, stub
from app.pipeline.panel import PanelDecision
from app.pipeline.progress import set_agent_status, set_stage
from app.prompts import load_prompt
from app.settings import get_config
from app.store import Store

log = logging.getLogger(__name__)
COMPOSER_RESERVE_S = 12.0   # always leave time to write the answer
MIN_STAGE_S = 4.0
AFTER_FAN_OUT_S = 30.0      # measured Oct 5: packager 6 s + judge 10 s + critic 6 s, plus the composer reserve


@dataclass
class Budget:
    deadline: float  # time.monotonic() value

    def left(self) -> float:
        return self.deadline - time.monotonic()

    def stage(self, name: str, reserve: float = COMPOSER_RESERVE_S) -> float:
        """Timeout for a stage: its configured limit, capped by the remaining budget minus `reserve`."""
        return max(0.0, min(get_config().timeout(name), self.left() - reserve))


@dataclass
class Investigation:
    findings: list[AgentFindings] = field(default_factory=list)
    missing_lanes: list[str] = field(default_factory=list)
    pack: EvidencePack | None = None
    decisions: dict[str, PanelDecision] = field(default_factory=dict)
    answers: dict[str, tuple[AnswerText, AnswerText]] = field(default_factory=dict)
    prompt_versions: dict[str, str] = field(default_factory=dict)
    degraded: bool = False
    stage_errors: dict[str, str] = field(default_factory=dict)  # stage -> why it failed (debugging)


# ---------- stage 4: fan-out ----------

async def fan_out(store: Store, llm: LLM, tools: Tools, req: CheckRequest, extraction: Extraction,
                  fetched: FetchedPost | None, budget: Budget, errors: dict[str, str] | None = None
                  ) -> tuple[list[AgentFindings], list[str]]:
    errors = errors if errors is not None else {}
    # Leave typical (not worst-case) time for packager, judge and critic, plus the composer reserve;
    # each later stage caps itself to what is left anyway.
    timeout = max(MIN_STAGE_S, min(get_config().timeout("sub_agent"), budget.left() - AFTER_FAN_OUT_S))
    lanes: dict[str, Callable[[], Awaitable[AgentFindings]]] = {
        "web_search": lambda: web_search.run(llm, extraction, timeout),
        "factcheck_sites": lambda: factcheck_sites.run(llm, tools, extraction, timeout),
    }
    skipped = []
    if source_credibility.has_origin(extraction, fetched):
        lanes["source_credibility"] = lambda: source_credibility.run(llm, tools, extraction, fetched, timeout)
    else:
        skipped.append("source_credibility")
    if media_provenance.has_media(req, fetched):
        lanes["media_provenance"] = lambda: media_provenance.run(llm, tools, extraction, req, fetched, timeout)
    else:
        skipped.append("media_provenance")
    for name in lanes:
        await set_agent_status(store, req.check_id, name, "pending")
    for name in skipped:
        await set_agent_status(store, req.check_id, name, "skipped")

    async def one(name: str) -> AgentFindings | None:
        try:
            result = await asyncio.wait_for(lanes[name](), timeout=timeout + 2)
            status = "done"
        except (TimeoutError, StageFailed) as e:
            result, status = None, "timeout" if "timeout" in str(e) or isinstance(e, TimeoutError) else "failed"
            log_event(log, "agent failed", logging.WARNING, agent=name, reason=str(e)[:300])
            errors[name] = f"{type(e).__name__}: {str(e)[:300]}"
        except Exception as e:  # noqa: BLE001  one lane must never take the check down
            result, status = None, "failed"
            log.exception("agent %s crashed", name, exc_info=e)
            errors[name] = f"crash {type(e).__name__}: {str(e)[:300]}"
        await set_agent_status(store, req.check_id, name, status)
        return result

    names = list(lanes)
    results = await asyncio.gather(*(one(n) for n in names))
    findings = [r for r in results if r is not None]
    missing = [n for n, r in zip(names, results, strict=True) if r is None]
    return findings, missing


# ---------- stage 6: panel ----------

def _nee(claim: Claim, reason: str, evidence: list[Evidence] | None = None) -> JudgeVerdict:
    """NOT_ENOUGH_EVIDENCE without a judge's reading. Evidence for and against still follows each item's
    classified stance (rule 4): Oct 16, a judge timeout showed "nothing found" next to a PTI fact check."""
    mine = [e for e in evidence or [] if e.claim_id == claim.claim_id and e.tier != SourceTier.NOT_A_SOURCE]
    return JudgeVerdict(claim_id=claim.claim_id, label=Label.NOT_ENOUGH_EVIDENCE, confidence=0,
                        what_is_true_en=reason, cited_ids=[], reasoning_en=reason,
                        evidence_for_ids=[e.evidence_id for e in mine if e.stance == Stance.SUPPORTS],
                        evidence_against_ids=[e.evidence_id for e in mine if e.stance == Stance.CONTRADICTS])


async def run_panel(llm: LLM, claims: list[Claim], pack: EvidencePack, budget: Budget, inv: Investigation
                    ) -> dict[str, PanelDecision]:
    evidence = pack.evidence
    try:
        judged = await panel_agents.judge(llm, pack, budget.stage("judge"))
        inv.prompt_versions["judge"] = load_prompt("08_judge.md").version
    except StageFailed as e:
        log_event(log, "judge failed", logging.WARNING, reason=str(e)[:300])
        inv.stage_errors["judge"] = str(e)[:300]
        inv.degraded = True
        return {c.claim_id: PanelDecision(_nee(c, "We could not complete the review of the evidence.", evidence),
                                          PanelOutcome.POLICY_DOWNGRADE, policy_reason="judge unavailable")
                for c in claims}
    by_claim = {v.claim_id: v for v in judged.verdicts}
    judged = JudgeOutput(verdicts=[by_claim.get(c.claim_id) or _nee(c, "The judge returned no verdict.")
                                   for c in claims])
    by_claim = {v.claim_id: v for v in judged.verdicts}

    critic_out: CriticOutput | None = None
    if budget.stage("critic") >= MIN_STAGE_S:
        try:
            critic_out = await panel_agents.critic(llm, pack, judged, budget.stage("critic"))
            inv.prompt_versions["critic"] = load_prompt("09_critic.md").version
        except StageFailed as e:
            log_event(log, "critic failed", logging.WARNING, reason=str(e)[:300])
            inv.stage_errors["critic"] = str(e)[:300]
    reviews: dict[str, CriticReview] = {r.claim_id: r for r in (critic_out.reviews if critic_out else [])}

    disagreed = [cid for cid, r in reviews.items()
                 if cid in by_claim and (r.decision == "DISAGREE" or r.proposed_label != by_claim[cid].label)]
    revised: dict[str, JudgeVerdict] = {}
    if disagreed and critic_out and budget.stage("judge_revision") >= MIN_STAGE_S:
        try:
            out = await panel_agents.revise(llm, pack, judged, critic_out, budget.stage("judge_revision"))
            revised = {v.claim_id: v for v in out.verdicts}
        except StageFailed as e:
            log_event(log, "judge revision failed", logging.WARNING, reason=str(e)[:300])
            inv.stage_errors["judge_revision"] = str(e)[:300]

    decisions = {}
    for c in claims:
        v = by_claim[c.claim_id]
        review = reviews.get(c.claim_id)
        # No revision available after a disagreement: pass the original verdict, which merge() turns
        # into a SPLIT unless it already matches the critic.
        decisions[c.claim_id] = panel.merge(v, review, evidence, revised=revised.get(c.claim_id, v))
    return decisions


# ---------- entry ----------

async def investigate(store: Store, llm: LLM, tools: Tools, req: CheckRequest, extraction: Extraction,
                      fetched: FetchedPost | None, budget: Budget,
                      timed: Callable[[str, Awaitable[Any]], Awaitable[Any]],
                      extra_findings: list[AgentFindings] | None = None) -> Investigation:
    """`extra_findings`: e.g. earlier verdicts on the same claim with a different date (tier 2 context)."""
    inv = Investigation()
    claims = extraction.claims

    await set_stage(store, req.check_id, Stage.SEARCHING)
    inv.findings, inv.missing_lanes = await timed("searching", fan_out(store, llm, tools, req, extraction, fetched,
                                                                        budget, inv.stage_errors))
    inv.findings += extra_findings or []
    for f in inv.findings:
        prompt = {"web_search": web_search.PROMPT, "factcheck_sites": factcheck_sites.PROMPT,
                  "source_credibility": source_credibility.PROMPT,
                  "media_provenance": media_provenance.PROMPT}.get(f.agent)
        if prompt:
            inv.prompt_versions[f.agent] = load_prompt(prompt).version

    await set_stage(store, req.check_id, Stage.PACKAGING)
    changed = await timed("same_media", same_media.run(llm, extraction, inv.findings, budget.stage("same_media")))
    if changed:
        inv.prompt_versions["same_media"] = load_prompt(same_media.PROMPT).version
        log_event(log, "same media re-marked", ids=changed)
    inv.pack = await timed("packaging", packager.run(llm, req.check_id, extraction, inv.findings,
                                                     inv.missing_lanes, budget.stage("packager")))
    inv.prompt_versions["packager"] = load_prompt(packager.PROMPT).version

    await set_stage(store, req.check_id, Stage.JUDGING)
    inv.decisions = await timed("judging", run_panel(llm, claims, inv.pack, budget, inv))

    await set_stage(store, req.check_id, Stage.COMPOSING)

    async def answer(c: Claim) -> tuple[AnswerText, AnswerText]:
        d = inv.decisions[c.claim_id]
        try:
            out = await composer.compose(llm, c, d.verdict, d.outcome, inv.pack.evidence, d.split_readings,
                                         extraction.content_language, extraction.content_script)
            return out.native, out.english
        except StageFailed as e:
            log_event(log, "composer failed", logging.WARNING, reason=str(e)[:300])
            inv.stage_errors["composer"] = str(e)[:300]
            inv.degraded = True
            en = composer.fallback_answer(c, d.verdict, inv.pack.evidence, d.split_readings)
            return en, en

    pairs = await timed("composing", asyncio.gather(*(answer(c) for c in claims)))
    inv.answers = {c.claim_id: p for c, p in zip(claims, pairs, strict=True)}
    inv.prompt_versions["composer"] = load_prompt(composer.PROMPT).version
    return inv


def degraded_answers(claims: list[Claim], language: str) -> dict[str, tuple[PanelDecision, AnswerText, AnswerText]]:
    """Budget exhausted before the panel finished: NOT_ENOUGH_EVIDENCE in the content language."""
    out = {}
    for c in claims:
        v = _nee(c, "We could not finish checking this claim in time.")
        out[c.claim_id] = (PanelDecision(v, PanelOutcome.POLICY_DOWNGRADE, policy_reason="time budget exceeded"),
                           stub.stub_answer(c, v, language), stub.stub_answer(c, v, "en"))
    return out
