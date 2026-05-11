"""
Pipeline orchestrator.

The orchestrator is what makes the Stage registry (Module 4) actually do
something. It:

  1. Takes a Config and a list of stage names (in order)
  2. Builds an initial PipelineContext (seeds it with config + ROI)
  3. For each stage:
       - Looks it up in the registry
       - Calls .validate(ctx, config) — raises on missing inputs
       - Calls .run(ctx, config) — gets a StageResult
       - Validates result.outputs matches stage.produces
       - Merges outputs into the context
       - Logs progress and accumulates the run report
  4. Writes a manifest (the run's config, stages, timings, warnings)

What this module is NOT:
  - It does NOT decide which stages to run. That comes from the caller
    (typically a CLI or a config-driven stage list). Why: keeping the
    orchestrator agnostic to the specific pipeline lets us run different
    pipelines (baseline, HLS variant, ecotone-only) without rewriting it.
  - It does NOT do GEE work itself. The orchestrator never touches ee.*
    directly — only stages do.

Failure mode (locked in DEC-013): exceptions propagate. If a stage raises,
the pipeline crashes and the traceback points at the offending stage. No
soft-fail / continue-on-error.
"""

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


# ---------- Run records ----------


@dataclass
class StageRecord:
    """One stage's record from a pipeline run, for the manifest and report."""

    name: str
    elapsed_sec: float
    produced: list[str]
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """The full result of a pipeline run."""

    config_name: str
    run_dir: Path
    stages: list[StageRecord] = field(default_factory=list)
    context: PipelineContext | None = None  # final context, for caller inspection
    total_elapsed_sec: float = 0.0


# ---------- Orchestrator ----------


class Pipeline:
    """
    The pipeline orchestrator.

    Usage:
        from fmu.config import load_config
        from fmu.utils.logging import init_logging
        from fmu.pipeline import Pipeline

        config = load_config("configs/sanjay_van_baseline.yaml")
        run_dir = init_logging(config_name=config.name)
        pipeline = Pipeline(stage_names=[
            "data_load", "masking", "features_optical", "segmentation",
            "clustering", "profiling", "export",
        ])
        result = pipeline.run(config=config, run_dir=run_dir)

    The stage names are looked up in the global stage registry (populated by
    @register_stage decorators when stage modules are imported).
    """

    def __init__(self, stage_names: list[str]) -> None:
        if not stage_names:
            raise ValueError("Pipeline must have at least one stage.")
        self.stage_names = list(stage_names)
        # Resolve stage classes upfront — fails fast if any name is unregistered.
        self.stage_classes: list[type[Stage]] = [
            get_stage_class(name) for name in stage_names
        ]

    def run(
        self,
        config: Config,
        run_dir: Path,
        initial_context: PipelineContext | None = None,
    ) -> PipelineResult:
        """
        Execute every stage in order.

        Args:
            config: The pipeline Config object.
            run_dir: Where to write the manifest and any stage outputs.
                Typically the path returned by init_logging().
            initial_context: Optional starting context. If None, a fresh
                empty PipelineContext is created. The orchestrator does NOT
                automatically seed the context with anything — stages that
                need the ROI/config should declare them as required_inputs
                and the caller must provide them. (We may revisit this later
                if it gets tedious; for now explicit > implicit.)

        Returns:
            PipelineResult with per-stage records and the final context.

        Raises:
            Any exception a stage raises. Wraps stage exceptions with
            context about which stage failed.
        """
        ctx = initial_context if initial_context is not None else PipelineContext()
        result = PipelineResult(config_name=config.name, run_dir=run_dir)

        log.info("=" * 60)
        log.info("Pipeline run: %s", config.name)
        log.info("Stages: %s", " → ".join(self.stage_names))
        log.info("Run directory: %s", run_dir)
        log.info("=" * 60)

        total_start = time.perf_counter()

        for stage_cls in self.stage_classes:
            record = self._run_one_stage(stage_cls, ctx, config)
            result.stages.append(record)

        result.total_elapsed_sec = time.perf_counter() - total_start
        result.context = ctx

        log.info("=" * 60)
        log.info("Pipeline complete in %.2f sec", result.total_elapsed_sec)
        log.info("=" * 60)

        # Write the manifest
        manifest_path = run_dir / "manifest.json"
        self._write_manifest(result, config, manifest_path)
        log.info("Manifest written: %s", manifest_path)

        return result

    def _run_one_stage(
        self,
        stage_cls: type[Stage],
        ctx: PipelineContext,
        config: Config,
    ) -> StageRecord:
        """Run a single stage and return its record."""
        stage = stage_cls()
        name = stage.name

        log.info("→ stage: %s", name)
        log.debug("  requires: %s", sorted(stage.required_inputs))
        log.debug("  produces: %s", sorted(stage.produces))

        start = time.perf_counter()

        try:
            # 1. Validate inputs are present
            stage.validate(ctx, config)

            # 2. Run the stage
            stage_result = stage.run(ctx, config)
            if not isinstance(stage_result, StageResult):
                raise TypeError(
                    f"Stage {name!r} returned {type(stage_result).__name__}, "
                    f"expected StageResult."
                )

            # 3. Validate produced keys match the declaration
            produced_keys = set(stage_result.outputs.keys())
            if produced_keys != stage.produces:
                missing = stage.produces - produced_keys
                extra = produced_keys - stage.produces
                msg_parts = [f"Stage {name!r} output mismatch."]
                if missing:
                    msg_parts.append(f"Missing declared outputs: {sorted(missing)}.")
                if extra:
                    msg_parts.append(f"Undeclared outputs: {sorted(extra)}.")
                raise ValueError(" ".join(msg_parts))

            # 4. Merge outputs into the context
            for key, value in stage_result.outputs.items():
                ctx.set(key, value)

        except Exception as e:
            elapsed = time.perf_counter() - start
            log.error("✗ stage %s FAILED after %.2f sec: %s", name, elapsed, e)
            raise

        elapsed = time.perf_counter() - start

        # Surface warnings to the log
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
        """Write a JSON manifest summarising the run. Goes next to the log."""
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
    """
    Recursively make an object JSON-serialisable for the manifest.

    Stage metadata can contain GEE objects, numpy arrays, or other things
    that don't serialise cleanly. We don't want manifest writing to crash
    on a stage that put something exotic in metadata — that data is
    informational. Fall back to str() for unknown types.
    """
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, str | int | float | bool) or obj is None:
        return obj
    return str(obj)
