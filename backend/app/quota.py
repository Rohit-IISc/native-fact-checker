"""Per-user daily quota (IST day) and the global circuit breaker on new investigations.

Usage docs: usage/{uid}_{YYYYMMDD} and usage/_global_{YYYYMMDD}. Cache hits count for users.
Failed checks, link-fetch failures and background retries are refunded.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.auth import User
from app.settings import get_config
from app.store import Store

USAGE = "usage"


def _tz() -> ZoneInfo:
    return ZoneInfo(get_config().limits["quota"].get("day_boundary_tz", "Asia/Kolkata"))


def day_key(now: datetime | None = None) -> str:
    now = now or datetime.now(_tz())
    return now.astimezone(_tz()).strftime("%Y%m%d")


def local_date(now: datetime | None = None) -> date:
    """The share date in the quota timezone (IST); the extractor resolves "today" with it."""
    return (now or datetime.now(_tz())).astimezone(_tz()).date()


def resets_at(now: datetime | None = None) -> datetime:
    now = (now or datetime.now(_tz())).astimezone(_tz())
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def user_limit(user: User) -> int:
    q = get_config().limits["quota"]
    return int(q["judge_checks_per_day"] if user.is_judge else q["checks_per_user_per_day"])


def usage_doc_id(uid: str, now: datetime | None = None) -> str:
    return f"{uid}_{day_key(now)}"


@dataclass
class QuotaStatus:
    used: int
    limit: int
    resets_at: datetime

    def as_dict(self) -> dict:
        return {"used": self.used, "limit": self.limit, "resets_at": self.resets_at.isoformat()}


async def get_quota(store: Store, user: User, now: datetime | None = None) -> QuotaStatus:
    doc = await store.get(USAGE, usage_doc_id(user.uid, now)) or {}
    return QuotaStatus(int(doc.get("count", 0)), user_limit(user), resets_at(now))


async def consume(store: Store, user: User, now: datetime | None = None) -> tuple[bool, QuotaStatus]:
    limit = user_limit(user)
    allowed, count = await store.increment_if_below(USAGE, usage_doc_id(user.uid, now), limit)
    return allowed, QuotaStatus(count, limit, resets_at(now))


async def refund(store: Store, uid: str, now: datetime | None = None) -> None:
    await store.decrement(USAGE, usage_doc_id(uid, now))


async def consume_global(store: Store, now: datetime | None = None) -> bool:
    """Circuit breaker: total full investigations per day across all users."""
    cap = int(get_config().limits["global_daily_new_checks"])
    allowed, _ = await store.increment_if_below(USAGE, f"_global_{day_key(now)}", cap)
    return allowed
