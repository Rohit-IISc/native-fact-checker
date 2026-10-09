"""Push on DONE: localized title, headline body, dead tokens dropped, failures never break a check."""
from app.models import CheckResult, Label
from app.output import notify
from app.store import MemoryStore
from tests.card_samples import sample_claim


def result(language="hi-IN", label=Label.FALSE) -> CheckResult:
    return CheckResult(check_id="chk", status="DONE", content_language=language,
                       claims=[sample_claim(language, label)])


def test_title_is_in_the_ui_language_and_body_is_the_answer_headline():
    r = result("hi-IN", Label.SCAM)
    title, body = notify.message_text(r, "kn")
    assert title == "ಫಲಿತಾಂಶ ಸಿದ್ಧವಾಗಿದೆ: ವಂಚನೆ"
    assert body == r.claims[0].answer.headline


def test_not_checkable_has_no_label():
    r = CheckResult(check_id="chk", status="DONE", non_checkable_message="Nothing to check here")
    assert notify.message_text(r, "en") == ("Result ready", "Nothing to check here")


async def test_sends_to_each_token_and_drops_dead_ones():
    store = MemoryStore()
    await store.set("users", "u1", {"fcm_tokens": ["a", "b", "a"]})
    sent = []

    def fake_send(tokens, check_id, title, body):
        sent.append((tokens, check_id, title))
        return ["b"]

    assert await notify.result_ready(store, "u1", "chk", result(), "en", send=fake_send) == 1
    assert sent == [(["a", "b"], "chk", "Result ready: False")]
    assert (await store.get("users", "u1"))["fcm_tokens"] == ["a"]


async def test_no_tokens_no_send():
    def boom(*a):
        raise AssertionError("must not send")

    assert await notify.result_ready(MemoryStore(), "nobody", "chk", result(), "en", send=boom) == 0


async def test_send_failure_is_swallowed():
    store = MemoryStore()
    await store.set("users", "u1", {"fcm_tokens": ["a"]})

    def broken(*a):
        raise RuntimeError("fcm down")

    assert await notify.result_ready(store, "u1", "chk", result(), "en", send=broken) == 0


async def test_off_without_real_firebase():
    assert not notify.enabled()  # tests run with dev auth and the memory store
