"""Rich-based logging with per-run output folders."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from fmu.settings import get_settings

_console = Console()
_initialized: bool = False


def _make_run_dir(config_name: str | None) -> Path:
    """outputs/runs/<config>_<timestamp>/ or outputs/runs/adhoc_<timestamp>/."""
    settings = get_settings()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = config_name or "adhoc"
    run_dir = settings.output_dir / "runs" / f"{name}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def init_logging(
    config_name: str | None = None,
    run_dir: Path | None = None,
    log_level: str | None = None,
) -> Path:
    """Set up terminal + file logging. Returns the run dir."""
    global _initialized

    settings = get_settings()
    level_str = (log_level or settings.log_level).upper()
    level = getattr(logging, level_str, logging.INFO)

    run_dir = run_dir if run_dir is not None else _make_run_dir(config_name)
    log_file = run_dir / "fmu.log"

    root = logging.getLogger()
    root.setLevel(level)

    # tear down any handlers from a previous init
    for h in list(root.handlers):
        root.removeHandler(h)
        with contextlib.suppress(Exception):
            h.close()

    rich_handler = RichHandler(
        console=_console,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
        markup=False,
    )
    rich_handler.setLevel(level)
    rich_handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%H:%M:%S]"))

    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root.addHandler(rich_handler)
    root.addHandler(file_handler)

    _initialized = True

    log = get_logger(__name__)
    log.info("Logging initialized — run dir: %s", run_dir)
    log.info("Log level: %s", level_str)

    return run_dir


def get_logger(name: str) -> logging.Logger:
    if not _initialized:
        # Minimal fallback if anyone forgets init_logging()
        root = logging.getLogger()
        if not root.handlers:
            logging.basicConfig(level=logging.WARNING)
    return logging.getLogger(name)


def get_console() -> Console:
    return _console
