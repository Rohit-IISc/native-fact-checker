"""Correction card (docs/03 stage 8, decision 5): a 1080 x 1350 PNG drawn by code, forwardable to WhatsApp.

Verdict colour band with the label in the answer language, the post's claim (trimmed), what is true, the top
two source names and the result link. Pillow with libraqm shapes Devanagari, Tamil and Kannada; fonts are
Noto (fonts-noto-core in the Dockerfile; FONT_DIR overrides). No generated imagery.
Rendered on first request by GET /v1/results/{id}/card and kept in the outputs bucket.
Run as a script to look at one:  uv run python -m app.output.card --lang kn-IN --out card.png
"""
from __future__ import annotations

import argparse
import asyncio
import io
import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

from app.models import ClaimResult, Label, SourceTier
from app.settings import get_config, get_settings

W, H = 1080, 1350
MARGIN = 72
BAND_H = 300
COLORS = {  # same as frontend/src/styles.css
    Label.TRUE: "#1e7d34", Label.FALSE: "#c62828", Label.MISLEADING: "#c25e00",
    Label.SCAM: "#6a1b9a", Label.NOT_ENOUGH_EVIDENCE: "#5f6368",
}
INK, MUTED, RULE, PAPER = "#1f1f1f", "#5f6368", "#dadce0", "#ffffff"
_TIER_RANK = {SourceTier.TIER_1: 0, SourceTier.TIER_2: 1, SourceTier.TIER_3: 2}


def _lang_cfg(language: str) -> dict:
    langs = get_config().languages.get("demo_languages") or {}
    return langs.get(language.split("-")[0].lower()) or langs.get("en") or {}


@lru_cache(maxsize=32)
def _font(family: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    root = Path(os.environ.get("FONT_DIR", "/usr/share/fonts/truetype/noto"))
    path = root / f"{family}-{'Bold' if bold else 'Regular'}.ttf"
    if not path.exists():
        path = root / f"NotoSans-{'Bold' if bold else 'Regular'}.ttf"
    engine = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC
    return ImageFont.truetype(str(path), size, layout_engine=engine)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int,
          max_lines: int) -> list[str]:
    """Greedy word wrap (all five demo languages separate words with spaces); ellipsis on overflow."""
    lines: list[str] = []
    line = ""
    words = " ".join(text.split()).split(" ")
    for i, word in enumerate(words):
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width or not line:
            line = trial
            continue
        lines.append(line)
        line = word
        if len(lines) == max_lines:
            line = ""
            rest = " ".join(words[i:])
            last = lines[-1]
            while last and draw.textlength(f"{last} …", font=font) > width:
                last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
            lines[-1] = f"{last} …" if rest else last
            break
    if line:
        lines.append(line)
    return lines


def _text_block(draw, xy, lines, font, fill, line_h) -> int:
    x, y = xy
    for ln in lines:
        draw.text((x, y), ln, font=font, fill=fill)
        y += line_h
    return y


def top_sources(claim: ClaimResult, n: int = 2) -> list[str]:
    """Names of the strongest cited sources (never social media or the shared item itself)."""
    cited = set(claim.evidence_for_ids) | set(claim.evidence_against_ids)
    items = [e for e in claim.evidence if e.url and e.tier in _TIER_RANK and e.evidence_id in cited]
    items.sort(key=lambda e: _TIER_RANK[e.tier])
    names: list[str] = []
    for e in items:
        name = (e.publisher or e.domain or "").strip()
        if name and name.lower() not in {x.lower() for x in names}:
            names.append(name)
        if len(names) == n:
            break
    return names


def render(claim: ClaimResult) -> bytes:
    """PNG bytes of the correction card for this claim, in the language of claim.answer."""
    a = claim.answer
    cfg = _lang_cfg(a.language)
    text = cfg.get("card") or {}
    family = cfg.get("font", "NotoSans")
    label = (text.get("labels") or {}).get(claim.label.value) or claim.label.value.replace("_", " ").title()
    color = COLORS.get(claim.label, COLORS[Label.NOT_ENOUGH_EVIDENCE])

    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    inner = W - 2 * MARGIN

    # Band: app name, then the label as big as fits.
    d.rectangle([0, 0, W, BAND_H], fill=color)
    d.text((MARGIN, 52), text.get("app_name", "Sach Check"), font=_font(family, 36, bold=True), fill="#ffffff")
    size = 120
    while size > 56 and d.textlength(label, font=_font(family, size, bold=True)) > inner:
        size -= 8
    top, bottom = 110, BAND_H - 30  # centre the label below the app name, whatever size it ended up
    box = d.textbbox((0, 0), label, font=_font(family, size, bold=True))
    d.text((MARGIN, top + (bottom - top - (box[3] - box[1])) // 2 - box[1]), label,
           font=_font(family, size, bold=True), fill="#ffffff")

    y = BAND_H + 56
    # The post's claim, quoted and muted: what this card answers.
    claim_font = _font(family, 38)
    y = _text_block(d, (MARGIN, y), _wrap(d, f"“{claim.claim_original}”", claim_font, inner, 3),
                    claim_font, MUTED, 56)
    y += 28
    d.line([MARGIN, y, W - MARGIN, y], fill=RULE, width=3)
    y += 40

    # What is true: the line people forward.
    d.text((MARGIN, y), text.get("what_is_true", "What is true"), font=_font(family, 40, bold=True), fill=color)
    y += 72
    # Fill the space down to the footer: smaller type before cutting the text short.
    foot_y = H - 250
    body = a.what_is_true or " ".join(a.card_lines)
    for size in (44, 40, 36, 32):
        body_font, line_h = _font(family, size), int(size * 1.5)
        max_lines = max(1, (foot_y - 40 - y) // line_h)
        lines = _wrap(d, body, body_font, inner, max_lines)
        if not lines[-1].endswith(" …"):
            break
    _text_block(d, (MARGIN, y), lines, body_font, INK, line_h)

    # Footer: sources and the link to the full result.
    names = top_sources(claim)
    if names:
        d.text((MARGIN, foot_y), text.get("sources", "Sources"), font=_font(family, 34, bold=True), fill=MUTED)
        src_font = _font("NotoSans", 36)
        line = _wrap(d, " · ".join(names), src_font, inner, 1)[0]
        d.text((MARGIN, foot_y + 54), line, font=src_font, fill=INK)
    d.rectangle([0, H - 110, W, H], fill="#f1f3f4")
    link = claim.result_url.removeprefix("https://").removeprefix("http://")
    d.text((MARGIN, H - 78), link, font=_font("NotoSans", 32), fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def card_object(verdict_id: str, language: str) -> str:
    return f"cards/{verdict_id}_{language}.png"


def card_url(verdict_id: str, language: str) -> str:
    """Public URL of a claim's card, served by GET /v1/results/{id}/card (rendered on first request)."""
    return f"{get_settings().public_base_url}/api/v1/results/{verdict_id}/card?lang={language}"


async def read_card(verdict_id: str, language: str) -> bytes | None:
    s = get_settings()
    name = card_object(verdict_id, language)
    try:
        if s.store == "memory" or not s.outputs_bucket:
            return await asyncio.to_thread((Path("/tmp/factcheck-outputs") / name).read_bytes)
        from app.intake.media import _download_gcs

        return await asyncio.to_thread(_download_gcs, s.outputs_bucket, name)
    except Exception:  # noqa: BLE001  not rendered yet
        return None


async def store_card(verdict_id: str, language: str, png: bytes) -> None:
    s = get_settings()
    name = card_object(verdict_id, language)
    if s.store == "memory" or not s.outputs_bucket:
        path = Path("/tmp/factcheck-outputs") / name
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, png)
        return
    from app.intake.media import _upload_gcs

    await asyncio.to_thread(_upload_gcs, s.outputs_bucket, name, png, "image/png")


if __name__ == "__main__":
    from tests.card_samples import sample_claim  # dev only: canned answers in the five languages

    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="hi-IN")
    ap.add_argument("--label", default="MISLEADING")
    ap.add_argument("--out", default="card.png")
    args = ap.parse_args()
    Path(args.out).write_bytes(render(sample_claim(args.lang, Label(args.label))))
    print(f"wrote {args.out}")
