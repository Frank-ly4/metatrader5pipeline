#!/usr/bin/env python3
"""
Enhanced Interactive Backtester

Features:
- UID selection from optimization results
- Chart selection (all charts or specific charts)
- Custom user inputs (fees, position size, starting capital)
- Results display from notebook
- Capital tracking (start/end values)
- Filter Backtesting (interactive): select runs, trials (multi), charts (all or subset),
  apply >=-style filters on performance metrics/risk ratios, view details, generate MQL5 EAs
"""
import os
import sys
import json
import time
from typing import Dict, List, Tuple, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# --- LIGHTWEIGHT BOOTSTRAP ---
# Defer heavy imports to improve startup time.


def select_run() -> Optional[Dict]:
    """Interactive run selection from JSON files in outputs/runs."""
    runs_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'runs')
    if not os.path.exists(runs_dir):
        print("❌ No runs directory found at outputs/runs/")
        return None

    runs = []
    for filename in sorted(os.listdir(runs_dir), reverse=True):
        if filename.lower().endswith('.json'):
            try:
                filepath = os.path.join(runs_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                metadata = data.get('metadata', {})
                runs.append({
                    'filepath': filepath,
                    'run_id': metadata.get('run_id', 'N/A'),
                    'method': metadata.get('method', 'N/A'),
                    'timestamp': metadata.get('timestamp', 'N/A'),
                    'num_results': len(data.get('results', [])),
                    'data': data
                })
            except (json.JSONDecodeError, KeyError):
                continue

    if not runs:
        print("❌ No optimization runs found in outputs/runs/")
        return None

    print("📁 AVAILABLE OPTIMIZATION RUNS (most recent first)")
    print("=" * 80)
    for i, run in enumerate(runs[:15], 1):  # Show 15 most recent
        print(f"{i:2d}. {run['timestamp']} | {run['run_id']} | {run['method'].upper():<7} | {run['num_results']} results")
    print("=" * 80)

    while True:
        try:
            choice = input(f"Select a run to analyze (1-{min(15, len(runs))}) or 'q' to quit: ").strip()
            if choice.lower() == 'q':
                return None
            idx = int(choice) - 1
            if 0 <= idx < min(15, len(runs)):
                return runs[idx]
            else:
                print("Invalid selection.")
        except ValueError:
            print("Please enter a valid number.")


def select_trial(run: Dict) -> Optional[Dict]:
    """Select a trial from the chosen run and return its full data row."""
    import pandas as pd  # Lazy

    results = run['data'].get('results', [])
    if not results:
        print("❌ No results found in this run.")
        return None

    df = pd.DataFrame(results)
    
    # --- Interactive Sorting and Filtering ---
    
    # 1. Select Metric
    metric_cols = sorted([c for c in df.columns if c in ['total_return', 'sharpe_ratio', 'sortino_ratio', 'calmar_ratio', 'max_drawdown', 'win_rate', 'total_trades']])
    print("\n📊 Select metric to sort by:")
    for i, col in enumerate(metric_cols, 1):
        print(f"  {i}. {col}")
    
    sort_metric = 'sharpe_ratio' # Default
    try:
        metric_choice = input(f"Enter choice [default: sharpe_ratio]: ").strip()
        if metric_choice:
            sort_metric = metric_cols[int(metric_choice) - 1]
    except (ValueError, IndexError):
        print(f"Invalid choice, defaulting to {sort_metric}.")

    # 2. Select Top X
    top_n = 15 # Default
    try:
        top_n_str = input(f"How many top trials to display? [default: 15]: ").strip()
        if top_n_str:
            top_n = int(top_n_str)
    except ValueError:
        print(f"Invalid number, defaulting to {top_n}.")
        
    # --- Sorting and Display ---

    # Sort ascending for drawdown, descending for others
    ascending = True if 'drawdown' in sort_metric else False
    df = df.sort_values(by=sort_metric, ascending=ascending)
    
    print(f"\n🏆 TOP {top_n} TRIALS from run {run['run_id']} (sorted by {sort_metric})")
    top_trials = df.head(top_n)

    # Display table
    print("-" * 110)
    header = f"{'#':<3} {'trial_uid':<20} {'Chart':<25} {'Return':>10} {'Sharpe':>10} {'Max DD':>10} {'Trades':>10}"
    print(header)
    print("-" * 110)
    for i, (_, row) in enumerate(top_trials.iterrows(), 1):
        print(f"{i:<3} {row.get('trial_uid', ''):<20} {row.get('chart', ''):<25} "
              f"{row.get('total_return', 0):>9.2f}% "
              f"{row.get('sharpe_ratio', 0):>10.3f} "
              f"{row.get('max_drawdown', 0):>9.2f}% "
              f"{row.get('total_trades', 0):>10.0f}")
    print("-" * 110)

    while True:
        try:
            choice = input(f"Select trial to backtest (1-{len(top_trials)}) or 'b' to go back: ").strip()
            if choice.lower() == 'b':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(top_trials):
                return top_trials.iloc[idx].to_dict()
            else:
                print("Invalid selection.")
        except ValueError:
            print("Please enter a valid number.")


def get_portfolio_overrides() -> Dict:
    """Get interactive overrides for portfolio settings."""
    from config.backtest_user_inputs import BACKTEST_CONFIG as DEFAULTS

    print("\n⚙️  PORTFOLIO CONFIGURATION (press Enter for default)")
    print("=" * 50)

    try:
        capital = float(input(f"Enter Starting Capital [{DEFAULTS['init_cash']}]: ").strip() or DEFAULTS['init_cash'])
    except ValueError:
        capital = DEFAULTS['init_cash']

    try:
        layers = int(input(f"Enter Max Concurrent Positions (Layers) [{DEFAULTS['max_layers']}]: ").strip() or DEFAULTS['max_layers'])
    except ValueError:
        layers = DEFAULTS['max_layers']

    try:
        fees_str = input(f"Enter Fees % [{DEFAULTS['fees']*100}]: ").strip().replace('%', '')
        fees = float(fees_str) / 100.0 if fees_str else DEFAULTS['fees']
    except ValueError:
        fees = DEFAULTS['fees']

    overrides = {
        'init_cash': capital,
        'max_layers': layers,
        'fees': fees
    }
    print("\n✓ Configuration updated:")
    print(f"  - Starting Capital: ${overrides['init_cash']:,.2f}")
    print(f"  - Max Layers: {overrides['max_layers']}")
    print(f"  - Fees: {overrides['fees']*100:.4f}%")

    return overrides


def select_charts() -> List[str]:
    """Interactive chart selection."""
    from src.io.data_loader import list_active_chart_paths

    available_charts = list_active_chart_paths()
    if not available_charts:
        print("❌ No charts found in active_charts directory")
        return []

    print("\n📊 CHART SELECTION")
    print("=" * 50)
    print("1. Test on ALL active charts")
    print("2. Select specific charts")
    
    while True:
        choice = input("Choose option (1-2): ").strip()
        if choice == '1':
            return available_charts
        elif choice == '2':
            for i, path in enumerate(available_charts, 1):
                print(f"  {i:2d}. {os.path.basename(path)}")
            
            try:
                sel = input("Enter chart numbers (e.g., 1,3,5 or 1-3): ").strip()
                selected_indices = set()
                for part in sel.replace(' ', '').split(','):
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        selected_indices.update(range(start - 1, end))
                    else:
                        selected_indices.add(int(part) - 1)
                
                valid_charts = [available_charts[i] for i in sorted(selected_indices) if 0 <= i < len(available_charts)]
                if valid_charts:
                    print(f"✓ Selected {len(valid_charts)} charts.")
                    return valid_charts
            except ValueError:
                print("Invalid input.")
        print("Please try again.")


def run_single_backtest(trial_data: Dict, chart_path: str, portfolio_overrides: Dict) -> Optional[Dict]:
    """Run backtest for a specific trial and chart."""
    # LAZY IMPORTS
    from src.io.data_loader import load_chart_from_path
    from src.strategy.bands import compute_signals
    from src.engine.backtest import run_backtest
    from config.user_inputs import TOGGLES

    params = {k.replace('param_', ''): v for k, v in trial_data.items() if isinstance(k, str) and k.startswith('param_')}
    if not params:
        print(f"  ✗ Error: No 'param_' columns found for trial {trial_data.get('trial_uid')}")
        return None
    
    price_data = load_chart_from_path(chart_path)
    entries, exits, _ = compute_signals(price_data, params, TOGGLES)
    
    # Combine defaults with user overrides
    from config.backtest_user_inputs import BACKTEST_CONFIG as DEFAULTS
    final_config = DEFAULTS.copy()
    final_config.update(portfolio_overrides)
    
    pf = run_backtest(price_data, entries, exits, backtest_overrides=final_config)
    stats = pf.stats()
    
    return {
        'chart': os.path.basename(chart_path),
        'trial_uid': trial_data.get('trial_uid'),
        'start_capital': stats.get('Start Value'),
        'end_capital': stats.get('End Value'),
        'total_return_pct': stats.get('Total Return [%]', 0),
        'sharpe_ratio': stats.get('Sharpe Ratio', 0),
        'max_drawdown_pct': stats.get('Max Drawdown [%]', 0),
        'total_trades': stats.get('Total Trades', 0),
        'win_rate_pct': stats.get('Win Rate [%]', 0),
        'stats': stats, # For detailed view
    }


def display_results(results: List[Dict]):
    """Display backtest results in a formatted table."""
    print(f"\n🎯 BACKTEST RESULTS")
    print("=" * 110)
    header = f"{'Chart':<30} {'Start $':>12} {'End $':>12} {'Return':>10} {'Sharpe':>10} {'Max DD':>10} {'Trades':>8} {'Win %':>8}"
    print(header)
    print("-" * 110)
    
    for res in results:
        print(f"{res.get('chart', ''):<30} "
              f"${res.get('start_capital', 0):>11,.2f} "
              f"${res.get('end_capital', 0):>11,.2f} "
              f"{res.get('total_return_pct', 0):>9.2f}% "
              f"{res.get('sharpe_ratio', 0):>10.3f} "
              f"{res.get('max_drawdown_pct', 0):>9.2f}% "
              f"{res.get('total_trades', 0):>8.0f} "
              f"{res.get('win_rate_pct', 0):>7.2f}%")
    print("=" * 110)


def run_backtest_workflow():
    """Main workflow for a single backtest run."""
    run = select_run()
    if not run:
        return True

    trial = select_trial(run)
    if not trial:
        return True
    
    charts = select_charts()
    if not charts:
        return True

    overrides = get_portfolio_overrides()

    print(f"\n🔬 Backtesting trial {trial['trial_uid']} on {len(charts)} chart(s)...")
    results = []
    for chart_path in charts:
        try:
            res = run_single_backtest(trial, chart_path, overrides)
            if res:
                results.append(res)
        except Exception as e:
            print(f"  ✗ Error on {os.path.basename(chart_path)}: {e}")

    if results:
        display_results(results)
        # Allow detailed view
        while True:
            try:
                choice = input("\nEnter chart number to see detailed stats (e.g., 1) or 'q' to finish: ").strip().lower()
                if choice == 'q':
                    break
                idx = int(choice) - 1
                if 0 <= idx < len(results):
                    stats = results[idx]['stats']
                    print(f"\n--- Detailed Stats for {results[idx]['chart']} ---")
                    # Use pandas to format the series nicely
                    import pandas as pd
                    print(pd.Series(stats))
                    print("-------------------------------------------------")
                else:
                    print("Invalid number.")
            except (ValueError, IndexError):
                print("Invalid input. Please enter a number from the list or 'q'.")
    return True


def main():
    """Main menu loop."""
    while True:
        print("\n🚀 INTERACTIVE BACKTESTER")
        print("=" * 50)
        print("1. Run New Backtest")
        print("2. Exit")

        choice = input("\nSelect option: ").strip()

        if choice == '1':
            if not run_backtest_workflow():
                break
        elif choice == '2':
            print("Goodbye!")
            break
        else:
            print("Invalid option. Please enter 1 or 2.")


if __name__ == '__main__':
    main()
