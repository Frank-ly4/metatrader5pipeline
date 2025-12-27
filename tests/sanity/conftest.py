import os
import pandas as pd
import numpy as np

# Path helpers relative to repository root
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ACTIVE_CHARTS_DIR = os.path.join(ROOT_DIR, "data", "active_charts")


def _load_first_chart(max_rows: int = 500):
    """Utility to load a small deterministic slice of the first chart in active_charts."""
    fnames = [f for f in os.listdir(ACTIVE_CHARTS_DIR) if f.lower().endswith(".csv")]
    if not fnames:
        raise FileNotFoundError("No CSV files found in data/active_charts for tests")
    path = os.path.join(ACTIVE_CHARTS_DIR, sorted(fnames)[0])
    df = pd.read_csv(path).head(max_rows)
    # Ensure datetime index
    if not isinstance(df.index, pd.DatetimeIndex):
        if "Date" in df.columns:
            df.index = pd.to_datetime(df["Date"])
        elif "date" in df.columns:
            df.index = pd.to_datetime(df["date"])
    return df


import pytest


@pytest.fixture(scope="session")
def price_df():
    """Small price DataFrame fixture for sanity tests."""
    return _load_first_chart()


@pytest.fixture(scope="session")
def sample_params():
    """Single deterministic parameter set for quick evaluation."""
    from config.strategy_params import PARAM_RANGES
    # Use median value of each range for stability
    params = {}
    for k, rng in PARAM_RANGES.items():
        if isinstance(rng, (list, tuple)) and len(rng) >= 2:
            lo, hi = rng[0], rng[-1]
            params[k] = lo + (hi - lo) / 2
        else:
            params[k] = rng[0] if isinstance(rng, list) else rng
    return params
