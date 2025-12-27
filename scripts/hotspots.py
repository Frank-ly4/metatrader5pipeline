import argparse
import os
import pandas as pd
import numpy as np


PARAM_COLS = [
    'param_fast_min_len','param_fast_max_len','param_slow_min_len','param_slow_max_len',
    'param_dma_atr_len','param_atr_len',
    'param_upper_outer_mult','param_lower_outer_mult','param_upper_inner_mult','param_lower_inner_mult',
    'param_momentum_len','param_momentum_threshold'
]


def _load_results(path: str, sheet: str | None) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if path.endswith('.xlsx'):
        return pd.read_excel(path, sheet_name=sheet or 'AllResults')
    if path.endswith('.csv'):
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file type: {path}")


def _select_top(df: pd.DataFrame, metric: str, frac: float | None, topk: int | None) -> pd.DataFrame:
    d = df.copy()
    if metric not in d.columns:
        raise ValueError(f"Metric not found: {metric}")
    d = d[d[metric].notna()]
    d = d.sort_values(metric, ascending=False)
    if topk is not None and topk > 0:
        return d.head(topk)
    if frac is not None and 0 < frac <= 1:
        k = max(1, int(round(frac * len(d))))
        return d.head(k)
    return d


def _quantile_bounds(series: pd.Series, lo: float = 0.1, hi: float = 0.9) -> tuple[float, float]:
    s = pd.to_numeric(series, errors='coerce').dropna()
    if len(s) == 0:
        return (np.nan, np.nan)
    return (float(s.quantile(lo)), float(s.quantile(hi)))


def suggest_ranges(df: pd.DataFrame, metric: str, top_frac: float = 0.1) -> dict:
    """Suggest narrowed PARAM_RANGES from the top-performing region using quantile envelopes.

    Returns mapping of param name (without 'param_' prefix) to string range spec.
    """
    top = _select_top(df, metric=metric, frac=top_frac, topk=None)
    out: dict[str, str] = {}
    for col in PARAM_COLS:
        if col not in top.columns:
            continue
        lo, hi = _quantile_bounds(top[col], 0.15, 0.85)
        if not np.isnan(lo) and not np.isnan(hi):
            name = col.replace('param_', '')
            # format as int or float range with sensible steps
            if float(lo).is_integer() and float(hi).is_integer():
                out[name] = f"{int(lo)}-{int(hi)}"
            else:
                # choose step 0.1 for fractional parameters
                lo_r = round(lo, 2)
                hi_r = round(hi, 2)
                out[name] = f"{lo_r}-{hi_r}:0.1"
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', required=True, help='Path to optimizer_central.xlsx or a CSV of results')
    p.add_argument('--sheet', default='AllResults', help='Excel sheet name to read (ignored for CSV)')
    p.add_argument('--metric', default='total_return')
    p.add_argument('--top-frac', type=float, default=0.10)
    p.add_argument('--chart', default=None)
    p.add_argument('--export', default=None, help='Optional path to write suggested ranges JSON')
    args = p.parse_args()

    df = _load_results(args.source, args.sheet)
    if args.chart and 'chart' in df.columns:
        df = df[df['chart'] == args.chart]
    if len(df) == 0:
        print('No data after filtering.')
        return

    suggested = suggest_ranges(df, metric=args.metric, top_frac=args.top_frac)
    if not suggested:
        print('No suggestions could be computed.')
        return

    print('Suggested narrowed ranges (based on top performers):')
    for k, v in suggested.items():
        print(f"  {k}: {v}")

    if args.export:
        import json
        with open(args.export, 'w', encoding='utf-8') as f:
            json.dump(suggested, f, indent=2)
        print(f"Exported suggestions to {os.path.abspath(args.export)}")


if __name__ == '__main__':
    main()


