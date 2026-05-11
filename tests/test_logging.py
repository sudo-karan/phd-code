"""
Tests for fmu.utils.logging.

These tests don't need GEE and don't make network calls.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from fmu.utils.logging import (
    get_console,
    get_logger,
    init_logging,
)


@pytest.fixture(autouse=True)
def reset_logging_state():
    """Reset the global logging state before each test."""
    import fmu.utils.logging as fmu_log

    fmu_log._initialized = False
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    yield
    # Cleanup again after
    fmu_log._initialized = False
    for h in list(root.handlers):
        root.removeHandler(h)


def test_init_logging_creates_run_dir(tmp_path, monkeypatch):
    """init_logging should create a per-run folder and log file."""
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from fmu.settings import get_settings

    get_settings(force_reload=True)

    run_dir = init_logging(config_name="test_cfg")

    assert run_dir.exists()
    assert run_dir.is_dir()
    assert (run_dir / "fmu.log").exists()
    # Folder name should start with the config name
    assert run_dir.name.startswith("test_cfg_")


def test_init_logging_writes_to_log_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from fmu.settings import get_settings

    get_settings(force_reload=True)

    run_dir = init_logging(config_name="filewrite")
    log = get_logger("test_module")
    log.warning("a distinctive test message 7Q3P")

    log_text = (run_dir / "fmu.log").read_text()
    assert "a distinctive test message 7Q3P" in log_text
    assert "test_module" in log_text  # logger name appears in file format
    assert "[WARNING]" in log_text


def test_init_logging_adhoc_when_no_config(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from fmu.settings import get_settings

    get_settings(force_reload=True)

    run_dir = init_logging(config_name=None)
    assert run_dir.name.startswith("adhoc_")


def test_init_logging_idempotent_clears_old_handlers(tmp_path, monkeypatch):
    """Calling init_logging twice should not double-up handlers."""
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from fmu.settings import get_settings

    get_settings(force_reload=True)

    init_logging(config_name="first")
    handlers_after_first = len(logging.getLogger().handlers)
    init_logging(config_name="second")
    handlers_after_second = len(logging.getLogger().handlers)
    assert handlers_after_first == handlers_after_second


def test_init_logging_explicit_run_dir(tmp_path):
    """If run_dir is provided, init_logging uses it instead of generating one."""
    explicit = tmp_path / "my_explicit_run"
    explicit.mkdir()
    result = init_logging(run_dir=explicit)
    assert result == explicit
    assert (explicit / "fmu.log").exists()


def test_init_logging_respects_log_level_override(tmp_path):
    explicit = tmp_path / "level_test"
    explicit.mkdir()
    init_logging(run_dir=explicit, log_level="DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_get_logger_returns_logger():
    log = get_logger("test.namespace")
    assert isinstance(log, logging.Logger)
    assert log.name == "test.namespace"


def test_get_logger_works_before_init():
    """get_logger before init_logging should not crash, just warn."""
    log = get_logger("pre_init")
    # Should not raise; just produce a logger that uses the fallback config.
    log.warning("this should work")


def test_get_console_returns_singleton():
    c1 = get_console()
    c2 = get_console()
    assert c1 is c2


def test_log_file_in_run_dir_has_init_message(tmp_path, monkeypatch):
    """The log file should record that logging was initialized."""
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from fmu.settings import get_settings

    get_settings(force_reload=True)

    run_dir = init_logging(config_name="initmsg")
    log_text = (run_dir / "fmu.log").read_text()
    assert "Logging initialized" in log_text


def test_run_dir_is_under_output_dir_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from fmu.settings import get_settings

    get_settings(force_reload=True)
    run_dir = init_logging(config_name="hierarchy_test")
    # Should be at <tmp_path>/runs/<config>_<timestamp>/
    assert run_dir.parent == tmp_path / "runs"


def test_path_returned_is_pathlib(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from fmu.settings import get_settings

    get_settings(force_reload=True)
    run_dir = init_logging(config_name="pathlib_check")
    assert isinstance(run_dir, Path)
