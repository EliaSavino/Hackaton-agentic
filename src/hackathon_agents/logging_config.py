from __future__ import annotations

import logging
from typing import Literal


def configure_logging(level: str | int = "INFO") -> None:
    """Configure readable logging, preferring Rich when installed."""

    resolved_level = logging.getLevelName(level) if isinstance(level, str) else level
    if isinstance(resolved_level, str):
        resolved_level = logging.INFO

    try:
        from rich.logging import RichHandler

        logging.basicConfig(
            level=resolved_level,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
        )
    except Exception:
        logging.basicConfig(
            level=resolved_level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )


def get_logger(name: str, level: Literal["debug", "info", "warning"] | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if level:
        logger.setLevel(level.upper())
    return logger
