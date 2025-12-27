"""
Non-interactive batch optimizer for systematic HTF-aware optimization.

Features:
- Auto-buckets charts by inferred timeframe (4H, 1H, 1D, etc.)
- Applies timeframe-specific HTF candidate lists
- Runs Sobol/LHS sampling with Calmar optimization
- Saves outputs (JSON + summary) for each bucket
"""
import os
import sys
import time
import json
import argparse
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

# Add project root to path for imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.user_inputs import BACKTEST_CONFIG as USER_BACKTEST_CONFIG, TOGGLES
from src.io.data_loader import list_active_chart_paths, load_chart_from_path
from src.io.json_io import write_run_json
from src.optimizer.search import normalize_param_ranges, sample_param_sets, evaluate_collect
from src.io.fast_io import vectorized_trial_uid_creation

# Suppress warnings
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=pd.errors.PerformanceWarning)


# HTF candidates per base timeframe (ratio ~4-10x base)
HTF_CANDIDATES = {
    '1m': ['5m', '15m', '30m', '1H'],
    '5m': ['15m', '30m', '1H', '2H'],
    '15m': ['1H', '2H', '4H', '8H'],
    '1H': ['4H', '8H', '12H', '1D'],
    '1h': ['4H', '8H', '12H', '1D'],
    '2H': ['8H', '12H', '1D', '2D'],
    '2h': ['8H', '12H', '1D', '2D'],
    '4H': ['8H', '12H', '1D', '2D', '1W'],
    '4h': ['8H', '12H', '1D', '2D', '1W'],
    '1D': ['2D', '3D', '1W', '2W'],
    '1d': ['2D', '3D', '1W', '2W'],
}


def infer_timeframe_from_filename(path: str) -> str | None:
    """Extract timeframe from chart filename like XAUUSD_4h_cl_1.csv"""
    name = os.path.basename(path).lower()
    for tf in ['15m', '1m', '5m', '30m', '1h', '2h', '4h', '8h', '12h', '1d']:
        if f'_{tf}_' in name or name.startswith(f'{tf}_'):
            return tf
    return None


def bucket_charts_by_tf(chart_paths: list[str]) -> dict[str, list[str]]:
    """Group charts by their inferred base timeframe."""
    buckets = {}
    for path in chart_paths:
        tf = infer_timeframe_from_filename(path)
        if tf:
            buckets.setdefault(tf, []).append(path)
        else:
            buckets.setdefault('unknown', []).append(path)
    return buckets


def get_param_ranges_for_tf(base_tf: str) -> dict:
    """Return param ranges with appropriate HTF candidates for the base timeframe."""
    from config.strategy_params_v1 import PARAM_RANGES
    
    ranges = PARAM_RANGES.copy()
    
    # Override htf_tf with timeframe-appropriate candidates
    htf_list = HTF_CANDIDATES.get(base_tf.lower(), ['1D', '1W'])
    ranges['htf_tf'] = htf_list
    
    # Ensure shorts and HTF filter are enabled for optimization
    ranges['enable_shorts'] = [True]  # Force shorts on for bidirectional testing
    ranges['use_htf_filter'] = [True]  # Force HTF filter on
    
    return ranges


def run_bucket_optimization(
    bucket_name: str,
    chart_paths: list[str],
    param_ranges: dict,
    method: str = 'sobol',
    trials_per_chart: int = 100,
    seed: int = 42,
    output_dir: str = None,
) -> pd.DataFrame:
    """Run optimization on a bucket of charts."""
    
    print(f"\n{'='*60}")
    print(f"OPTIMIZING BUCKET: {bucket_name.upper()}")
    print(f"Charts: {len(chart_paths)}")
    print(f"Method: {method}, Trials/chart: {trials_per_chart}")
    print(f"{'='*60}")
    
    # Import strategy
    from src.strategy.bands_v1 import compute_signals
    
    # Normalize ranges
    normalized_ranges = normalize_param_ranges(param_ranges)
    
    all_rows = []
    trial_counter = 0
    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    for chart_idx, chart_path in enumerate(chart_paths):
        chart_name = os.path.basename(chart_path)
        print(f"\n[{chart_idx+1}/{len(chart_paths)}] Processing: {chart_name}")
        
        try:
            price = load_chart_from_path(chart_path)
            print(f"  Loaded {len(price)} bars")
        except Exception as e:
            print(f"  ERROR loading chart: {e}")
            continue
        
        # Sample parameters
        param_sets = sample_param_sets(normalized_ranges, method=method, n=trials_per_chart, seed=seed + chart_idx)
        
        for param_idx, trial_params in enumerate(param_sets):
            try:
                row, trades_df = evaluate_collect(price, trial_params, TOGGLES, compute_signals)
                trial_counter += 1
                
                # Flatten params into row
                row_params = row.get('params', {})
                flat_params = {f"param_{k}": v for k, v in row_params.items()}
                
                row.update({
                    'bucket': bucket_name,
                    'chart': chart_name,
                    'trial_id': trial_counter,
                    'method': method,
                })
                row.pop('params', None)
                row.update(flat_params)
                all_rows.append(row)
                
            except Exception as e:
                print(f"  Trial {param_idx} error: {e}")
                continue
        
        # Progress
        print(f"  Completed {len(param_sets)} trials")
    
    # Build results DataFrame
    results_df = pd.DataFrame(all_rows)
    
    if len(results_df) == 0:
        print("No results collected!")
        return results_df
    
    # Add trial UIDs
    results_df['trial_uid'] = vectorized_trial_uid_creation(results_df['trial_id'], run_id)
    
    # Sort by Calmar (primary metric)
    if 'calmar_ratio' in results_df.columns:
        results_df = results_df.sort_values('calmar_ratio', ascending=False)
    
    # Save outputs
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        
        # JSON output
        json_filename = f'{bucket_name}_{run_id}.json'
        metadata = {
            'run_id': run_id,
            'bucket': bucket_name,
            'method': method,
            'trials_per_chart': trials_per_chart,
            'num_charts': len(chart_paths),
            'total_trials': len(results_df),
            'timestamp': datetime.now().isoformat(),
        }
        payload = {
            'metadata': metadata,
            'results': results_df.to_dict(orient='records'),
        }
        json_path = write_run_json(output_dir, json_filename, payload)
        print(f"\nSaved: {json_path}")
        
        # CSV summary
        csv_path = os.path.join(output_dir, f'{bucket_name}_{run_id}_summary.csv')
        results_df.head(50).to_csv(csv_path, index=False)
        print(f"Saved: {csv_path}")
    
    return results_df


def print_top_results(df: pd.DataFrame, n: int = 10):
    """Print top N results summary."""
    if len(df) == 0:
        return
    
    print(f"\n{'='*60}")
    print(f"TOP {n} RESULTS (by Calmar)")
    print(f"{'='*60}")
    
    cols = ['trial_id', 'chart', 'calmar_ratio', 'sharpe_ratio', 'max_drawdown', 
            'total_return', 'total_trades', 'param_htf_tf', 'param_cooldown_bars']
    available_cols = [c for c in cols if c in df.columns]
    
    print(df[available_cols].head(n).to_string(index=False))


def main():
    parser = argparse.ArgumentParser(description='Batch optimizer for HTF-aware bidirectional strategy')
    parser.add_argument('--method', choices=['random', 'lhs', 'sobol', 'grid'], default='sobol')
    parser.add_argument('--trials', type=int, default=100, help='Trials per chart')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--buckets', nargs='+', default=None, help='Only run specific buckets (e.g., 4h 1h)')
    parser.add_argument('--output', default='outputs/batch_runs', help='Output directory')
    args = parser.parse_args()
    
    print("=" * 60)
    print("BATCH OPTIMIZER - HTF-Aware Bidirectional Strategy")
    print("=" * 60)
    
    # Get all charts
    chart_paths = list_active_chart_paths()
    if not chart_paths:
        print("ERROR: No charts found in active_charts!")
        return
    
    print(f"Found {len(chart_paths)} charts")
    
    # Bucket by timeframe
    buckets = bucket_charts_by_tf(chart_paths)
    print(f"\nBuckets: {list(buckets.keys())}")
    for tf, paths in buckets.items():
        print(f"  {tf}: {len(paths)} charts")
    
    # Filter buckets if specified
    if args.buckets:
        buckets = {k: v for k, v in buckets.items() if k.lower() in [b.lower() for b in args.buckets]}
    
    if not buckets:
        print("ERROR: No matching buckets found!")
        return
    
    # Run optimization for each bucket
    all_results = {}
    
    for bucket_name, bucket_paths in buckets.items():
        if bucket_name == 'unknown':
            print(f"\nSkipping 'unknown' bucket with {len(bucket_paths)} charts")
            continue
        
        # Get timeframe-specific param ranges
        param_ranges = get_param_ranges_for_tf(bucket_name)
        print(f"\nHTF candidates for {bucket_name}: {param_ranges.get('htf_tf', [])}")
        
        # Run optimization
        results = run_bucket_optimization(
            bucket_name=bucket_name,
            chart_paths=bucket_paths,
            param_ranges=param_ranges,
            method=args.method,
            trials_per_chart=args.trials,
            seed=args.seed,
            output_dir=args.output,
        )
        
        all_results[bucket_name] = results
        print_top_results(results, n=10)
    
    print("\n" + "=" * 60)
    print("BATCH OPTIMIZATION COMPLETE")
    print("=" * 60)
    
    # Summary
    for bucket_name, df in all_results.items():
        if len(df) > 0:
            best = df.iloc[0]
            print(f"\n{bucket_name.upper()} Best:")
            print(f"  Calmar: {best.get('calmar_ratio', 0):.4f}")
            print(f"  Sharpe: {best.get('sharpe_ratio', 0):.4f}")
            print(f"  HTF: {best.get('param_htf_tf', 'N/A')}")
            print(f"  Cooldown: {best.get('param_cooldown_bars', 'N/A')}")


if __name__ == '__main__':
    main()

