"""Push "Result ready: {label}" when a check is DONE (docs/02, docs/07), with Firebase Cloud Messaging.

Always sent on DONE; the service worker (frontend/src/sw.ts) skips the notification when that check is
already on screen. Data-only web push so the service worker decides; title in the UI language, body the
headline in the answer language. Tokens FCM reports as dead are removed from users/{uid}.fcm_tokens.
Push is a courtesy: it never fails or slows a check (deadline from config/limits.yaml).
"""
from __future__ import annotations

import asyncio
import logging

from app.models import CheckResult
from app.observability.logging import log_event
from app.settings import get_config, get_settings
from app.store import Store

log = logging.getLogger(__name__)
USERS = "users"


def _lang(language: str | None) -> dict:
    langs = get_config().languages.get("demo_languages") or {}
    return langs.get((language or "en").split("-")[0].lower()) or langs.get("en") or {}


def message_text(result: CheckResult, ui_language: str | None) -> tuple[str, str]:
    """(title, body). Claims are already ordered most harmful first, so the first label is the headline."""
    cfg = _lang(ui_language)
    title = cfg.get("push_title", "Result ready")
    if result.claims:
        c = result.claims[0]
        label = ((cfg.get("card") or {}).get("labels") or {}).get(c.label.value) or c.label.value
        return f"{title}: {label}", c.answer.headline
    return title, result.non_checkable_message or ""


def enabled() -> bool:
    """Only against real Firebase (not dev auth, the memory store or tests)."""
    s = get_settings()
    return s.auth_mode == "firebase" and s.store == "firestore"


def _send(tokens: list[str], check_id: str, title: str, body: str) -> list[str]:
    """Blocking FCM send; returns the tokens FCM says are gone."""
    from firebase_admin import messaging

    from app.auth import _firebase

    msgs = [messaging.Message(
        token=t,
        data={"check_id": check_id, "title": title, "body": body[:200]},
        webpush=messaging.WebpushConfig(headers={"Urgency": "high", "TTL": "3600"}),
    ) for t in tokens]
    resp = messaging.send_each(msgs, app=_firebase())
    dead = []
    for t, r in zip(tokens, resp.responses, strict=True):
        if not r.success and isinstance(r.exception, (messaging.UnregisteredError, messaging.SenderIdMismatchError)):
            dead.append(t)
        elif not r.success:
            log_event(log, "push failed", logging.WARNING, reason=f"{type(r.exception).__name__}: {r.exception}"[:200])
    return dead


async def result_ready(store: Store, uid: str, check_id: str, result: CheckResult, ui_language: str | None,
                       *, send=None) -> int:
    """Push to the user's devices. Returns how many tokens it went to. `send` is for tests."""
    if send is None and not enabled():
        return 0
    try:
        user = await store.get(USERS, uid) or {}
        tokens = list(dict.fromkeys(user.get("fcm_tokens") or []))
        if not tokens:
            return 0
        title, body = message_text(result, ui_language)
        dead = await asyncio.wait_for(asyncio.to_thread(send or _send, tokens, check_id, title, body),
                                      get_config().timeout("push"))
        if dead:
            await store.set(USERS, uid, {"fcm_tokens": [t for t in tokens if t not in dead]}, merge=True)
        return len(tokens) - len(dead)
    except Exception as e:  # noqa: BLE001  never let a notification break a finished check
        log_event(log, "push failed", logging.WARNING, reason=f"{type(e).__name__}: {e}"[:200])
        return 0
