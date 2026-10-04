"""config/messages.yaml: every demo language has every key, and answers follow the content language."""
from app.devtools import harness
from app.pipeline import stub
from app.settings import get_config
from app.store import MemoryStore


def _keys(d: dict, prefix: str = "") -> set[str]:
    out = set()
    for k, v in d.items():
        out |= _keys(v, f"{prefix}{k}.") if isinstance(v, dict) else {f"{prefix}{k}"}
    return out


def test_every_demo_language_has_every_message():
    msgs = get_config().messages
    want = _keys(msgs["en"])
    for lang in get_config().languages["demo_languages"]:
        assert lang in msgs, f"messages.yaml has no {lang}"
        assert _keys(msgs[lang]) == want, f"{lang}: missing {want - _keys(msgs[lang])}"


def test_unknown_language_falls_back_to_english():
    assert stub.non_checkable_message("JOKE", "fr-FR") == get_config().messages["en"]["non_checkable"]["JOKE"]


async def test_hindi_post_gets_hindi_answer(llm):
    req, _, _ = await harness.build_request("सरकार सभी को मुफ्त लैपटॉप दे रही है।")
    run, _ = await harness.run(req, store=MemoryStore(), llm=llm)
    hi = get_config().messages["hi"]["stub"]
    claim = run.result.claims[0]
    assert claim.answer.language == "hi-IN"
    assert claim.answer.headline == hi["headline"] and claim.answer.what_is_true == hi["what_is_true"]
    assert claim.answer_en.headline == get_config().messages["en"]["stub"]["headline"]
