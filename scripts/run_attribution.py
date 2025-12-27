#!/usr/bin/env python3
"""
Run Read-Only Attribution Reports
---------------------------------

Usage:
  python scripts/run_attribution.py --run-json outputs/runs/<file>.json --trades-csv <path_to_trades.csv> \
      [--features-dir outputs/features] [--provider mcg|pa_only] [--feature-version v1] [--chart <chart_name>]

Emits CSV reports under reports/attribution/<run_uid>/.

Notes:
- This script is read-only: it does not change optimizer/backtester logic.
- It refuses to join if parity checks on bars metadata fail.
"""

import argparse
import os
import json
import pandas as pd

from analyzer.feature_writer import compute_bars_hash, build_metadata
from analyzer.reports.attribution_join import join_and_report
from src.io.data_loader import load_chart_from_path
from config.data import ACTIVE_CHARTS_DIR


def _derive_run_uid(run_json_path: str) -> str:
    return os.path.splitext(os.path.basename(run_json_path))[0]


def _resolve_chart_name(run_json: dict, explicit_chart: str | None) -> str:
    if explicit_chart:
        return explicit_chart
    charts = run_json.get('metadata', {}).get('charts_processed') or []
    if isinstance(charts, list) and len(charts) > 0:
        return charts[0]
    # Fallback: try first result row
    results = run_json.get('results') or []
    for row in results:
        name = row.get('chart')
        if name:
            return name
    raise ValueError('Unable to resolve chart name from run JSON; pass --chart explicitly')


def _resolve_features_path(features_dir: str, symbol: str, timeframe: str, provider: str, feature_version: str) -> str:
    fname = f"{symbol}_{timeframe}_{provider}_{feature_version}.parquet"
    path = os.path.join(features_dir, fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Features parquet not found: {path}")
    return path


def _parse_symbol_timeframe(chart_name: str) -> tuple[str, str | None]:
    base = os.path.splitext(os.path.basename(chart_name))[0]
    parts = base.split('_')
    sym = parts[0] if parts else base
    tf = None
    for token in parts[1:]:
        if token.endswith(('m','h','d')) and token[:-1].isdigit():
            tf = token
            break
    return sym, tf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-json', required=True, help='Path to outputs/runs JSON file')
    ap.add_argument('--trades-csv', required=True, help='Path to trades CSV for the run (vectorbt records_readable)')
    ap.add_argument('--features-dir', default=os.path.join('outputs','features'))
    ap.add_argument('--provider', default='mcg', choices=['mcg','pa_only'])
    ap.add_argument('--feature-version', default='v1')
    ap.add_argument('--exec-align', default='at_bar_close', choices=['at_bar_close','next_bar_open','intrabar_mid'])
    ap.add_argument('--nan-policy', default='drop', choices=['drop','unknown_bucket'])
    ap.add_argument('--alias', action='append', help='Symbol alias mapping like A=B (trades=A -> features=B). Can use multiple.')
    ap.add_argument('--chart', default=None, help='Chart filename as in active_charts (optional)')
    args = ap.parse_args()

    run_data = json.load(open(args.run_json, 'r', encoding='utf-8'))
    run_uid = _derive_run_uid(args.run_json)
    out_dir = os.path.join('reports','attribution', run_uid)
    os.makedirs(out_dir, exist_ok=True)

    chart_name = _resolve_chart_name(run_data, args.chart)
    price_path = os.path.join(ACTIVE_CHARTS_DIR, chart_name)
    if not os.path.exists(price_path):
        raise FileNotFoundError(f"Chart not found in active_charts: {chart_name}")
    price = load_chart_from_path(price_path)

    symbol, timeframe = _parse_symbol_timeframe(chart_name)
    if timeframe is None:
        # Infer from index if not encoded in name
        from src.strategy.regime import infer_timeframe
        timeframe = infer_timeframe(pd.DatetimeIndex(price.index))

    features_path = _resolve_features_path(args.features_dir, symbol, timeframe, args.provider, args.feature_version)

    # Compute price-side metadata for parity check
    price_meta = build_metadata(price, symbol=symbol, timeframe=timeframe)
    # Load trades
    trades = pd.read_csv(args.trades_csv)
    # Perform join and reporting
    outs, info = join_and_report(
        run_json_path=args.run_json,
        trades_df=trades,
        features_parquet_path=features_path,
        output_dir=out_dir,
        price_meta=pd.Series(price_meta),
        execution_alignment=args.exec_align,
        alias_map=dict(a.split('=',1) for a in args.alias) if args.alias else None,
        nan_policy=args.nan_policy,
        expected_feature_version=args.feature_version,
    )
    # Write summary.json with inputs, hashes, counts, provider/version
    # Enrich summary with config snapshot and environment
    import subprocess, sys
    try:
        git_sha = subprocess.check_output(['git','rev-parse','HEAD'], cwd=os.path.dirname(__file__)+"/..", stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        git_sha = ''
    try:
        import pkg_resources
        pkgs = {d.project_name: d.version for d in pkg_resources.working_set}
    except Exception:
        pkgs = {}

    summary = {
        'run_uid': run_uid,
        'chart': chart_name,
        'symbol': symbol,
        'timeframe': timeframe,
        'provider': args.provider,
        'feature_version': args.feature_version,
        'features_parquet': os.path.relpath(features_path, out_dir),
        'bars_hash': price_meta['bars_hash'],
        'bar_count': price_meta['bar_count'],
        'first_ts': price_meta['first_ts'],
        'last_ts': price_meta['last_ts'],
        'tz': price_meta['tz'],
        'run_created_at': price_meta.get('created_at', ''),
        'git_sha': git_sha,
        'python_version': sys.version,
        'packages': pkgs,
        'cli_args': vars(args),
        'execution_alignment': args.exec_align,
        'nan_policy': args.nan_policy,
        'alias_map': dict(a.split('=',1) for a in args.alias) if args.alias else {},
        'artifacts': {k: os.path.relpath(v, out_dir) for k, v in outs.items()},
        'info': info,
    }
    with open(os.path.join(out_dir, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    print("Attribution reports:")
    for k, v in outs.items():
        print(f"  {k}: {os.path.abspath(v)}")


if __name__ == '__main__':
    main()


