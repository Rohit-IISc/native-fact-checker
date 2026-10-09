"""Composer guards: answers must be in the expected script; the fallback answer is honest English."""
import pytest

from app.agents import composer
from app.llm import FakeLLM, StageFailed
from app.models import AnswerText, Claim, ClaimType, JudgeVerdict, Label, PanelOutcome, TimeSensitivity


def answer(text: str, language: str = "en") -> AnswerText:
    return AnswerText(language=language, headline=text, summary=text, what_post_claims=text, what_is_true=text,
                      evidence_for=[], evidence_against=[], confidence_phrase="", sources_spoken="",
                      audio_script=text, card_lines=[text])


HINDI = "यह दावा गलत है क्योंकि भरोसेमंद स्रोतों ने इसका खंडन किया है"
ENGLISH = "This claim is false because trusted sources have denied it"
TAMIL = "இந்தக் கூற்று தவறானது என்று நம்பகமான ஆதாரங்கள் கூறுகின்றன"

CLAIM = Claim(claim_id="c1", claim_original="x", claim_en="x", claim_type=ClaimType.OTHER,
              time_sensitivity=TimeSensitivity.EVERGREEN)
VERDICT = JudgeVerdict(claim_id="c1", label=Label.FALSE, confidence=90, what_is_true_en="y", evidence_for_ids=[],
                       evidence_against_ids=[], cited_ids=[], reasoning_en="z")


@pytest.mark.parametrize("text,script,ok", [
    (ENGLISH, "Latn", True), (HINDI, "Latn", False), (HINDI, "Deva", True), (ENGLISH, "Deva", False),
    (TAMIL, "Taml", True), (HINDI, "Taml", False), (f"{HINDI} (Reuters, PIB)", "Deva", True),
])
def test_script_matches(text, script, ok):
    assert composer.script_matches(answer(text), script) is ok


async def test_wrong_script_is_retried_then_accepted():
    outputs = iter([answer(HINDI), answer(ENGLISH)])
    llm = FakeLLM({"composer": lambda _p: next(outputs)})
    out = await composer.compose(llm, CLAIM, VERDICT, PanelOutcome.AGREED, [], None, "en-IN", "Latn")
    assert out.native.headline == ENGLISH and len(llm.prompts["composer"]) == 2
    assert "not written in English" in llm.prompts["composer"][1]
    assert "(en, script Latn)" in llm.prompts["composer"][0]  # never "en-IN" in the prompt


async def test_wrong_script_twice_fails_the_stage():
    llm = FakeLLM({"composer": lambda _p: answer(HINDI)})
    with pytest.raises(StageFailed):
        await composer.compose(llm, CLAIM, VERDICT, PanelOutcome.AGREED, [], None, "en-IN", "Latn")


async def test_native_and_english_are_written_separately_for_indic_posts():
    llm = FakeLLM({"composer": lambda p: answer(ENGLISH if "English (en" in p else HINDI)})
    out = await composer.compose(llm, CLAIM, VERDICT, PanelOutcome.AGREED, [], None, "hi-IN", "Deva")
    assert out.native.language == "hi-IN" and out.native.headline == HINDI
    assert out.english.language == "en" and out.english.headline == ENGLISH


async def test_split_readings_reach_the_stored_result():
    from app.models import Claim as _C
    from app.pipeline.results import VERDICTS, claim_result_from_doc, persist_verdict
    from app.store import MemoryStore

    store = MemoryStore()
    nee = VERDICT.model_copy(update={"label": Label.NOT_ENOUGH_EVIDENCE, "confidence": 40})
    readings = ["One reviewer: MISLEADING, The Hindu shows the video from 2022.",
                "The other reviewer: TRUE, Deccan Herald reports flooding today."]
    native = answer(HINDI, "hi-IN").model_copy(update={"panel_readings": ["पहला", "दूसरा"]})
    english = composer.fallback_answer(CLAIM, nee, [], readings)
    assert english.panel_readings == readings
    vid = await persist_verdict(store, check_id="c", claim=_C.model_validate(CLAIM.model_dump()), verdict=nee,
                                outcome=PanelOutcome.SPLIT, evidence=[], answer=native, answer_en=english,
                                prompt_versions={}, model_versions={}, split_readings=readings)
    result = claim_result_from_doc(await store.get(VERDICTS, vid), "hi-IN")
    assert result.panel_outcome == PanelOutcome.SPLIT and result.answer.panel_readings == ["पहला", "दूसरा"]


def test_verdict_word_is_the_word_the_app_shows():
    from app.agents.composer import verdict_word

    assert verdict_word("MISLEADING", "hi") == "भ्रामक"
    assert verdict_word("FALSE", "kn") == "ಸುಳ್ಳು"
    assert verdict_word("MISLEADING", "en") == "Misleading"
    assert verdict_word("SCAM", "te") == "Scam"  # other languages: the English word
