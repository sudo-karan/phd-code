"""The per-step cache keys the runs recorded, and the fields added to a hashed block (review B11).

Since round 9 every config is cached in the per-step layout (fmu.utils.caching):
its assets are named by each step's key, a hash of the settings `STEP_SETTINGS`
lists for the step, as dumped, defaults included. Two things are pinned here.

1. The keys of record. Each run of the per-step layout recorded its step keys,
   in its `_run.json` and, stage by stage, in its manifests. The configs must
   still give those keys, or a later batch, resume or read-only script would
   miss the assets the runs cached. This also pins the graph of steps
   (`step_upstream`), which no other test pins (review C52). A round 13 fix
   moves the keys of the steps it changes on purpose (a revision, and for
   features_static the water settings of review A1): those steps get a new key,
   and with the fixes' changes undone (`_keyed_as_the_records_were`) every
   recorded key comes back.
2. A field added to a block a step hashes. Listed in `_STEP_OMITTED_AT_DEFAULT`
   (and in `_OMITTED_AT_DEFAULT` for the legacy fingerprint), it moves no key
   while it holds its default, and moves the steps that hash it when it does not.
   Before round 13 only the legacy fingerprint had such a table, so the field
   moved six step keys of every kept-land config (review B11).

If a test of part 1 fails, do not update the recorded keys: change the code so
that the configs give them again.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fmu.config import load_config
from fmu.utils import caching
from fmu.utils.caching import STEP_SETTINGS, config_fingerprint, step_key, step_keys

REPO = Path(__file__).parent.parent
CONFIGS = REPO / "configs"
RECORD_DIRS = ("r9_runs", "round12_runs", "round9_cache_test")


def _records(pattern: str, has: str) -> list[Path]:
    found = []
    for d in RECORD_DIRS:
        for p in sorted((REPO / "docs" / "reproducibility" / d).glob(pattern)):
            if has in json.loads(p.read_text()):
                found.append(p)
    return found


RUN_RECORDS = _records("*_run.json", "step_keys")
MANIFESTS = _records("*_manifest_*.json", "stages")

# A kept-land run of the hand-crafted arm, and one of the AlphaEarth arm.
HANDCRAFTED = CONFIGS / "odisha_v120_3ha_squares_angul_keptland_s1desc_r9.yaml"
ALPHAEARTH = CONFIGS / "odisha_alphaearth_3ha_squares_angul_keptland_r9.yaml"


class _ConfigWithAField:
    """A loaded config, dumped as if one of its blocks had one more field."""

    def __init__(self, config: Any, block: str, field: str, value: Any):
        self._config = config
        self._where = (block, field, value)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        dumped = self._config.model_dump(**kwargs)
        block, field, value = self._where
        target = dumped
        for part in block.split("."):
            target = target[part]
        target[field] = value
        return dumped

    def __getattr__(self, name: str) -> Any:
        return getattr(self._config, name)


def _downstream(cfg: Any, revised: set[str]) -> set[str]:
    """The steps in `revised` and every step that reads one of them, directly or not.

    k_elbow reads clustering's scaled feature stack without having clustering
    upstream (its key leaves k out), so a revision of clustering reaches it too.
    """

    def reaches(step: str) -> bool:
        return (
            step in revised
            or (step == "k_elbow" and reaches("clustering"))
            or any(reaches(u) for u in caching.step_upstream(cfg, step))
        )

    return {s for s in STEP_SETTINGS if reaches(s)}


def _moved_by_revisions(cfg: Any) -> set[str]:
    return _downstream(cfg, {s for s, r in caching.STEP_REVISION.items() if r})


# What features_static's key hashed when the runs of record were made, before round 13's fix
# of review A1: the stage read masking's water_mask, so masking was upstream of it, and it
# listed no water setting of its own. The fix moved its key on purpose (with its revision).
_STATIC_SETTINGS_OF_RECORD = ("dates.climate", "datasets.dem", "datasets.climate", "features_static")
_STATIC_SETTINGS_ADDED_BY_A1 = ("datasets.water", "masking.jrc_water_occurrence_threshold")


def _keyed_as_the_records_were(monkeypatch) -> None:
    """Undo the round's deliberate changes to the keys: every revision, and A1's re-keying of
    features_static. The configs must then give exactly the keys the runs recorded."""
    monkeypatch.setattr(caching, "STEP_REVISION", {})
    monkeypatch.setitem(caching.STEP_SETTINGS, "features_static", _STATIC_SETTINGS_OF_RECORD)
    upstream = caching.step_upstream
    monkeypatch.setattr(
        caching,
        "step_upstream",
        lambda cfg, step: ("masking",) if step == "features_static" else upstream(cfg, step),
    )


# ---------------------------------------------------------------------
# 1. The keys of record
# ---------------------------------------------------------------------


def test_the_records_of_the_per_step_runs_are_all_found():
    # 11 runs of rounds 9 and 10, 8 of round 12, the 2 of round 9's cache test.
    assert len(RUN_RECORDS) == 21, [p.name for p in RUN_RECORDS]
    assert len(MANIFESTS) >= 4 * len(RUN_RECORDS)


@pytest.mark.parametrize("record", RUN_RECORDS, ids=lambda p: p.stem)
def test_a_config_still_has_the_step_keys_its_run_recorded(record: Path, monkeypatch):
    # Not needed since round 14: the ROI file is read from the checkout root, whatever the
    # working directory (round 13 question 41; until then it was read from it, review C40).
    monkeypatch.chdir(REPO)
    rec = json.loads(record.read_text())
    assert rec["cache_layout"] == "per_step"
    cfg = load_config(CONFIGS / f"{rec['config']}.yaml")
    assert cfg.name == rec["config"]
    assert config_fingerprint(cfg) == rec["fingerprint"]
    keys = step_keys(cfg)
    # A step raised in STEP_REVISION moves, with every step downstream of it; no other.
    assert {s for s in keys if keys[s] != rec["step_keys"][s]} == _moved_by_revisions(cfg)
    _keyed_as_the_records_were(monkeypatch)
    assert step_keys(cfg) == rec["step_keys"]


@pytest.mark.parametrize("manifest", MANIFESTS, ids=lambda p: p.stem)
def test_each_stage_of_a_manifest_still_has_its_recorded_key(manifest: Path, monkeypatch):
    monkeypatch.chdir(REPO)
    rec = json.loads(manifest.read_text())
    if rec["cache_layout"] != "per_step":
        pytest.skip("legacy layout")
    cfg = load_config(CONFIGS / f"{rec['config_name']}.yaml")
    recorded = {s["name"]: s["cache_key"] for s in rec["stages"] if s.get("cache_key")}
    assert recorded, "no stage of the manifest recorded a key"
    # step_key, not step_keys: a stage with no settings of its own (profiling) is keyed too.
    moved = _moved_by_revisions(cfg)
    now = {s: step_key(cfg, s) for s in recorded}
    assert {s for s in recorded if now[s] != recorded[s]} == moved & set(recorded)
    _keyed_as_the_records_were(monkeypatch)
    assert {s: step_key(cfg, s) for s in recorded} == recorded


def test_a1_re_keyed_features_static_by_the_water_settings_only(monkeypatch):
    """What _keyed_as_the_records_were undoes is A1's change and nothing else."""
    monkeypatch.chdir(REPO)
    assert sorted(STEP_SETTINGS["features_static"]) == sorted(
        (*_STATIC_SETTINGS_OF_RECORD, *_STATIC_SETTINGS_ADDED_BY_A1)
    )
    for path in (HANDCRAFTED, ALPHAEARTH):
        assert caching.step_upstream(load_config(path), "features_static") == ()
    assert caching.STEP_REVISION.get("features_static", 0) >= 1


# ---------------------------------------------------------------------
# 2. A field added to a hashed block
# ---------------------------------------------------------------------

def _hashed_blocks() -> list[str]:
    """Every block or sub-block whose fields some step's key hashes as a whole."""
    dumped = load_config(HANDCRAFTED).model_dump(mode="json")
    return sorted(
        p
        for p in {p for paths in STEP_SETTINGS.values() for p in paths}
        if isinstance(caching._setting(dumped, p), dict)
    )


HASHED_BLOCKS = _hashed_blocks()


def _list(monkeypatch, block: str, field: str, default: Any) -> None:
    """List a field the way a new setting is to be listed: in both tables, beside the
    fields listed there already (round 14 listed the first ones)."""
    if "." not in block:
        monkeypatch.setitem(caching._OMITTED_AT_DEFAULT, (block, field), default)
    monkeypatch.setitem(caching._STEP_OMITTED_AT_DEFAULT, (block, field), default)


def test_the_blocks_tried_are_the_hashed_ones():
    assert {"masking", "data_load", "features_static", "segmentation", "merge"} <= set(
        HASHED_BLOCKS
    )
    assert {"clustering", "normalization", "dates.phenology", "k_elbow"} <= set(HASHED_BLOCKS)


@pytest.mark.parametrize("block", HASHED_BLOCKS)
@pytest.mark.parametrize("path", [HANDCRAFTED, ALPHAEARTH], ids=lambda p: p.stem)
def test_a_field_added_at_its_default_and_listed_moves_no_key(block: str, path: Path, monkeypatch):
    """Review B11: before round 13 such a field moved the step keys though listed.

    The legacy table lists top-level blocks only, so the legacy fingerprint is
    checked for those; a field of a sub-block ("dates.phenology") moves it.
    """
    monkeypatch.chdir(REPO)
    cfg = load_config(path)
    keys, fingerprint = step_keys(cfg), config_fingerprint(cfg)
    _list(monkeypatch, block, "new_option", False)
    added = _ConfigWithAField(cfg, block, "new_option", False)
    assert step_keys(added) == keys
    if "." not in block:
        assert config_fingerprint(added) == fingerprint


def test_switched_on_it_moves_the_steps_that_hash_its_block_and_what_follows(monkeypatch):
    monkeypatch.chdir(REPO)
    cfg = load_config(HANDCRAFTED)
    keys = step_keys(cfg)
    _list(monkeypatch, "masking", "new_option", False)
    on = step_keys(_ConfigWithAField(cfg, "masking", "new_option", True))
    moved = {s for s in keys if keys[s] != on[s]}
    # The kept-land mask is read by segmentation and the merge too (mask_before_snic).
    # features_static reads no masking output and only the water threshold of the block,
    # by name, since round 13 (review A1), so a new masking field does not move it.
    assert moved == {
        "masking", "segmentation", "merge", "clustering", "k_elbow",
    }
    assert config_fingerprint(_ConfigWithAField(cfg, "masking", "new_option", True)) != (
        config_fingerprint(cfg)
    )


def test_a_field_listed_as_a_setting_of_its_own_is_left_out_at_its_default(monkeypatch):
    """A new field another step reads by name ("merge.new_option" for clustering)."""
    monkeypatch.chdir(REPO)
    cfg = load_config(HANDCRAFTED)
    keys = step_keys(cfg)
    monkeypatch.setitem(
        caching.STEP_SETTINGS, "clustering", (*STEP_SETTINGS["clustering"], "merge.new_option")
    )
    _list(monkeypatch, "merge", "new_option", 0.5)
    assert step_keys(_ConfigWithAField(cfg, "merge", "new_option", 0.5)) == keys
    on = step_keys(_ConfigWithAField(cfg, "merge", "new_option", 0.7))
    assert {s for s in keys if keys[s] != on[s]} == {"merge", "clustering", "k_elbow"}


def test_an_unlisted_field_still_moves_the_keys(monkeypatch):
    """The table, not the value, keeps a field out: a field nobody listed is hashed."""
    monkeypatch.chdir(REPO)
    cfg = load_config(HANDCRAFTED)
    keys = step_keys(cfg)
    added = step_keys(_ConfigWithAField(cfg, "merge", "new_option", False))
    assert {s for s in keys if keys[s] != added[s]} == {"merge", "clustering", "k_elbow"}


def test_the_table_lists_round_14s_settings_at_their_model_defaults():
    """Empty until round 14 (review B11). Each field listed since is a setting added to a
    hashed block, off by default; its default in the table is the model's own, so a config
    that leaves it off hashes as before (the record tests above pin that the keys of
    record do not move)."""
    from fmu.config import Config

    assert caching._STEP_OMITTED_AT_DEFAULT
    fields = Config.model_fields
    for (block, field), default in caching._STEP_OMITTED_AT_DEFAULT.items():
        model: Any = Config
        for part in block.split("."):
            model = model.model_fields[part].annotation
        assert field in model.model_fields, (block, field)
        assert model.model_fields[field].default == default, (block, field)
    assert fields  # the model is the one the configs load


# ---------------------------------------------------------------------
# 3. A step's revision (round 13)
# ---------------------------------------------------------------------


def _moved_by(cfg: Any, revision: dict[str, int], monkeypatch) -> set[str]:
    monkeypatch.setattr(caching, "STEP_REVISION", {}, raising=False)
    before = step_keys(cfg)
    monkeypatch.setattr(caching, "STEP_REVISION", revision, raising=False)
    after = step_keys(cfg)
    return {s for s in before if before[s] != after[s]}


def test_a_revision_moves_its_step_and_every_step_downstream_and_no_other(monkeypatch):
    """What a fix that changes a step's output, with no setting changed, must do (review A4)."""
    monkeypatch.chdir(REPO)
    handcrafted, alphaearth = load_config(HANDCRAFTED), load_config(ALPHAEARTH)
    assert _moved_by(handcrafted, {"data_load": 1}, monkeypatch) == {
        "data_load", "features_optical", "features_radar", "segmentation", "merge",
        "clustering", "k_elbow",
    }
    # The AlphaEarth arm draws its superpixels on the embedding, and merges on the
    # hand-crafted optical and structure features.
    assert _moved_by(alphaearth, {"data_load": 1}, monkeypatch) == {
        "data_load", "features_optical", "features_radar", "merge", "clustering", "k_elbow",
    }
    assert _moved_by(alphaearth, {"features_static": 1}, monkeypatch) == {"features_static"}
    assert _moved_by(handcrafted, {"features_static": 1}, monkeypatch) == {
        "features_static", "clustering", "k_elbow",
    }


def test_a_revision_of_clustering_moves_the_elbow_too(monkeypatch):
    """k_elbow reads clustering's cached feature stack (fmu.stages.k_elbow.training_rows),
    so a change to what clustering computes must move the elbow's key, whose
    settings leave k out and so do not include clustering's key."""
    monkeypatch.chdir(REPO)
    for path in (HANDCRAFTED, ALPHAEARTH):
        cfg = load_config(path)
        assert _moved_by(cfg, {"clustering": 1}, monkeypatch) == {"clustering", "k_elbow"}
        assert _moved_by(cfg, {"k_elbow": 1}, monkeypatch) == {"k_elbow"}
    # And k still moves clustering only, whatever the revisions.
    monkeypatch.setattr(caching, "STEP_REVISION", {"clustering": 1}, raising=False)
    a = step_keys(load_config(HANDCRAFTED))
    other = load_config(HANDCRAFTED).model_copy(deep=True)
    other.clustering.k = 7
    b = step_keys(other)
    assert {s for s in a if a[s] != b[s]} == {"clustering"}


def test_a_revision_of_the_merge_moves_clustering_and_the_elbow_too(monkeypatch):
    """With the merge on, clustering and k_elbow read the merge's stands, so a change to
    what the merge computes moves their keys with the merge's, and no other key."""
    monkeypatch.chdir(REPO)
    for path in (HANDCRAFTED, ALPHAEARTH):
        cfg = load_config(path)
        assert _moved_by(cfg, {"merge": 1}, monkeypatch) == {"merge", "clustering", "k_elbow"}


ALL_CONFIGS = sorted([*CONFIGS.glob("*.yaml"), *(CONFIGS / "experiments").glob("*.yaml")])


def test_the_merge_at_revision_3_moves_the_merge_clustering_and_elbow_keys_of_every_config(
    monkeypatch,
):
    """Round 14 (round 13 question 24, answer (a); register entry
    spec-merge-fallback-tie-by-centroid): the shared-edge fallback's tie broken by
    centroid raised the merge from revision 2 to 3. Against the keys at revision 2 that
    moves the merge, clustering and k_elbow keys of a config with the merge on, which
    all 74 configs had when it was made, and no other key; the legacy fingerprint has
    no revision. (With the merge off, clustering reads the superpixels, and only the
    merge's own key, which no stage then reads, would move.)"""
    monkeypatch.chdir(REPO)
    revision = caching.STEP_REVISION["merge"]
    assert revision >= 3
    assert len(ALL_CONFIGS) >= 74
    for path in ALL_CONFIGS:
        cfg = load_config(path)
        now, fingerprint = step_keys(cfg), config_fingerprint(cfg)
        monkeypatch.setitem(caching.STEP_REVISION, "merge", 2)
        at_2, fingerprint_at_2 = step_keys(cfg), config_fingerprint(cfg)
        monkeypatch.setitem(caching.STEP_REVISION, "merge", revision)
        moves = {"merge", "clustering", "k_elbow"} if cfg.merge.enabled else {"merge"}
        assert {s for s in now if now[s] != at_2[s]} == moves, path
        assert fingerprint == fingerprint_at_2, path


def test_each_raise_gives_a_new_key_and_revision_zero_is_no_revision(monkeypatch):
    monkeypatch.chdir(REPO)
    cfg = load_config(HANDCRAFTED)
    monkeypatch.setattr(caching, "STEP_REVISION", {}, raising=False)
    plain = step_keys(cfg)["data_load"]
    seen = {plain}
    for revision in (1, 2, 3):
        monkeypatch.setattr(caching, "STEP_REVISION", {"data_load": revision}, raising=False)
        seen.add(step_keys(cfg)["data_load"])
    assert len(seen) == 4
    monkeypatch.setattr(caching, "STEP_REVISION", {"data_load": 0}, raising=False)
    assert step_keys(cfg)["data_load"] == plain


def test_each_revision_is_of_a_cached_step_and_at_least_one():
    for step, revision in caching.STEP_REVISION.items():
        assert step in STEP_SETTINGS, step
        assert isinstance(revision, int) and not isinstance(revision, bool) and revision >= 1
