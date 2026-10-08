"""packager.media_evidence: neutral observations of the shared item enter the pack, never as a source."""
from app.agents import packager
from app.models import AgentFindings, Extraction, SourceTier, Stance
from tests.helpers import ev


def extraction(markers: list[str]) -> Extraction:
    return Extraction.model_validate({
        "content_language": "hi-IN", "content_script": "Deva", "summary_en": "A newspaper page.",
        "checkable": True, "media_markers": markers,
        "claims": [{"claim_id": "c1", "claim_original": "x", "claim_en": "The newspaper page is real news",
                    "claim_type": "MEDIA_AUTHENTICITY", "time_sensitivity": "EVERGREEN"}],
    })


def test_markers_become_one_not_a_source_context_item_per_claim():
    items = packager.media_evidence(extraction(["Text at the top reads 'बुरा न मानो होली है'"]))
    assert len(items) == 1
    mi = items[0]
    assert (mi.evidence_id, mi.agent, mi.tier, mi.stance, mi.url) == (
        "mi-c1", "media_itself", SourceTier.NOT_A_SOURCE, Stance.CONTEXT, None)
    assert "बुरा न मानो होली है" in mi.snippet_en


def test_no_markers_no_item():
    assert packager.media_evidence(extraction(["  "])) == []


def test_media_item_survives_the_item_cap(monkeypatch):
    findings = [AgentFindings(agent="web_search", evidence=[ev(f"ws-{i}", SourceTier.TIER_2, f"P{i}")
                                                             for i in range(20)])]
    pack = packager.code_pack("chk", extraction(["Masthead dated 25 March 2024"]), findings, [])
    assert "mi-c1" in pack.briefs[0].evidence_ids
    assert any(e.evidence_id == "mi-c1" for e in pack.evidence)


def test_media_item_alone_still_reports_the_gap():
    pack = packager.code_pack("chk", extraction(["Masthead dated 25 March 2024"]), [], [])
    assert pack.briefs[0].gaps_en == ["No evidence was found for this claim."]
