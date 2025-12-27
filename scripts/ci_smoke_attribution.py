#!/usr/bin/env python3
"""
CI Smoke Test: Features + Attribution Join
-----------------------------------------

This script generates a tiny synthetic OHLCV dataset, computes pa_only features
with basic patterns, writes a Parquet file, runs the attribution join with
parity checks, and asserts:
- Parquet schema present
- Hash parity passes
- Duplicate timestamps rejected
- Expected KPI files produced (trend, pattern)

Run:
  python scripts/ci_smoke_attribution.py
"""

import os
import json
import time
import pandas as pd
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer.providers.pa_only import compute_pa_trend
from analyzer.patterns.basic import detect_patterns
from analyzer.feature_writer import write_features_parquet, build_metadata, compute_bars_hash
from analyzer.reports.attribution_join import join_and_report


def _make_synth_ohlcv() -> pd.DataFrame:
    # Build a 2H synthetic series with patterns similar to unit tests
    rows = [
        {'Open': 10.0,  'High': 11.0,  'Low':  9.0,  'Close':  9.5,  'Volume': 1000},  # bear body
        {'Open':  9.6,  'High': 11.5,  'Low':  9.1,  'Close': 11.2,  'Volume': 1100},  # bull engulf
        {'Open': 11.2,  'High': 11.8,  'Low': 10.8,  'Close': 11.0,  'Volume':  900},
        {'Open': 11.0,  'High': 11.1,  'Low': 10.0,  'Close': 10.1,  'Volume':  950},  # pin bull
        {'Open': 10.1,  'High': 11.2,  'Low': 10.0,  'Close': 10.2,  'Volume':  980},
        {'Open': 10.2,  'High': 10.25, 'Low': 10.15, 'Close': 10.21, 'Volume': 1005},  # doji
        {'Open': 10.21, 'High': 10.3,  'Low': 10.2,  'Close': 10.25, 'Volume':  995},
        {'Open': 10.25, 'High': 10.5,  'Low': 10.0,  'Close': 10.1,  'Volume': 1010},  # outside bar
        {'Open': 10.1,  'High': 10.15, 'Low': 10.05, 'Close': 10.1,  'Volume': 1000},  # inside bar
        {'Open': 10.1,  'High': 10.6,  'Low':  9.9,  'Close': 10.5,  'Volume': 1020},
        {'Open': 10.6,  'High': 11.4,  'Low': 10.3,  'Close': 11.1,  'Volume': 1030},
        {'Open': 11.0,  'High': 11.8,  'Low': 10.7,  'Close': 11.6,  'Volume': 1040},
    ]
    idx = pd.date_range('2020-01-01', periods=len(rows), freq='2h')
    df = pd.DataFrame(rows, index=idx)
    return df


def _assert_schema(df: pd.DataFrame, required_cols: list[str]):
    missing = [c for c in required_cols if c not in df.columns]
    assert not missing, f"Missing required columns in features parquet: {missing}"


def run_smoke():
    symbol = 'XAUUSD'
    timeframe = '2H'
    provider = 'pa_only'
    feature_version = 'v1'
    run_uid = f"CI_{time.strftime('%Y%m%d_%H%M%S')}"

    price = _make_synth_ohlcv()
    # Compute features
    pa = compute_pa_trend(price, left=1, right=1)
    pats = detect_patterns(price, include_swings=True, swings=pa)
    
    # Since `pats` was created using swings from `pa`, `pa` already contains
    # all swing-related columns. We only need to join the new candle patterns.
    candle_pattern_cols = pats.columns.difference(pa.columns)
    feat = pa.join(pats[candle_pattern_cols])

    # Write features parquet
    out_dir = os.path.join('outputs', 'features_ci')
    os.makedirs(out_dir, exist_ok=True)
    parquet_path = write_features_parquet(
        chart_path=os.path.join('data', 'active_charts', f'{symbol}_{timeframe}_synthetic.csv'),
        price=price,
        features=feat,
        provider=provider,
        feature_version=feature_version,
        out_dir=out_dir,
        symbol=symbol,
        timeframe=timeframe,
        run_uid=run_uid,
        expected_symbol=symbol,
        expected_timeframe=timeframe,
    )

    # Parquet schema check
    pf = pd.read_parquet(parquet_path)
    required = [
        'timestamp','symbol','timeframe','provider','feature_version','run_uid','created_at',
        'bars_hash','bar_count','first_ts','last_ts','tz',
        'trend_label'
    ]
    _assert_schema(pf, required)

    # Parity meta
    price_meta = build_metadata(price, symbol=symbol, timeframe=timeframe, run_uid=run_uid, created_at=pf['created_at'].iloc[0])

    # Build toy trades aligned at bar close
    ts = price.index
    trades = pd.DataFrame({
        'Id': list(range(1, 7)),
        'Entry Date': [ts[1], ts[3], ts[5], ts[7], ts[9], ts[11]],
        'Return [%]': [2.5, -1.2, 0.1, 1.8, -0.7, 3.3],
    })

    # Run join and assert outputs exist
    out_dir_reports = os.path.join('reports', 'attribution', run_uid)
    outs, info = join_and_report(
        run_json_path=os.path.join('outputs','runs','ci_placeholder.json'),
        trades_df=trades,
        features_parquet_path=parquet_path,
        output_dir=out_dir_reports,
        price_meta=pd.Series(price_meta),
        execution_alignment='at_bar_close',
        nan_policy='drop',
        expected_feature_version=feature_version,
    )

    assert 'kpi_by_trend' in outs and os.path.exists(outs['kpi_by_trend'])
    assert 'kpi_by_pattern' in outs and os.path.exists(outs['kpi_by_pattern'])

    # Duplicate timestamp rejection
    price_dup = price.copy()
    price_dup.index = price_dup.index.where(price_dup.index != price_dup.index[-1], price_dup.index[-2])
    try:
        compute_bars_hash(price_dup)
        raise AssertionError('Expected duplicate timestamp rejection did not occur')
    except ValueError:
        pass

    # Basic buckets presence
    kpi_trend = pd.read_csv(outs['kpi_by_trend'])
    assert len(kpi_trend) > 0
    kpi_pattern = pd.read_csv(outs['kpi_by_pattern'])
    assert len(kpi_pattern) > 0

    print(json.dumps({
        'status': 'ok',
        'features_parquet': parquet_path,
        'reports': outs,
        'info_keys': list(info.keys()),
    }, indent=2))


if __name__ == '__main__':
    run_smoke()


