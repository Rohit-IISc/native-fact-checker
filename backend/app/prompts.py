"""Prompt loader. Prompts live in prompts/*.md, each starting with a `version:` header.

The shared rules (00_shared_rules.md) are prepended to every prompt. `{{name}}`
placeholders are filled by code. Values are escaped so user content cannot close
the <user_content>/<evidence> data blocks it is placed in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from app.settings import get_settings

SHARED = "00_shared_rules.md"
_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
_DATA_TAGS = re.compile(r"</?\s*(user_content|fetched_page|evidence|tool_result)\s*>", re.IGNORECASE)
_HEADER_KEY = re.compile(r"^([a-z_]+):\s*(.*)$")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    body: str
    meta: dict[str, str]

    def render(self, **values: object) -> str:
        # Models' training ends before the dates they now read; without today's date they called real
        # 2026 fact checks "impossible future dates" (Oct 7). Every prompt gets it via the shared rules.
        values.setdefault("today", date.today().isoformat())
        missing = set(_PLACEHOLDER.findall(self.body)) - set(values)
        if missing:
            raise KeyError(f"Prompt {self.name} missing values: {sorted(missing)}")

        def sub(m: re.Match[str]) -> str:
            return escape_data(str(values[m.group(1)]))

        return _PLACEHOLDER.sub(sub, self.body)


def escape_data(value: str) -> str:
    """Neutralise data-block tags inside user-supplied values."""
    return _DATA_TAGS.sub(lambda m: m.group(0).replace("<", "&lt;").replace(">", "&gt;"), value)


def _parse(name: str, text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    meta: dict[str, str] = {}
    i = 0
    while i < len(lines) and (m := _HEADER_KEY.match(lines[i].strip())):
        meta[m.group(1)] = m.group(2).strip()
        i += 1
    if "version" not in meta:
        raise ValueError(f"Prompt {name} has no version header")
    return meta, "\n".join(lines[i:]).strip()


@lru_cache
def load_prompt(name: str, *, section: str | None = None) -> Prompt:
    """Load prompts/{name}. `section="translate"` returns the TRANSLATE MODE part of the composer."""
    d = get_settings().prompts_dir
    meta, body = _parse(name, (d / name).read_text(encoding="utf-8"))
    parts = re.split(r"^---\s*$", body, flags=re.MULTILINE)
    if section == "translate":
        if len(parts) < 2:
            raise ValueError(f"Prompt {name} has no translate section")
        body = parts[1].strip()
    else:
        body = parts[0].strip()
    shared_meta, shared_body = _parse(SHARED, (d / SHARED).read_text(encoding="utf-8"))
    version = f"{meta['version']}+{shared_meta['version']}"
    return Prompt(name=name, version=version, body=f"{shared_body}\n\n{body}", meta=meta)


@lru_cache
def load_block(name: str) -> Prompt:
    """Load a prompt fragment (no shared rules), e.g. the judge revision block."""
    meta, body = _parse(name, (get_settings().prompts_dir / name).read_text(encoding="utf-8"))
    return Prompt(name=name, version=meta["version"], body=body, meta=meta)
