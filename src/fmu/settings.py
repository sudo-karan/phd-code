"""Per-machine settings loaded from .env (see docs/design_notes.md)."""

from __future__ import annotations

import threading
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    gee_project_id: str = Field(default="")
    gee_asset_root: str = Field(default="")  # falls back to projects/{id}/assets/fmu if empty
    output_dir: Path = Field(default=Path("outputs"))
    log_level: str = Field(default="INFO")

    def resolved_asset_root(self) -> str:
        if self.gee_asset_root:
            return self.gee_asset_root
        if not self.gee_project_id:
            raise ValueError("GEE_PROJECT_ID not set in .env")
        return f"projects/{self.gee_project_id}/assets/fmu"


# Module-level singleton + lock. The lock protects against double-load in
# multi-threaded contexts (pytest-xdist, future async work). In the common
# single-threaded case the lock is uncontended and adds negligible overhead.
_cached: Settings | None = None
_cache_lock = threading.Lock()


def get_settings(force_reload: bool = False) -> Settings:
    """Get the cached Settings instance, loading it from .env if needed.

    Args:
        force_reload: re-read .env even if a cached instance exists. Used
            in tests that mutate environment variables between cases.
    """
    global _cached
    # Fast path: already loaded, no reload requested
    if _cached is not None and not force_reload:
        return _cached
    # Slow path: take the lock and check again
    with _cache_lock:
        if _cached is None or force_reload:
            _cached = Settings()
        return _cached
