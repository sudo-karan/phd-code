"""
Environment settings — values that come from `.env` or the shell environment,
not from the YAML config.

These are things that vary per-machine and per-user: the GEE project ID,
output directories, log level. They should NEVER be committed to git, which
is why they live in `.env` (gitignored) with `.env.example` as a template.

The `Settings` class is a singleton — load it once at the start of a pipeline
run and pass it down. It is separate from the per-experiment `Config` (in
config.py) because they have different lifecycles: Settings is per-machine
and roughly never changes; Config changes with every experiment.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Environment-driven settings.

    Loaded from (in order of priority, highest first):
      1. Actual environment variables set in the shell
      2. The `.env` file at the repo root
      3. The defaults defined below

    To override any setting for a single run, just set the env var:
        GEE_PROJECT_ID=my-other-project python scripts/run_pipeline.py ...
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Don't fail if .env is missing — defaults will be used.
        extra="ignore",
        case_sensitive=False,
    )

    # === GEE ===
    gee_project_id: str = Field(
        default="",
        description=(
            "Google Cloud project ID with Earth Engine API enabled. "
            "Required for any pipeline run that touches GEE."
        ),
    )
    gee_asset_root: str = Field(
        default="",
        description=(
            "Path prefix where exported assets are written, e.g. "
            "'projects/my-project/assets/fmu'. If empty, defaults to "
            "'projects/{gee_project_id}/assets/fmu'."
        ),
    )

    # === Local paths ===
    output_dir: Path = Field(
        default=Path("outputs"),
        description="Where the pipeline writes local outputs (reports, GeoTIFFs).",
    )

    # === Logging ===
    log_level: str = Field(
        default="INFO",
        description="One of DEBUG, INFO, WARNING, ERROR.",
    )

    def resolved_asset_root(self) -> str:
        """
        Return the asset root, falling back to a project-based default if
        GEE_ASSET_ROOT is not set.
        """
        if self.gee_asset_root:
            return self.gee_asset_root
        if not self.gee_project_id:
            raise ValueError(
                "Cannot resolve asset root: GEE_PROJECT_ID is not set. "
                "Edit your .env file."
            )
        return f"projects/{self.gee_project_id}/assets/fmu"


# Cache the settings instance so we don't re-read the .env file every call.
_settings_cache: Settings | None = None


def get_settings(force_reload: bool = False) -> Settings:
    """
    Return the global Settings instance.

    Args:
        force_reload: If True, re-read the .env file. Mostly useful in tests.
    """
    global _settings_cache
    if _settings_cache is None or force_reload:
        _settings_cache = Settings()
    return _settings_cache
