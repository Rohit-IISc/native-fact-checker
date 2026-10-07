"""Assign source tiers to URLs from config/source_tiers.yaml. Code assigns tiers, never the model."""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from app.models import SourceTier
from app.settings import get_config

_TIER_KEYS = [
    ("not_a_source", SourceTier.NOT_A_SOURCE),
    ("tier_1", SourceTier.TIER_1),
    ("tier_2", SourceTier.TIER_2),
]


def host_of(url_or_domain: str) -> str:
    s = url_or_domain.strip().lower()
    if "://" not in s:
        s = "http://" + s
    host = urlsplit(s).hostname or ""
    return host[4:] if host.startswith("www.") else host


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


@lru_cache
def _rules() -> list[tuple[SourceTier, list[str], list[str]]]:
    cfg = get_config().source_tiers
    out = []
    for key, tier in _TIER_KEYS:
        section = cfg.get(key) or {}
        out.append((tier, [d.lower() for d in section.get("domains") or []],
                    [s.lower() for s in section.get("suffixes") or []]))
    return out


def tier_for_url(url: str | None, domain: str | None = None) -> SourceTier:
    """Most specific rule wins: path-prefixed entries (site.com/fact-check) beat bare domains.

    NOT_A_SOURCE is checked first for bare domains, so youtube.com is never upgraded by a suffix.
    """
    if not url and not domain:
        return SourceTier.NOT_A_SOURCE
    raw = url or domain or ""
    host = host_of(raw)
    if not host:
        return SourceTier.NOT_A_SOURCE
    path = urlsplit(raw if "://" in raw else "http://" + raw).path.lower().rstrip("/")

    best: tuple[int, SourceTier] | None = None
    for tier, domains, suffixes in _rules():
        for entry in domains:
            entry_host, _, entry_path = entry.partition("/")
            if not _host_matches(host, entry_host):
                continue
            if entry_path.endswith("*"):
                # "dw.com/en/fact-check*" also matches /en/fact-check-some-story/a-123 (no section folder).
                if not path.startswith("/" + entry_path[:-1]):
                    continue
            elif entry_path:
                prefix = "/" + entry_path.rstrip("/")
                if not (path == prefix or path.startswith(prefix + "/")):
                    continue
            # Specificity: path entries > longer domains. NOT_A_SOURCE wins ties.
            score = (1000 if entry_path else 0) + len(entry_host)
            if best is None or score > best[0]:
                best = (score, tier)
        for suf in suffixes:
            if host.endswith(suf):
                score = len(suf)
                if best is None or score > best[0]:
                    best = (score, tier)
    if best:
        return best[1]
    default = get_config().source_tiers.get("default_tier", "tier_3")
    return {"tier_1": SourceTier.TIER_1, "tier_2": SourceTier.TIER_2}.get(default, SourceTier.TIER_3)
