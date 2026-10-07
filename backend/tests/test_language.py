"""Caption language decides the answer language on cache hits (acceptance case 3)."""
import pytest

from app.intake.language import caption_language


@pytest.mark.parametrize("caption,lang", [
    ("ಇಂದು ಬೆಂಗಳೂರಿನಲ್ಲಿ ಭಾರೀ ಪ್ರವಾಹ", "kn-IN"),
    ("दिल्ली में आज भारी बाढ़", "hi-IN"),
    ("இன்று சென்னையில் வெள்ளம்", "ta-IN"),
    ("Banjir besar di Jakarta hari ini, sudah sampai ke rumah", "id-ID"),
    ("Heavy floods in Mumbai today", "en-IN"),
    ("दिल्ली में बाढ़ https://x.com/a/status/1 🙏", "hi-IN"),
])
def test_caption_language(caption, lang):
    assert caption_language(caption)[0] == lang


@pytest.mark.parametrize("caption", [None, "", "🙏🙏🙏", "https://x.com/a/status/1", "!!"])
def test_no_words_means_no_caption_language(caption):
    assert caption_language(caption) is None


async def test_tier1_hit_with_a_new_caption_language_is_translated_once(store, llm):
    """The same video, re-shared with a Hindi caption after a Kannada check, answers in Hindi."""
    from app.models import AnswerText, Claim, ClaimType, JudgeVerdict, Label, PanelOutcome, TimeSensitivity
    from app.pipeline import reuse
    from app.pipeline.results import VERDICTS, persist_verdict

    def answer(text, lang):
        return AnswerText(language=lang, headline=text, summary=text, what_post_claims=text, what_is_true=text,
                          evidence_for=[], evidence_against=[], confidence_phrase="", sources_spoken="",
                          audio_script=text, card_lines=[text])

    claim = Claim(claim_id="c1", claim_original="ಪ್ರವಾಹ", claim_en="Floods in Bengaluru today",
                  claim_type=ClaimType.EVENT, time_sensitivity=TimeSensitivity.LIVE_EVENT)
    v = JudgeVerdict(claim_id="c1", label=Label.MISLEADING, confidence=90, what_is_true_en="Old video from 2022",
                     evidence_for_ids=[], evidence_against_ids=[], cited_ids=[], reasoning_en="x")
    vid = await persist_verdict(store, check_id="c0", claim=claim, verdict=v, outcome=PanelOutcome.AGREED,
                                evidence=[], answer=answer("ತಪ್ಪುದಾರಿಗೆಳೆಯುವ", "kn-IN"),
                                answer_en=answer("Misleading", "en"), prompt_versions={}, model_versions={})
    hindi = answer("भ्रामक: यह वीडियो 2022 का बेंगलुरु का है", "hi")
    llm.fixtures["composer"] = lambda _p: hindi
    hit = {"key": "sha256:x", "verdicts": [await store.get(VERDICTS, vid)], "non_checkable": None}

    result = await reuse.tier1_answer(store, llm, "c1", hit, "दिल्ली में आज भारी बाढ़")
    assert result.content_language == "hi-IN" and result.claims[0].answer.language == "hi-IN"
    assert result.claims[0].answer.headline.startswith("भ्रामक") and result.cache_tier_hit == "T1"
    stored = await store.get(VERDICTS, vid)
    assert "hi-IN" in stored["answers"] and "kn-IN" in stored["answers"]

    calls = len(llm.prompts["composer"])
    again = await reuse.tier1_answer(store, llm, "c2", {**hit, "verdicts": [stored]}, "दिल्ली में बाढ़")
    assert again.claims[0].answer.language == "hi-IN" and len(llm.prompts["composer"]) == calls  # stored, not redone

    same = await reuse.tier1_answer(store, llm, "c3", {**hit, "verdicts": [stored]}, "ಬೆಂಗಳೂರು ಪ್ರವಾಹ")
    assert same.claims[0].answer.language == "kn-IN"


async def test_failed_translation_answers_in_the_cached_language(store, llm):
    """Never label the result Hindi while the text is still Kannada."""
    from app.llm import StageFailed
    from app.models import AnswerText, Claim, ClaimType, JudgeVerdict, Label, PanelOutcome, TimeSensitivity
    from app.pipeline import reuse
    from app.pipeline.results import VERDICTS, persist_verdict

    def answer(text, lang):
        return AnswerText(language=lang, headline=text, summary=text, what_post_claims=text, what_is_true=text,
                          evidence_for=[], evidence_against=[], confidence_phrase="", sources_spoken="",
                          audio_script=text, card_lines=[text])

    claim = Claim(claim_id="c1", claim_original="ಪ್ರವಾಹ", claim_en="Floods", claim_type=ClaimType.EVENT,
                  time_sensitivity=TimeSensitivity.LIVE_EVENT)
    v = JudgeVerdict(claim_id="c1", label=Label.MISLEADING, confidence=90, what_is_true_en="x",
                     evidence_for_ids=[], evidence_against_ids=[], cited_ids=[], reasoning_en="x")
    vid = await persist_verdict(store, check_id="c0", claim=claim, verdict=v, outcome=PanelOutcome.AGREED,
                                evidence=[], answer=answer("ತಪ್ಪುದಾರಿ", "kn-IN"), answer_en=answer("Misleading", "en"),
                                prompt_versions={}, model_versions={})
    llm.fixtures["composer"] = lambda _p: StageFailed("composer", "timeout")
    hit = {"key": "k", "verdicts": [await store.get(VERDICTS, vid)], "non_checkable": None}
    result = await reuse.tier1_answer(store, llm, "c1", hit, "दिल्ली में आज भारी बाढ़")
    assert result.content_language == "kn-IN" and result.claims[0].answer.language == "kn-IN"
