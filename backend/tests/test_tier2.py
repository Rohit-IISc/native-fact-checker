"""Tier 2 cache (docs/04): semantic match after extraction, near-match decision, translation on reuse."""
from app.devtools import harness
from app.fixtures import demo_fixtures
from app.llm import FakeLLM
from app.models import Claim, ClaimType, Extraction, TimeSensitivity
from app.pipeline.results import VERDICTS
from app.store import MemoryStore


def extraction(claim_en: str, lang: str = "en-IN", script: str = "Latn", original: str | None = None) -> Extraction:
    return Extraction(content_language=lang, content_script=script, summary_en="s", checkable=True, claims=[Claim(
        claim_id="c1", claim_original=original or claim_en, claim_en=claim_en, claim_type=ClaimType.HEALTH,
        time_sensitivity=TimeSensitivity.EVERGREEN)])


def llm_with(extractions: list[Extraction], near_match: str | None = None, translated: dict | None = None):
    fx = demo_fixtures()
    queue = iter(extractions)
    fx["extractor"] = lambda _p: next(queue)
    if near_match:
        fx["near_match"] = {"decision": near_match, "reason": "test"}
    if translated:
        base = fx["composer"]
        fx["composer"] = lambda p: translated if "TRANSLATE MODE" in p or "English AnswerText" in p else base(p)
    return FakeLLM(fx)


async def check(store, llm, text):
    req, keys, _ = await harness.build_request(text)
    run, _ = await harness.run(req, store=store, llm=llm, cache_keys=keys)
    return run


CLAIM = "Drinking hot water with lemon kills the coronavirus"
REWORDED = "Drinking hot lemon water kills the coronavirus"


async def test_reworded_claim_reuses_the_verdict_without_new_searches():
    store = MemoryStore()
    llm = llm_with([extraction(CLAIM), extraction(REWORDED)], near_match="SAME")
    first = await check(store, llm, "first post")
    vid = first.result.claims[0].verdict_id
    assert len(store.data["claims"]) == 1 and "embedding" in next(iter(store.data["claims"].values()))
    searches = len(llm.prompts.get("web_search", []))

    second = await check(store, llm, "second post, different words")
    assert second.result.cache_tier_hit == "T2" and second.result.claims[0].verdict_id == vid
    assert len(llm.prompts.get("web_search", [])) == searches  # no fan-out for the cached claim
    assert len(llm.prompts["near_match"]) == 1


async def test_different_claim_runs_the_full_pipeline():
    store = MemoryStore()
    llm = llm_with([extraction(CLAIM), extraction(REWORDED)], near_match="DIFFERENT")
    await check(store, llm, "first post")
    second = await check(store, llm, "second post")
    assert second.result.cache_tier_hit == "NONE"
    assert len(llm.prompts["web_search"]) == 2


async def test_unrelated_claim_is_not_even_a_candidate():
    store = MemoryStore()
    llm = llm_with([extraction(CLAIM), extraction("The Reserve Bank raised the repo rate to 7 percent")],
                   near_match="SAME")
    await check(store, llm, "first post")
    second = await check(store, llm, "second post")
    assert second.result.cache_tier_hit == "NONE" and "near_match" not in llm.prompts


async def test_same_claim_different_date_adds_context_for_the_judge():
    store = MemoryStore()
    llm = llm_with([extraction(CLAIM), extraction(REWORDED)], near_match="SAME_CLAIM_DIFFERENT_DATE")
    await check(store, llm, "first post")
    second = await check(store, llm, "second post")
    assert second.result.cache_tier_hit == "NONE"
    assert "Previously checked on" in llm.prompts["judge"][-1]  # the archived verdict reached the judge


async def test_cached_verdict_is_translated_once_into_the_new_language():
    store = MemoryStore()
    tamil = {"language": "ta", "headline": "உறுதிசெய்யப்படவில்லை", "summary": "சுருக்கம் இங்கே உள்ளது",
             "what_post_claims": "கூற்று", "what_is_true": "உண்மை என்ன", "evidence_for": [], "evidence_against": [],
             "confidence_phrase": "உறுதியாகத் தெரியவில்லை", "sources_spoken": "", "audio_script": "ஒலி",
             "card_lines": ["அட்டை"]}
    llm = llm_with([extraction(CLAIM), extraction(REWORDED, "ta-IN", "Taml", "எலுமிச்சை")], near_match="SAME",
                   translated=tamil)
    first = await check(store, llm, "first post")
    second = await check(store, llm, "இரண்டாவது")
    claim = second.result.claims[0]
    assert claim.answer.language == "ta-IN" and claim.answer.headline == "உறுதிசெய்யப்படவில்லை"
    stored = await store.get(VERDICTS, first.result.claims[0].verdict_id)
    assert "ta-IN" in stored["answers"] and "en" in stored["answers"]


async def test_vector_search_failure_never_fails_the_check():
    class Broken(MemoryStore):
        async def find_nearest(self, *a, **k):
            raise RuntimeError("index missing")

    store = Broken()
    llm = llm_with([extraction(CLAIM)])
    run = await check(store, llm, "post")
    assert run.result.status == "DONE" and run.result.cache_tier_hit == "NONE"
