"""Implement processing logs. Streamlit often hides stderr; logs/implement.log always works."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

LOGGER_NAME = "cord.implement"
LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "implement.log"

_EXECUTION_LOGGER_NAMES = ("UIExecutor", "VisionLocator", "ElementResolver", "APIExecutor")
_wired_execution_loggers = False


def _write_line(message: str) -> None:
    line = f"{datetime.now():%H:%M:%S} [implement] {message}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def get_logger() -> logging.Logger:
    configure_implement_logging()
    return logging.getLogger(LOGGER_NAME)


def emit(message: str) -> None:
    """Write one processing line to stdout and logs/implement.log."""
    configure_implement_logging()
    _write_line(message)


def configure_implement_logging() -> None:
    log = logging.getLogger(LOGGER_NAME)
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log.propagate = False


class _ForwardHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _write_line(record.getMessage())
        except Exception:
            pass


def wire_execution_loggers() -> None:
    """Route UIExecutor / API executor module loggers into implement.log."""
    global _wired_execution_loggers
    if _wired_execution_loggers:
        return
    configure_implement_logging()

    handler = _ForwardHandler()
    handler.setLevel(logging.INFO)

    for name in _EXECUTION_LOGGER_NAMES:
        module_log = logging.getLogger(name)
        module_log.setLevel(logging.INFO)
        if not any(isinstance(h, _ForwardHandler) for h in module_log.handlers):
            module_log.addHandler(handler)
        module_log.propagate = False

    _wired_execution_loggers = True
