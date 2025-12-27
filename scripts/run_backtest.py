import argparse
import os
import json
import pandas as pd
from src.io.data_loader import load_first_chart, load_chart_from_path
from src.strategy.bands import compute_signals
from src.engine.backtest import run_backtest
from config.user_inputs import BACKTEST_CONFIG as USER_BACKTEST_CONFIG, TOGGLES
from config.strategy_params import BASELINE_PARAMS


PARAMS = BASELINE_PARAMS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial-uid', type=str, default=None, help='Run backtest for a specific trial UID (20250823_130210:671)')
    parser.add_argument('--run-json', type=str, default=None, help='Path to run JSON (defaults to latest in outputs/runs)')
    args = parser.parse_args()

    params = PARAMS.copy()
    price = None

    if args.trial_uid:
        # Resolve run JSON path
        run_json = args.run_json
        if not run_json:
            # Pick latest JSON in outputs/runs
            runs_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'runs')
            jsons = [os.path.join(runs_dir, f) for f in os.listdir(runs_dir) if f.lower().endswith('.json')]
            if not jsons:
                raise FileNotFoundError('No run JSON found under outputs/runs')
            run_json = max(jsons, key=os.path.getmtime)
        data = json.load(open(run_json, 'r', encoding='utf-8'))
        df = pd.DataFrame(data.get('results') or [])
        row = df[df.get('trial_uid') == args.trial_uid]
        if len(row) == 0:
            raise ValueError(f'Trial UID not found: {args.trial_uid}')
        r0 = row.iloc[0]
        # Extract params
        for k, v in r0.items():
            if isinstance(k, str) and k.startswith('param_'):
                params[k.replace('param_', '')] = v
        # Load chart
        chart_name = r0.get('chart')
        if not chart_name:
            raise ValueError('Selected trial row has no chart name')
        from config.data import ACTIVE_CHARTS_DIR
        chart_path = os.path.join(ACTIVE_CHARTS_DIR, chart_name)
        if not os.path.exists(chart_path):
            raise FileNotFoundError(f'Chart not found in active_charts: {chart_name}')
        price = load_chart_from_path(chart_path)
        print(f"Loaded trial {args.trial_uid} on chart {chart_name}")
    else:
        price = load_first_chart()

    entries, exits, _ = compute_signals(price, params, TOGGLES)
    pf = run_backtest(price, entries, exits, backtest_overrides=USER_BACKTEST_CONFIG)
    stats = pf.stats()
    print("\n=== Backtest Stats ===")
    print(stats)


if __name__ == '__main__':
    main()


