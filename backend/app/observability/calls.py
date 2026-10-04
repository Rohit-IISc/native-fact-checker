"""Per-check record of model calls and paid API usage, with cost from config/models.yaml."""
from __future__ import annotations

import contextvars
from dataclasses import asdict, dataclass, field

from app.settings import get_config


@dataclass
class ModelCall:
    check_id: str | None
    stage: str
    model_id: str
    prompt_version: str
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    success: bool = True
    retry: bool = False
    grounding_queries: int = 0

    def row(self) -> dict:
        d = asdict(self)
        d.pop("grounding_queries")
        return d


@dataclass
class CheckLedger:
    """Collects everything billable for one check; written to BigQuery at the end."""

    calls: list[ModelCall] = field(default_factory=list)
    grounding_queries: int = 0
    vision_calls: int = 0
    tts_chars: int = 0
    stage_latency_ms: dict[str, int] = field(default_factory=dict)

    @property
    def model_cost_usd(self) -> float:
        return round(sum(c.cost_usd for c in self.calls), 6)

    @property
    def total_cost_usd(self) -> float:
        cfg = get_config().models
        grounding = self.grounding_queries * cfg["grounding"]["price_per_1000"] / 1000
        vision = self.vision_calls * cfg["vision"]["web_detection_price_per_1000"] / 1000
        tts = cfg["models"]["tts"].get("est_cost_per_answer", 0) if self.tts_chars else 0
        return round(self.model_cost_usd + grounding + vision + tts, 6)


ledger_var: contextvars.ContextVar[CheckLedger | None] = contextvars.ContextVar("ledger", default=None)


def current_ledger() -> CheckLedger:
    ledger = ledger_var.get()
    if ledger is None:
        ledger = CheckLedger()
        ledger_var.set(ledger)
    return ledger


def model_cost(model_key: str, input_tokens: int, output_tokens: int, thinking_tokens: int = 0) -> float:
    """USD cost of one call. Thinking tokens are billed as output."""
    m = get_config().models["models"][model_key]
    price_in = float(m.get("price_in", 0))
    price_out = float(m.get("price_out", 0))
    return round((input_tokens * price_in + (output_tokens + thinking_tokens) * price_out) / 1_000_000, 8)
