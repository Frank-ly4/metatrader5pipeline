import os
import pandas as pd
from config.data import ACTIVE_CHARTS_DIR


def find_first_csv(directory: str) -> str | None:
    for fname in os.listdir(directory):
        if fname.lower().endswith('.csv'):
            return os.path.join(directory, fname)
    return None


def load_chart_from_path(path: str) -> pd.DataFrame:
    """Load a chart CSV quickly with a tiny on-disk Parquet cache.

    Rules:
    1. If <chart>.parquet exists alongside the CSV and is newer, load it.
    2. Otherwise read the CSV using the fast *pyarrow* engine when available,
       then immediately write a Parquet cache for future runs.
    3. Skip expensive `asfreq` resampling unless the index appears irregular
       ( >1 % of deltas deviate from the median ).
    """

    import pathlib, numpy as _np

    csv_path = pathlib.Path(path)
    pq_path = csv_path.with_suffix('.parquet')

    try:
        if pq_path.exists() and pq_path.stat().st_mtime >= csv_path.stat().st_mtime:
            return pd.read_parquet(pq_path)
    except Exception:
        # Fallback to CSV directly if any issues with cache metadata
        pass

    # Fast CSV read
    read_kwargs = dict(index_col=0, parse_dates=True)
    try:
        df = pd.read_csv(path, engine='pyarrow', **read_kwargs)  # pandas ≥2.0
    except Exception:
        df = pd.read_csv(path, **read_kwargs)  # fallback C-engine

    # Normalize column names to OHLC
    rename_map = {
        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
        'Open': 'Open', 'High': 'High', 'Low': 'Low', 'Close': 'Close'
    }
    df = df.rename(columns={c: rename_map.get(c, c) for c in df.columns})
    required = ['Open', 'High', 'Low', 'Close']
    if not all(c in df.columns for c in required):
        raise ValueError(f"Chart must contain columns: {required}")


    # Keep only real bars: sort + dedupe timestamps, do NOT synthesize missing bars.
    df.index = pd.to_datetime(df.index, errors='coerce')
    if df.index.hasnans:
        df = df[~df.index.isna()]
    df = df[~df.index.duplicated(keep='last')].sort_index()

    # Write/update Parquet cache for next run (best-effort)
    try:
        df.to_parquet(pq_path, index=True)
    except Exception:
        pass
    return df


def load_first_chart() -> pd.DataFrame:
    path = find_first_csv(ACTIVE_CHARTS_DIR)
    if path is None:
        raise FileNotFoundError(f"No CSV files found in {ACTIVE_CHARTS_DIR}")
    return load_chart_from_path(path)


def list_active_chart_paths() -> list[str]:
    try:
        return [
            os.path.join(ACTIVE_CHARTS_DIR, f)
            for f in os.listdir(ACTIVE_CHARTS_DIR)
            if f.lower().endswith('.csv')
        ]
    except FileNotFoundError:
        return []


