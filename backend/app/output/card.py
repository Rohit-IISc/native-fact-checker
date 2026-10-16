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


class Fonts:
    """The script font plus NotoSans for Latin runs. Noto's Devanagari, Tamil and Kannada fonts have no Latin
    letters, so "CHCKR" or "DELHI" inside a Hindi card drew as empty boxes (Oct 16)."""

    def __init__(self, family: str, size: int, bold: bool = False) -> None:
        self.script = _font(family, size, bold)
        self.latin = _font("NotoSans", size, bold) if family != "NotoSans" else self.script

    def runs(self, text: str) -> list[tuple[str, ImageFont.FreeTypeFont]]:
        """Split into runs: ASCII letters and digits use the Latin font, other letters the script font;
        spaces and punctuation stay with the run they are in."""
        out: list[tuple[str, ImageFont.FreeTypeFont]] = []
        for ch in text:
            if ch.isascii() and ch.isalnum():
                f = self.latin
            elif ch.isalpha():
                f = self.script
            else:
                f = out[-1][1] if out else self.latin
            if out and out[-1][1] is f:
                out[-1] = (out[-1][0] + ch, f)
            else:
                out.append((ch, f))
        return out

    def length(self, draw: ImageDraw.ImageDraw, text: str) -> float:
        return sum(draw.textlength(t, font=f) for t, f in self.runs(text))

    def draw(self, draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, fill: str) -> None:
        """Draw at (x, y) as the top of the script font's line, every run on one shared baseline."""
        x, y = xy
        baseline = y + self.script.getmetrics()[0]
        for t, f in self.runs(text):
            draw.text((x, baseline), t, font=f, fill=fill, anchor="ls")
            x += draw.textlength(t, font=f)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Fonts, width: int, max_lines: int) -> list[str]:
    """Greedy word wrap (all five demo languages separate words with spaces); ellipsis on overflow."""
    lines: list[str] = []
    line = ""
    words = " ".join(text.split()).split(" ")
    for i, word in enumerate(words):
        trial = f"{line} {word}".strip()
        if font.length(draw, trial) <= width or not line:
            line = trial
            continue
        lines.append(line)
        line = word
        if len(lines) == max_lines:
            line = ""
            rest = " ".join(words[i:])
            last = lines[-1]
            while last and font.length(draw, f"{last} …") > width:
                last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
            lines[-1] = f"{last} …" if rest else last
            break
    if line:
        lines.append(line)
    return lines


def _text_block(draw, xy, lines, font, fill, line_h) -> int:
    x, y = xy
    for ln in lines:
        font.draw(draw, (x, y), ln, fill)
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
    Fonts(family, 36, bold=True).draw(d, (MARGIN, 52), text.get("app_name", "CHCKR"), "#ffffff")
    size = 120
    while size > 56 and Fonts(family, size, bold=True).length(d, label) > inner:
        size -= 8
    top, bottom = 110, BAND_H - 30  # centre the label below the app name, whatever size it ended up
    box = d.textbbox((0, 0), label, font=_font(family, size, bold=True))
    Fonts(family, size, bold=True).draw(d, (MARGIN, top + (bottom - top - (box[3] - box[1])) // 2 - box[1]),
                                        label, "#ffffff")

    y = BAND_H + 56
    # The post's claim, quoted and muted: what this card answers.
    claim_font = Fonts(family, 38)
    y = _text_block(d, (MARGIN, y), _wrap(d, f"“{claim.claim_original}”", claim_font, inner, 3),
                    claim_font, MUTED, 56)
    y += 28
    d.line([MARGIN, y, W - MARGIN, y], fill=RULE, width=3)
    y += 40

    # What is true: the line people forward.
    Fonts(family, 40, bold=True).draw(d, (MARGIN, y), text.get("what_is_true", "What is true"), color)
    y += 72
    # Fill the space down to the footer: smaller type before cutting the text short.
    foot_y = H - 250
    body = a.what_is_true or " ".join(a.card_lines)
    for size in (44, 40, 36, 32):
        body_font, line_h = Fonts(family, size), int(size * 1.5)
        max_lines = max(1, (foot_y - 40 - y) // line_h)
        lines = _wrap(d, body, body_font, inner, max_lines)
        if not lines[-1].endswith(" …"):
            break
    _text_block(d, (MARGIN, y), lines, body_font, INK, line_h)

    # Footer: sources and the link to the full result.
    names = top_sources(claim)
    if names:
        Fonts(family, 34, bold=True).draw(d, (MARGIN, foot_y), text.get("sources", "Sources"), MUTED)
        src_font = Fonts(family, 36)  # publisher names can be in any script ("विश्वास न्यूज")
        line = _wrap(d, " · ".join(names), src_font, inner, 1)[0]
        src_font.draw(d, (MARGIN, foot_y + 54), line, INK)
    d.rectangle([0, H - 110, W, H], fill="#f1f3f4")
    link = claim.result_url.removeprefix("https://").removeprefix("http://")
    Fonts("NotoSans", 32).draw(d, (MARGIN, H - 78), link, MUTED)

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
