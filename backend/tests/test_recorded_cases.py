"""Replay recorded model outputs (tests/fixtures/{case}/, written by `make record`) through the
real pipeline. Free and fast; catches pipeline regressions on real-shaped model output."""
import pytest

from app.agents.tools import ReplayTools
from app.devtools import harness
from app.devtools.accept import ROOT, load_cases, same_language
from app.devtools.recording import load_fixtures, load_tool_calls, recorded_cases, replay_llm
from app.intake import links
from app.models import FetchedPost
from app.prompts import load_prompt
from app.store import MemoryStore

PROMPT_FILES = {
    "extractor": "01_extractor.md", "web_search": "03_web_search_agent.md",
    "web_search_classify": "03b_web_search_classify.md", "factcheck_sites": "04_factcheck_agent.md",
    "source_credibility": "05_source_credibility_agent.md", "media_provenance": "06_media_provenance_agent.md",
    "packager": "07_packager.md", "judge": "08_judge.md", "critic": "09_critic.md", "composer": "10_composer.md",
}
CASES = {c.id: c for c in load_cases()}
RECORDED = [cid for cid in recorded_cases() if cid in CASES]


@pytest.mark.parametrize("case_id", RECORDED)
async def test_recorded_case_replays(case_id, monkeypatch):
    case = CASES[case_id]

    async def offline_fetch(url, **_):
        # make test stays offline; the extractor output is replayed, so the page text is not needed.
        return FetchedPost(source_url=url, platform="news", text="(recorded)", fetch_method="html")

    monkeypatch.setattr(links, "fetch", offline_fetch)
    file = case.input.get("file")
    req, _, _ = await harness.build_request(case.input.get("text"), file and str(ROOT / file), case.input.get("url"))
    store = MemoryStore()
    run, _ = await harness.run(req, store=store, llm=replay_llm(case_id),
                               tools=ReplayTools(store, load_tool_calls(case_id)))
    assert run.error is None
    assert run.result is not None and run.result.status == "DONE"
    assert same_language(run.language, case.language)
    if "NOT_CHECKABLE" in case.expected:
        assert run.label == "NOT_CHECKABLE"
    else:
        assert run.result.claims, "a checkable case must produce at least one claim"
        for c in run.result.claims:
            assert c.answer.language == run.result.content_language


@pytest.mark.parametrize("case_id", RECORDED)
def test_recorded_fixture_matches_current_prompt(case_id):
    for stage, rec in load_fixtures(case_id).items():
        if stage in PROMPT_FILES:
            current = load_prompt(PROMPT_FILES[stage]).version
            assert rec["prompt_version"] == current, (
                f"{case_id}/{stage}.json was recorded with {rec['prompt_version']}, prompt is now {current}: "
                "run `make record`"
            )
