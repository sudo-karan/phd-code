"""The round 9 copies of configs, offline.

Round 9 (17 Oct 2026) re-runs configs from scratch as copies named `<name>_r9`, and its cache
test (task D) a second copy `<name>_r9_check`, each changing nothing but the name. A copy has
its source's fingerprint and per-step keys, under a new name, so its cache starts empty, and
having no legacy asset it runs in the per-step layout. Copies that change more than the name
(task H's AlphaEarth configs) are listed with what they change.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from fmu.config import load_config
from fmu.utils.caching import config_fingerprint, step_keys

REPO = Path(__file__).resolve().parent.parent
CONFIGS = REPO / "configs"
R9 = sorted(p for p in CONFIGS.glob("*_r9*.yaml"))
SUFFIXES = ("_r9_check", "_r9")
# A copy that changes more than its name: copy -> (source, the keys it changes besides the name).
NOT_NAME_ONLY: dict[str, tuple[str, set[tuple[str, ...]]]] = {}


def _source(stem: str) -> str:
    for suffix in SUFFIXES:
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    raise AssertionError(f"{stem} is not a round 9 copy")


def _flat(d: dict, prefix: tuple = ()) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flat(v, prefix + (k,)))
        else:
            out[prefix + (k,)] = v
    return out


def test_there_are_round_9_copies():
    assert {p.stem for p in R9} >= {
        "odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9",
        "odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9_check",
    }


@pytest.mark.parametrize("path", R9, ids=lambda p: p.stem)
def test_a_copy_changes_only_its_name(path: Path):
    source, extra = NOT_NAME_ONLY.get(path.stem, (_source(path.stem), set()))
    a = _flat(yaml.safe_load((CONFIGS / f"{source}.yaml").read_text()))
    b = _flat(yaml.safe_load(path.read_text()))
    changed = {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
    assert changed == {("name",)} | extra, sorted(changed)
    assert b[("name",)] == path.stem


@pytest.mark.parametrize("path", R9, ids=lambda p: p.stem)
def test_a_name_only_copy_has_its_sources_keys(path: Path):
    if path.stem in NOT_NAME_ONLY:
        pytest.skip("changes more than the name")
    copy, source = load_config(path), load_config(CONFIGS / f"{_source(path.stem)}.yaml")
    assert config_fingerprint(copy) == config_fingerprint(source)
    assert step_keys(copy) == step_keys(source)
