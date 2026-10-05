import pytest

from app.models import CriticReview, Label, PanelOutcome, SourceTier
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
