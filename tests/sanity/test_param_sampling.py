import pytest

from src.optimizer.search import normalize_param_ranges, build_param_space, sample_param_sets


def _sample(ranges: dict, method: str, n: int = 128, seed: int = 0):
    norm = normalize_param_ranges(ranges)
    return sample_param_sets(norm, method=method, n=n, seed=seed)


def test_lhs_respects_categorical_lists():
    ranges = {"foo": [11, 22, 33], "bar": [1.5, 2.5]}
    samples = _sample(ranges, method="lhs", n=256, seed=1)
    for row in samples:
        assert row["foo"] in ranges["foo"]
        assert row["bar"] in ranges["bar"]


def test_sobol_respects_categorical_lists():
    ranges = {"length": [44, 51, 72]}
    samples = _sample(ranges, method="sobol", n=256, seed=2)
    assert {row["length"] for row in samples} <= set(ranges["length"])


def test_regression_base_slow_len_never_below_floor():
    ranges = {"base_slow_len": [44, 51, 72]}
    samples = _sample(ranges, method="lhs", n=256, seed=3)
    assert all(row["base_slow_len"] >= 44 for row in samples)

