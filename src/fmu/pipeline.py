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
    config_fingerprint,
    load_cached_image,
    start_export,
)
from fmu.utils.logging import get_logger

log = get_logger(__name__)


# Stages that run after clustering, keyed by how far a run should go. Each
# inspect script asks for the tail it needs (clustering / profiling / export /
# metrics); the base masking->clustering prefix is shared. metrics does NOT run
# profiling+export (it only needs cluster_labels), matching the historical
# inspect_metrics behavior; export runs profiling first (its dissolved layer
# consumes cluster_profiles).
_STAGE_TAILS: dict[str, list[str]] = {
    "clustering": [],
    "profiling": ["profiling"],
    "export": ["profiling", "export"],
    "metrics": ["metrics"],
}


# Which stage produces each context key a SNIC input band can name. Keys match
# SnicInputBand.source; `s2_composite` comes from data_load, which always runs.
_SNIC_SOURCE_STAGE: dict[str, str] = {
    "s2_composite": "data_load",
    "optical_features": "features_optical",
    "radar_features": "features_radar",
    "structure_features": "features_structure",
    "static_features": "features_static",
    "embedding_features": "features_embedding",
}

# Canonical order of the feature stages. Membership is computed per config; this
# only fixes the order, so that two runs needing the same set run it the same way.
_FEATURE_STAGE_ORDER: list[str] = [
    "features_optical",
    "features_radar",
    "features_structure",
    "features_static",
    "features_embedding",
]


def default_stage_names(config: Config, through: str = "metrics") -> list[str]:
    """Canonical stage order for a config, up to and including `through`.

    Which feature stages run is the union of what the run's three independent
    consumers ask for:

      - clustering, via `clustering.feature_source`: "handcrafted" pulls
        optical + radar + structure + static; "embedding" pulls only
        features_embedding.
      - segmentation, via `segmentation.input_bands`, which names its sources.
      - merge, via `merge.criteria`, which names its sources.

    Segmentation is NOT held identical across arms any more. Under the merge
    design, SNIC plus merge produces the stand, so each arm segments on its own
    feature space and the resulting stand maps are compared directly, and the
    stage list has to follow the config rather than a hardcoded branch.

    The *merge rule* is held identical across arms, which is why an embedding
    run still needs the hand-crafted structure/optical stages: "what makes two
    adjacent patches one stand" is a fact about forestry, not about the sensor
    pipeline, and holding it constant is what leaves delineation as the only
    thing differing between the arms.

    `through` selects the post-clustering tail: "clustering" (stop there),
    "profiling", "export" (profiling then export), or "metrics" (default).
    The inspect scripts each pass the tail they need; this helper is the one
    place the feature-source branch lives. Callers must still import the stage
    modules so `@register_stage` has run (see the inspect scripts).
    """
    if through not in _STAGE_TAILS:
        raise ValueError(
            f"through must be one of {sorted(_STAGE_TAILS)}, got {through!r}"
        )
    if config.clustering.feature_source == "embedding":
        needed = {"features_embedding"}
    else:
        needed = {
            "features_optical",
            "features_radar",
            "features_structure",
            "features_static",
        }
    needed |= _feature_stages_for(config.segmentation.input_sources())
    if config.merge.enabled:
        needed |= _feature_stages_for(config.merge.input_sources())
    feature_stages = [s for s in _FEATURE_STAGE_ORDER if s in needed]
    return [
        "masking",
        "data_load",
        *feature_stages,
        "segmentation",
        *(["merge"] if config.merge.enabled else []),
        "clustering",
        *_STAGE_TAILS[through],
    ]


def _feature_stages_for(sources: set[str]) -> set[str]:
    """Feature stages that produce these context keys.

    `data_load` is filtered out rather than returned: it always runs, and it is
    not in `_FEATURE_STAGE_ORDER`, so leaving it in would silently drop out of
    the ordered list anyway.
    """
    return {
        _SNIC_SOURCE_STAGE[s] for s in sources if _SNIC_SOURCE_STAGE[s] != "data_load"
    }


def segmentation_stage_names(config: Config) -> list[str]:
    """Stages needed to reach segmentation, and no further.

    `default_stage_names(through=...)` always includes clustering, because every
    tail it offers sits downstream of it. `inspect_segmentation.py` wants to
    stop earlier, and must not hardcode its own list -- which stages SNIC needs
    now depends on `segmentation.input_bands`, so a hardcoded list silently
    breaks any arm that segments on something else.

    Only segmentation's own sources are included: a baseline inspect run has no
    reason to pay for features_static, which nothing upstream of SNIC reads.
    """
    needed = _feature_stages_for(config.segmentation.input_sources())
    return [
        "masking",
        "data_load",
        *[s for s in _FEATURE_STAGE_ORDER if s in needed],
        "segmentation",
    ]


@dataclass
class StageRecord:
    name: str
    elapsed_sec: float
    produced: list[str]
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    cache_status: dict[str, str] = field(default_factory=dict)  # key -> "hit" / "miss-exported" / "off"
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
            Off by default; turn on for normal runs that need shareable
            assets / fast visualization. Tests should leave this off.
    """

    def __init__(self, stage_names: list[str], use_cache: bool = False) -> None:
        if not stage_names:
            raise ValueError("Pipeline must have at least one stage.")
        self.stage_names = list(stage_names)
        # eager resolution: typos in stage names fail now, not after 10 min of GEE work
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
        log.info("Stages: %s", " -> ".join(self.stage_names))
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

        log.info("stage: %s", name)
        log.debug("  requires: %s", sorted(stage.required_inputs))
        log.debug("  produces: %s", sorted(stage.produces))

        t0 = time.perf_counter()
        cache_status: dict[str, str] = {}
        export_tasks: list[ExportTaskInfo] = []
        cached_outputs: dict[str, Any] = {}

        # Which produces are cacheable as GEE assets?
        # - cacheable_outputs is the truth: if any class in the MRO declares
        #   it (including the empty set, meaning "nothing cacheable, always
        #   run, results live in memory only"), honor that declaration.
        # - If NO class between the concrete stage and Stage declares it, the
        #   stage didn't customize at all; default to caching everything in
        #   produces (preserves the original behavior for image-only stages).
        # Walking the MRO instead of checking only `stage.__class__.__dict__`
        # is critical: subclasses (e.g., the smoke test's _SmokeExport) inherit
        # the parent's cacheable_outputs through MRO but don't redeclare it
        # in their own __dict__.
        cacheable = self._resolve_cacheable_outputs(stage)

        try:
            stage.validate(ctx, config)

            # Try cache-first if enabled
            if self.use_cache:
                cached_outputs = self._try_load_cache(stage, config, cache_status, cacheable)
                # Skip the live run only if every produces key is cacheable AND
                # every cacheable key actually hit. Empty cacheable set never skips.
                all_cacheable_hit = (
                    cacheable
                    and len(cached_outputs) == len(cacheable)
                    and cacheable == stage.produces
                )
                if all_cacheable_hit:
                    log.info("  [cache] all %d outputs hit; skipping stage run", len(cached_outputs))
                    for key, value in cached_outputs.items():
                        ctx.set(key, value)
                    elapsed = time.perf_counter() - t0
                    log.info("stage %s done in %.2f sec (from cache)", name, elapsed)
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
            for key, cached_image in cached_outputs.items():
                final_outputs[key] = cached_image

            for key, value in final_outputs.items():
                ctx.set(key, value)

            # Submit exports for any cacheable outputs that missed
            if self.use_cache:
                export_tasks = self._submit_exports(
                    stage, config, ctx, final_outputs, cache_status, cacheable
                )

        except Exception as e:
            # Stage failure: log, then re-raise. We intentionally do NOT try
            # to clean up partial context state. Pipelines are one-shot, and
            # the next run starts with a fresh context anyway. We also leave
            # any in-flight export tasks alone; GEE handles its own task
            # cleanup, and orphaned exports cost the user nothing.
            elapsed = time.perf_counter() - t0
            log.error("stage %s FAILED after %.2f sec: %s", name, elapsed, e)
            raise

        elapsed = time.perf_counter() - t0

        for w in stage_result.warnings:
            log.warning("  [%s] %s", name, w)

        log.info("stage %s done in %.2f sec", name, elapsed)

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

    @staticmethod
    def _resolve_cacheable_outputs(stage: Stage) -> set[str]:
        """Resolve a stage's cacheable_outputs declaration via MRO walk.

        Returns the first `cacheable_outputs` set declared in any class
        between the concrete stage class and the base Stage (exclusive).
        If no override is found, defaults to the stage's `produces` set
        (preserving the historical "cache everything by default" behavior
        for image-only stages).

        Walking the MRO is necessary because test subclasses and other
        derived classes inherit cacheable_outputs through the chain
        without redeclaring it in their own __dict__.
        """
        for klass in type(stage).__mro__:
            if klass is Stage:
                # Reached the base class without finding an override
                break
            if "cacheable_outputs" in klass.__dict__:
                return klass.__dict__["cacheable_outputs"]
        return stage.produces

    def _try_load_cache(
        self,
        stage: Stage,
        config: Config,
        cache_status: dict[str, str],
        cacheable: set[str],
    ) -> dict[str, Any]:
        """Check which cacheable outputs exist in cache.

        Returns a dict of loaded outputs (possibly empty if none hit).
        Mutates cache_status with "hit" / "miss" per cacheable key.
        Non-cacheable keys are not checked.
        """
        outputs: dict[str, Any] = {}
        fingerprint = config_fingerprint(config)
        for key in sorted(cacheable):
            path = cached_asset_path(config.name, stage.name, key, fingerprint)
            if asset_exists(path):
                cache_status[key] = "hit"
                outputs[key] = load_cached_image(path)
                log.debug("  [cache] hit:  %s at %s", key, path)
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

        if not ctx.has("roi"):
            log.warning(
                "  [cache] cannot export; `roi` not in context, skipping export."
            )
            return []
        roi = ctx.get("roi")
        if not isinstance(roi, ee.Geometry):
            log.warning(
                "  [cache] cannot export; `roi` in context isn't an ee.Geometry, "
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
                    "  [cache] skipping export of %s: declared cacheable but not an ee.Image (got %s)",
                    key, type(image).__name__,
                )
                continue
            path = cached_asset_path(
                config.name, stage.name, key, config_fingerprint(config)
            )
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
