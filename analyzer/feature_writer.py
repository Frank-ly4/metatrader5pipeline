"""
Feature Writer
---------------

Writes a single tidy per-bar Parquet file for a given chart analysis run.

Schema (columns):
- timestamp: pandas datetime64[ns] for each bar (from price index)
- symbol: string, repeated per row
- timeframe: string label inferred from bar spacing (normalized: '2H', '15M')
- provider: string trend/pattern provider name (e.g., 'mcg', 'pa_only')
- feature_version: string version tag (e.g., 'v1')
- trend_label: string per bar trend label (e.g., 'trend_up'/'trend_down'/'range' or 'up'/'down'/'range')
- regime_label: optional string per bar regime (present for providers that compute it)
- Any additional feature/pattern columns (0/1 flags) appended as needed

Metadata (as repeated columns for invariants & parity checks):
- bars_hash: SHA256 over (Timestamp, Open, High, Low, Close, Volume) in ascending index order
- bar_count: integer number of rows
- first_ts, last_ts: ISO8601 strings for first/last timestamps
- tz: string representation of timezone (e.g., 'UTC', 'naive', 'US/Eastern')
- run_uid: unique identifier for this feature write
- created_at: ISO8601 timestamp when this file was created

Notes:
- We keep file-level metadata embedded as columns to avoid hard dependency on a specific Parquet engine.
- PNG export behavior is unchanged and handled elsewhere.
"""

from __future__ import annotations

import hashlib
import os
from typing import Dict, Iterable, Optional

import pandas as pd

from src.strategy.regime import infer_timeframe
import time


def _infer_symbol_from_path(chart_path: str) -> str:
    base = os.path.splitext(os.path.basename(chart_path))[0]
    # Heuristic: symbol is the first token before an underscore
    # e.g., 'XAUUSD_4h_cl_1' -> 'XAUUSD'
    return base.split('_', 1)[0] if '_' in base else base


def _normalize_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError('symbol must be a string')
    return symbol.upper()


def _normalize_timeframe_label(tf: str) -> str:
    # Convert e.g. '4h' -> '4H', '15m' -> '15M', '1d' -> '1D'
    if not isinstance(tf, str):
        raise ValueError('timeframe must be a string')
    tf = tf.strip()
    if len(tf) >= 2 and tf[:-1].isdigit():
        unit = tf[-1]
        if unit in ('m','h','d'):
            return f"{tf[:-1]}{unit.upper()}"
    return tf.upper()


def _index_timezone_str(index: pd.DatetimeIndex) -> str:
    try:
        tz = index.tz
        if tz is None:
            return 'naive'
        # tz could be tzinfo or pytz/zoneinfo; str() is acceptable
        return str(tz)
    except Exception:
        return 'unknown'


def compute_bars_hash(price: pd.DataFrame) -> str:
    """Compute a stable SHA256 hash over (Timestamp, Open, High, Low, Close, Volume).

    If 'Volume' is missing, treat it as zeros for hashing purposes (recorded in metadata).
    """
    required_base = ['Open', 'High', 'Low', 'Close']
    for col in required_base:
        if col not in price.columns:
            raise ValueError(f"Missing required column in price: {col}")
    # Build a bytes buffer deterministically
    idx = pd.DatetimeIndex(price.index)
    if not idx.is_monotonic_increasing:
        raise ValueError('price index must be monotonic increasing')
    if not idx.is_unique:
        raise ValueError('price index has duplicate timestamps')
    buf_parts: list[bytes] = []
    # Use nanosecond epoch for precision and stability
    ts_ns = idx.view('int64')
    buf_parts.append(ts_ns.tobytes())
    for col in required_base:
        # Ensure float64 for deterministic bytes
        arr = pd.to_numeric(price[col], errors='coerce').astype('float64').to_numpy()
        buf_parts.append(arr.tobytes())
    # Volume (fill zeros if missing)
    if 'Volume' in price.columns:
        vol_arr = pd.to_numeric(price['Volume'], errors='coerce').fillna(0.0).astype('float64').to_numpy()
    else:
        import numpy as _np
        vol_arr = _np.zeros(len(price), dtype='float64')
    buf_parts.append(vol_arr.tobytes())
    data = b''.join(buf_parts)
    return hashlib.sha256(data).hexdigest()


def build_metadata(price: pd.DataFrame, *, symbol: str | None = None, timeframe: str | None = None,
                   run_uid: str | None = None, created_at: str | None = None) -> Dict[str, object]:
    idx = pd.DatetimeIndex(price.index)
    meta = {
        'bars_hash': compute_bars_hash(price),
        'bar_count': int(len(price)),
        'first_ts': (pd.to_datetime(idx[0]).isoformat() if len(idx) > 0 else None),
        'last_ts': (pd.to_datetime(idx[-1]).isoformat() if len(idx) > 0 else None),
        'tz': _index_timezone_str(idx),
        'timeframe': _normalize_timeframe_label(timeframe or infer_timeframe(idx)),
        'volume_filled': bool('Volume' not in price.columns),
    }
    if symbol is not None:
        meta['symbol'] = _normalize_symbol(symbol)
    if run_uid:
        meta['run_uid'] = run_uid
    if created_at:
        meta['created_at'] = created_at
    return meta


def write_features_parquet(
    chart_path: str,
    price: pd.DataFrame,
    features: pd.DataFrame,
    *,
    provider: str,
    feature_version: str = 'v1',
    out_dir: str = os.path.join('outputs', 'features'),
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    run_uid: Optional[str] = None,
    created_at: Optional[str] = None,
    expected_symbol: Optional[str] = None,
    expected_timeframe: Optional[str] = None,
) -> str:
    """Write tidy per-bar features to Parquet with required metadata columns.

    Returns the absolute file path written.
    """
    os.makedirs(out_dir, exist_ok=True)

    sym_raw = symbol or _infer_symbol_from_path(chart_path)
    sym = _normalize_symbol(sym_raw)
    tf_infer = timeframe or infer_timeframe(pd.DatetimeIndex(price.index))
    tf = _normalize_timeframe_label(tf_infer)

    # Validate expected symbol/timeframe if provided
    if expected_symbol is not None and _normalize_symbol(expected_symbol) != sym:
        raise ValueError(f"Symbol mismatch: expected {expected_symbol}, got {sym}")
    if expected_timeframe is not None and _normalize_timeframe_label(expected_timeframe) != tf:
        raise ValueError(f"Timeframe mismatch: expected {expected_timeframe}, got {tf}")

    # Stamp run uid and created_at
    ru = run_uid or time.strftime('%Y%m%d_%H%M%S')
    ca = created_at or time.strftime('%Y-%m-%dT%H:%M:%S')

    meta = build_metadata(price, symbol=sym, timeframe=tf, run_uid=ru, created_at=ca)

    # Assemble tidy frame
    out = features.copy()
    # Ensure a 'timestamp' column
    if not isinstance(out.index, pd.DatetimeIndex):
        raise ValueError('features must have a DatetimeIndex')
    out = out.copy()
    out.insert(0, 'timestamp', pd.to_datetime(out.index))
    out.insert(1, 'symbol', sym)
    out.insert(2, 'timeframe', tf)
    out.insert(3, 'provider', provider)
    out.insert(4, 'feature_version', feature_version)
    out.insert(5, 'run_uid', ru)
    out.insert(6, 'created_at', ca)
    # Required invariants as columns
    out['bars_hash'] = meta['bars_hash']
    out['bar_count'] = meta['bar_count']
    out['first_ts'] = meta['first_ts']
    out['last_ts'] = meta['last_ts']
    out['tz'] = meta['tz']

    # Filename pattern includes run_uid to avoid overwrite collisions
    fname = f"{sym}_{tf}_{provider}_{feature_version}_{ru}.parquet"
    path = os.path.abspath(os.path.join(out_dir, fname))
    # Write
    out.to_parquet(path, index=False)
    return path


