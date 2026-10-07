import pytest

from app.models import CriticReview, Label, PanelOutcome, SourceTier, Stance
from app.pipeline import panel
from tests.helpers import ev, verdict

PACK = [ev("fc-1", SourceTier.TIER_1, "BOOM"), ev("ws-1", SourceTier.TIER_2, "NDTV", stance="SUPPORTS"),
        ev("ws-2", SourceTier.TIER_3, "Blog")]


def critic(decision, label, conf=80, objections=None):
    return CriticReview(claim_id="c1", decision=decision, proposed_label=label, proposed_confidence=conf,
                        objections_en=objections or [])


def test_agree_takes_min_confidence():
    d = panel.merge(verdict(Label.FALSE, ["fc-1"], 92), critic("AGREE", Label.FALSE, 80), PACK)
    assert d.outcome == PanelOutcome.AGREED
    assert d.verdict.label == Label.FALSE and d.verdict.confidence == 80


def test_policy_downgrade_is_final():
    d = panel.merge(verdict(Label.FALSE, ["ws-2"], 90), critic("AGREE", Label.FALSE), PACK)
    assert d.outcome == PanelOutcome.POLICY_DOWNGRADE
    assert d.verdict.label == Label.NOT_ENOUGH_EVIDENCE and d.policy_reason


def test_disagree_then_revision_matches_critic():
    judge = verdict(Label.FALSE, ["fc-1"], 90)
    revised = verdict(Label.MISLEADING, ["fc-1"], 85)
    d = panel.merge(judge, critic("DISAGREE", Label.MISLEADING, 75), PACK, revised=revised)
    assert d.outcome == PanelOutcome.AGREED_AFTER_REVISION
    assert d.verdict.label == Label.MISLEADING and d.verdict.confidence == 75


def test_disagree_and_revision_holds_gives_split_with_both_sides():
    judge = verdict(Label.FALSE, ["fc-1"], 90, against=["fc-1"], for_ids=[])
    revised = verdict(Label.FALSE, ["fc-1"], 88, against=["fc-1"], for_ids=["ws-1"])
    d = panel.merge(judge, critic("DISAGREE", Label.TRUE, 70, ["ws-1 supports it"]), PACK, revised=revised)
    assert d.outcome == PanelOutcome.SPLIT
    assert d.verdict.label == Label.NOT_ENOUGH_EVIDENCE
    assert d.verdict.confidence <= 50
    assert "ws-1" in d.verdict.evidence_for_ids and "fc-1" in d.verdict.evidence_against_ids
    assert len(d.split_readings) == 2


def test_revision_matching_critic_but_failing_policy_is_split():
    judge = verdict(Label.FALSE, ["fc-1"], 90)
    revised = verdict(Label.TRUE, ["ws-2"], 80, against=[], for_ids=["ws-2"])
    d = panel.merge(judge, critic("DISAGREE", Label.TRUE, 70), PACK, revised=revised)
    assert d.outcome == PanelOutcome.SPLIT and d.verdict.label == Label.NOT_ENOUGH_EVIDENCE


def test_agree_with_mismatched_label_is_treated_as_disagree():
    with pytest.raises(ValueError):
        panel.merge(verdict(Label.FALSE, ["fc-1"]), critic("AGREE", Label.MISLEADING), PACK)


def test_critic_missing_caps_confidence():
    d = panel.merge(verdict(Label.FALSE, ["fc-1"], 95), None, PACK)
    assert d.verdict.label == Label.FALSE and d.verdict.confidence == 84


def test_not_enough_evidence_never_shows_high_confidence():
    v = verdict(Label.NOT_ENOUGH_EVIDENCE, [], confidence=100, against=[])
    agree = CriticReview(claim_id="c1", decision="AGREE", proposed_label=Label.NOT_ENOUGH_EVIDENCE,
                         proposed_confidence=95)
    d = panel.merge(v, agree, evidence=[])
    assert d.verdict.label == Label.NOT_ENOUGH_EVIDENCE and d.verdict.confidence == 50


def test_stance_check_moves_items_to_the_side_their_stance_says():
    evidence = [ev("fc-1", SourceTier.TIER_1, "BOOM", stance=Stance.CONTRADICTS),
                ev("ws-1", SourceTier.TIER_1, "Reuters", stance=Stance.SUPPORTS)]
    v = verdict(Label.TRUE, ["ws-1"], for_ids=["fc-1", "ws-1"], against=[])
    out = panel.reconcile_stances(v, evidence)
    assert out.evidence_for_ids == ["ws-1"] and out.evidence_against_ids == ["fc-1"]
    assert "Stance check" in out.reasoning_en


def test_contradicting_item_cannot_carry_a_true_verdict():
    """The only TIER_1 source was classified as contradicting the claim: it cannot carry TRUE."""
    evidence = [ev("fc-1", SourceTier.TIER_1, "BOOM", stance=Stance.CONTRADICTS),
                ev("ws-1", SourceTier.TIER_3, "Blog", stance=Stance.SUPPORTS)]
    v = verdict(Label.TRUE, ["fc-1", "ws-1"], for_ids=["fc-1", "ws-1"], against=[])
    d = panel.merge(v, None, evidence)
    assert d.verdict.label == Label.NOT_ENOUGH_EVIDENCE and d.outcome == PanelOutcome.POLICY_DOWNGRADE


def test_context_can_back_misleading():
    """An old photo's real origin is CONTEXT evidence; it is exactly what makes the post MISLEADING."""
    evidence = [ev("mp-1", SourceTier.TIER_1, "AFP", stance=Stance.CONTEXT)]
    v = verdict(Label.MISLEADING, ["mp-1"], against=["mp-1"])
    d = panel.merge(v, None, evidence)
    assert d.verdict.label == Label.MISLEADING


def test_consistent_verdict_is_untouched():
    evidence = [ev("fc-1", SourceTier.TIER_1, "AFP", stance=Stance.CONTRADICTS)]
    v = verdict(Label.FALSE, ["fc-1"], against=["fc-1"])
    assert panel.reconcile_stances(v, evidence) is v


def test_ai_generation_survives_a_revision_that_omits_it():
    from app.models import AIGenerationAssessment

    evidence = [ev("ws-1", SourceTier.TIER_1, "BOOM", stance=Stance.CONTRADICTS)]
    ai = AIGenerationAssessment(likelihood_ai=90, signals_ai=["fact-checkers found it AI-made"], signals_real=[])
    judge = verdict(Label.FALSE, ["ws-1"]).model_copy(update={"ai_generation": ai})
    disagree = CriticReview(claim_id="c1", decision="DISAGREE", proposed_label=Label.MISLEADING,
                            proposed_confidence=80, objections_en=["x"])
    revised = verdict(Label.MISLEADING, ["ws-1"])
    d = panel.merge(judge, disagree, evidence, revised=revised)
    assert d.verdict.label == Label.MISLEADING and d.verdict.ai_generation == ai


def test_claims_are_ordered_most_harmful_first():
    from app.pipeline.runner import order_by_severity

    class C:
        def __init__(self, label):
            self.label = Label(label)

    got = [c.label.value for c in order_by_severity([C("TRUE"), C("FALSE"), C("NOT_ENOUGH_EVIDENCE"), C("SCAM")])]
    assert got == ["SCAM", "FALSE", "NOT_ENOUGH_EVIDENCE", "TRUE"]
