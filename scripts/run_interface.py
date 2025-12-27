import os
import json
import glob

RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'runs')


def list_trial_files():
    pattern = os.path.abspath(os.path.join(RESULTS_DIR, '*.json'))
    files = glob.glob(pattern)
    # Sort newest first
    files = sorted(files, key=os.path.getmtime, reverse=True)
    return [os.path.basename(f) for f in files]


def load_trial(filename: str):
    path = os.path.abspath(os.path.join(RESULTS_DIR, filename))
    if not os.path.exists(path):
        print('File not found:', path)
        return None
    with open(path, 'r') as f:
        return json.load(f)


def top_n_by_metric(results_list, metric: str, n: int = 10):
    try:
        sorted_list = sorted(results_list, key=lambda r: (r.get(metric) is None, r.get(metric)), reverse=True)
        return sorted_list[:n]
    except Exception:
        return []


def main():
    print("\n=== Trials Available (latest first) ===")
    files = list_trial_files()
    if not files:
        print("No trial result files found in outputs.")
        return
    for i, f in enumerate(files, 1):
        print(f"{i}. {f}")

    print("\nMetrics menu:")
    metrics = [
        ('M_1', 'total_return'),
        ('M_2', 'sharpe_ratio'),
        ('M_3', 'sortino_ratio'),
        ('M_4', 'calmar_robust'),
        ('M_5', 'max_drawdown'),
        ('M_6', 'profit_factor'),
        ('M_7', 'win_rate')
    ]
    for code, name in metrics:
        print(f"Type {code} for top by {name}")

    selection = input("\nEnter metric code: ").strip().upper()
    metric_map = {code: name for code, name in metrics}
    if selection not in metric_map:
        print("Invalid selection.")
        return
    metric = metric_map[selection]

    trial_idx = input("Enter trial number from list above: ").strip()
    try:
        idx = int(trial_idx) - 1
        trial_file = files[idx]
    except Exception:
        print("Invalid trial number.")
        return

    data = load_trial(trial_file)
    if data is None:
        return
    results = data.get('results', []) if isinstance(data, dict) else []
    top10 = top_n_by_metric(results, metric, n=10)
    print(f"\n=== Top 10 by {metric} for {trial_file} ===")
    # Show trial_uid, chart, metric, and a compact param view
    for i, row in enumerate(top10, 1):
        uid = row.get('trial_uid') or row.get('trial_id')
        chart = row.get('chart')
        metric_val = row.get(metric)
        param_keys = [k for k in row.keys() if isinstance(k, str) and k.startswith('param_')]
        sample_params = {k.replace('param_', ''): row.get(k) for k in sorted(param_keys)}
        print(f"{i}. uid={uid} | chart={chart} | {metric}={metric_val} | params={sample_params}")


if __name__ == '__main__':
    main()


