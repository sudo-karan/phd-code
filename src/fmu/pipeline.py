"""Pipeline orchestrator. Walks registered stages, manages context, writes manifest."""

from __future__ import annotations

import hashlib
import json
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from fmu.config import Config
from fmu.stages.base import (
    PipelineContext,
    Stage,
    StageResult,
    get_stage_class,
    list_registered_stages,
)
from fmu.utils.caching import (
    CACHE_LAYOUTS,
    INPUT_IMAGES_PROPERTY,
    LEGACY_LAYOUT,
    PER_STEP_LAYOUT,
    ExportTaskInfo,
    active_layout,
    asset_exists,
    cache_key,
    cached_asset_path,
    config_fingerprint,
    input_images_record,
    layout_in_use,
    load_cached_image,
    load_cached_table,
    start_export,
    start_table_export,
)
from fmu.utils.gee import safe_get_info
from fmu.utils.grid import analysis_grid_export_args
from fmu.utils.logging import get_logger
from fmu.utils.provenance import environment_state, git_state, git_state_now

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
    # The k elbow (round 9): cached, not part of any default run.
    "k_elbow": ["k_elbow"],
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

# Stages whose run() submits Earth Engine tasks itself, outside the cache exports
# the orchestrator controls: the export stage starts its Drive exports directly.
# `Pipeline(..., submit_exports=False)` refuses these, because it could not keep
# its promise with one of them in the run.
_SUBMITS_OWN_TASKS: frozenset[str] = frozenset({"export"})

# The image ids of an input collection are listed in the manifest when there are
# at most this many; a longer list is given by its count and SHA-256 there, and
# in full in the run folder's input_images.json.
_INPUT_IDS_LISTED_UP_TO = 100

# The order cache_layout_for looks for legacy assets in: the pipeline's own stages
# first, as a run makes them, then any other registered stage.
_PIPELINE_ORDER: tuple[str, ...] = (
    "masking", "data_load", *_FEATURE_STAGE_ORDER, "segmentation", "clustering",
)


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


def feature_stage_names(config: Config) -> list[str]:
    """masking, data_load and every feature stage a full run of the config needs.

    The first pass of a batch run (round 9, issue #44 item 2): every feature stage
    is cached before the first pass that reads any of them, segmentation's and the
    merge's and clustering's alike, so that no later pass computes a feature image
    live that another pass reads from the cache. `segmentation_stage_names` has
    only segmentation's own; this has the union `default_stage_names` takes.
    """
    full = default_stage_names(config, through="clustering")
    return [n for n in full if n in ("masking", "data_load", *_FEATURE_STAGE_ORDER)]


def cache_layout_for(config: Config) -> tuple[str, str]:
    """Which cache layout a config's cached assets are in, and why.

    The legacy layout if the cache holds an asset of that layout for any
    cacheable output of any registered stage (the asset made under the config's
    legacy fingerprint, `config_fingerprint`), the per-step layout otherwise. A
    config run before round 9 therefore goes on reading the assets it made, and
    is written to as it always was; a config never run, or whose legacy assets
    have all been deleted, gets the per-step layout: per-step keys, and assets
    on the analysis grid (fmu.utils.caching).

    Up to one small request per cacheable output (about fifteen for a config with
    no legacy asset), stopping at the first asset found.
    """
    fingerprint = config_fingerprint(config)
    registered = list_registered_stages()
    order = [n for n in _PIPELINE_ORDER if n in registered]
    order += [n for n in registered if n not in order]
    for stage_name in order:
        stage = get_stage_class(stage_name)()
        for key in sorted(Pipeline._resolve_cacheable_outputs(stage)):
            path = cached_asset_path(config.name, stage_name, key, fingerprint)
            if asset_exists(path):
                return LEGACY_LAYOUT, f"its cache holds an asset of the legacy layout: {path}"
    return PER_STEP_LAYOUT, "its cache holds no asset of the legacy layout"


def cache_asset_path_for(config: Config, stage_name: str, key: str, layout: str) -> str:
    """The asset path of one cacheable output of a stage, under a cache layout."""
    return cached_asset_path(config.name, stage_name, key, cache_key(config, stage_name, layout))


# Layouts found by current_cache_key, per config, for the life of the process.
_found_layouts: dict[tuple[str, str], str] = {}


def current_cache_key(config: Config, stage_name: str) -> str:
    """The key of a stage's cached assets in the layout the config uses.

    Inside a pipeline run, the run's layout; outside one (a script naming a
    config's assets), the layout `cache_layout_for` finds, asked once per config
    per process.
    """
    layout = active_layout(config)
    if layout is None:
        memo = (config.name, config_fingerprint(config))
        if memo not in _found_layouts:
            _found_layouts[memo] = cache_layout_for(config)[0]
        layout = _found_layouts[memo]
    return cache_key(config, stage_name, layout)


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
    # key -> "hit" (read from the cache) / "miss-exported" (computed live, export
    # submitted) / "miss" (computed live, nothing submitted). Empty with caching off.
    cache_status: dict[str, str] = field(default_factory=dict)
    # The cache exports the orchestrator submitted for this stage's outputs. Tasks a
    # stage submits itself (the export stage's Drive files) are not here: they are in
    # its metadata, and nothing waits on them (review C39).
    export_tasks: list[dict[str, str]] = field(default_factory=list)
    # The stage's transparency declaration, filled in: its display layers (with
    # the cache asset each belongs at, when caching is on) and its summary numbers.
    transparency: dict[str, Any] = field(default_factory=dict)
    # What follows `__` in the names of the stage's cached assets in this run's
    # cache layout. None with caching off, and for a stage that caches nothing.
    cache_key: str | None = None
    # The images of each input collection the stage's outputs were made from,
    # per cacheable output (or under "live" with caching off): computed in this
    # run, or read from the cached asset (Stage.input_collections). Empty for a
    # stage that names no input collection.
    input_images: dict[str, Any] = field(default_factory=dict)
    # The files the stage handed over (StageResult.files, round 14), written into the
    # run folder: file name -> {"bytes", "sha256"}. Empty for a stage that wrote none.
    files: dict[str, dict[str, Any]] = field(default_factory=dict)


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
        submit_exports: only matters with `use_cache=True`. True (default) is
            the behaviour described above. False reads the cache without
            writing to it: cached outputs are still read and used, outputs
            that miss are computed live and used for this run, and no export
            task is submitted and no asset folder is created. Their
            `cache_status` stays "miss" and `export_tasks` is empty. For
            scripts that read an existing cached run (maps, inspectors,
            reproducibility checks) and must add nothing to the task queue.
            It covers the orchestrator's cache exports only, so a stage that
            submits tasks of its own (see `_SUBMITS_OWN_TASKS`) is refused
            here rather than run.
        summaries: if True (default), call each stage's `summarise()` after it
            has run and write the declared summary numbers into the manifest.
            Turn off to skip the Earth Engine round trips they can cost
            (masking's is one reduction over the ROI).
        cache_layout: only matters with `use_cache=True`. "auto" (default)
            takes the layout the config's cache is in (`cache_layout_for`):
            "legacy" for a config run before round 9, "per_step" otherwise.
            Giving one of the two names it instead (for tests, and for a tool
            that must read one layout whatever is there).
    """

    def __init__(
        self,
        stage_names: list[str],
        use_cache: bool = False,
        *,
        submit_exports: bool = True,
        summaries: bool = True,
        cache_layout: str = "auto",
    ) -> None:
        if not stage_names:
            raise ValueError("Pipeline must have at least one stage.")
        if cache_layout != "auto" and cache_layout not in CACHE_LAYOUTS:
            raise ValueError(
                f"cache_layout must be 'auto' or one of {CACHE_LAYOUTS}, got {cache_layout!r}"
            )
        self.stage_names = list(stage_names)
        # eager resolution: typos in stage names fail now, not after 10 min of GEE work
        self.stage_classes: list[type[Stage]] = [get_stage_class(n) for n in stage_names]
        self.use_cache = use_cache
        self.submit_exports = submit_exports
        self.summaries = summaries
        self.cache_layout = cache_layout
        # Set at the start of every run().
        self._layout: str | None = None
        self._layout_reason: str | None = None
        self._grid_args: dict[str, Any] | None = None
        self._input_image_lists: dict[str, dict[str, list[str]]] = {}
        # The run folder of the run in progress, where stages' files go (round 14).
        self._run_dir: Path | None = None
        if not submit_exports:
            own = sorted(set(self.stage_names) & _SUBMITS_OWN_TASKS)
            if own:
                raise ValueError(
                    f"submit_exports=False promises a run that submits no Earth "
                    f"Engine task, but stage(s) {own} submit their own and the "
                    f"orchestrator cannot stop them. Leave them out of this run."
                )

    def run(
        self,
        config: Config,
        run_dir: Path,
        initial_context: PipelineContext | None = None,
    ) -> PipelineResult:
        ctx = initial_context if initial_context is not None else PipelineContext()
        result = PipelineResult(config_name=config.name, run_dir=run_dir)
        self._run_dir = run_dir
        # Which code ran: asked now, before any stage, so that the manifest's `git` (and the
        # export stage's) is the tree this run started from, not one changed while it ran
        # (fmu.utils.provenance remembers the first answer; review C32, round 13).
        git_state()

        log.info("=" * 60)
        log.info("Pipeline run: %s", config.name)
        log.info("Stages: %s", " -> ".join(self.stage_names))
        log.info("Run directory: %s", run_dir)

        self._layout, self._layout_reason = None, None
        self._grid_args = None
        self._input_image_lists = {}
        if self.use_cache:
            if self.cache_layout == "auto":
                self._layout, self._layout_reason = cache_layout_for(config)
            else:
                self._layout, self._layout_reason = self.cache_layout, "given to Pipeline()"
            log.info("Cache layout: %s (%s)", self._layout, self._layout_reason)
        log.info("=" * 60)

        t0 = time.perf_counter()
        with layout_in_use(config, self._layout) if self._layout else nullcontext():
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
        if self._input_image_lists:
            # Every id, however many: the manifest lists only short lists.
            (run_dir / "input_images.json").write_text(
                json.dumps(self._input_image_lists, indent=1, sort_keys=True)
            )

        return result

    def _cache_key(self, config: Config, stage_name: str) -> str:
        """The key of a stage's cached assets in this run's layout."""
        if self._layout is None:
            raise RuntimeError("no cache layout outside a run with use_cache=True")
        return cache_key(config, stage_name, self._layout)

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
                    transparency, summary_warnings = self._transparency(
                        stage, ctx, config, cacheable, cache_status
                    )
                    input_images = self._recorded_input_images(stage, cached_outputs)
                    elapsed = time.perf_counter() - t0
                    log.info("stage %s done in %.2f sec (from cache)", name, elapsed)
                    return StageRecord(
                        name=name,
                        elapsed_sec=elapsed,
                        produced=sorted(cached_outputs.keys()),
                        warnings=summary_warnings,
                        metadata={"source": "cache"},
                        cache_status=cache_status,
                        export_tasks=[],
                        transparency=transparency,
                        cache_key=self._cache_key(config, name),
                        input_images=input_images,
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

            # The stage's result files, written now, so that a later stage that fails
            # does not lose them (round 14).
            files = self._write_stage_files(name, stage_result.files)

            # For cacheable outputs that hit cache, swap in the cached version
            # so downstream stages and exports use the persisted asset.
            final_outputs = dict(stage_result.outputs)
            for key, cached_image in cached_outputs.items():
                final_outputs[key] = cached_image

            for key, value in final_outputs.items():
                ctx.set(key, value)

            # Which images the outputs computed now were made from, and, for any
            # output read from the cache, what its asset says it was made from.
            computed_now = {
                k for k in (cacheable if self.use_cache else {"live"})
                if cache_status.get(k) != "hit"
            }
            live_images, live_summary = (
                self._live_input_images(stage, ctx, config, name) if computed_now else ({}, {})
            )
            input_images = {
                **({k: live_images for k in sorted(computed_now)} if live_images else {}),
                **self._recorded_input_images(stage, cached_outputs),
            }

            # Submit exports for any cacheable outputs that missed
            if self.use_cache and self.submit_exports:
                export_tasks = self._submit_exports(
                    stage, config, ctx, final_outputs, cache_status, cacheable,
                    input_images_summary=live_summary,
                )
            elif self.use_cache:
                # Read-only run: the misses were computed live above and stay
                # "miss". Nothing is submitted and no folder is created.
                missed = sorted(k for k, v in cache_status.items() if v == "miss")
                if missed:
                    log.info(
                        "  [cache] submit_exports is off: computed live and not "
                        "exported: %s", missed,
                    )

            transparency, summary_warnings = self._transparency(
                stage, ctx, config, cacheable, cache_status
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
            warnings=[*stage_result.warnings, *summary_warnings],
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
            transparency=transparency,
            # None for a stage that caches nothing: no asset carries its key.
            cache_key=self._cache_key(config, name) if self.use_cache and cacheable else None,
            input_images=input_images,
            files=files,
        )

    def _write_stage_files(self, stage_name: str, files: dict[str, str]) -> dict[str, dict[str, Any]]:
        """Write a stage's result files into the run folder: {name: {"bytes", "sha256"}}.

        A name must be a plain file name, new in the folder: not a path, not manifest.json or
        input_images.json, and not one an earlier stage of the run wrote.
        """
        written: dict[str, dict[str, Any]] = {}
        if not files:
            return written
        if self._run_dir is None:
            raise RuntimeError("a stage's files can be written only during Pipeline.run")
        for file_name in sorted(files):
            if (
                not file_name
                or file_name in (".", "..", "manifest.json", "input_images.json")
                or Path(file_name).name != file_name
            ):
                raise ValueError(
                    f"Stage {stage_name!r}: file name {file_name!r} is not a plain file name "
                    f"for the run folder"
                )
            path = self._run_dir / file_name
            if path.exists():
                raise ValueError(f"Stage {stage_name!r}: {file_name} is already in the run folder")
            data = files[file_name].encode()
            path.write_bytes(data)
            written[file_name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            log.info("  wrote %s (%d bytes)", file_name, len(data))
        return written

    @staticmethod
    def _names_input_collections(stage: Stage) -> bool:
        return type(stage).input_collections is not Stage.input_collections

    def _live_input_images(
        self, stage: Stage, ctx: PipelineContext, config: Config, name: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """The record of the stage's input images, computed now, and its short form.

        One request per stage: the ids of every input collection it names, read
        together. The record goes in the manifest (ids listed when there are at
        most _INPUT_IDS_LISTED_UP_TO), the full lists in the run folder, and the
        short form (count and SHA-256 per collection) onto every asset the stage
        exports in the per-step layout. A failure is recorded, never raised: the
        stage's products are already made.
        """
        if not self._names_input_collections(stage):
            return {}, {}
        try:
            collections = stage.input_collections(ctx, config)
            if not collections:
                return {}, {}
            import ee

            ids = safe_get_info(
                ee.Dictionary(
                    {n: ee.ImageCollection(c).aggregate_array("system:id")
                     for n, c in collections.items()}
                ),
                context=f"{name} input image ids",
            )
        except Exception as e:  # noqa: BLE001 - recorded in the manifest, see docstring
            msg = f"input image ids not read: {type(e).__name__}: {e}"
            log.warning("  [%s] %s", name, msg)
            return {"source": "computed in this run", "error": msg}, {}
        ids = {n: [str(i) for i in (v or [])] for n, v in ids.items()}
        self._input_image_lists[name] = ids
        record = input_images_record(ids, list_up_to=_INPUT_IDS_LISTED_UP_TO)
        for n, r in record.items():
            log.info("  input images, %s: %d (sha256 %s)", n, r["count"], r["sha256"][:12])
        summary = {n: {"count": r["count"], "sha256": r["sha256"]} for n, r in record.items()}
        return {"source": "computed in this run", "collections": record}, summary

    def _recorded_input_images(
        self, stage: Stage, cached_outputs: dict[str, Any]
    ) -> dict[str, Any]:
        """What each cached output's asset says its input images were.

        Only for a stage that names input collections, so a stage that names
        none costs nothing; one request for all of a stage's cached outputs. An
        asset made before round 9, or in the legacy layout, carries no record.
        """
        if not cached_outputs or not self._names_input_collections(stage):
            return {}
        try:
            import ee

            raw = safe_get_info(
                ee.Dictionary(
                    {k: v.get(INPUT_IMAGES_PROPERTY) for k, v in sorted(cached_outputs.items())}
                ),
                context=f"{stage.name} input images of the cached assets",
            )
        except Exception as e:  # noqa: BLE001 - recorded in the manifest, never raised
            return {
                k: {"source": "the cached asset", "error": f"{type(e).__name__}: {e}"}
                for k in sorted(cached_outputs)
            }
        out: dict[str, Any] = {}
        for k in sorted(cached_outputs):
            value = (raw or {}).get(k)
            if not value:
                out[k] = {
                    "source": "the cached asset",
                    "not_recorded": "the asset carries no record of its input images "
                    "(made before round 9, or in the legacy layout)",
                }
                continue
            try:
                out[k] = {"source": "the cached asset", "collections": json.loads(value)}
            except (TypeError, ValueError):
                out[k] = {"source": "the cached asset", "error": f"unreadable record: {value!r}"[:300]}
        return out

    def _transparency(
        self,
        stage: Stage,
        ctx: PipelineContext,
        config: Config,
        cacheable: set[str],
        cache_status: dict[str, str],
    ) -> tuple[dict[str, Any], list[str]]:
        """Fill in a stage's transparency declaration for the manifest.

        Returns the record and any warnings. Runs after the stage's outputs are
        in the context, so it is the same whether they were computed or read
        from the cache.

        Each display layer is recorded with the cache asset it belongs at and
        that asset's status for this run ("hit", "miss-exported" or "miss"), so
        a reader knows whether there is an asset to draw from: under "miss"
        there is none, and under "miss-exported" not until the task finishes.
        Both are None when caching is off or the key is not cacheable.

        A summary that fails is recorded and warned about, never raised. That
        covers an Earth Engine timeout or memory limit on the reduction, any
        other exception inside `summarise()`, and a `summarise()` that returns
        other names than the stage declared. The stage's products are already
        in the context by now, and when caching is on their exports are already
        submitted; a run must not lose them, or the record of those tasks, to a
        failed report about them. The fast tests are where a wrong `summarise()`
        is made to fail loudly.
        """
        layers: list[dict[str, Any]] = []
        for layer in stage.display_layers:
            entry = layer.to_manifest()
            cached = self.use_cache and layer.key in cacheable
            entry["asset"] = (
                cached_asset_path(
                    config.name, stage.name, layer.key, self._cache_key(config, stage.name)
                )
                if cached
                else None
            )
            entry["asset_status"] = cache_status.get(layer.key) if cached else None
            layers.append(entry)

        record: dict[str, Any] = {"display_layers": layers, "summary_numbers": []}
        declared = [s.name for s in stage.summary_numbers]
        if not declared:
            return record, []
        if not self.summaries:
            record["summary_skipped"] = "Pipeline(summaries=False)"
            return record, []

        def failed(why: str) -> tuple[dict[str, Any], list[str]]:
            msg = f"summary numbers not computed: {why}"
            log.warning("  [%s] %s", stage.name, msg)
            record["summary_error"] = msg
            return record, [msg]

        try:
            values = stage.summarise(ctx, config)
        except Exception as e:  # noqa: BLE001 - recorded in the manifest, see docstring
            return failed(f"{type(e).__name__}: {e}")
        if not isinstance(values, dict) or set(values) != set(declared):
            returned = (
                sorted(str(k) for k in values)
                if isinstance(values, dict)
                else f"a {type(values).__name__}"
            )
            return failed(
                f"summarise() returned {returned}, but the stage declares "
                f"{sorted(declared)}"
            )

        record["summary_numbers"] = [
            {
                "name": s.name,
                "description": s.description,
                "unit": s.unit,
                "value": _json_safe(values[s.name]),
            }
            for s in stage.summary_numbers
        ]
        return record, []

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
        key_suffix = self._cache_key(config, stage.name)
        tables = type(stage).table_outputs
        for key in sorted(cacheable):
            path = cached_asset_path(config.name, stage.name, key, key_suffix)
            if asset_exists(path):
                cache_status[key] = "hit"
                outputs[key] = load_cached_table(path) if key in tables else load_cached_image(path)
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
        *,
        input_images_summary: dict[str, Any] | None = None,
    ) -> list[ExportTaskInfo]:
        """Submit async export tasks for cacheable outputs that missed the cache.

        In the per-step layout an image goes onto the analysis grid (the ROI's
        UTM zone at export.analysis_scale_m), the grid segmentation works on, and
        carries the count and SHA-256 of its input images as a property; in the
        legacy layout it is exported as before round 9, with the scale alone. A
        table output (`Stage.table_outputs`) is exported as a table.
        """
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
        per_step = self._layout == PER_STEP_LAYOUT
        tables = type(stage).table_outputs
        for key, image in outputs.items():
            if key not in cacheable:
                continue
            if cache_status.get(key) == "hit":
                continue
            path = cached_asset_path(config.name, stage.name, key, self._cache_key(config, stage.name))
            description = f"{config.name}_{stage.name}_{key}"
            if key in tables:
                if not isinstance(image, ee.FeatureCollection):
                    log.warning(
                        "  [cache] skipping export of %s: declared a table output but not an "
                        "ee.FeatureCollection (got %s)", key, type(image).__name__,
                    )
                    continue
                task = start_table_export(image, asset_path=path, description=description)
            elif not isinstance(image, ee.Image):
                log.warning(
                    "  [cache] skipping export of %s: declared cacheable but not an ee.Image (got %s)",
                    key, type(image).__name__,
                )
                continue
            elif per_step:
                if self._grid_args is None:
                    self._grid_args = analysis_grid_export_args(
                        roi, config.export.analysis_scale_m
                    )
                    log.info("  [cache] exports on the analysis grid: %s", self._grid_args)
                if input_images_summary:
                    # A cast, not ee.Image(...): Element.set() is typed as
                    # returning Element, and the value is the same image.
                    image = cast(
                        ee.Image,
                        image.set(
                            INPUT_IMAGES_PROPERTY,
                            json.dumps(input_images_summary, sort_keys=True),
                        ),
                    )
                task = start_export(
                    image=image,
                    asset_path=path,
                    roi=roi,
                    scale=config.export.analysis_scale_m,
                    description=description,
                    **self._grid_args,
                )
            else:
                task = start_export(
                    image=image,
                    asset_path=path,
                    roi=roi,
                    scale=10,
                    description=description,
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
            # How the run was asked to treat the asset cache and the summaries,
            # as given to Pipeline(). submit_exports has no effect unless
            # use_cache is on.
            "use_cache": self.use_cache,
            "submit_exports": self.submit_exports,
            "summaries": self.summaries,
            # Which cache layout the run read and wrote (None with caching off),
            # and why: fmu.utils.caching, "Two cache layouts".
            "cache_layout": self._layout,
            "cache_layout_reason": self._layout_reason,
            # Which code ran: the commit of the checkout the fmu package was
            # imported from, and whether it had uncommitted changes, as the run
            # started (asked at the start of run()).
            "git": git_state(),
            # The same checkout read again as the manifest is written: a commit
            # or an edit made while the run ran shows as a difference (C32).
            "git_at_end": git_state_now(),
            # And in which Python environment (round 9).
            "environment": environment_state(),
            "stages": [
                {
                    "name": s.name,
                    "elapsed_sec": round(s.elapsed_sec, 3),
                    "produced": s.produced,
                    "warnings": s.warnings,
                    "metadata": _json_safe(s.metadata),
                    "cache_status": s.cache_status,
                    "cache_key": s.cache_key,
                    "export_tasks": s.export_tasks,
                    "transparency": _json_safe(s.transparency),
                    "input_images": _json_safe(s.input_images),
                    # Only for a stage that wrote files (round 14), so that every other
                    # stage's entry has the keys it always had.
                    **({"files": s.files} if s.files else {}),
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
