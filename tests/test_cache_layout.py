"""The per-step cache layout (round 9, issue #44 items 1 and 2), offline.

Three things are pinned here.

1. What a per-step key covers. Each cached step's key hashes the settings
   `STEP_SETTINGS` lists for it and the keys of the steps whose outputs it reads.
   A setting a step reads that is not listed would leave its key unchanged when
   the setting changes: the stale-cache bug, for one step, with nothing in the
   output to say so. `test_every_setting_a_stage_reads_is_in_its_key` reads each
   stage's module and fails on any config setting it reads that is not listed
   for that stage. It follows the names bound to the config and to its blocks,
   and expands the Config methods a stage calls into the settings they read
   (from config.py's own source), so a new read in any of them fails here.
2. How keys move: a setting changes the key of the step that reads it and of the
   steps downstream of it, and nothing upstream; a config's name changes none.
3. Which layout a config gets: the legacy one when its cache already holds an
   asset of that layout, the per-step one otherwise (fmu.pipeline.cache_layout_for).
"""

from __future__ import annotations

import ast
import copy
import re
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

import fmu.stages.clustering  # noqa: F401  (registers the stages)
import fmu.stages.data_load  # noqa: F401
import fmu.stages.features_embedding  # noqa: F401
import fmu.stages.features_optical  # noqa: F401
import fmu.stages.features_radar  # noqa: F401
import fmu.stages.features_static  # noqa: F401
import fmu.stages.features_structure  # noqa: F401
import fmu.stages.k_elbow  # noqa: F401
import fmu.stages.masking  # noqa: F401
import fmu.stages.merge  # noqa: F401
import fmu.stages.segmentation  # noqa: F401
from fmu import config as config_module
from fmu.config import Config, load_config
from fmu.pipeline import _SNIC_SOURCE_STAGE, Pipeline, cache_layout_for
from fmu.stages.base import _stage_registry, get_stage_class
from fmu.utils.caching import (
    _EVERY_STEP,
    LEGACY_LAYOUT,
    PER_STEP_LAYOUT,
    SOURCE_STEP,
    STEP_SETTINGS,
    active_layout,
    cache_key,
    config_fingerprint,
    input_images_record,
    layout_in_use,
    step_key,
    step_keys,
    step_upstream,
)

REPO = Path(__file__).resolve().parent.parent
STAGES_DIR = REPO / "src" / "fmu" / "stages"
CONFIGS_DIR = REPO / "configs"
CONFIG_DIR = REPO / "configs"
KENDUJHAR = CONFIG_DIR / "odisha_v120_3ha_squares_kendujhar_keptland_s1desc.yaml"
ALL_CONFIGS = sorted(CONFIG_DIR.glob("*.yaml"))

_REGISTERED = {n: c for n, c in _stage_registry.items() if c.__module__.startswith("fmu.stages.")}


@pytest.fixture(autouse=True)
def _restore_stage_registry():
    """Other test modules empty the registry; put the pipeline's stages back."""
    _stage_registry.clear()
    _stage_registry.update(_REGISTERED)
    yield
    _stage_registry.clear()
    _stage_registry.update(_REGISTERED)


def _raw(path: Path = KENDUJHAR) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def _cfg(raw: dict[str, Any]) -> Config:
    return Config.model_validate(raw)


# ---------------------------------------------------------------------
# 1. What a key covers: the settings each stage's code reads
# ---------------------------------------------------------------------

# Config fields -> the model class of the block (to resolve block methods).
_BLOCK_CLASS = {
    name: field.annotation.__name__
    for name, field in Config.model_fields.items()
    if isinstance(field.annotation, type)
}


def _method_reads() -> dict[tuple[str, str], set[str]]:
    """(class name, method name) -> the settings the method reads, from config.py.

    Config's methods read `self.<block>.<field>`; a block's methods read
    `self.<field>`, which is `<block>.<field>` for every Config field of that
    class. Calls to other methods are followed.
    """
    tree = ast.parse(Path(config_module.__file__).read_text())
    raw: dict[tuple[str, str], tuple[set[str], set[tuple[str, str]]]] = {}
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
            paths: set[str] = set()
            calls: set[tuple[str, str]] = set()
            for node in ast.walk(fn):
                if isinstance(node, ast.Attribute) and not isinstance(_parent(fn, node), ast.Attribute):
                    chain = _chain(node)
                    if chain and chain[0] == "self" and len(chain) > 1:
                        rest = chain[1:]
                        if cls.name == "Config":
                            if rest[0] in Config.model_fields:
                                paths.add(".".join(rest[:2]))
                            else:
                                calls.add((cls.name, rest[0]))
                        else:
                            calls.add((cls.name, rest[0]))
                            paths.add(f"<{cls.name}>." + rest[0])
            raw[(cls.name, fn.name)] = (paths, calls)

    def resolve(key: tuple[str, str], seen: set[tuple[str, str]]) -> set[str]:
        if key in seen or key not in raw:
            return set()
        seen.add(key)
        paths, calls = raw[key]
        out = set(paths)
        for c in calls:
            out |= resolve(c, seen)
        return out

    return {key: resolve(key, set()) for key in raw}


def _parent(root: ast.AST, target: ast.AST) -> ast.AST | None:
    for node in ast.walk(root):
        for child in ast.iter_child_nodes(node):
            if child is target:
                return node
    return None


def _chain(node: ast.AST) -> list[str] | None:
    """`a.b.c` as ["a", "b", "c"]; None if it is not rooted at a plain name."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return parts[::-1]
    return None


def _expand(path_parts: list[str], method_reads: dict[tuple[str, str], set[str]]) -> set[str]:
    """Config attribute parts (after the config name) -> the settings they read."""
    if not path_parts:
        return {"<the whole config>"}
    head = path_parts[0]
    if head in Config.model_fields:
        cls = _BLOCK_CLASS.get(head)
        if len(path_parts) >= 2 and cls and (cls, path_parts[1]) in method_reads:
            return {
                p.replace(f"<{cls}>", head) if p.startswith(f"<{cls}>") else p
                for p in method_reads[(cls, path_parts[1])]
            }
        return {".".join(path_parts[:2])}
    if ("Config", head) in method_reads:
        return set(method_reads[("Config", head)])
    return {f"<unknown: config.{'.'.join(path_parts)}>"}


def config_reads(path: Path) -> set[str]:
    """Every config setting a module reads, as "block" or "block.field".

    In every function: the parameters named `config` (or `cfg`, or annotated
    Config) are the config; a name assigned from an attribute of the config is
    that part of it (`params = config.merge`). Each attribute read off either is a
    setting; a Config method called on it is the settings that method reads; a
    name used whole (passed to a function, say) is all of what it names.
    """
    tree = ast.parse(path.read_text())
    method_reads = _method_reads()
    reads: set[str] = set()
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]:
        aliases: dict[str, list[str]] = {}
        for arg in [*fn.args.args, *fn.args.kwonlyargs]:
            annotated = isinstance(arg.annotation, ast.Name) and arg.annotation.id == "Config"
            if arg.arg in ("config", "cfg") or annotated:
                aliases[arg.arg] = []
        if not aliases:
            continue
        changed = True
        while changed:
            changed = False
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                ):
                    chain = _chain(node.value)
                    name = node.targets[0].id
                    if chain and chain[0] in aliases and name not in aliases:
                        aliases[name] = aliases[chain[0]] + chain[1:]
                        changed = True
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute):
                parent = _parent(fn, node)
                if isinstance(parent, ast.Attribute):
                    continue  # not the outermost attribute of its chain
                if (
                    isinstance(parent, ast.Assign)
                    and node is parent.value
                    and len(parent.targets) == 1
                    and isinstance(parent.targets[0], ast.Name)
                ):
                    continue  # an alias being made (`ds = config.datasets`): its uses count
                chain = _chain(node)
                if chain and chain[0] in aliases:
                    reads |= _expand(aliases[chain[0]] + chain[1:], method_reads)
            elif isinstance(node, ast.Name) and node.id in aliases and isinstance(node.ctx, ast.Load):
                parent = _parent(fn, node)
                if isinstance(parent, ast.Attribute) and parent.value is node:
                    continue
                if isinstance(parent, ast.Assign) and node is parent.value:
                    continue  # an alias being made, not a read
                if not aliases[node.id]:
                    # The config itself, handed on: fine to a function of this
                    # module (its own reads are found), not to one elsewhere.
                    module_functions = {
                        f.name for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
                    }
                    if (
                        isinstance(parent, ast.Call)
                        and isinstance(parent.func, ast.Name)
                        and (parent.func.id in _IDENTITY_ONLY or parent.func.id in module_functions)
                    ):
                        continue
                    if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute):
                        chain = _chain(parent.func)
                        if chain and chain[0] == "self":
                            continue  # a method of this module's stage
                    reads.add("<the whole config, handed outside the module>")
                else:
                    reads |= _expand(aliases[node.id], method_reads)
    return reads


# Functions outside the stage modules that are handed the whole config but read
# only which config it is (its name and legacy fingerprint), never a setting.
_IDENTITY_ONLY = {"active_layout"}


def _covered(path: str, declared: tuple[str, ...]) -> bool:
    return any(path == d or path.startswith(d + ".") for d in declared)


# Steps upstream of a step in every config: a setting one of them hashes moves this step's
# key through theirs (step_upstream), so the stage may read it. Round 14: features_optical
# reads dates.phenology, the window data_load filters the collection by, for its window mean.
_ALWAYS_UPSTREAM = {"features_optical": ("data_load",), "features_radar": ("data_load",)}


def test_the_always_upstream_steps_are_upstream_in_every_config():
    from fmu.config import load_config
    from fmu.utils.caching import step_upstream

    paths = sorted(CONFIGS_DIR.glob("*.yaml")) + sorted((CONFIGS_DIR / "experiments").glob("*.yaml"))
    assert paths
    for path in paths:
        cfg = load_config(path)
        for step, ups in _ALWAYS_UPSTREAM.items():
            assert set(ups) <= set(step_upstream(cfg, step)), (path.name, step)


@pytest.mark.parametrize("stage", sorted(STEP_SETTINGS))
def test_every_setting_a_stage_reads_is_in_its_key(stage: str):
    module = STAGES_DIR / f"{stage}.py"
    declared = (
        *_EVERY_STEP,
        *STEP_SETTINGS[stage],
        *(s for up in _ALWAYS_UPSTREAM.get(stage, ()) for s in STEP_SETTINGS[up]),
    )
    reads = config_reads(module)
    assert reads, f"no config read found in {module.name}: the scan is broken"
    missing = sorted(p for p in reads if not _covered(p, declared))
    assert not missing, (
        f"{stage} reads {missing}, which its per-step key does not cover. Add them "
        f"to STEP_SETTINGS[{stage!r}] in src/fmu/utils/caching.py."
    )


def test_the_scan_catches_a_read_that_is_not_declared(tmp_path: Path):
    """The check above has teeth: a module reading an undeclared setting fails it."""
    module = tmp_path / "fake_stage.py"
    module.write_text(
        "def run(self, ctx, config):\n"
        "    params = config.segmentation\n"
        "    size = params.size\n"
        "    use(size, config.merge.max_area_ha, config.kept_patch_min_pixels())\n"
        "    helper(config)\n"
    )
    reads = config_reads(module)
    assert "segmentation.size" in reads
    assert "merge.max_area_ha" in reads
    assert "merge.min_area_ha" in reads  # through kept_patch_min_pixels()
    assert "<the whole config, handed outside the module>" in reads
    assert not _covered("merge.max_area_ha", ("segmentation", "export.analysis_scale_m"))


def test_every_cached_stage_of_the_pipeline_has_a_key():
    cached = {
        name for name, cls in _REGISTERED.items()
        if Pipeline._resolve_cacheable_outputs(cls())
    }
    assert cached <= set(STEP_SETTINGS), sorted(cached - set(STEP_SETTINGS))


def test_every_declared_setting_exists():
    dumped = _cfg(_raw()).model_dump(mode="json")
    for stage, paths in STEP_SETTINGS.items():
        for p in (*_EVERY_STEP, *paths):
            value: Any = dumped
            for part in p.split("."):
                assert isinstance(value, dict) and part in value, f"{stage}: no setting {p}"
                value = value[part]


def test_the_k_elbow_key_covers_every_clustering_setting_but_k():
    clustering_fields = set(Config.model_fields["clustering"].annotation.model_fields)
    in_key = {p.split(".", 1)[1] for p in STEP_SETTINGS["k_elbow"] if p.startswith("clustering.")}
    assert in_key == clustering_fields - {"k"}
    assert "clustering" not in STEP_SETTINGS["k_elbow"]


def test_source_steps_agree_with_the_pipeline():
    assert SOURCE_STEP == _SNIC_SOURCE_STAGE


# ---------------------------------------------------------------------
# 2. How keys move
# ---------------------------------------------------------------------


def test_keys_have_the_per_step_form_and_are_stable():
    cfg = _cfg(_raw())
    keys = step_keys(cfg)
    assert set(keys) == set(STEP_SETTINGS)
    for k in keys.values():
        assert re.fullmatch(r"s[0-9a-f]{10}", k), k
    assert step_keys(_cfg(_raw())) == keys
    # never a legacy fingerprint (ten hex digits)
    assert config_fingerprint(cfg) not in keys.values()


def test_the_name_and_the_description_change_no_key():
    raw = _raw()
    other = copy.deepcopy(raw)
    other["name"] = raw["name"] + "_r9_check"
    other["description"] = "another description"
    other["export"]["drive_folder"] = "another_folder"
    assert step_keys(_cfg(raw)) == step_keys(_cfg(other))


def _moved(mutate) -> set[str]:
    raw = _raw()
    before = step_keys(_cfg(raw))
    changed = copy.deepcopy(raw)
    mutate(changed)
    after = step_keys(_cfg(changed))
    return {s for s in before if before[s] != after[s]}


def test_a_merge_tolerance_moves_the_merge_and_what_follows_only():
    def bump(raw):
        raw["merge"].setdefault("relax_factor", 1.75)
        raw["merge"]["relax_factor"] = 2.0

    assert _moved(bump) == {"merge", "clustering", "k_elbow"}


def test_the_orbit_moves_radar_and_its_readers_not_the_mask():
    def orbit(raw):
        raw["data_load"]["s1_orbit"] = "ASCENDING"

    moved = _moved(orbit)
    assert {"data_load", "features_radar", "clustering", "k_elbow"} <= moved
    assert "masking" not in moved and "features_structure" not in moved
    assert "features_static" not in moved


def test_k_moves_clustering_and_not_the_elbow():
    def k(raw):
        raw["clustering"]["k"] = 7

    assert _moved(k) == {"clustering"}


def test_an_elbow_setting_moves_the_elbow_only():
    def kmax(raw):
        raw["k_elbow"] = {"k_max": 10}

    assert _moved(kmax) == {"k_elbow"}


def test_the_analysis_scale_moves_every_key():
    def scale(raw):
        raw["export"]["analysis_scale_m"] = 20

    assert _moved(scale) == set(STEP_SETTINGS)


def test_the_roi_file_content_is_in_every_key(tmp_path: Path):
    raw = _raw()
    roi = tmp_path / "roi.geojson"
    roi.write_text((REPO / raw["roi"]["roi_file"]).read_text())
    raw["roi"]["roi_file"] = str(roi)
    before = step_keys(_cfg(raw))
    roi.write_text(roi.read_text().replace("]]]", "]]] ", 1) + "\n")
    after = step_keys(_cfg(raw))
    assert all(before[s] != after[s] for s in before)


def test_segmentation_follows_its_input_bands():
    cfg = _cfg(_raw())
    sources = {_SNIC_SOURCE_STAGE[s] for s in cfg.segmentation.input_sources()}
    ups = set(step_upstream(cfg, "segmentation"))
    assert sources <= ups
    assert ("masking" in ups) == cfg.segmentation.mask_before_snic


def test_an_embedding_config_does_not_key_clustering_on_handcrafted_features():
    cfg = load_config(CONFIG_DIR / "sanjay_van_alphaearth_keptland.yaml")
    ups = set(step_upstream(cfg, "clustering"))
    assert "features_embedding" in ups and "features_radar" not in ups


@pytest.mark.parametrize("path", ALL_CONFIGS, ids=lambda p: p.stem)
def test_every_config_has_keys(path: Path):
    cfg = load_config(path)
    keys = step_keys(cfg)
    assert len(set(keys.values())) == len(keys)


def test_cache_key_by_layout():
    cfg = _cfg(_raw())
    assert cache_key(cfg, "masking", LEGACY_LAYOUT) == config_fingerprint(cfg)
    assert cache_key(cfg, "masking", PER_STEP_LAYOUT) == step_key(cfg, "masking")
    with pytest.raises(ValueError):
        cache_key(cfg, "masking", "other")


def test_a_stage_without_settings_is_keyed_on_everything():
    raw = _raw()
    a = step_key(_cfg(raw), "not_a_pipeline_stage")
    raw["features"] = {"radar": False}
    assert step_key(_cfg(raw), "not_a_pipeline_stage") != a


# ---------------------------------------------------------------------
# 3. Which layout a config gets
# ---------------------------------------------------------------------


def test_a_config_with_a_legacy_asset_keeps_the_legacy_layout():
    cfg = _cfg(_raw())
    legacy = f"projects/p/assets/fmu/{cfg.name}/masking/habitat_mask__{config_fingerprint(cfg)}"
    with patch("fmu.pipeline.cached_asset_path",
               side_effect=lambda n, s, k, f=None: f"projects/p/assets/fmu/{n}/{s}/{k}__{f}"), \
         patch("fmu.pipeline.asset_exists", side_effect=lambda p: p == legacy):
        layout, why = cache_layout_for(cfg)
    assert layout == LEGACY_LAYOUT and legacy in why


def test_a_config_with_no_legacy_asset_gets_the_per_step_layout():
    cfg = _cfg(_raw())
    looked: list[str] = []

    def exists(p: str) -> bool:
        looked.append(p)
        return False

    with patch("fmu.pipeline.cached_asset_path",
               side_effect=lambda n, s, k, f=None: f"projects/p/assets/fmu/{n}/{s}/{k}__{f}"), \
         patch("fmu.pipeline.asset_exists", side_effect=exists):
        layout, _why = cache_layout_for(cfg)
    assert layout == PER_STEP_LAYOUT
    # it looked for every cacheable output of every stage, at the legacy path
    assert any("/masking/habitat_mask__" in p for p in looked)
    assert any("/clustering/cluster_labels__" in p for p in looked)
    assert all(p.endswith("__" + config_fingerprint(cfg)) for p in looked)


def test_the_layout_in_use_is_set_only_for_the_run():
    cfg = _cfg(_raw())
    assert active_layout(cfg) is None
    with layout_in_use(cfg, PER_STEP_LAYOUT):
        assert active_layout(cfg) == PER_STEP_LAYOUT
    assert active_layout(cfg) is None
    with pytest.raises(ValueError), layout_in_use(cfg, "neither"):
        pass


def test_input_images_record_lists_short_lists_and_hashes_all():
    rec = input_images_record({"a": ["x2", "x1"], "b": [f"i{n}" for n in range(150)]}, list_up_to=100)
    assert rec["a"]["count"] == 2 and rec["a"]["ids"] == ["x1", "x2"]
    assert rec["b"]["count"] == 150 and rec["b"]["ids"] is None
    again = input_images_record({"a": ["x1", "x2"]}, list_up_to=100)
    assert again["a"]["sha256"] == rec["a"]["sha256"]  # order does not matter


def test_the_k_elbow_stage_is_registered_and_cached_as_a_table():
    cls = get_stage_class("k_elbow")
    assert cls.cacheable_outputs == {"k_elbow"} == cls.table_outputs
