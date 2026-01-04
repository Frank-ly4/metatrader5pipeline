import os
import json
import pandas as pd
import numpy as np
import argparse
from typing import Dict, List, Optional

def find_runs() -> List[Dict]:
    """Find and parse metadata from all JSON run files."""
    runs_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'runs')
    if not os.path.exists(runs_dir):
        return []
    
    runs = []
    for filename in sorted(os.listdir(runs_dir), reverse=True):
        if filename.lower().endswith('.json'):
            try:
                filepath = os.path.join(runs_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    # Only load metadata to be fast
                    data = json.load(f)
                    metadata = data.get('metadata', {})
                
                runs.append({
                    'filename': filename,
                    'filepath': filepath,
                    'run_id': metadata.get('run_id', 'N/A'),
                    'method': metadata.get('method', 'N/A'),
                    'timestamp': metadata.get('timestamp', 'N/A'),
                    'num_results': len(data.get('results', [])),
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return runs

def select_run(runs: List[Dict]) -> Optional[Dict]:
    """Display a list of runs and prompt the user to select one."""
    if not runs:
        print("❌ No optimization runs found in outputs/runs/")
        return None
    
    print("📁 AVAILABLE OPTIMIZATION RUNS (most recent first)")
    print("=" * 80)
    for i, run in enumerate(runs[:15], 1): # Show 15 most recent
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

def flatten_regime_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract regime_stats nested dict into flat columns.
    Handles missing keys gracefully (fills NaN).
    
    Creates columns like:
    - trend_weak_trades, trend_weak_avg_return
    - trend_moderate_trades, trend_moderate_avg_return
    - trend_strong_trades, trend_strong_avg_return
    - trend_extreme_trades, trend_extreme_avg_return
    - vol_low_trades, vol_low_avg_return
    - vol_medlow_trades, vol_medlow_avg_return
    - vol_medhigh_trades, vol_medhigh_avg_return
    - vol_high_trades, vol_high_avg_return
    """
    df = df.copy()
    
    def safe_extract(row, *keys):
        val = row.get('regime_stats')
        if not isinstance(val, dict):
            return None
        for k in keys:
            val = val.get(k) if isinstance(val, dict) else None
            if val is None:
                return None
        return val
    
    # Trend buckets (ADX-based: Weak, Moderate, Strong, Extreme)
    for bucket in ['Weak', 'Moderate', 'Strong', 'Extreme']:
        bucket_lower = bucket.lower()
        df[f'trend_{bucket_lower}_trades'] = df.apply(
            lambda r: safe_extract(r, 'trend_buckets', bucket, 'trades'), axis=1
        )
        df[f'trend_{bucket_lower}_avg_return'] = df.apply(
            lambda r: safe_extract(r, 'trend_buckets', bucket, 'avg_return'), axis=1
        )
    
    # Volatility buckets (ATR-based: Low, MedLow, MedHigh, High)
    for bucket in ['Low', 'MedLow', 'MedHigh', 'High']:
        bucket_lower = bucket.lower()
        df[f'vol_{bucket_lower}_trades'] = df.apply(
            lambda r: safe_extract(r, 'volatility_buckets', bucket, 'trades'), axis=1
        )
        df[f'vol_{bucket_lower}_avg_return'] = df.apply(
            lambda r: safe_extract(r, 'volatility_buckets', bucket, 'avg_return'), axis=1
        )
    
    return df

def regime_score(trades: float, avg_return: float) -> float:
    """Score = avg_return * sqrt(trades) for statistical significance."""
    if pd.isna(trades) or pd.isna(avg_return) or trades < 1:
        return -np.inf
    return avg_return * (trades ** 0.5)

def list_available_regimes(df: pd.DataFrame):
    """Print what regime dimensions exist in this run."""
    df_with_regime = df[df['regime_stats'].notna()]
    if len(df_with_regime) == 0:
        print("No regime_stats found in this run.")
        return
    
    sample_row = df_with_regime.iloc[0]
    rs = sample_row['regime_stats']
    
    print("\n📊 Available regime dimensions:")
    for key in sorted(rs.keys()):
        buckets = list(rs[key].keys()) if isinstance(rs[key], dict) else []
        print(f"  {key}: {buckets}")
    
    # Show example counts
    print("\n📈 Example regime stats (first trial with regime_stats):")
    for key in sorted(rs.keys()):
        if isinstance(rs[key], dict):
            print(f"  {key}:")
            for bucket, stats in rs[key].items():
                trades = stats.get('trades', 0)
                avg_ret = stats.get('avg_return', 0)
                print(f"    {bucket}: {trades} trades, avg_return={avg_ret:.4f}")

def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Interactively apply filters to the results DataFrame."""
    filtered_df = df.copy()
    
    while True:
        print("\n🔎 APPLY FILTERS (e.g., 'sharpe_ratio > 1.5', 'total_trades >= 10')")
        print("   Enter a filter expression, or type 'done' to finish, 'reset' to clear filters.")
        
        filter_str = input("Filter: ").strip()
        
        if filter_str.lower() == 'done':
            break
        if filter_str.lower() == 'reset':
            filtered_df = df.copy()
            print("Filters reset.")
            continue
        
        try:
            # Use pandas.eval for safe evaluation of the query
            filtered_df = filtered_df.eval(filter_str, engine='python')
            print(f"✅ Filter applied. {len(filtered_df)} rows remaining.")
        except Exception as e:
            print(f"❌ Invalid filter expression: {e}")
            print("   Example: 'sharpe_ratio > 1.5 and total_trades > 20'")
            print(f"   Available columns: {list(df.columns)}")
            
    return filtered_df

def filter_by_regime(df: pd.DataFrame, regime_str: str, min_regime_trades: int = 20, dd_max: float = 0.045) -> pd.DataFrame:
    """
    Filter and rank trials by regime-specific performance.
    
    Args:
        df: DataFrame with flattened regime_stats columns
        regime_str: Format "trend:strong" or "vol:high" (case-insensitive)
        min_regime_trades: Minimum trades in the specified regime
        dd_max: Maximum drawdown threshold (hard filter)
    
    Returns:
        Filtered and scored DataFrame
    """
    df = df.copy()
    
    # Hard filter: max_drawdown constraint
    if 'max_drawdown' in df.columns:
        df = df[df['max_drawdown'] <= dd_max].copy()
    
    # Parse regime string
    parts = regime_str.lower().split(':')
    if len(parts) != 2:
        raise ValueError(f"Invalid regime format: '{regime_str}'. Expected 'trend:strong' or 'vol:high'")
    
    dim, bucket = parts[0].strip(), parts[1].strip()
    
    # Map user-friendly names to column names
    bucket_map = {
        'weak': 'weak', 'moderate': 'moderate', 'strong': 'strong', 'extreme': 'extreme',
        'low': 'low', 'medlow': 'medlow', 'medlow': 'medlow', 'medhigh': 'medhigh', 'high': 'high'
    }
    bucket_normalized = bucket_map.get(bucket, bucket)
    
    if dim == 'trend':
        trades_col = f'trend_{bucket_normalized}_trades'
        avg_return_col = f'trend_{bucket_normalized}_avg_return'
    elif dim == 'vol':
        trades_col = f'vol_{bucket_normalized}_trades'
        avg_return_col = f'vol_{bucket_normalized}_avg_return'
    else:
        raise ValueError(f"Unknown regime dimension: '{dim}'. Use 'trend' or 'vol'")
    
    # Check if columns exist
    if trades_col not in df.columns or avg_return_col not in df.columns:
        raise ValueError(f"Regime columns not found. Did you flatten regime_stats? Missing: {trades_col}, {avg_return_col}")
    
    # Hard filter: minimum regime trades
    df = df[df[trades_col] >= min_regime_trades].copy()
    
    # Compute regime_score
    df['regime_score'] = df.apply(
        lambda row: regime_score(row[trades_col], row[avg_return_col]), axis=1
    )
    
    # Remove infinite scores
    df = df[df['regime_score'] != -np.inf].copy()
    
    return df

def display_regime_results(df: pd.DataFrame, regime_str: str, top_n: int, metric: str = 'regime_score'):
    """Display top N trials for a regime with compact formatting."""
    if df.empty:
        print(f"No trials match regime '{regime_str}' with the specified filters.")
        return
    
    # Sort by metric
    if metric not in df.columns:
        metric = 'regime_score'
    
    sorted_df = df.sort_values(by=metric, ascending=False).head(top_n)
    
    # Extract regime dimension and bucket for column selection
    parts = regime_str.lower().split(':')
    dim, bucket = parts[0].strip(), parts[1].strip()
    bucket_map = {
        'weak': 'weak', 'moderate': 'moderate', 'strong': 'strong', 'extreme': 'extreme',
        'low': 'low', 'medlow': 'medlow', 'medhigh': 'medhigh', 'high': 'high'
    }
    bucket_normalized = bucket_map.get(bucket, bucket)
    
    if dim == 'trend':
        trades_col = f'trend_{bucket_normalized}_trades'
        avg_return_col = f'trend_{bucket_normalized}_avg_return'
    else:
        trades_col = f'vol_{bucket_normalized}_trades'
        avg_return_col = f'vol_{bucket_normalized}_avg_return'
    
    print(f"\n🏆 TOP {len(sorted_df)} TRIALS (Regime: {regime_str}, sorted by {metric})")
    print("=" * 120)
    
    # Select display columns
    display_cols = ['trial_uid', 'chart', 'total_return', 'sharpe_ratio', 'max_drawdown', 
                    trades_col, avg_return_col, 'regime_score']
    available_cols = [col for col in display_cols if col in sorted_df.columns]
    
    # Add param preview (first few params)
    param_cols = [col for col in sorted_df.columns if col.startswith('param_')]
    if param_cols:
        # Show a few key params
        key_params = ['param_base_fast_len', 'param_base_slow_len', 'param_upper_outer_mult', 'param_lower_outer_mult']
        for kp in key_params:
            if kp in sorted_df.columns and kp not in available_cols:
                available_cols.append(kp)
    
    formatted_df = sorted_df[available_cols].copy()
    
    # Format numeric columns
    for col in ['total_return', 'max_drawdown']:
        if col in formatted_df.columns:
            formatted_df[col] = formatted_df[col].map(lambda x: f'{x*100:.2f}%' if not pd.isna(x) else 'N/A')
    
    for col in ['sharpe_ratio']:
        if col in formatted_df.columns:
            formatted_df[col] = formatted_df[col].map(lambda x: f'{x:.3f}' if not pd.isna(x) else 'N/A')
    
    if trades_col in formatted_df.columns:
        formatted_df[trades_col] = formatted_df[trades_col].map(lambda x: f'{int(x)}' if not pd.isna(x) else 'N/A')
    
    if avg_return_col in formatted_df.columns:
        formatted_df[avg_return_col] = formatted_df[avg_return_col].map(lambda x: f'{x:.4f}' if not pd.isna(x) else 'N/A')
    
    if 'regime_score' in formatted_df.columns:
        formatted_df['regime_score'] = formatted_df['regime_score'].map(lambda x: f'{x:.3f}' if not pd.isna(x) else 'N/A')
    
    print(formatted_df.to_string(index=False))
    print("=" * 120)

def main():
    """Main query tool with CLI and interactive modes."""
    parser = argparse.ArgumentParser(
        description='Query and analyze optimization run results with regime-aware filtering',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--run', type=str, help='Path to run JSON file (or use interactive mode)')
    parser.add_argument('--list-regimes', action='store_true', help='List available regime dimensions and buckets')
    parser.add_argument('--regime', type=str, help='Filter by regime (e.g., "trend:strong" or "vol:high")')
    parser.add_argument('--top-n', type=int, default=10, help='Number of top results to display (default: 10)')
    parser.add_argument('--min-regime-trades', type=int, default=20, help='Minimum trades in regime (default: 20)')
    parser.add_argument('--dd-max', type=float, default=0.045, help='Maximum drawdown threshold (default: 0.045)')
    parser.add_argument('--metric', type=str, default='regime_score', help='Sorting metric (default: regime_score)')
    
    args = parser.parse_args()
    
    # CLI mode
    if args.run or args.list_regimes or args.regime:
        if not args.run:
            # Find latest run
            runs = find_runs()
            if not runs:
                print("❌ No optimization runs found in outputs/runs/")
                return
            selected_run = runs[0]
            print(f"Using latest run: {selected_run['filename']}")
        else:
            selected_run = {'filepath': args.run, 'filename': os.path.basename(args.run)}
        
        print(f"\nLoading run: {selected_run['filename']}...")
        with open(selected_run['filepath'], 'r', encoding='utf-8') as f:
            full_data = json.load(f)
        
        results_df = pd.DataFrame(full_data.get('results', []))
        if results_df.empty:
            print("This run contains no results.")
            return
        
        # Flatten regime_stats
        results_df = flatten_regime_stats(results_df)
        
        # List regimes if requested
        if args.list_regimes:
            list_available_regimes(results_df)
            return
        
        # Filter by regime if requested
        if args.regime:
            try:
                filtered_df = filter_by_regime(
                    results_df, 
                    args.regime, 
                    args.min_regime_trades, 
                    args.dd_max
                )
                display_regime_results(filtered_df, args.regime, args.top_n, args.metric)
            except Exception as e:
                print(f"❌ Error filtering by regime: {e}")
                return
        else:
            # Default: show top N by sharpe_ratio with DD filter
            filtered_df = results_df[results_df['max_drawdown'] <= args.dd_max].copy() if 'max_drawdown' in results_df.columns else results_df.copy()
            sorted_df = filtered_df.sort_values(by='sharpe_ratio', ascending=False).head(args.top_n)
            
            display_cols = ['trial_uid', 'chart', 'total_return', 'sharpe_ratio', 'max_drawdown', 'total_trades']
            available_cols = [col for col in display_cols if col in sorted_df.columns]
            formatted_df = sorted_df[available_cols].copy()
            
            for col in ['total_return', 'max_drawdown']:
                if col in formatted_df.columns:
                    formatted_df[col] = formatted_df[col].map(lambda x: f'{x*100:.2f}%' if not pd.isna(x) else 'N/A')
            
            print(f"\n🏆 TOP {len(formatted_df)} RESULTS (DD < {args.dd_max*100:.1f}%)")
            print(formatted_df.to_string(index=False))
        
        return
    
    # Interactive mode (original behavior)
    while True:
        runs = find_runs()
        selected_run = select_run(runs)
        
        if not selected_run:
            break
            
        print(f"\nLoading run: {selected_run['filename']}...")
        with open(selected_run['filepath'], 'r', encoding='utf-8') as f:
            full_data = json.load(f)
        
        results_df = pd.DataFrame(full_data.get('results', []))
        if results_df.empty:
            print("This run contains no results.")
            continue
        
        # Flatten regime_stats for interactive mode too
        results_df = flatten_regime_stats(results_df)
        
        # Check if regime_stats exist
        if results_df['regime_stats'].notna().any():
            print("\n💡 Tip: Use --list-regimes and --regime flags for regime-aware analysis")
        
        # Apply filters
        filtered_df = apply_filters(results_df)
        
        if filtered_df.empty:
            print("No results match the current filters.")
            continue
            
        # Get sorting and display preferences
        print("\n📊 SORT & DISPLAY")
        sort_metric = input(f"Sort by which metric? [sharpe_ratio]: ").strip() or 'sharpe_ratio'
        if sort_metric not in filtered_df.columns:
            print(f"Metric '{sort_metric}' not found. Defaulting to 'sharpe_ratio'.")
            sort_metric = 'sharpe_ratio'
            
        top_n_str = input("How many top results to display? [10]: ").strip() or '10'
        top_n = int(top_n_str)
        
        # Sort and display results
        sorted_df = filtered_df.sort_values(by=sort_metric, ascending=False).head(top_n)
        
        print(f"\n🏆 TOP {len(sorted_df)} RESULTS (sorted by {sort_metric})")
        
        display_cols = ['trial_uid', 'chart', 'total_return', 'sharpe_ratio', 'sortino_ratio', 'calmar_ratio', 'max_drawdown', 'total_trades', 'win_rate']
        available_cols = [col for col in display_cols if col in sorted_df.columns]
        
        # Pretty print with formatting
        formatted_df = sorted_df[available_cols].copy()
        for col in ['total_return', 'max_drawdown', 'win_rate']:
            if col in formatted_df.columns:
                formatted_df[col] = formatted_df[col].map('{:.2f}%'.format)
        for col in ['sharpe_ratio', 'sortino_ratio', 'calmar_ratio']:
            if col in formatted_df.columns:
                formatted_df[col] = formatted_df[col].map('{:.3f}'.format)
        
        print(formatted_df.to_string())

        another_run = input("\nAnalyze another run? (y/n) [y]: ").strip().lower()
        if another_run == 'n':
            break

if __name__ == '__main__':
    main()


