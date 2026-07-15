"""
Centralised logging configuration for DocBot v3.

Usage
-----
At application startup (launcher or main), call::

    from docbot.logging_setup import setup_logging
    setup_logging()

Once a session directory is known, attach a per-session log file::

    from docbot.logging_setup import attach_session_log
    attach_session_log(session_dir)

All other modules simply do::

    from loguru import logger
    logger.info("…")
    logger.debug("…")
    logger.warning("…")
"""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

# Loguru sink IDs — kept so callers can remove them if needed
_STDERR_SINK_ID: Optional[int] = None
_SESSION_SINK_ID: Optional[int] = None

# Default format strings
_STDERR_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>"
)
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{name}:{function}:{line} — {message}"
)


def setup_logging(level: str = "INFO") -> None:
    """
    Configure loguru sinks.

    Removes the default loguru sink and installs:
    - A coloured stderr sink at *level* (default INFO).

    Call once at application startup before any logger usage.
    """
    global _STDERR_SINK_ID

    # Remove loguru's default handler
    logger.remove()

    _STDERR_SINK_ID = logger.add(
        sys.stderr,
        level=level,
        format=_STDERR_FORMAT,
        colorize=True,
        backtrace=True,
        diagnose=False,
    )

    logger.debug("Logging initialised (stderr sink active).")


def attach_session_log(session_dir: Path) -> None:
    """
    Add a rotating per-session DEBUG log file.

    Can be called multiple times; only the most recent session sink is kept.

    Args:
        session_dir: The session folder (e.g. ``sessions/session_20260715_123456``).
                     The log file ``run.log`` will be created inside it.
    """
    global _SESSION_SINK_ID

    # Remove previous session sink if any
    if _SESSION_SINK_ID is not None:
        try:
            logger.remove(_SESSION_SINK_ID)
        except ValueError:
            pass
        _SESSION_SINK_ID = None

    log_path = Path(session_dir) / "run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    _SESSION_SINK_ID = logger.add(
        str(log_path),
        level="DEBUG",
        format=_FILE_FORMAT,
        rotation="10 MB",
        retention=3,
        encoding="utf-8",
        backtrace=True,
        diagnose=True,
    )

    logger.debug(f"Session log attached: {log_path}")
