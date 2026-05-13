"""Pipeline orchestrator. Walks registered stages, manages context, writes manifest."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, get_stage_class
from fmu.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class StageRecord:
    name: str
    elapsed_sec: float
    produced: list[str]
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    config_name: str
    run_dir: Path
    stages: list[StageRecord] = field(default_factory=list)
    context: PipelineContext | None = None
    total_elapsed_sec: float = 0.0


class Pipeline:
    """Run a sequence of registered stages."""

    def __init__(self, stage_names: list[str]) -> None:
        if not stage_names:
            raise ValueError("Pipeline must have at least one stage.")
        self.stage_names = list(stage_names)
        # eager resolution — typos in stage names fail now, not after 10 min of GEE work
        self.stage_classes: list[type[Stage]] = [get_stage_class(n) for n in stage_names]

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

        try:
            stage.validate(ctx, config)

            stage_result = stage.run(ctx, config)
            if not isinstance(stage_result, StageResult):
                raise TypeError(
                    f"Stage {name!r} returned {type(stage_result).__name__}, expected StageResult."
                )

            # produced keys must match the declaration exactly
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

            for key, value in stage_result.outputs.items():
                ctx.set(key, value)

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
        )

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
