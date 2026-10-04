"""Firebase ID token + App Check verification, and Pub/Sub OIDC verification for /internal/pipeline."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from app.observability.logging import hash_uid, uid_hash_var
from app.settings import get_config, get_settings

log = logging.getLogger(__name__)
_firebase_app = None


def _firebase():
    global _firebase_app
    if _firebase_app is None:
        import firebase_admin

        s = get_settings()
        opts = {"projectId": s.firebase_project_id} if s.firebase_project_id else None
        _firebase_app = firebase_admin.initialize_app(options=opts)
    return _firebase_app


@dataclass(frozen=True)
class User:
    uid: str
    email: str | None = None
    name: str | None = None

    @property
    def is_judge(self) -> bool:
        allow = {e.lower() for e in get_config().limits["quota"].get("judge_allowlist") or []}
        return bool(self.email and self.email.lower() in allow)


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, detail={"error_code": "UNAUTHENTICATED"})
    return authorization.split(" ", 1)[1].strip()


async def current_user(
    authorization: str | None = Header(default=None),
    x_firebase_appcheck: str | None = Header(default=None),
) -> User:
    token = _bearer(authorization)
    s = get_settings()
    if s.auth_mode == "dev":
        if not token.startswith("dev:"):
            raise HTTPException(401, detail={"error_code": "UNAUTHENTICATED"})
        uid = token[4:] or "dev-user"
        user = User(uid=uid, email=f"{uid}@dev.local", name=uid)
    else:
        from firebase_admin import app_check
        from firebase_admin import auth as fb_auth

        app = _firebase()
        try:
            claims = await asyncio.to_thread(fb_auth.verify_id_token, token, app)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(401, detail={"error_code": "UNAUTHENTICATED"}) from e
        if s.app_check_enforce:
            if not x_firebase_appcheck:
                raise HTTPException(403, detail={"error_code": "APP_CHECK_REQUIRED"})
            try:
                await asyncio.to_thread(app_check.verify_token, x_firebase_appcheck, app)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(403, detail={"error_code": "APP_CHECK_FAILED"}) from e
        user = User(uid=claims["uid"], email=claims.get("email"), name=claims.get("name"))
    uid_hash_var.set(hash_uid(user.uid))
    return user


async def verify_pubsub_push(request: Request) -> None:
    """Accept only Pub/Sub push requests signed by the push service account."""
    s = get_settings()
    if s.auth_mode == "dev":
        return
    token = _bearer(request.headers.get("authorization"))
    from google.auth.transport import requests as ga_requests
    from google.oauth2 import id_token

    audience = str(request.url).split("?", 1)[0]
    # Cloud Run terminates TLS; the push audience is the https URL.
    audience = audience.replace("http://", "https://", 1)
    try:
        claims = await asyncio.to_thread(id_token.verify_oauth2_token, token, ga_requests.Request(), audience)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(401, detail={"error_code": "BAD_PUSH_TOKEN"}) from e
    if s.push_sa and claims.get("email") != s.push_sa:
        raise HTTPException(403, detail={"error_code": "BAD_PUSH_SA"})
