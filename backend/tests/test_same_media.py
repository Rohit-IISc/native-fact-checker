"""same_media: a second look turns "this very video is old" from CONTEXT into CONTRADICTS (case 01)."""
from app.agents import same_media
from app.llm import StageFailed
from app.models import AgentFindings, Extraction, SourceTier, Stance
from tests.helpers import ev


def extraction(claim_en="The video in this post shows heavy flooding in Bengaluru today.", ocr="DELHI संकट मे"):
    return Extraction.model_validate({
        "content_language": "kn-IN", "content_script": "Knda", "summary_en": "flood video", "checkable": True,
        "ocr_text": ocr, "claims": [{"claim_id": "c1", "claim_original": "x", "claim_en": claim_en,
                                     "claim_type": "EVENT", "time_sensitivity": "LIVE_EVENT"}]})


def findings():
    quint = ev("fc-1", SourceTier.TIER_1, "The Quint", stance=Stance.CONTEXT)
    blog = ev("ws-9", SourceTier.TIER_3, "A blog", stance=Stance.CONTEXT)
    news = ev("ws-1", SourceTier.TIER_2, "Hindustan Times", stance=Stance.CONTEXT)
    return [AgentFindings(agent="factcheck_sites", evidence=[quint]),
            AgentFindings(agent="web_search", evidence=[blog, news])]


class FakeLLM:
    def __init__(self, items=None, fail=False):
        self.items, self.fail, self.calls = items or [], fail, 0

    async def generate(self, *, schema, **_):
        self.calls += 1
        if self.fail:
            raise StageFailed("same_media", "timeout")
        return schema.model_validate({"items": self.items})


def test_only_credible_context_items_of_media_claims_are_candidates():
    c = same_media.candidates(extraction(), findings())
    assert [e.evidence_id for e in c["c1"]] == ["fc-1", "ws-1"]  # tier 3 blog left out
    assert same_media.candidates(extraction(claim_en="Bengaluru flooded today."), findings()) == {}
    assert same_media.candidates(extraction(ocr=None), findings()) == {}  # nothing known about the media


async def test_same_media_that_contradicts_becomes_contradicts():
    f = findings()
    llm = FakeLLM([{"evidence_id": "fc-1", "same_media": True, "contradicts": True},
                   {"evidence_id": "ws-1", "same_media": False, "contradicts": False}])
    assert await same_media.run(llm, extraction(), f, 8) == ["fc-1"]
    assert f[0].evidence[0].stance == Stance.CONTRADICTS and f[1].evidence[1].stance == Stance.CONTEXT


async def test_failure_or_no_candidates_changes_nothing():
    f = findings()
    assert await same_media.run(FakeLLM(fail=True), extraction(), f, 8) == []
    assert f[0].evidence[0].stance == Stance.CONTEXT
    llm = FakeLLM()
    assert await same_media.run(llm, extraction(claim_en="Bengaluru flooded today."), f, 8) == [] and llm.calls == 0
