from app.models import Label, SourceTier, Stance
from app.verify import source_policy
from tests.helpers import ev, verdict

T1, T2, T3, NAS = SourceTier.TIER_1, SourceTier.TIER_2, SourceTier.TIER_3, SourceTier.NOT_A_SOURCE


def test_one_tier1_passes():
    pack = [ev("ws-1", T1, "Reuters")]
    assert source_policy.check(verdict(Label.FALSE, ["ws-1"]), pack).passed


def test_two_tier2_different_publishers_pass():
    pack = [ev("ws-1", T2, "The Hindu"), ev("ws-2", T2, "NDTV")]
    assert source_policy.check(verdict(Label.TRUE, ["ws-1", "ws-2"]), pack).passed


def test_two_tier2_same_publisher_fails():
    pack = [ev("ws-1", T2, "NDTV"), ev("ws-2", T2, " ndtv ")]
    r = source_policy.check(verdict(Label.TRUE, ["ws-1", "ws-2"]), pack)
    assert not r.passed and "TIER_2" in r.reason


def test_tier2_publisher_falls_back_to_domain():
    pack = [ev("a", T2, url="https://www.ndtv.com/x"), ev("b", T2, url="https://ndtv.com/y")]
    assert not source_policy.check(verdict(Label.FALSE, ["a", "b"]), pack).passed


def test_tier3_only_fails():
    pack = [ev("ws-1", T3, "Blog"), ev("ws-2", T3, "Other")]
    assert not source_policy.check(verdict(Label.MISLEADING, ["ws-1", "ws-2"]), pack).passed


def test_social_media_as_support_fails_even_with_tier1():
    pack = [ev("ws-1", T1, "PIB"), ev("ws-2", NAS, "X")]
    r = source_policy.check(verdict(Label.FALSE, ["ws-1", "ws-2"]), pack)
    assert not r.passed and "NOT_A_SOURCE" in r.reason


def test_unknown_cited_id_fails():
    pack = [ev("ws-1", T1, "Reuters")]
    r = source_policy.check(verdict(Label.FALSE, ["ws-1", "ws-9"]), pack)
    assert not r.passed and "ws-9" in r.reason


def test_unknown_id_in_for_against_lists_fails():
    pack = [ev("ws-1", T1, "Reuters")]
    v = verdict(Label.FALSE, ["ws-1"], against=["ws-1", "fc-7"])
    assert not source_policy.check(v, pack).passed


def test_no_citations_fails():
    assert not source_policy.check(verdict(Label.SCAM, []), []).passed


def test_not_enough_evidence_always_passes():
    assert source_policy.check(verdict(Label.NOT_ENOUGH_EVIDENCE, []), []).passed


def test_apply_downgrades_and_records_reason():
    pack = [ev("ws-1", T3, "Blog")]
    v, r = source_policy.apply(verdict(Label.FALSE, ["ws-1", "zz"], confidence=95), pack)
    assert v.label == Label.NOT_ENOUGH_EVIDENCE
    assert v.confidence <= 50
    assert "zz" not in v.cited_ids and "ws-1" in v.cited_ids
    assert "Source policy" in v.reasoning_en and not r.passed


def media_item(eid: str = "mi-c1"):
    return ev(eid, NAS, "The shared item itself", stance=Stance.CONTEXT).model_copy(update={"agent": "media_itself"})


def test_media_observation_alongside_a_tier1_source_passes():
    pack = [ev("fc-1", T1, "BOOM"), media_item()]
    assert source_policy.check(verdict(Label.MISLEADING, ["fc-1", "mi-c1"]), pack).passed


def test_media_observation_alone_never_carries_a_verdict():
    r = source_policy.check(verdict(Label.MISLEADING, ["mi-c1"]), [media_item()])
    assert not r.passed and r.reason == "no cited evidence"


def test_media_observation_does_not_count_toward_two_tier2():
    pack = [ev("ws-1", T2, "NDTV"), media_item()]
    assert not source_policy.check(verdict(Label.MISLEADING, ["ws-1", "mi-c1"]), pack).passed
