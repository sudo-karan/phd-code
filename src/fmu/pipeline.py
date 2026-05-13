"""Pipeline orchestrator. Walks registered stages, manages context, writes manifest."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, get_stage_class
from fmu.utils.caching import (
    ExportTaskInfo,
    asset_exists,
    cached_asset_path,
    load_cached_image,
    start_export,
)
from fmu.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class StageRecord:
    name: str
    elapsed_sec: float
    produced: list[str]
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    cache_status: dict[str, str] = field(default_factory=dict)  # key → "hit" / "miss-exported" / "off"
    export_tasks: list[dict[str, str]] = field(default_factory=list)


@dataclass
class PipelineResult:
    config_name: str
    run_dir: Path
    stages: list[StageRecord] = field(default_factory=list)
    context: PipelineContext | None = None
    total_elapsed_sec: float = 0.0


class Pipeline:
    """Run a sequence of registered stages.

    Args:
        stage_names: ordered list of registered stage names to run.
        use_cache: if True, check GEE asset cache before running each stage
            and submit async export tasks for outputs that aren't cached.
            Off by default — turn on for normal runs that need shareable
            assets / fast visualization. Tests should leave this off.
    """

    def __init__(self, stage_names: list[str], use_cache: bool = False) -> None:
        if not stage_names:
            raise ValueError("Pipeline must have at least one stage.")
        self.stage_names = list(stage_names)
        # eager resolution — typos in stage names fail now, not after 10 min of GEE work
        self.stage_classes: list[type[Stage]] = [get_stage_class(n) for n in stage_names]
        self.use_cache = use_cache

    def run(
        self,
        config: Config,
        run_dir: Path,
        initial_context: PipelineContext | None = None,
    ) -> PipelineResult:
        ctx = initial_context if initial_context is not None else PipelineContext()
        result = PipelineResult(config_name=config.name, run_dir=run_dir)

        log.info("=" * 60)
        log.info("Pipeline run: %s", config.name)
        log.info("Stages: %s", " → ".join(self.stage_names))
        log.info("Run directory: %s", run_dir)
        log.info("=" * 60)

        t0 = time.perf_counter()
        for stage_cls in self.stage_classes:
            result.stages.append(self._run_one(stage_cls, ctx, config))
        result.total_elapsed_sec = time.perf_counter() - t0
        result.context = ctx

        log.info("=" * 60)
        log.info("Pipeline complete in %.2f sec", result.total_elapsed_sec)
        log.info("=" * 60)

        manifest_path = run_dir / "manifest.json"
        self._write_manifest(result, config, manifest_path)
        log.info("Manifest written: %s", manifest_path)

        return result

    def _run_one(
        self,
        stage_cls: type[Stage],
        ctx: PipelineContext,
        config: Config,
    ) -> StageRecord:
        stage = stage_cls()
        name = stage.name

        log.info("→ stage: %s", name)
        log.debug("  requires: %s", sorted(stage.required_inputs))
        log.debug("  produces: %s", sorted(stage.produces))

        t0 = time.perf_counter()
        cache_status: dict[str, str] = {}
        export_tasks: list[ExportTaskInfo] = []

        # Which produces are cacheable as GEE assets? Default: all of them
        # (preserves behavior for stages that only produce ee.Image outputs).
        cacheable = stage.cacheable_outputs if stage.cacheable_outputs else stage.produces

        try:
            stage.validate(ctx, config)

            # Try cache-first if enabled
            if self.use_cache:
                cached_outputs = self._try_load_cache(stage, config, cache_status, cacheable)
                # Skip the live run only if every produces key is cacheable AND in cache.
                if cached_outputs is not None and cacheable == stage.produces:
                    log.info("  [cache] all %d outputs hit; skipping stage run", len(cached_outputs))
                    for key, value in cached_outputs.items():
                        ctx.set(key, value)
                    elapsed = time.perf_counter() - t0
                    log.info("✓ stage %s done in %.2f sec (from cache)", name, elapsed)
                    return StageRecord(
                        name=name,
                        elapsed_sec=elapsed,
                        produced=sorted(cached_outputs.keys()),
                        warnings=[],
                        metadata={"source": "cache"},
                        cache_status=cache_status,
                        export_tasks=[],
                    )

            # Run live
            stage_result = stage.run(ctx, config)
            if not isinstance(stage_result, StageResult):
                raise TypeError(
                    f"Stage {name!r} returned {type(stage_result).__name__}, expected StageResult."
                )

            produced_keys = set(stage_result.outputs.keys())
            if produced_keys != stage.produces:
                missing = stage.produces - produced_keys
                extra = produced_keys - stage.produces
                parts = [f"Stage {name!r} output mismatch."]
                if missing:
                    parts.append(f"Missing declared outputs: {sorted(missing)}.")
                if extra:
                    parts.append(f"Undeclared outputs: {sorted(extra)}.")
                raise ValueError(" ".join(parts))

            # For cacheable outputs that hit cache, swap in the cached version
            # so downstream stages and exports use the persisted asset.
            final_outputs = dict(stage_result.outputs)
            if self.use_cache:
                for key, cached_image in (cached_outputs or {}).items():
                    final_outputs[key] = cached_image

            for key, value in final_outputs.items():
                ctx.set(key, value)

            # Submit exports for any cacheable outputs that missed
            if self.use_cache:
                export_tasks = self._submit_exports(
                    stage, config, ctx, final_outputs, cache_status, cacheable
                )

        except Exception as e:
            elapsed = time.perf_counter() - t0
            log.error("✗ stage %s FAILED after %.2f sec: %s", name, elapsed, e)
            raise

        elapsed = time.perf_counter() - t0

        for w in stage_result.warnings:
            log.warning("  [%s] %s", name, w)

        log.info("✓ stage %s done in %.2f sec", name, elapsed)

        return StageRecord(
            name=name,
            elapsed_sec=elapsed,
            produced=sorted(stage_result.outputs.keys()),
            warnings=list(stage_result.warnings),
            metadata=dict(stage_result.metadata),
            cache_status=cache_status,
            export_tasks=[
                {
                    "task_id": t.task_id,
                    "asset_path": t.asset_path,
                    "description": t.description,
                }
                for t in export_tasks
            ],
        )

    def _try_load_cache(
        self,
        stage: Stage,
        config: Config,
        cache_status: dict[str, str],
        cacheable: set[str],
    ) -> dict[str, Any] | None:
        """Check which cacheable outputs exist in cache.

        Returns a dict of loaded outputs (possibly empty if none hit).
        Mutates cache_status with "hit" / "miss" per cacheable key.
        Non-cacheable keys are not checked.
        """
        outputs: dict[str, Any] = {}
        for key in sorted(cacheable):
            path = cached_asset_path(config.name, stage.name, key)
            if asset_exists(path):
                cache_status[key] = "hit"
                outputs[key] = load_cached_image(path)
                log.debug("  [cache] hit:  %s → %s", key, path)
            else:
                cache_status[key] = "miss"
                log.debug("  [cache] miss: %s (expected %s)", key, path)
        return outputs

    def _submit_exports(
        self,
        stage: Stage,
        config: Config,
        ctx: PipelineContext,
        outputs: dict[str, Any],
        cache_status: dict[str, str],
        cacheable: set[str],
    ) -> list[ExportTaskInfo]:
        """Submit async export tasks for cacheable outputs that missed the cache."""
        import ee  # local import: only needed if caching is on

        roi = ctx.get("roi")
        if not isinstance(roi, ee.Geometry):
            log.warning(
                "  [cache] cannot export — `roi` in context isn't an ee.Geometry; "
                "skipping export. Got: %s", type(roi).__name__
            )
            return []

        tasks: list[ExportTaskInfo] = []
        for key, image in outputs.items():
            if key not in cacheable:
                continue
            if cache_status.get(key) == "hit":
                continue
            if not isinstance(image, ee.Image):
                log.warning(
                    "  [cache] skipping export of %s — declared cacheable but not an ee.Image (got %s)",
                    key, type(image).__name__,
                )
                continue
            path = cached_asset_path(config.name, stage.name, key)
            task = start_export(
                image=image,
                asset_path=path,
                roi=roi,
                scale=10,
                description=f"{config.name}_{stage.name}_{key}",
            )
            cache_status[key] = "miss-exported"
            tasks.append(task)
        return tasks

    def _write_manifest(
        self,
        result: PipelineResult,
        config: Config,
        path: Path,
    ) -> None:
        manifest = {
            "config_name": result.config_name,
            "run_dir": str(result.run_dir),
            "total_elapsed_sec": round(result.total_elapsed_sec, 3),
            "stages": [
                {
                    "name": s.name,
                    "elapsed_sec": round(s.elapsed_sec, 3),
                    "produced": s.produced,
                    "warnings": s.warnings,
                    "metadata": _json_safe(s.metadata),
                    "cache_status": s.cache_status,
                    "export_tasks": s.export_tasks,
                }
                for s in result.stages
            ],
            "config": config.model_dump(mode="json"),
        }
        path.write_text(json.dumps(manifest, indent=2, default=str))


def _json_safe(obj: Any) -> Any:
    # stage metadata might contain GEE objects or numpy arrays; fall back to str()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, str | int | float | bool) or obj is None:
        return obj
    return str(obj)
