import math

from app.models import Evidence, Label, SourceTier, Stance
from app.verify import source_policy as sp
from tests.helpers import verdict

T1, T2, T3, NAS = SourceTier.TIER_1, SourceTier.TIER_2, SourceTier.TIER_3, SourceTier.NOT_A_SOURCE


def e(eid, tier, publisher, title, snippet="snippet", domain=None, rating=None, stance=Stance.CONTRADICTS,
      agent="web_search"):
    return Evidence(evidence_id=eid, agent=agent, claim_id="c1", publisher=publisher, title=title,
                    snippet_en=snippet, domain=domain, rating_text=rating, stance=stance, tier=tier)


async def score(label, for_ids, against, pack, claim_type="OTHER", claim_en="x", **kw):
    v = verdict(label, for_ids + against, for_ids=for_ids, against=against)
    return await sp.evidence_score(v, pack, claim_type=claim_type, claim_en=claim_en, **kw)


async def test_three_independent_tier1_contradictions_make_false():
    pack = [e("a", T1, "Reuters", "One"), e("b", T1, "AFP", "Two"), e("c", T1, "PIB", "Three")]
    s = await score(Label.FALSE, [], ["a", "b", "c"], pack)
    assert math.isclose(s.score, -9.0)
    assert s.score_label == Label.FALSE and len(s.groups_against) == 3
    assert sp.gate(Label.FALSE, s).action == "kept"


async def test_wire_copies_count_once_plus_extra():
    pack = [e("a", T1, "PTI", "Minister denies quote"), e("b", T2, "Times", "Minister denies quote"),
            e("c", T2, "Daily", "Other words", snippet="According to PTI, the minister denied it")]
    s = await score(Label.FALSE, [], ["a", "b", "c"], pack)
    assert len(s.groups_against) == 1
    assert math.isclose(s.score, -3.0 - 0.2 * 2)


async def test_factcheck_rating_false_weighs_more():
    pack = [e("f", T1, "BOOM", "Fact check", rating="False", agent="factcheck_sites")]
    s = await score(Label.FALSE, [], ["f"], pack)
    assert math.isclose(s.score, -3.5)


async def test_discounted_domain_adds_nothing_when_supporting():
    pack = [e("s", T2, "Unknown site", "Claim repeated", domain="new-news.xyz", stance=Stance.SUPPORTS)]
    s = await score(Label.TRUE, ["s"], [], pack, discounted_domains={"new-news.xyz"})
    assert s.score == 0 and not s.groups_for


async def test_single_tier2_cannot_carry_false_and_blocks():
    pack = [e("a", T2, "Some paper", "Denial")]
    s = await score(Label.FALSE, [], ["a"], pack)
    assert s.score_label == Label.NOT_ENOUGH_EVIDENCE
    d = sp.gate(Label.FALSE, s)
    assert d.action == "blocked" and d.label == Label.NOT_ENOUGH_EVIDENCE


async def test_high_harm_needs_more():
    pack = [e("a", T1, "WHO", "Myth"), e("b", T3, "Blog", "Myth too")]
    s = await score(Label.FALSE, [], ["a", "b"], pack, claim_type="HEALTH")
    # -3.7 -> p_true 0.024: passes 0.05 for high harm
    assert s.high_harm and s.cutoff == 0.95 and s.score_label == Label.FALSE
    one = await score(Label.FALSE, [], ["a"], pack[:1], claim_type="HEALTH")
    assert one.score_label == Label.FALSE  # -3.0 -> 0.047
    tier2 = await score(Label.FALSE, [], ["b"], [e("b", T2, "Paper", "x")], claim_type="HEALTH")
    assert tier2.score_label == Label.NOT_ENOUGH_EVIDENCE


async def test_event_harm_by_terms():
    assert sp.is_high_harm("EVENT", "Video shows floods in Delhi")
    assert not sp.is_high_harm("EVENT", "Singer opened a restaurant")


async def test_nee_with_strong_score_goes_to_critic_and_misleading_stays():
    pack = [e("a", T1, "Reuters", "One", stance=Stance.SUPPORTS), e("b", T1, "AP", "Two", stance=Stance.SUPPORTS)]
    s = await score(Label.NOT_ENOUGH_EVIDENCE, ["a", "b"], [], pack)
    d = sp.gate(Label.NOT_ENOUGH_EVIDENCE, s)
    assert d.action == "to_critic" and d.proposed == Label.TRUE and d.label == Label.NOT_ENOUGH_EVIDENCE
    assert sp.gate(Label.MISLEADING, s).action == "unchanged"


async def test_embedding_similarity_groups():
    pack = [e("a", T1, "Reuters", "Alpha"), e("b", T1, "AP", "Beta")]

    async def embed(texts):
        return [[1.0, 0.0] for _ in texts]

    s = await score(Label.FALSE, [], ["a", "b"], pack, embed=embed)
    assert len(s.groups_against) == 1 and math.isclose(s.score, -3.2)


async def test_for_verdict_display():
    pack = [e("a", T1, "Reuters", "One"), e("b", T1, "AFP", "Two")]
    s = await score(Label.FALSE, [], ["a", "b"], pack)
    pct, agree, against = s.for_verdict(Label.FALSE)
    assert pct == 99 and agree == 2 and against == 0
