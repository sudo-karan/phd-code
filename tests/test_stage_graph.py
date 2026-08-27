"""Non-live structural test: does the stage graph actually connect?

Every other test here checks one stage in isolation. This one walks the real
canonical stage list for each shipped config, threading a context through it and
calling each stage's own `validate()` with only the keys earlier stages actually
declared. If any stage asks for something nothing upstream produces, this fails
-- without Earth Engine, without a run, and in CI.

That check has teeth now in a way it did not before. Four stages
(`segmentation`, `merge`, `clustering`, `metrics`) derive their real
requirements from config rather than from the static `required_inputs`, because
a class attribute cannot see the config. So the wiring is only as correct as
those four `validate()` methods agreeing with `default_stage_names()`, and
nothing else checks that agreement.

Deliberately NOT marked `live_gee`: the live tier needs auth and does not run in
CI, so an invariant that only the live tier pins is an invariant nothing pins.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# Importing the stage modules is what runs @register_stage.
import fmu.stages.clustering  # noqa: F401
import fmu.stages.data_load  # noqa: F401
import fmu.stages.export  # noqa: F401
import fmu.stages.features_embedding  # noqa: F401
import fmu.stages.features_optical  # noqa: F401
import fmu.stages.features_radar  # noqa: F401
import fmu.stages.features_static  # noqa: F401
import fmu.stages.features_structure  # noqa: F401
import fmu.stages.masking  # noqa: F401
import fmu.stages.merge  # noqa: F401
import fmu.stages.metrics  # noqa: F401
import fmu.stages.profiling  # noqa: F401
import fmu.stages.segmentation  # noqa: F401
from fmu.config import Config, load_config
from fmu.pipeline import default_stage_names, segmentation_stage_names
from fmu.stages.base import PipelineContext, _stage_registry, get_stage_class

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "configs"
SHIPPED_CONFIGS = sorted(CONFIG_DIR.glob("sanjay_van_*.yaml"))

# Snapshot taken at import, when every stage module above has registered.
# `test_pipeline.py` and `test_stages_base.py` legitimately empty the registry
# to test the registry itself, and pytest imports all modules before running any
# test -- so re-importing here would be a no-op against the module cache.
# Restoring the snapshot per test is what actually works.
_REGISTERED_STAGES = dict(_stage_registry)


@pytest.fixture(autouse=True)
def _restore_stage_registry():
    _stage_registry.clear()
    _stage_registry.update(_REGISTERED_STAGES)
    yield


def _walk(config: Config, stage_names: list[str]) -> PipelineContext:
    """Thread a context through the stage list, validating each stage.

    Values are placeholder strings: `validate()` inspects keys, never values.
    """
    ctx = PipelineContext()
    ctx.set("roi", "<roi>")  # the pipeline pre-populates this
    for name in stage_names:
        stage = get_stage_class(name)()
        stage.validate(ctx, config)
        for key in sorted(stage.produces):
            if not ctx.has(key):
                ctx.set(key, f"<{key}>")
    return ctx


@pytest.mark.parametrize("path", SHIPPED_CONFIGS, ids=lambda p: p.stem)
@pytest.mark.parametrize("through", ["clustering", "profiling", "export", "metrics"])
def test_every_stage_gets_what_it_asks_for(path: Path, through: str):
    """The whole graph, for every shipped config and every tail."""
    config = load_config(path)
    _walk(config, default_stage_names(config, through=through))


@pytest.mark.parametrize("path", SHIPPED_CONFIGS, ids=lambda p: p.stem)
def test_segmentation_only_list_is_self_sufficient(path: Path):
    """`inspect_segmentation.py` runs a shorter list; it has to close too."""
    config = load_config(path)
    _walk(config, segmentation_stage_names(config))


@pytest.mark.parametrize("path", SHIPPED_CONFIGS, ids=lambda p: p.stem)
def test_the_run_produces_the_stand_layer(path: Path):
    """SNIC + merge produces the stand -- so a full run must end up holding it."""
    config = load_config(path)
    ctx = _walk(config, default_stage_names(config))
    assert ctx.has(config.unit_label_key())
    assert config.unit_label_key() == "stand_clusters"


def test_disabling_merge_still_closes_the_graph():
    """The fallback path: no merge stage, everything downstream reduces over raw
    superpixels instead. It has to remain runnable, or `merge.enabled` is a
    switch that only breaks things."""
    raw = yaml.safe_load((CONFIG_DIR / "sanjay_van_baseline.yaml").read_text())
    raw["merge"] = {"enabled": False}
    config = Config.model_validate(raw)
    ctx = _walk(config, default_stage_names(config))
    assert not ctx.has("stand_clusters")
    assert ctx.has("snic_clusters")
    assert config.unit_label_key() == "snic_clusters"


def test_no_stage_declares_an_output_another_also_declares():
    """PipelineContext is write-once, so two stages producing the same key is a
    run-time KeyError halfway through a GEE run. Catch it here instead."""
    seen: dict[str, str] = {}
    for name in (
        "masking",
        "data_load",
        "features_optical",
        "features_radar",
        "features_structure",
        "features_static",
        "features_embedding",
        "segmentation",
        "merge",
        "clustering",
        "profiling",
        "export",
        "metrics",
    ):
        for key in get_stage_class(name).produces:
            assert key not in seen, f"{key} produced by both {seen[key]} and {name}"
            seen[key] = name


@pytest.mark.parametrize("path", SHIPPED_CONFIGS, ids=lambda p: p.stem)
def test_merge_runs_after_everything_its_criteria_need(path: Path):
    """The specific ordering the merge design depends on: the criteria bands
    have to exist before the gate reads them."""
    config = load_config(path)
    stages = default_stage_names(config)
    from fmu.pipeline import _SNIC_SOURCE_STAGE

    for source in config.merge.input_sources():
        producer = _SNIC_SOURCE_STAGE[source]
        assert producer in stages, (path.stem, source)
        assert stages.index(producer) < stages.index("merge"), (path.stem, source)


@pytest.mark.parametrize("path", SHIPPED_CONFIGS, ids=lambda p: p.stem)
def test_segmentation_runs_after_everything_its_bands_need(path: Path):
    config = load_config(path)
    stages = default_stage_names(config)
    from fmu.pipeline import _SNIC_SOURCE_STAGE

    for source in config.segmentation.input_sources():
        producer = _SNIC_SOURCE_STAGE[source]
        assert producer in stages, (path.stem, source)
        assert stages.index(producer) < stages.index("segmentation"), (
            path.stem,
            source,
        )


@pytest.mark.parametrize("path", SHIPPED_CONFIGS, ids=lambda p: p.stem)
def test_r2_attributes_are_available_when_metrics_runs(path: Path):
    """An r2 attribute from a stage this arm does not run would silently drop
    out of exactly one side of the comparison."""
    config = load_config(path)
    stages = default_stage_names(config)
    from fmu.pipeline import _SNIC_SOURCE_STAGE

    for source in config.metrics.input_sources():
        producer = _SNIC_SOURCE_STAGE[source]
        assert producer in stages, (path.stem, source)


def test_a_config_naming_an_unrun_r2_source_is_visible():
    """Not an error -- the metrics stage logs and skips rather than failing a
    long run at the last step -- but the graph walk should show the gap."""
    raw = yaml.safe_load((CONFIG_DIR / "sanjay_van_alphaearth.yaml").read_text())
    raw["metrics"]["r2_attributes"] = [
        {"source": "radar_features", "band": "vh_p50", "held_out": True}
    ]
    config = Config.model_validate(raw)
    from fmu.pipeline import _SNIC_SOURCE_STAGE

    stages = default_stage_names(config)
    # features_radar is not pulled in by an r2 attribute, by design: metrics is
    # a consumer, and making it drive the stage list would let a diagnostic
    # change what the experiment computes.
    assert _SNIC_SOURCE_STAGE["radar_features"] not in stages
