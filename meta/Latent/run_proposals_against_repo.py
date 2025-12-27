import argparse
import json
import os
import sys

# Add repo to path for imports
DEFAULT_REPO = r"C:\Users\frank\Desktop\opt_4\4.2\4.2.4"
if DEFAULT_REPO not in sys.path:
    sys.path.insert(0, DEFAULT_REPO)

import pandas as pd
from src.io.data_loader import load_first_chart, load_chart_from_path
from src.strategy.bands import compute_signals
from src.engine.backtest import run_backtest
from config.user_inputs import BACKTEST_CONFIG as USER_BACKTEST_CONFIG, TOGGLES
from config.strategy_params import BASELINE_PARAMS
from config.data import ACTIVE_CHARTS_DIR


def load_proposals(path: str):
    data = json.load(open(path, 'r', encoding='utf-8'))
    if not isinstance(data, list):
        raise ValueError('proposals.json must be a list')
    return data


def params_from_decoded(decoded: dict) -> dict:
    p = BASELINE_PARAMS.copy()
    for k, v in decoded.items():
        p[k] = v
    return p


def run_on_chart(chart_name: str, params: dict) -> dict:
    chart_path = os.path.join(ACTIVE_CHARTS_DIR, chart_name)
    if not os.path.exists(chart_path):
        raise FileNotFoundError(f'Chart not found in active_charts: {chart_name}')
    price = load_chart_from_path(chart_path)
    entries, exits, _ = compute_signals(price, params, TOGGLES)
    pf = run_backtest(price, entries, exits, backtest_overrides=USER_BACKTEST_CONFIG)
    stats = pf.stats()
    return {k: (float(v) if hasattr(v, 'item') else v) for k, v in stats.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--proposals', default=os.path.join('.', 'proposals', 'proposals.json'))
    ap.add_argument('--charts', nargs='*', default=None, help='Chart file names from active_charts to test')
    ap.add_argument('--out', default=os.path.join('.', 'proposals', 'proposal_backtests.json'))
    args = ap.parse_args()

    props = load_proposals(args.proposals)
    # default to first chart only to keep runtime down
    charts = args.charts
    if not charts:
        # Choose the first available chart in active_charts
        ac = [f for f in os.listdir(ACTIVE_CHARTS_DIR) if f.lower().endswith('.csv')]
        if not ac:
            raise FileNotFoundError('No charts found in active_charts')
        charts = [ac[0]]

    results = []
    for p in props:
        decoded = p.get('decoded_params') or {}
        params = params_from_decoded(decoded)
        for chart in charts:
            try:
                stats = run_on_chart(chart, params)
            except Exception as e:
                stats = {'error': str(e)}
            row = {
                'chart': chart,
                'cluster_id': p.get('cluster_id'),
                'method': p.get('method'),
                'decoded_params': decoded,
                'stats': stats
            }
            results.append(row)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    print(f'Wrote {len(results)} proposal backtest result(s) to {args.out}')


if __name__ == '__main__':
    main()
