"""Structured JSON logging for Cloud Logging. Every line carries check_id, stage and uid_hash."""
from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import sys
from datetime import UTC, datetime

check_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("check_id", default=None)
stage_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("stage", default=None)
uid_hash_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("uid_hash", default=None)


def hash_uid(uid: str) -> str:
    return hashlib.sha256(uid.encode()).hexdigest()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "logger": record.name,
            "check_id": check_id_var.get(),
            "stage": stage_var.get(),
            "uid_hash": uid_hash_var.get(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            entry.update(extra)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def log_event(logger: logging.Logger, message: str, level: int = logging.INFO, **fields: object) -> None:
    logger.log(level, message, extra={"fields": fields})
