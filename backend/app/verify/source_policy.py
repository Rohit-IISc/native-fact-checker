"""Source policy (docs/09), enforced in code.

TRUE, FALSE, MISLEADING or SCAM need, among the cited evidence ids:
  - at least 1 TIER_1 source, or at least 2 TIER_2 sources from different publishers, and
  - no cited id with tier NOT_A_SOURCE used as support, and
  - every cited id present in the evidence pack, and
  - at least one cited item that confirms or contradicts the claim (SUPPORTS or CONTRADICTS): background
    alone (CONTEXT) cannot carry a verdict (decision 46: old crocodile sightings read as "real event,
    wrong date" gave MISLEADING at 90% for a new sighting, case 15).
Otherwise the label becomes NOT_ENOUGH_EVIDENCE and the reason is recorded.

Items from agent "media_itself" (neutral observations of the shared item, such as a satire tag) may be
cited to explain what the item is, but are ignored when counting: they never satisfy or fail the policy.
"""
from __future__ import annotations

import math
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.models import ClaimType, Evidence, JudgeVerdict, Label, SourceTier, Stance
from app.settings import get_config
from app.verify.source_tiers import host_of

DECISIVE = {Label.TRUE, Label.FALSE, Label.MISLEADING, Label.SCAM}


@dataclass(frozen=True)
class PolicyResult:
    passed: bool
    reason: str | None = None


def _publisher_key(ev: Evidence) -> str:
    if ev.publisher:
        return ev.publisher.strip().lower()
    return host_of(ev.domain or ev.url or "") or ev.evidence_id


def check(verdict: JudgeVerdict, evidence: list[Evidence]) -> PolicyResult:
    if verdict.label not in DECISIVE:
        return PolicyResult(True)
    by_id = {e.evidence_id: e for e in evidence}
    cited_all = set(verdict.cited_ids) | set(verdict.evidence_for_ids) | set(verdict.evidence_against_ids)
    unknown = sorted(i for i in cited_all if i not in by_id)
    if unknown:
        return PolicyResult(False, f"cited ids not in evidence pack: {', '.join(unknown)}")
    cited = [by_id[i] for i in verdict.cited_ids if by_id[i].agent != "media_itself"]
    if not cited:
        return PolicyResult(False, "no cited evidence")
    social = [e.evidence_id for e in cited if e.tier == SourceTier.NOT_A_SOURCE]
    if social:
        return PolicyResult(False, f"NOT_A_SOURCE evidence used as support: {', '.join(social)}")
    if all(e.stance == Stance.CONTEXT for e in cited):
        return PolicyResult(False, "only background (CONTEXT) evidence; nothing confirms or contradicts the claim")
    if any(e.tier == SourceTier.TIER_1 for e in cited):
        return PolicyResult(True)
    tier2_publishers = {_publisher_key(e) for e in cited if e.tier == SourceTier.TIER_2}
    if len(tier2_publishers) >= 2:
        return PolicyResult(True)
    return PolicyResult(False, "needs 1 TIER_1 or 2 TIER_2 sources from different publishers")


def apply(verdict: JudgeVerdict, evidence: list[Evidence]) -> tuple[JudgeVerdict, PolicyResult]:
    """Return the verdict, downgraded to NOT_ENOUGH_EVIDENCE if the policy fails."""
    result = check(verdict, evidence)
    if result.passed:
        return verdict, result
    known = {e.evidence_id for e in evidence}
    downgraded = verdict.model_copy(update={
        "label": Label.NOT_ENOUGH_EVIDENCE,
        "confidence": min(verdict.confidence, 50),
        "cited_ids": [i for i in verdict.cited_ids if i in known],
        "evidence_for_ids": [i for i in verdict.evidence_for_ids if i in known],
        "evidence_against_ids": [i for i in verdict.evidence_against_ids if i in known],
        "reasoning_en": f"{verdict.reasoning_en}\n[Source policy: {result.reason}]",
    })
    return downgraded, result


# ---------- Evidence score (decision 50; replay only until after judging) ----------
#
# A deterministic log-odds score over the evidence the Judge placed for and against the claim. The Judge
# still decides stance and same-claim matching (which items go in evidence_for_ids / evidence_against_ids)
# and MISLEADING / SCAM; the score can block a TRUE or FALSE, and can propose an upgrade from
# NOT_ENOUGH_EVIDENCE that only the Critic may accept. Weights: config/source_tiers.yaml evidence_score.



Embedder = Callable[[list[str]], Awaitable[list[list[float]]]]


@dataclass(frozen=True)
class ScoredItem:
    evidence_id: str
    direction: int        # +1 supports the claim, -1 contradicts it
    weight: float         # signed log-odds contribution before grouping
    why: str


@dataclass(frozen=True)
class EvidenceScore:
    score: float                      # log-odds that the claim is true
    p_true: float
    groups_for: list[list[str]]       # independent groups of evidence ids, strongest first
    groups_against: list[list[str]]
    items: list[ScoredItem]
    high_harm: bool
    cutoff: float

    @property
    def score_label(self) -> Label:
        if self.p_true >= self.cutoff:
            return Label.TRUE
        if self.p_true <= 1 - self.cutoff:
            return Label.FALSE
        return Label.NOT_ENOUGH_EVIDENCE

    def for_verdict(self, label: Label) -> tuple[int, int, int]:
        """(score out of 100 for the verdict, independent reports agreeing, independent reports against).
        Shown between 1 and 99: evidence never makes an answer certain."""
        def pct(p: float) -> int:
            return min(99, max(1, round(100 * p)))

        if label == Label.TRUE:
            return pct(self.p_true), len(self.groups_for), len(self.groups_against)
        if label in (Label.FALSE, Label.MISLEADING, Label.SCAM):
            return pct(1 - self.p_true), len(self.groups_against), len(self.groups_for)
        fors, againsts = len(self.groups_for), len(self.groups_against)
        return pct(max(self.p_true, 1 - self.p_true)), max(fors, againsts), min(fors, againsts)


def _cfg() -> dict:
    return get_config().source_tiers["evidence_score"]


def is_high_harm(claim_type: ClaimType | str | None, claim_en: str) -> bool:
    cfg = _cfg()
    ct = claim_type.value if isinstance(claim_type, ClaimType) else (claim_type or "")
    if ct in cfg["high_harm_claim_types"]:
        return True
    if ct == ClaimType.EVENT.value:
        text = claim_en.lower()
        return any(re.search(rf"\b{re.escape(t)}(s|es|ed|ing)?\b", text) for t in cfg["high_harm_event_terms"])
    return False


def _rating(text: str | None) -> int:
    """+1 a fact check rated the claim true, -1 rated it false (or misleading, altered...), 0 no rating."""
    if not text:
        return 0
    t = text.lower()
    cfg = _cfg()
    if any(re.search(rf"\b{re.escape(w)}\b", t) for w in cfg["factcheck_false_words"]):
        return -1
    if any(re.search(rf"\b{re.escape(w)}\b", t) for w in cfg["factcheck_true_words"]):
        return 1
    return 0


def item_weight(ev: Evidence, direction: int, discounted_domains: set[str]) -> ScoredItem:
    cfg = _cfg()
    table = cfg["support"] if direction > 0 else cfg["contradict"]
    w = float(table.get(ev.tier.value, 0.0))
    why = ev.tier.value
    rating = _rating(ev.rating_text)
    if direction > 0 and rating > 0 and ev.tier != SourceTier.NOT_A_SOURCE:
        w, why = max(w, float(table["factcheck_true"])), "fact check rated true"
    if direction < 0 and rating < 0 and ev.tier != SourceTier.NOT_A_SOURCE:
        w, why = min(w, float(table["factcheck_false"])), "fact check rated false"
    host = host_of(ev.domain or ev.url or "")
    if direction > 0 and host and host in discounted_domains:
        w, why = 0.0, "repeat offender or young domain"
    return ScoredItem(ev.evidence_id, direction, w, why)


def _norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()[:80]


def _cites(a: Evidence, b: Evidence) -> bool:
    """a names b's publisher or domain (e.g. a report 'according to PTI')."""
    text = f"{a.title or ''} {a.snippet_en}".lower()
    names = {n for n in ((b.publisher or "").lower().split("(")[0].strip(), host_of(b.domain or b.url or "")) if n}
    return any(len(n) >= 3 and re.search(rf"\b{re.escape(n)}\b", text) for n in names)


def _cosine(u: list[float], v: list[float]) -> float:
    dot = sum(x * y for x, y in zip(u, v, strict=False))
    nu, nv = math.sqrt(sum(x * x for x in u)), math.sqrt(sum(x * x for x in v))
    return dot / (nu * nv) if nu and nv else 0.0


async def group_same_origin(items: list[Evidence], embed: Embedder | None) -> list[list[Evidence]]:
    """Union of: same normalized title, embedding similarity above the threshold, one citing the other."""
    n = len(items)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    vecs: list[list[float]] | None = None
    if embed and n > 1:
        try:
            vecs = await embed([f"{e.title or ''}. {e.snippet_en}" for e in items])
        except Exception:  # noqa: BLE001  grouping falls back to titles and citations
            vecs = None
    threshold = float(_cfg()["same_origin_similarity"])
    for i in range(n):
        for j in range(i + 1, n):
            a, b = items[i], items[j]
            same_title = _norm_title(a.title) and _norm_title(a.title) == _norm_title(b.title)
            similar = vecs is not None and _cosine(vecs[i], vecs[j]) > threshold
            if same_title or similar or _cites(a, b) or _cites(b, a):
                union(i, j)
    groups: dict[int, list[Evidence]] = {}
    for i, e in enumerate(items):
        groups.setdefault(find(i), []).append(e)
    return list(groups.values())


async def evidence_score(verdict: JudgeVerdict, evidence: list[Evidence], *, claim_type: ClaimType | str | None,
                         claim_en: str, discounted_domains: set[str] | None = None,
                         embed: Embedder | None = None) -> EvidenceScore:
    cfg = _cfg()
    by_id = {e.evidence_id: e for e in evidence if e.agent != "media_itself"}
    discounted = discounted_domains or set()
    scored: dict[str, ScoredItem] = {}
    sides: dict[int, list[Evidence]] = {1: [], -1: []}
    for direction, ids in ((1, verdict.evidence_for_ids), (-1, verdict.evidence_against_ids)):
        for i in dict.fromkeys(ids):
            if i in by_id and i not in scored:
                scored[i] = item_weight(by_id[i], direction, discounted)
                sides[direction].append(by_id[i])
    extra = float(cfg["extra_in_group"])
    total = 0.0
    grouped: dict[int, list[list[str]]] = {1: [], -1: []}
    for direction, items in sides.items():
        for group in await group_same_origin(items, embed):
            weights = sorted((scored[e.evidence_id].weight for e in group), key=abs, reverse=True)
            if weights[0] == 0:
                continue  # nothing credible in this group (social posts, discounted domains)
            total += weights[0] + direction * extra * (len(group) - 1)
            grouped[direction].append([e.evidence_id for e in sorted(
                group, key=lambda e: abs(scored[e.evidence_id].weight), reverse=True)])
    high = is_high_harm(claim_type, claim_en)
    cutoff = float(cfg["cutoffs"]["high_harm" if high else "other"])
    p = 1 / (1 + math.exp(-total))
    return EvidenceScore(total, p, grouped[1], grouped[-1], list(scored.values()), high, cutoff)


@dataclass(frozen=True)
class ScoreDecision:
    label: Label            # what the verdict would become with gating on
    action: str             # kept, blocked, to_critic, unchanged
    proposed: Label | None = None


def gate(judge_label: Label, s: EvidenceScore) -> ScoreDecision:
    """The score can always block a TRUE or FALSE; it never decides MISLEADING or SCAM; an upgrade from
    NOT_ENOUGH_EVIDENCE goes to the Critic, which accepts it only if the cited items are about the same claim
    and independent."""
    proposed = s.score_label
    if judge_label in (Label.TRUE, Label.FALSE):
        if proposed != judge_label:
            return ScoreDecision(Label.NOT_ENOUGH_EVIDENCE, "blocked")
        return ScoreDecision(judge_label, "kept")
    if judge_label == Label.NOT_ENOUGH_EVIDENCE and proposed in (Label.TRUE, Label.FALSE):
        return ScoreDecision(Label.NOT_ENOUGH_EVIDENCE, "to_critic", proposed)
    return ScoreDecision(judge_label, "unchanged")
