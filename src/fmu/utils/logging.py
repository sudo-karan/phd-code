"""
Logging setup for the pipeline.

Goals:
  1. Pretty terminal output (Rich) — colored, readable, with timestamps and levels.
  2. Per-run log files — every pipeline run gets its own folder with its own log,
     so you can look up what happened on Nov 5 without grepping through everything.
  3. One-call setup — `init_logging(run_dir)` configures everything; after that
     `get_logger(__name__)` in any module returns a configured logger.

Usage pattern (typical):
    from fmu.utils.logging import init_logging, get_logger

    run_dir = init_logging()              # creates outputs/runs/<config>_<timestamp>/
    log = get_logger(__name__)
    log.info("Pipeline starting")

Inside any module after init_logging() has been called:
    from fmu.utils.logging import get_logger
    log = get_logger(__name__)
    log.info("Doing something")

Why not just use Python's `logging` directly?
  - Rich makes terminal output dramatically more readable (colors, levels,
    timestamps, traceback rendering).
  - We add the per-run file handler with one call, instead of every script
    re-implementing it.

Why a function (`init_logging`) rather than module-level setup?
  - Module-level setup runs on import. We don't want logging configured by
    the act of importing the package — only by an explicit "I am running
    a pipeline" call.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from fmu.settings import get_settings

# Module-level state: a single Rich console reused everywhere.
_console = Console()

# Track whether init_logging has been called so we don't double-configure.
_initialized: bool = False


def _make_run_dir(config_name: str | None) -> Path:
    """
    Create and return the per-run output directory under OUTPUT_DIR/runs/.

    Format: <output_dir>/runs/<config_name>_<YYYYmmdd_HHMMSS>/

    If config_name is None, the folder is named "adhoc_<timestamp>" so we
    can log things even before a config has been loaded.
    """
    settings = get_settings()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = config_name if config_name else "adhoc"
    run_dir = settings.output_dir / "runs" / f"{name}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def init_logging(
    config_name: str | None = None,
    run_dir: Path | None = None,
    log_level: str | None = None,
) -> Path:
    """
    Initialize logging for a pipeline run.

    Args:
        config_name: The Config.name from the YAML being run, used to label
            this run's folder. Pass None for ad-hoc setup (e.g. tests, REPL).
        run_dir: Override the run directory. If None, a new one is created
            under OUTPUT_DIR/runs/.
        log_level: Override the level from Settings.log_level.

    Returns:
        The Path of the run directory. The pipeline can write GeoTIFFs,
        reports, and manifests here as well.

    Effects:
        - Configures the root logger with a Rich handler (terminal) and
          a FileHandler (run_dir/fmu.log).
        - Subsequent get_logger() calls return loggers using this setup.
        - Calling init_logging() more than once is safe: it tears down the
          previous handlers before installing new ones.
    """
    global _initialized

    settings = get_settings()
    level_str = (log_level or settings.log_level).upper()
    level = getattr(logging, level_str, logging.INFO)

    run_dir = run_dir if run_dir is not None else _make_run_dir(config_name)
    log_file = run_dir / "fmu.log"

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any handlers from a previous init (idempotent setup).
    for h in list(root.handlers):
        root.removeHandler(h)
        with contextlib.suppress(Exception):
            h.close()

    # Terminal handler — Rich for pretty colored output.
    rich_handler = RichHandler(
        console=_console,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
        markup=False,
    )
    rich_handler.setLevel(level)
    rich_handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%H:%M:%S]"))

    # File handler — plain text, full path, for the run's log file.
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

    # Log the setup itself so the log file has context.
    log = get_logger(__name__)
    log.info("Logging initialized — run dir: %s", run_dir)
    log.info("Log level: %s", level_str)

    return run_dir


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger for the given module name.

    If init_logging() hasn't been called yet, the returned logger still works
    but only prints to stderr at WARNING level — enough to not lose anything
    important but a sign that something forgot to call init_logging().
    """
    if not _initialized:
        # Minimal fallback: configure only if no handlers exist at all,
        # so we don't fight with init_logging() if it runs later.
        root = logging.getLogger()
        if not root.handlers:
            logging.basicConfig(level=logging.WARNING)
    return logging.getLogger(name)


def get_console() -> Console:
    """
    Return the shared Rich console. Use this for direct print calls when
    you want colored/styled terminal output outside of a log message:

        from fmu.utils.logging import get_console
        get_console().print("[bold green]Done![/bold green]")
    """
    return _console
