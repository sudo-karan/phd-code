"""The transparency contract: every step must have something to show for itself.

A stage declares display layers (context key, band, how to draw it, legend) and
summary numbers; the orchestrator writes both into the run manifest. See the top
of `fmu.stages.base`.

The contract is enforced stage by stage. `ENFORCED` names the stages that must
declare something today; `PENDING` names the ones that do not yet. Every
pipeline stage has to be in exactly one of the two, so a new stage cannot be
added without deciding, and a pending stage that gains a declaration has to be
moved to `ENFORCED` -- the list can only shrink.

What is tested here: which stages are bound, what masking and merge declare, the
arithmetic behind masking's numbers, and that the orchestrator carries a
declaration into the manifest. The checks on a single declaration (a legend
entry, a layer, a stage class) are in test_stages_base.py; the cache switches
are in test_pipeline.py.

No Earth Engine: these are class-level declarations and pure-Python arithmetic.
Where a test needs the masking stage to "run", its Earth Engine half is replaced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# Importing the stage modules is what runs @register_stage.
import fmu.stages.clustering  # noqa: F401
import fmu.stages.data_load  # noqa: F401
import fmu.stages.export  # noqa: F401
import fmu.stages.features_embedding  # noqa: F401
import fmu.stages.features_optical  # noqa: F401
import fmu.stages.features_radar  # noqa: F401
import fmu.stages.features_static  # noqa: F401
import fmu.stages.features_structure  # noqa: F401
import fmu.stages.masking as masking_module
import fmu.stages.merge  # noqa: F401
import fmu.stages.metrics  # noqa: F401
import fmu.stages.profiling  # noqa: F401
import fmu.stages.segmentation  # noqa: F401
from fmu.config import MaskingParams
from fmu.pipeline import Pipeline
from fmu.stages.base import (
    DisplayLayer,
    LegendEntry,
    PipelineContext,
    Stage,
    StageResult,
    SummaryNumber,
    _stage_registry,
    get_stage_class,
    register_stage,
    transparency_gaps,
)
from fmu.stages.masking import (
    _INDIASAT_REASON_CLASSES,
    _WORLDCOVER_REASON_CLASSES,
    REASON_BUILT_UP,
    REASON_CROPLAND,
    REASON_KEPT,
    REASON_NAMES,
    REASON_NO_DATA,
    REASON_OTHER,
    REASON_WATER,
    SOURCE_INDIASAT,
    SOURCE_NAMES,
    SOURCE_NONE,
    SOURCE_WORLDCOVER,
    MaskingStage,
    _reason_from_classes,
    tabulate_mask_provenance,
)

REPO_ROOT = Path(__file__).parent.parent

# Stages that must declare display layers or summary numbers.
ENFORCED = {"masking", "merge"}

# Stages that do not yet. Listed in the PR as pending; move a name to ENFORCED
# when its stage declares something.
PENDING = {
    "data_load",
    "features_optical",
    "features_radar",
    "features_structure",
    "features_static",
    "features_embedding",
    "segmentation",
    "clustering",
    "profiling",
    "export",
    "metrics",
}

# The pipeline's own stages, snapshotted at import, when every stage module
# above has registered. Other test modules empty the registry to test the
# registry itself, and may register stand-in stages of their own; only classes
# defined under fmu.stages count here.
_PIPELINE_STAGES = {
    name: cls
    for name, cls in _stage_registry.items()
    if cls.__module__.startswith("fmu.stages.")
}


@pytest.fixture(autouse=True)
def _restore_stage_registry():
    _stage_registry.clear()
    _stage_registry.update(_PIPELINE_STAGES)
    yield
    _stage_registry.clear()
    _stage_registry.update(_PIPELINE_STAGES)


# ---------------------------------------------------------------------
# Which stages the contract binds
# ---------------------------------------------------------------------


def test_every_stage_is_either_enforced_or_pending():
    assert not ENFORCED & PENDING
    listed = ENFORCED | PENDING
    assert set(_PIPELINE_STAGES) == listed, (
        "Every pipeline stage must be listed in ENFORCED or PENDING. "
        f"Unlisted: {sorted(set(_PIPELINE_STAGES) - listed)}. "
        f"Listed but not registered: {sorted(listed - set(_PIPELINE_STAGES))}."
    )


@pytest.mark.parametrize("name", sorted(ENFORCED))
def test_enforced_stage_declares_something(name: str):
    assert transparency_gaps(get_stage_class(name)) == []


@pytest.mark.parametrize("name", sorted(PENDING))
def test_pending_stage_is_really_pending(name: str):
    """A pending stage that now declares something belongs in ENFORCED."""
    cls = get_stage_class(name)
    assert not cls.display_layers and not cls.summary_numbers, (
        f"{name} now declares transparency outputs: move it from PENDING to "
        f"ENFORCED in this file."
    )


def test_the_check_fails_for_a_stage_that_declares_neither():
    """The rule itself, on a stand-in: this is what an enforced stage that
    declared nothing would trip."""

    class _Silent(Stage):
        name = "silent"
        produces = {"x"}

        def run(self, ctx: PipelineContext, config: Any) -> StageResult:
            return StageResult(outputs={"x": 1})

    gaps = transparency_gaps(_Silent)
    assert gaps and "neither display_layers nor summary_numbers" in gaps[0]


# ---------------------------------------------------------------------
# Masking: what it declares
# ---------------------------------------------------------------------


def _masking_layer(band: str) -> DisplayLayer:
    return next(layer for layer in MaskingStage.display_layers if layer.band == band)


def test_masking_declares_the_reason_and_source_layers():
    assert "mask_provenance" in MaskingStage.produces
    assert [(layer.key, layer.band) for layer in MaskingStage.display_layers] == [
        ("mask_provenance", "reason"),
        ("mask_provenance", "source"),
    ]


def test_masking_legend_says_it_is_a_habitat_mask():
    """The supervisor asked for the land-cover mask; it must not read as a
    forest mask, because it keeps shrubs and (in the fallback) grassland. The
    text sits in the legend note, which goes wherever the legend is drawn."""
    note = _masking_layer("reason").legend_note
    assert "habitat mask, not a strict forest mask" in note
    for kept in ("IndiaSAT Trees", "Shrubs/Scrub", "tree cover", "shrubland", "grassland"):
        assert kept in note
    assert "where IndiaSAT has no data" in note
    assert "docs/design_notes.md" in note
    # The kept class says so too, for a legend drawn without its note.
    kept_entry = next(e for e in _masking_layer("reason").legend if e.value == REASON_KEPT)
    assert "habitat" in kept_entry.label and "not only forest" in kept_entry.label


def test_the_section_the_legend_points_to_exists():
    """The note sends the reader to a section of docs/design_notes.md by name.
    If the section is renamed, the pointer has to follow."""
    note = _masking_layer("reason").legend_note
    heading = "Masking: IndiaSAT-primary, single-phase habitat"
    assert heading in note
    design_notes = (REPO_ROOT / "docs" / "design_notes.md").read_text()
    assert f"## {heading}\n" in design_notes


def test_the_classes_the_legend_names_are_the_schema_defaults():
    """The note says "by default it keeps" Trees and Shrubs/Scrub (IndiaSAT 6
    and 12) and tree cover, shrubland and grassland (WorldCover 10, 20, 30). If
    the defaults change, the wording has to change with them."""
    defaults = MaskingParams()
    assert defaults.indiasat_habitat_classes == [6, 12]
    assert defaults.keep_worldcover_classes == [10, 20, 30]
    assert "By default" in _masking_layer("reason").legend_note


def test_masking_legends_cover_every_code():
    assert {e.value for e in _masking_layer("reason").legend} == set(REASON_NAMES)
    assert {e.value for e in _masking_layer("source").legend} == set(SOURCE_NAMES)


def test_reason_and_source_codes_fit_the_summary_key():
    """The summary packs (disagrees, source, reason) into one integer as
    disagrees * 100 + source * 10 + reason, so each code needs one digit."""
    assert all(0 <= code <= 9 for code in REASON_NAMES)
    assert all(0 <= code <= 9 for code in SOURCE_NAMES)
    assert len(set(REASON_NAMES.values())) == len(REASON_NAMES)
    assert len(set(SOURCE_NAMES.values())) == len(SOURCE_NAMES)


@pytest.mark.parametrize(
    "groups", [_INDIASAT_REASON_CLASSES, _WORLDCOVER_REASON_CLASSES], ids=["indiasat", "worldcover"]
)
def test_reason_groups_are_removal_reasons_and_do_not_overlap(groups):
    assert set(groups) == {REASON_CROPLAND, REASON_BUILT_UP, REASON_WATER}
    classes = [c for members in groups.values() for c in members]
    assert len(classes) == len(set(classes)), "a class is listed under two reasons"


def test_indiasat_groups_match_the_documented_legend():
    """fmu.config.MaskingParams: water 2-4, crops 5/8-11, built-up 1. Barren (7)
    and orchard/plantation (13, docs/datasets.md) are in no group, so they come
    out as other non-habitat; the default habitat classes are in none either."""
    assert set(_INDIASAT_REASON_CLASSES[REASON_BUILT_UP]) == {1}
    assert set(_INDIASAT_REASON_CLASSES[REASON_WATER]) == {2, 3, 4}
    assert set(_INDIASAT_REASON_CLASSES[REASON_CROPLAND]) == {5, 8, 9, 10, 11}
    grouped = {c for members in _INDIASAT_REASON_CLASSES.values() for c in members}
    assert not grouped & {7, 13}
    assert not grouped & set(MaskingParams().indiasat_habitat_classes)


def test_worldcover_groups_match_the_dataset_class_table():
    """ESA WorldCover v200, from the class table on the Earth Engine asset:
    40 cropland, 50 built-up, 80 permanent water bodies. The repo itself only
    documents the kept classes, which are in no removal group."""
    assert set(_WORLDCOVER_REASON_CLASSES[REASON_CROPLAND]) == {40}
    assert set(_WORLDCOVER_REASON_CLASSES[REASON_BUILT_UP]) == {50}
    assert set(_WORLDCOVER_REASON_CLASSES[REASON_WATER]) == {80}
    grouped = {c for members in _WORLDCOVER_REASON_CLASSES.values() for c in members}
    assert not grouped & set(MaskingParams().keep_worldcover_classes)


class _RemapRecorder:
    """Stands in for an ee.Image: records the lookup table `remap` is given."""

    def remap(self, src: list[int], dst: list[int], default: int) -> _RemapRecorder:
        self.table = dict(zip(src, dst, strict=True))
        self.default = default
        return self


@pytest.mark.parametrize(
    "groups", [_INDIASAT_REASON_CLASSES, _WORLDCOVER_REASON_CLASSES], ids=["indiasat", "worldcover"]
)
def test_reason_remap_sends_each_class_to_its_reason_and_the_rest_to_other(groups):
    recorder = _RemapRecorder()
    assert _reason_from_classes(recorder, groups) is recorder  # type: ignore[arg-type]
    assert recorder.table == {
        cls: reason for reason, members in groups.items() for cls in members
    }
    assert recorder.default == REASON_OTHER
    # Kept and no-data are never produced by the class lookup: kept comes from
    # the habitat decision itself, no-data from the absence of both maps.
    assert REASON_KEPT not in recorder.table.values()
    assert REASON_NO_DATA not in recorder.table.values()


# ---------------------------------------------------------------------
# Masking summary arithmetic (the Earth Engine call returns area per key)
# ---------------------------------------------------------------------


def _key(reason: int, source: int, disagrees: int = 0) -> int:
    return disagrees * 100 + source * 10 + reason


def test_tabulate_mask_provenance_shares_and_sources():
    out = tabulate_mask_provenance(
        {
            _key(REASON_KEPT, SOURCE_INDIASAT): 60_000.0,
            _key(REASON_KEPT, SOURCE_WORLDCOVER): 10_000.0,
            _key(REASON_CROPLAND, SOURCE_INDIASAT): 20_000.0,
            _key(REASON_BUILT_UP, SOURCE_WORLDCOVER): 10_000.0,
        }
    )
    assert out["area_ha"] == 10.0
    assert out["share_kept"] == 0.7
    assert out["share_by_reason"] == {
        "no_data": 0.0, "kept": 0.7, "cropland": 0.2, "built_up": 0.1,
        "water": 0.0, "other_non_habitat": 0.0,
    }
    assert out["share_kept_by_source"] == {
        "none": 0.0, "indiasat": 0.6, "worldcover": 0.1,
    }
    assert out["share_decided_by_source"] == {
        "none": 0.0, "indiasat": 0.8, "worldcover": 0.2,
    }
    assert out["area_ha_by_reason_and_source"]["kept"] == {
        "none": 0.0, "indiasat": 6.0, "worldcover": 1.0,
    }
    assert out["area_ha_by_reason_and_source"]["built_up"]["worldcover"] == 1.0
    assert out["area_ha_reason_disagrees_with_habitat_mask"] == 0.0


def test_tabulate_mask_provenance_parts_add_up():
    out = tabulate_mask_provenance(
        {
            _key(REASON_KEPT, SOURCE_INDIASAT): 123_456.7,
            _key(REASON_WATER, SOURCE_INDIASAT): 7_654.3,
            _key(REASON_OTHER, SOURCE_WORLDCOVER): 1_111.1,
            _key(REASON_NO_DATA, SOURCE_NONE): 999.9,
        }
    )
    assert sum(out["share_by_reason"].values()) == pytest.approx(1.0, abs=1e-5)
    assert sum(out["share_decided_by_source"].values()) == pytest.approx(1.0, abs=1e-5)
    assert sum(out["share_kept_by_source"].values()) == pytest.approx(
        out["share_kept"], abs=1e-5
    )
    table = out["area_ha_by_reason_and_source"]
    assert sum(sum(row.values()) for row in table.values()) == pytest.approx(
        out["area_ha"], abs=1e-3
    )


def test_tabulate_mask_provenance_reports_disagreement():
    """Reason says kept on 10 ha, but on 1 of them the (older, cached)
    habitat_mask says not kept; and on 0.5 ha it is the other way round."""
    out = tabulate_mask_provenance(
        {
            _key(REASON_KEPT, SOURCE_INDIASAT): 90_000.0,
            _key(REASON_KEPT, SOURCE_INDIASAT, disagrees=1): 10_000.0,
            _key(REASON_CROPLAND, SOURCE_INDIASAT): 95_000.0,
            _key(REASON_CROPLAND, SOURCE_INDIASAT, disagrees=1): 5_000.0,
        }
    )
    assert out["area_ha"] == 20.0
    assert out["area_ha_reason_disagrees_with_habitat_mask"] == 1.5
    # The reason layer's own tally: 10 ha kept, 10 ha cropland.
    assert out["share_by_reason"]["kept"] == 0.5
    assert out["share_by_reason"]["cropland"] == 0.5
    # share_kept follows habitat_mask, the mask the pipeline actually uses:
    # 9 ha where both say kept, plus the 0.5 ha only the mask keeps.
    assert out["share_kept"] == 0.475
    assert out["share_kept_by_source"]["indiasat"] == 0.475


def test_tabulate_mask_provenance_empty_roi():
    out = tabulate_mask_provenance({})
    assert out["area_ha"] == 0.0 and out["share_kept"] == 0.0
    assert set(out["share_by_reason"]) == set(REASON_NAMES.values())
    assert set(out["share_decided_by_source"]) == set(SOURCE_NAMES.values())


@pytest.mark.parametrize("bad_key", [7, 31, 211])
def test_tabulate_mask_provenance_rejects_a_key_it_cannot_decode(bad_key: int):
    """Reason 7, source 3 and disagrees 2 do not exist. Summing them into the
    wrong row would be worse than saying so."""
    with pytest.raises(ValueError, match="does not decode"):
        tabulate_mask_provenance({bad_key: 1.0})


# ---------------------------------------------------------------------
# Masking: summarise() and the manifest
# ---------------------------------------------------------------------

# 100 ha, in square metres per (source, reason).
_CANNED_AREAS = {
    _key(REASON_KEPT, SOURCE_INDIASAT): 600_000.0,
    _key(REASON_CROPLAND, SOURCE_INDIASAT): 200_000.0,
    _key(REASON_BUILT_UP, SOURCE_INDIASAT): 100_000.0,
    _key(REASON_KEPT, SOURCE_WORLDCOVER): 50_000.0,
    _key(REASON_WATER, SOURCE_WORLDCOVER): 30_000.0,
    _key(REASON_NO_DATA, SOURCE_NONE): 20_000.0,
}
_CANNED_NUMBERS = {
    "area_ha": 100.0,
    "share_kept": 0.65,
    "share_by_reason": {
        "no_data": 0.02, "kept": 0.65, "cropland": 0.2, "built_up": 0.1,
        "water": 0.03, "other_non_habitat": 0.0,
    },
    "share_kept_by_source": {"none": 0.0, "indiasat": 0.6, "worldcover": 0.05},
    "share_decided_by_source": {"none": 0.02, "indiasat": 0.9, "worldcover": 0.08},
    "area_ha_by_reason_and_source": {
        "no_data": {"none": 2.0, "indiasat": 0.0, "worldcover": 0.0},
        "kept": {"none": 0.0, "indiasat": 60.0, "worldcover": 5.0},
        "cropland": {"none": 0.0, "indiasat": 20.0, "worldcover": 0.0},
        "built_up": {"none": 0.0, "indiasat": 10.0, "worldcover": 0.0},
        "water": {"none": 0.0, "indiasat": 0.0, "worldcover": 3.0},
        "other_non_habitat": {"none": 0.0, "indiasat": 0.0, "worldcover": 0.0},
    },
    "area_ha_reason_disagrees_with_habitat_mask": 0.0,
    "kept_classes": {"indiasat": [6, 12], "worldcover": [10, 20, 30]},
}


def _config():
    from fmu.config import Config, DateRange, DatesConfig, ROIConfig

    return Config(
        name="transparency_test",
        roi=ROIConfig(name="t", roi_file=Path("aois/t.geojson")),
        dates=DatesConfig(
            phenology=DateRange(start="2020-01-01", end="2024-12-31"),
            radar=DateRange(start="2020-01-01", end="2024-12-31"),
            optical_composite=DateRange(start="2023-01-01", end="2023-12-31"),
        ),
    )


@pytest.fixture
def masking_without_earth_engine(monkeypatch):
    """The masking stage with both Earth Engine halves replaced.

    `run()` hands back placeholders for the four outputs, and the area
    reduction returns `_CANNED_AREAS`. Everything between them is the real
    code: the declaration, `summarise()`, the tabulation, the orchestrator.
    Yields the list of calls the area reduction received.
    """
    calls: list[tuple[Any, ...]] = []

    def fake_run(self, ctx: PipelineContext, config: Any) -> StageResult:
        return StageResult(
            outputs={key: f"<{key}>" for key in MaskingStage.produces},
            metadata={"faked": True},
        )

    def fake_areas(mask_provenance, habitat_mask, roi, scale) -> dict[int, float]:
        calls.append((mask_provenance, habitat_mask, roi, scale))
        return dict(_CANNED_AREAS)

    monkeypatch.setattr(MaskingStage, "run", fake_run)
    monkeypatch.setattr(masking_module, "mask_provenance_areas", fake_areas)
    return calls


def test_masking_summarise_returns_exactly_the_declared_names(
    masking_without_earth_engine,
):
    ctx = PipelineContext()
    ctx.set("roi", "<roi>")
    ctx.set("mask_provenance", "<mask_provenance>")
    ctx.set("habitat_mask", "<habitat_mask>")
    config = _config()

    numbers = MaskingStage().summarise(ctx, config)

    assert set(numbers) == {s.name for s in MaskingStage.summary_numbers}
    assert numbers == _CANNED_NUMBERS
    # It read the images and the ROI from the context, at the analysis scale.
    assert masking_without_earth_engine == [
        ("<mask_provenance>", "<habitat_mask>", "<roi>", config.export.analysis_scale_m)
    ]


def test_kept_classes_follow_the_config(masking_without_earth_engine):
    """A config that keeps other classes says so in its own summary, which is
    what the legend note points the reader to."""
    ctx = PipelineContext()
    for key in ("roi", "mask_provenance", "habitat_mask"):
        ctx.set(key, f"<{key}>")
    config = _config()
    config.masking.indiasat_habitat_classes = [6, 12, 13]
    config.masking.keep_worldcover_classes = [10]

    numbers = MaskingStage().summarise(ctx, config)

    assert numbers["kept_classes"] == {"indiasat": [6, 12, 13], "worldcover": [10]}


def _stage_entry(tmp_path: Path, index: int = 0) -> dict[str, Any]:
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    return manifest["stages"][index]


def test_what_masking_declares_is_what_the_manifest_carries(
    masking_without_earth_engine, tmp_path: Path
):
    ctx = PipelineContext()
    ctx.set("roi", "<roi>")
    Pipeline(["masking"]).run(config=_config(), run_dir=tmp_path, initial_context=ctx)

    entry = _stage_entry(tmp_path)
    assert entry["name"] == "masking"
    assert entry["produced"] == sorted(MaskingStage.produces)
    assert entry["warnings"] == []
    record = entry["transparency"]
    assert "summary_error" not in record

    # Every declared layer, in order, field by field.
    assert len(record["display_layers"]) == len(MaskingStage.display_layers)
    for carried, declared in zip(
        record["display_layers"], MaskingStage.display_layers, strict=True
    ):
        assert carried["key"] == declared.key
        assert carried["band"] == declared.band
        assert carried["title"] == declared.title
        assert carried["description"] == declared.description
        assert carried["legend_note"] == declared.legend_note
        assert carried["legend"] == [
            {"value": e.value, "label": e.label, "color": e.color}
            for e in declared.legend
        ]
        # Masking's codes run 0..n with no gaps, so the palette is the legend's
        # colours in value order.
        by_value = sorted(declared.legend, key=lambda e: e.value)
        assert carried["vis"] == {
            "bands": [declared.band],
            "min": by_value[0].value,
            "max": by_value[-1].value,
            "palette": [e.color for e in by_value],
        }
        # Caching is off in this run, so there is no asset to point at.
        assert carried["asset"] is None and carried["asset_status"] is None

    # The habitat caveat reaches the manifest with the reason layer.
    reason = next(d for d in record["display_layers"] if d["band"] == "reason")
    assert "habitat mask, not a strict forest mask" in reason["legend_note"]

    # Every declared number, in order, with its description, unit and value.
    assert [
        (n["name"], n["description"], n["unit"]) for n in record["summary_numbers"]
    ] == [(s.name, s.description, s.unit) for s in MaskingStage.summary_numbers]
    assert {n["name"]: n["value"] for n in record["summary_numbers"]} == _CANNED_NUMBERS


# ---------------------------------------------------------------------
# The orchestrator writes any stage's declaration into the manifest
# ---------------------------------------------------------------------


def _declaring_stage(summarise_impl):
    @register_stage("declaring")
    class _Declaring(Stage):
        name = "declaring"
        produces = {"layer"}
        cacheable_outputs: set[str] = set()
        display_layers = (
            DisplayLayer(
                "layer", "b", "A layer", "what it shows",
                legend=(LegendEntry(0, "out", "000000"), LegendEntry(1, "in", "ffffff")),
                legend_note="read this with the legend",
            ),
        )
        summary_numbers = (SummaryNumber("share_in", "share of the area in", "fraction"),)

        def run(self, ctx: PipelineContext, config: Any) -> StageResult:
            return StageResult(outputs={"layer": "an image"})

        def summarise(self, ctx: PipelineContext, config: Any) -> dict[str, Any]:
            return summarise_impl(ctx)

    return _Declaring


def test_manifest_carries_layers_and_summary_numbers(tmp_path: Path):
    _declaring_stage(lambda ctx: {"share_in": 0.25})
    Pipeline(["declaring"]).run(config=_config(), run_dir=tmp_path)
    t = _stage_entry(tmp_path)["transparency"]
    assert t["display_layers"] == [
        {
            "key": "layer",
            "band": "b",
            "title": "A layer",
            "description": "what it shows",
            "vis": {"bands": ["b"], "min": 0, "max": 1, "palette": ["000000", "ffffff"]},
            "legend": [
                {"value": 0, "label": "out", "color": "000000"},
                {"value": 1, "label": "in", "color": "ffffff"},
            ],
            "legend_note": "read this with the legend",
            "asset": None,  # caching is off
            "asset_status": None,
        }
    ]
    assert t["summary_numbers"] == [
        {
            "name": "share_in",
            "description": "share of the area in",
            "unit": "fraction",
            "value": 0.25,
        }
    ]


def test_summarise_reads_the_context_after_the_stage_ran(tmp_path: Path):
    _declaring_stage(lambda ctx: {"share_in": len(ctx.get("layer"))})
    Pipeline(["declaring"]).run(config=_config(), run_dir=tmp_path)
    t = _stage_entry(tmp_path)["transparency"]
    assert t["summary_numbers"][0]["value"] == len("an image")


def test_a_failed_summary_is_recorded_not_fatal(tmp_path: Path):
    """An Earth Engine memory limit on the reduction must not cost the run: the
    stage's products are already made."""

    def boom(ctx):
        raise RuntimeError("user memory limit exceeded")

    _declaring_stage(boom)
    result = Pipeline(["declaring"]).run(config=_config(), run_dir=tmp_path)
    entry = _stage_entry(tmp_path)
    assert "RuntimeError: user memory limit exceeded" in entry["transparency"]["summary_error"]
    assert entry["transparency"]["summary_numbers"] == []
    assert any("summary numbers not computed" in w for w in entry["warnings"])
    # The stage's output is in the context and on the record all the same.
    assert entry["produced"] == ["layer"]
    assert result.context is not None and result.context.get("layer") == "an image"
    # The layers do not depend on the summary and are still written.
    assert entry["transparency"]["display_layers"][0]["key"] == "layer"


@pytest.mark.parametrize(
    "returned",
    [{"something_else": 1}, {"share_in": 0.5, "extra": 1}, {}, [0.5]],
    ids=["other_name", "extra_name", "nothing", "not_a_dict"],
)
def test_a_summary_with_the_wrong_names_is_recorded_not_fatal(tmp_path: Path, returned):
    """Same rule as a summary that raises: by now the products are made, and
    with caching on their exports are submitted. The test that makes a wrong
    summarise() fail loudly is the per-stage one above."""
    _declaring_stage(lambda ctx: returned)
    Pipeline(["declaring"]).run(config=_config(), run_dir=tmp_path)
    entry = _stage_entry(tmp_path)
    assert "summarise() returned" in entry["transparency"]["summary_error"]
    assert "share_in" in entry["transparency"]["summary_error"]
    assert entry["transparency"]["summary_numbers"] == []
    assert any("summary numbers not computed" in w for w in entry["warnings"])


def test_a_later_stage_still_runs_after_a_failed_summary(tmp_path: Path):
    def boom(ctx):
        raise RuntimeError("computation timed out")

    _declaring_stage(boom)

    @register_stage("after")
    class _After(Stage):
        name = "after"
        required_inputs = {"layer"}
        produces = {"seen"}
        cacheable_outputs: set[str] = set()

        def run(self, ctx: PipelineContext, config: Any) -> StageResult:
            return StageResult(outputs={"seen": ctx.get("layer")})

    result = Pipeline(["declaring", "after"]).run(config=_config(), run_dir=tmp_path)
    assert result.context is not None and result.context.get("seen") == "an image"
    assert _stage_entry(tmp_path, 1)["name"] == "after"


def test_summaries_can_be_switched_off(tmp_path: Path):
    def boom(ctx):
        raise AssertionError("summarise must not be called")

    _declaring_stage(boom)
    Pipeline(["declaring"], summaries=False).run(config=_config(), run_dir=tmp_path)
    entry = _stage_entry(tmp_path)
    t = entry["transparency"]
    assert t["summary_numbers"] == [] and "summary_skipped" in t
    assert "summary_error" not in t and entry["warnings"] == []
    # The layers are a declaration, not a computation, and are still written.
    assert len(t["display_layers"]) == 1
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["summaries"] is False


def test_the_manifest_says_summaries_were_on(tmp_path: Path):
    _declaring_stage(lambda ctx: {"share_in": 1.0})
    Pipeline(["declaring"]).run(config=_config(), run_dir=tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["summaries"] is True


def test_a_stage_that_declares_nothing_gets_an_empty_record(tmp_path: Path):
    @register_stage("plain")
    class _Plain(Stage):
        name = "plain"
        produces = {"x"}
        cacheable_outputs: set[str] = set()

        def run(self, ctx: PipelineContext, config: Any) -> StageResult:
            return StageResult(outputs={"x": 1})

    Pipeline(["plain"]).run(config=_config(), run_dir=tmp_path)
    assert _stage_entry(tmp_path)["transparency"] == {
        "display_layers": [],
        "summary_numbers": [],
    }
