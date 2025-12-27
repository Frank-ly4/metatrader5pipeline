import os
import json
import argparse
from typing import List, Dict, Any, Optional

import pandas as pd
import numpy as np


def list_run_jsons(runs_dir: str, max_files: Optional[int] = None) -> List[str]:
    files = [
        os.path.join(runs_dir, f)
        for f in os.listdir(runs_dir)
        if f.lower().endswith('.json')
    ]
    # newest first
    files = sorted(files, key=lambda p: os.path.getmtime(p), reverse=True)
    if isinstance(max_files, int) and max_files > 0:
        files = files[:max_files]
    return files


def load_runs(runs_dir: str, max_files: Optional[int] = None) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for path in list_run_jsons(runs_dir, max_files=max_files):
        try:
            data = json.load(open(path, 'r', encoding='utf-8'))
        except Exception:
            continue
        results = data.get('results') if isinstance(data, dict) else None
        if isinstance(results, list):
            for row in results:
                row['run_file'] = path
                rows.append(row)
    return pd.DataFrame(rows)


def flatten_params(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df


def select_metrics(df: pd.DataFrame, metric_columns: List[str]) -> pd.DataFrame:
    cols = [c for c in metric_columns if c in df.columns]
    return df[cols] if cols else pd.DataFrame(index=df.index)


def _run_length_stats(series: pd.Series) -> Dict[str, float]:
    stats = {'max_pos_run': 0, 'max_neg_run': 0}
    if series is None or len(series) == 0:
        return stats
    b = series.astype(bool).values
    max_pos = max_neg = cur_pos = cur_neg = 0
    for v in b:
        if v:
            cur_pos += 1
            cur_neg = 0
        else:
            cur_neg += 1
            cur_pos = 0
        max_pos = max(max_pos, cur_pos)
        max_neg = max(max_neg, cur_neg)
    stats['max_pos_run'] = float(max_pos)
    stats['max_neg_run'] = float(max_neg)
    return stats


def _dd_hist_stub(df: pd.DataFrame) -> Dict[str, float]:
    out = {}
    key = 'max_drawdown'
    if key in df.columns:
        try:
            vals = df[key].astype(float).values
            bins = [-100, -50, -30, -15, -10, 0]
            labels = ['dd_le_50', 'dd_le_30', 'dd_le_15', 'dd_le_10', 'dd_le_0']
            hist = {lab: 0.0 for lab in labels}
            for v in vals:
                for i in range(len(bins)-1):
                    if v >= bins[i] and v < bins[i+1]:
                        hist[labels[i]] += 1
                        break
            total = max(1.0, float(len(vals)))
            out = {k: (v/total) for k, v in hist.items()}
        except Exception:
            pass
    return out


def build_features(runs_dir: str, out_path: str, metric_columns: List[str], max_runs: Optional[int] = None) -> pd.DataFrame:
    df = load_runs(runs_dir, max_files=max_runs)
    if df.empty:
        print('No run JSONs found; nothing to build.')
        return df
    df = flatten_params(df)

    id_cols = [c for c in ['run_id', 'trial_id', 'trial_uid', 'chart'] if c in df.columns]
    param_cols = [c for c in df.columns if isinstance(c, str) and c.startswith('param_')]
    metric_cols = [c for c in metric_columns if c in df.columns]

    features = df[id_cols + param_cols + metric_cols].copy()

    if 'win_rate' in df.columns:
        win_rate = df['win_rate'].astype(float) / 100.0
        mask = win_rate > 0.5
        stats = _run_length_stats(mask)
        for k, v in stats.items():
            features[k] = v
    dd_bins = _dd_hist_stub(df)
    for k, v in dd_bins.items():
        features[k] = v

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    features.to_parquet(out_path, index=False)
    print(f'Wrote features to {out_path} with {len(features)} rows and {len(features.columns)} columns (from newest {max_runs or "all"} run file(s))')
    return features


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs_dir', required=True)
    ap.add_argument('--out_path', required=True)
    ap.add_argument('--metrics', nargs='*', default=[])
    ap.add_argument('--max_runs', type=int, default=None, help='Limit to newest N run JSONs')
    args = ap.parse_args()

    build_features(args.runs_dir, args.out_path, args.metrics, max_runs=args.max_runs)


if __name__ == '__main__':
    main()
