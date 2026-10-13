"""Fast tests of the synthetic generator (`fmu.evaluation.synthetic`) and of the
validation script built on it (`scripts/evaluation_synthetic_validation.py`).

All data are generated inside the tests. Nothing is read from a site. The
layouts used here are small and made up.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import shapely

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import evaluation_synthetic_validation as esv  # noqa: E402

from fmu.evaluation import synthetic as sy  # noqa: E402
from fmu.evaluation.agreement import adjusted_rand_index  # noqa: E402
from fmu.evaluation.spatial_null import PolygonStandMap, rotation_null  # noqa: E402

LAYOUT = {0: (12, 7), 1: (30,), 3: (9, 1)}  # 59 plots, 5 groups, 3 super-groups
SIZES = [12, 7, 30, 9, 1]


@pytest.fixture(scope="module")
def ds() -> sy.SyntheticDataset:
    return sy.make_dataset(11, 1.5, LAYOUT)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def _same(a: sy.SyntheticDataset, b: sy.SyntheticDataset) -> bool:
    arrays = ("coords", "groups", "super_group", "attributes", "field_type", "stand_id", "stand_type")
    return all(np.array_equal(getattr(a, k), getattr(b, k)) for k in arrays) and all(
        np.array_equal(a.planted[g].labels, b.planted[g].labels)
        and np.array_equal(a.unrelated[g].labels, b.unrelated[g].labels)
        for g in a.planted
    )


def test_same_seed_same_dataset(ds):
    assert _same(ds, sy.make_dataset(11, 1.5, LAYOUT))
    assert not _same(ds, sy.make_dataset(12, 1.5, LAYOUT))


def test_seed_sequence_is_not_used_up():
    seq = np.random.SeedSequence(5, spawn_key=(1, 2))
    first = sy.make_dataset(seq, 0.5, {0: (8, 6)})
    second = sy.make_dataset(seq, 0.5, {0: (8, 6)})
    assert _same(first, second)
    other = sy.make_dataset(np.random.SeedSequence(5, spawn_key=(1, 3)), 0.5, {0: (8, 6)})
    assert not _same(first, other)


def test_degraded_maps_and_layer_repeat(ds):
    for make in (sy.shifted_maps, sy.merged_maps, sy.split_maps):
        a, b = make(ds), make(ds)
        assert all(np.array_equal(a[g].labels, b[g].labels) for g in a)
    layer = sy.make_layer(ds.planted[0], 3, effect=1.0, n_bands=2)
    assert np.array_equal(layer, sy.make_layer(ds.planted[0], 3, effect=1.0, n_bands=2))
    assert layer.shape == (2, *ds.planted[0].labels.shape)


# ---------------------------------------------------------------------------
# The layout asked for is the layout produced
# ---------------------------------------------------------------------------


def test_group_sizes_are_those_requested(ds):
    assert ds.n_plots == sum(SIZES)
    assert ds.n_groups == len(SIZES)
    assert np.bincount(ds.groups).tolist() == SIZES
    # super-group of each group, in layout order
    per_group = [int(ds.super_group[ds.groups == g][0]) for g in range(ds.n_groups)]
    assert per_group == [0, 0, 1, 3, 3]
    for g in range(ds.n_groups):
        assert len(set(ds.super_group[ds.groups == g].tolist())) == 1
    assert ds.attributes.shape == (sum(SIZES), ds.params.n_attributes)
    assert set(ds.field_type.tolist()) == set(range(ds.params.n_field_types))


def test_plots_are_spaced_inside_their_region_and_on_a_stand(ds):
    for g in range(ds.n_groups):
        xy = ds.coords[ds.groups == g]
        assert shapely.contains_xy(ds.regions[g], xy[:, 0], xy[:, 1]).all()
        if xy.shape[0] > 1:
            gaps = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
            assert gaps[np.triu_indices_from(gaps, 1)].min() >= ds.params.min_plot_spacing
        side = np.sqrt(xy.shape[0] * ds.params.area_per_plot)
        assert np.ptp(xy[:, 0]) <= side and np.ptp(xy[:, 1]) <= side
    assert (ds.stand_id >= 0).all() and (ds.stand_type >= 0).all()
    assert ds.stand_type.max() < ds.params.n_types


def test_stand_codes_are_unique_and_match_the_rotation_null(ds):
    # no stand code is shared by two groups
    owners = {}
    for code, g in zip(ds.stand_id.tolist(), ds.groups.tolist(), strict=True):
        assert owners.setdefault(code, g) == g
    draws = rotation_null(ds.coords, ds.groups, ds.planted, ds.regions, 2, 0)
    assert np.array_equal(draws.observed_id, ds.stand_id)
    assert np.array_equal(draws.observed_type, ds.stand_type)


def test_bad_inputs_raise():
    with pytest.raises(ValueError):
        sy.make_dataset(1, 1.0, {})
    with pytest.raises(ValueError):
        sy.make_dataset(1, 1.0, {0: (5, 0)})
    with pytest.raises(ValueError):
        sy.make_dataset(1, -1.0, {0: (8,)})
    with pytest.raises(ValueError):
        sy.make_dataset(1, 1.0, {0: (3,)})  # fewer plots than field types
    with pytest.raises(TypeError):
        sy.make_dataset(None, 1.0, {0: (8,)})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        sy.SyntheticParams(type_share=1.5)


# ---------------------------------------------------------------------------
# Effect zero: unrelated to the map, still smooth
# ---------------------------------------------------------------------------


def test_attributes_are_background_plus_effect_times_signal(ds):
    assert np.allclose(ds.attributes, ds.background + 1.5 * ds.signal, rtol=0, atol=1e-12)
    zero = sy.make_dataset(11, 0.0, LAYOUT)
    assert np.array_equal(zero.attributes, zero.background)
    # the background and the map do not depend on the effect
    assert np.array_equal(zero.background, ds.background)
    assert np.array_equal(zero.stand_id, ds.stand_id)


def test_effect_zero_attributes_do_not_depend_on_the_map():
    """Change the map (other stand size, other types): the attributes stay the same, bit for bit."""
    a = sy.make_dataset(4, 0.0, LAYOUT)
    b = sy.make_dataset(
        4, 0.0, LAYOUT, replace(sy.DEFAULT_PARAMS, stand_spacing=90.0, stand_jitter=20.0, n_types=3)
    )
    assert np.array_equal(a.coords, b.coords)
    assert not np.array_equal(a.stand_id, b.stand_id)
    assert np.array_equal(a.attributes, b.attributes)
    assert np.array_equal(a.field_type, b.field_type)
    # with an effect, the same change of map does change them
    c = sy.make_dataset(4, 1.0, LAYOUT)
    d = sy.make_dataset(4, 1.0, LAYOUT, replace(sy.DEFAULT_PARAMS, stand_spacing=90.0))
    assert not np.array_equal(c.attributes, d.attributes)


def _pair_squares(data: sy.SyntheticDataset, values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Within-group pairs: distance, mean squared difference of `values`, same planted stand."""
    dist, sq, same = [], [], []
    for g in range(data.n_groups):
        idx = np.flatnonzero(data.groups == g)
        i, j = np.triu_indices(idx.shape[0], 1)
        xy = data.coords[idx]
        dist.append(np.hypot(*(xy[i] - xy[j]).T))
        sq.append(((values[idx][i] - values[idx][j]) ** 2).mean(axis=1))
        same.append(data.stand_id[idx][i] == data.stand_id[idx][j])
    return np.concatenate(dist), np.concatenate(sq), np.concatenate(same)


def test_effect_zero_is_smooth_but_blind_to_stands():
    """Near plots are more alike than far ones; same-stand pairs are no more alike than
    other pairs at the same distance."""
    near, far, same, other = [], [], [], []
    for seed in range(6):
        data = sy.make_dataset(seed, 0.0, {0: (40, 40, 40)})
        dist, sq, same_stand = _pair_squares(data, data.attributes)
        near.append(sq[dist < 150])
        far.append(sq[dist > 600])
        close = dist < 150
        same.append(sq[close & same_stand])
        other.append(sq[close & ~same_stand])
    near_m, far_m = np.concatenate(near).mean(), np.concatenate(far).mean()
    p = sy.DEFAULT_PARAMS
    # expected: 2 * (nugget + smooth * (1 - exp(-d / range)))
    assert far_m > 2 * (p.nugget_var + 0.9 * p.smooth_var) * 0.9
    assert near_m < 0.85 * far_m
    same_all, other_all = np.concatenate(same), np.concatenate(other)
    assert same_all.shape[0] > 100
    # no planted effect: the two means differ by sampling error only
    se = np.sqrt(same_all.var(ddof=1) / same_all.shape[0] + other_all.var(ddof=1) / other_all.shape[0])
    assert abs(same_all.mean() - other_all.mean()) < 4 * se


def test_planted_signal_follows_stands_and_types(ds):
    big = sy.make_dataset(2, 3.0, {0: (40, 40, 40)})
    dist, sq, same_stand = _pair_squares(big, big.signal)
    assert same_stand.sum() > 10
    assert np.allclose(sq[same_stand], 0.0)  # two plots of one stand carry the same signal
    assert sq[~same_stand].mean() > 0.5
    assert 0.6 < big.signal.var() < 1.6  # variance 1 by construction
    assert sy.planted_signal_share(0.0) == 0.0
    assert sy.planted_signal_share(1.0) == pytest.approx(1 / 2.5)


# ---------------------------------------------------------------------------
# Maps
# ---------------------------------------------------------------------------


def _type_raster(stand_map) -> np.ndarray:
    return stand_map.stand_type[stand_map.labels]


def _nested(fine: np.ndarray, coarse: np.ndarray) -> bool:
    """Every segment of `fine` lies inside one segment of `coarse`."""
    pairs = np.unique(np.column_stack([fine.ravel(), coarse.ravel()]), axis=0)
    return pairs.shape[0] == np.unique(fine).shape[0]


def test_split_cuts_every_stand_in_two_and_keeps_types(ds):
    split = sy.split_maps(ds)
    for g, planted in ds.planted.items():
        assert _nested(split[g].labels, planted.labels)
        assert planted.n_stands < split[g].n_stands <= 2 * planted.n_stands
        assert np.array_equal(_type_raster(split[g]), _type_raster(planted))


def test_merge_joins_stands(ds):
    merged = sy.merged_maps(ds)
    for g, planted in ds.planted.items():
        assert _nested(planted.labels, merged[g].labels)
        assert merged[g].n_stands < planted.n_stands / 2
    with pytest.raises(ValueError):
        sy.rasterise(ds.planted_seeds[0], merge_block=0)


def test_shift_moves_the_whole_map(ds):
    pixels = 3
    step = pixels * ds.params.pixel_size
    shifted = sy.shifted_maps(ds, (step, step))
    for g, planted in ds.planted.items():
        # +x is +columns, +y (north) is -rows
        moved = shifted[g].labels[:-pixels, pixels:]
        original = planted.labels[pixels:, :-pixels]
        assert adjusted_rand_index(moved.ravel(), original.ravel()) == 1.0
        assert np.array_equal(_type_raster(shifted[g])[:-pixels, pixels:], _type_raster(planted)[pixels:, :-pixels])
    default = sy.shifted_maps(ds)
    assert adjusted_rand_index(default[2].labels.ravel(), ds.planted[2].labels.ravel()) < 0.5


def test_unrelated_map_has_similar_stands_but_is_another_map(ds):
    offsets = []
    for g, planted in ds.planted.items():
        other = ds.unrelated[g]
        assert other.labels.shape == planted.labels.shape
        assert 0.7 < other.n_stands / planted.n_stands < 1.4
        # Two independent maps of compact stands of one size still share many pixel
        # pairs (near pixels are together in both), so the pixel-level adjusted Rand
        # index of unrelated maps is around 0.4, not 0. It must be far from 1.
        assert adjusted_rand_index(other.labels.ravel(), planted.labels.ravel()) < 0.7
        # the two seed grids do not sit on one lattice: averaged over the seeds the
        # jitter cancels and the grid offset is left
        offsets.append((ds.unrelated_seeds[g].xy - ds.planted_seeds[g].xy).mean(axis=0))
    assert np.abs(np.asarray(offsets)).max() > 20.0
    n_planted = sum(m.n_stands for m in ds.planted.values())
    n_other = sum(m.n_stands for m in ds.unrelated.values())
    assert abs(n_planted - n_other) / n_planted < 0.15
    # mean stand area close to the square of the seed spacing
    pixels = sum(m.labels.size for m in ds.planted.values())
    mean_area = pixels * ds.params.pixel_size**2 / n_planted
    assert 0.6 < mean_area / ds.params.stand_spacing**2 < 1.2


def test_polygons_are_the_same_map_as_the_raster(ds):
    stand_map = ds.planted[1]
    polygons = sy.raster_to_polygons(stand_map)
    assert len(polygons) == stand_map.n_stands
    areas = shapely.area(np.asarray(polygons, dtype=object))
    counts = np.bincount(stand_map.labels.ravel(), minlength=stand_map.n_stands)
    assert np.allclose(areas, counts * stand_map.pixel_size**2)
    rng = np.random.default_rng(0)
    h, w = stand_map.labels.shape
    x0, y_top = stand_map.origin
    # points strictly inside pixels
    col = rng.integers(0, w, 400)
    row = rng.integers(0, h, 400)
    frac = rng.uniform(0.05, 0.95, size=(400, 2))
    xy = np.column_stack(
        [x0 + (col + frac[:, 0]) * stand_map.pixel_size, y_top - (row + frac[:, 1]) * stand_map.pixel_size]
    )
    assert np.array_equal(PolygonStandMap(polygons).lookup(xy), stand_map.lookup(xy))
    assert np.array_equal(stand_map.lookup(xy), stand_map.labels[row, col])


def test_read_stands_offsets_and_errors(ds):
    stand_id, stand_type = sy.read_stands(ds.planted, ds.coords, ds.groups)
    assert np.array_equal(stand_id, ds.stand_id) and np.array_equal(stand_type, ds.stand_type)
    first = ds.groups == 0
    assert np.array_equal(stand_id[first], ds.planted[0].lookup(ds.coords[first]))
    second = ds.groups == 1
    assert np.array_equal(
        stand_id[second], ds.planted[1].lookup(ds.coords[second]) + ds.planted[0].n_stands
    )
    with pytest.raises(ValueError):
        sy.read_stands({0: ds.planted[0]}, ds.coords, ds.groups)


def test_layer_follows_the_map_only_when_asked(ds):
    stand_map = ds.planted[0]
    exact = sy.make_layer(stand_map, 1, effect=1.0, noise_var=0.0)
    for code in range(0, stand_map.n_stands, 7):
        inside = exact[0][stand_map.labels == code]
        assert np.ptp(inside) == 0.0
    blind = sy.make_layer(stand_map, 1, effect=0.0, noise_var=1.0)
    means = np.bincount(stand_map.labels.ravel(), weights=blind[0].ravel()) / np.bincount(
        stand_map.labels.ravel()
    )
    assert abs(means.mean()) < 0.2 and means.std() < 0.5  # stand means are noise only


# ---------------------------------------------------------------------------
# The validation script
# ---------------------------------------------------------------------------

TINY = esv.Design(
    name="quick",
    n_recovery=1,
    n_size=2,
    n_power=1,
    recovery_draws=9,
    test_draws=5,
    recovery_effect=4.0,
    power_effects=(2.0,),
)
TINY = replace(TINY, n_map_groups=1)
TINY_LAYOUT = {0: (16, 12), 1: (20,)}
# coarse pixels keep the polygon steps of the map experiments few
TINY_PARAMS = replace(sy.DEFAULT_PARAMS, pixel_size=40.0)


def test_helpers_of_the_script():
    low, high = esv.wilson_interval(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-4) and high == pytest.approx(0.7634, abs=1e-4)
    low, high = esv.wilson_interval(0, 10)
    assert low == 0.0 and high == pytest.approx(0.2775, abs=1e-4)
    assert esv.size_verdict(0.06, 0.2) == "too high"
    assert esv.size_verdict(0.03, 0.08) == "acceptable"
    assert esv.size_verdict(0.0, 0.04) == "below 0.05"
    half = esv.scaled(esv.FULL, 0.5)
    assert (half.n_recovery, half.n_size, half.n_power) == (5, 150, 40)
    assert (half.recovery_draws, half.test_draws, half.power_effects) == (999, 99, esv.FULL.power_effects)
    with pytest.raises(ValueError):
        esv.scaled(esv.FULL, 0.0)
    assert sum(sum(v) for v in esv.PLOTS_PER_GROUP.values()) == 267
    assert sum(len(v) for v in esv.PLOTS_PER_GROUP.values()) == 20
    # --quick is a part of the full run: same seed keys
    quick_keys = {(e, key) for e, key, _ in esv._tasks(esv.QUICK)}
    assert quick_keys <= {(e, key) for e, key, _ in esv._tasks(esv.FULL)}


def test_tiny_validation_repeats_and_is_complete(tmp_path):
    outputs = []
    for name in ("a", "b"):
        results = esv.run_validation(TINY, layout=TINY_LAYOUT, params=TINY_PARAMS)
        csv_path, md_path = esv.write_outputs(results, tmp_path / name, "command")
        outputs.append((csv_path.read_bytes(), md_path.read_bytes()))
    assert outputs[0] == outputs[1]

    rows = esv.summarise(results)
    assert esv.identity_failures(results) == 0
    rates = [r for r in rows if r["quantity"] == "rejection_rate"]
    for experiment, nulls in (("size", esv.NULLS), ("power", esv.NULLS), ("recovery", TINY.recovery_nulls)):
        cells = {(r["statistic"], r["null"]) for r in rates if r["experiment"] == experiment}
        assert cells == {(s, n) for s in esv.STATISTICS for n in nulls}
    for r in rows:
        if r["quantity"] != "mean_value":
            assert 0.0 <= r["value"] <= 1.0
    # with a very strong planted effect the planted map scores above the unrelated one
    # (checked for the statistics that do not go through k-means)
    for statistic in ("pair_stand", "mantel_stand", "anosim_stand", "permanova_stand"):
        value = {
            r["map"]: r["value"]
            for r in rows
            if r["experiment"] == "recovery" and r["statistic"] == statistic and r["quantity"] == "mean_value"
        }
        assert value["planted"] > value["unrelated"]
    # the planted map is a perfect match to its own polygons
    reference = {
        (r["statistic"], r["map"]): r["value"] for r in rows if r["experiment"] == "reference_polygons"
    }
    assert reference[("d", "planted")] == 0.0 and reference[("boundary_f", "planted")] == 1.0
    assert reference[("d", "unrelated")] > 0.1
    text = outputs[0][1].decode()
    assert "## 2. Size" in text and "## 5. No reference data" in text
