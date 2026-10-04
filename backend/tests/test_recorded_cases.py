"""Replay recorded model outputs (tests/fixtures/{case}/, written by `make record`) through the
real pipeline. Free and fast; catches pipeline regressions on real-shaped model output."""
import pytest

from app.devtools import harness
from app.devtools.accept import load_cases, same_language
from app.devtools.recording import load_fixtures, recorded_cases, replay_llm
from app.prompts import load_prompt
from app.store import MemoryStore

PROMPT_FILES = {"extractor": "01_extractor.md"}
CASES = {c.id: c for c in load_cases()}
RECORDED = [cid for cid in recorded_cases() if cid in CASES]


@pytest.mark.parametrize("case_id", RECORDED)
async def test_recorded_case_replays(case_id):
    case = CASES[case_id]
    req, _, _ = harness.build_request(case.input.get("text"), None, case.input.get("url"))
    run, _ = await harness.run(req, store=MemoryStore(), llm=replay_llm(case_id))
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
