"""Diagnosis processing logs. Streamlit/Uvicorn often hides stderr; the file always works."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

LOGGER_NAME = "cord.diagnosis"
LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "diagnosis.log"


def get_logger() -> logging.Logger:
    configure_diagnosis_logging()
    return logging.getLogger(LOGGER_NAME)


def emit(message: str) -> None:
    """Write one processing line to stdout and logs/diagnosis.log."""
    configure_diagnosis_logging()
    line = f"{datetime.now():%H:%M:%S} [diagnosis] {message}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass
    logging.getLogger(LOGGER_NAME).info(message)


def configure_diagnosis_logging() -> None:
    log = logging.getLogger(LOGGER_NAME)
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [diagnosis] %(message)s", datefmt="%H:%M:%S")
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    log.addHandler(file_handler)
    log.addHandler(stream_handler)
    log.propagate = False
