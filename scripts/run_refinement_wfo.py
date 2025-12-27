"""
Refinement and WFO validation script.

1. Analyzes coarse optimization results to narrow parameter ranges
2. Runs refinement optimization with narrowed ranges
3. Runs WFO validation on best candidates
"""
import os
import sys
import json
import argparse
import pandas as pd
import numpy as np
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.user_inputs import TOGGLES
from config.strategy_params_v1 import PARAM_RANGES
from src.io.data_loader import load_chart_from_path
from src.optimizer.search import normalize_param_ranges, sample_param_sets, evaluate_collect
from src.optimizer.wfo import anchored_walk_forward, check_parameter_fragility
from src.strategy.bands_v1 import compute_signals
from src.io.json_io import write_run_json
from src.io.fast_io import vectorized_trial_uid_creation


def analyze_top_results(df: pd.DataFrame, top_n: int = 10) -> dict:
    """Analyze top N results to create narrowed parameter ranges."""
    # Sort by Calmar
    top = df.nlargest(top_n, 'calmar_ratio').copy()
    
    narrowed = {}
    
    # For numeric params, create ranges around top performers
    numeric_params = [
        'fast_min_len', 'fast_max_len', 'slow_min_len', 'slow_max_len',
        'dma_atr_len', 'atr_len',
        'upper_outer_mult', 'lower_outer_mult', 'upper_inner_mult', 'lower_inner_mult',
        'momentum_len', 'momentum_threshold', 'momentum_lookback',
        'rsi_len', 'rsi_oversold', 'rsi_overbought',
        'trailing_atr_mult', 'catastrophic_stop_atr_mult',
        'dma_exit_bars', 'dma_exit_buffer_atr', 'roc_len', 'cooldown_bars'
    ]
    
    for param in numeric_params:
        col = f'param_{param}'
        if col in top.columns:
            values = top[col].dropna()
            if len(values) > 0:
                # Create range: mean ± 1.5 * std, but within original bounds
                mean_val = values.mean()
                std_val = values.std()
                min_val = max(values.min(), mean_val - 1.5 * std_val)
                max_val = min(values.max(), mean_val + 1.5 * std_val)
                
                # Ensure reasonable step sizes
                if param in ['fast_min_len', 'fast_max_len', 'slow_min_len', 'slow_max_len',
                            'dma_atr_len', 'atr_len', 'momentum_len', 'momentum_lookback',
                            'rsi_len', 'rsi_oversold', 'rsi_overbought', 'roc_len', 'dma_exit_bars', 'cooldown_bars']:
                    # Integer params
                    min_val = int(max(1, np.floor(min_val)))
                    max_val = int(np.ceil(max_val))
                    narrowed[param] = list(range(min_val, max_val + 1))
                else:
                    # Float params - create list with reasonable step
                    if 'mult' in param or 'threshold' in param or 'buffer' in param:
                        step = 0.1 if 'mult' in param else 0.05
                    else:
                        step = 0.01
                    narrowed[param] = list(np.arange(min_val, max_val + step, step))
    
    # For categorical params, keep only values seen in top performers
    categorical_params = ['htf_tf', 'ranging_confirm_bar', 'enable_shorts', 
                         'use_dma_fail_exit', 'use_directional_momentum', 'use_htf_filter']
    
    for param in categorical_params:
        col = f'param_{param}'
        if col in top.columns:
            values = top[col].dropna().unique().tolist()
            if len(values) > 0:
                narrowed[param] = values
    
    # Ensure critical params are set
    narrowed.setdefault('enable_shorts', [True])
    narrowed.setdefault('use_htf_filter', [True])
    
    return narrowed


def run_refinement(
    chart_paths: list[str],
    narrowed_ranges: dict,
    method: str = 'sobol',
    trials_per_chart: int = 200,
    seed: int = 42,
    output_dir: str = None,
) -> pd.DataFrame:
    """Run refinement optimization with narrowed ranges."""
    print(f"\n{'='*60}")
    print(f"REFINEMENT OPTIMIZATION")
    print(f"Charts: {len(chart_paths)}")
    print(f"Method: {method}, Trials/chart: {trials_per_chart}")
    print(f"{'='*60}")
    
    normalized_ranges = normalize_param_ranges(narrowed_ranges)
    
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
                
                # Flatten params
                row_params = row.get('params', {})
                flat_params = {f"param_{k}": v for k, v in row_params.items()}
                
                row.update({
                    'trial_id': trial_counter,
                    'chart': chart_name,
                    'method': method,
                    'refinement': True,
                })
                row.pop('params', None)
                row.update(flat_params)
                all_rows.append(row)
                
            except Exception as e:
                print(f"  Trial {param_idx} error: {e}")
                continue
        
        print(f"  Completed {len(param_sets)} trials")
    
    results_df = pd.DataFrame(all_rows)
    
    if len(results_df) == 0:
        print("No results collected!")
        return results_df
    
    # Add trial UIDs
    results_df['trial_uid'] = vectorized_trial_uid_creation(results_df['trial_id'], run_id)
    
    # Sort by Calmar
    if 'calmar_ratio' in results_df.columns:
        results_df = results_df.sort_values('calmar_ratio', ascending=False)
    
    # Save outputs
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        
        json_filename = f'refinement_{run_id}.json'
        metadata = {
            'run_id': run_id,
            'method': method,
            'trials_per_chart': trials_per_chart,
            'num_charts': len(chart_paths),
            'total_trials': len(results_df),
            'timestamp': datetime.now().isoformat(),
            'refinement': True,
        }
        payload = {
            'metadata': metadata,
            'results': results_df.to_dict(orient='records'),
        }
        json_path = write_run_json(output_dir, json_filename, payload)
        print(f"\nSaved: {json_path}")
        
        csv_path = os.path.join(output_dir, f'refinement_{run_id}_summary.csv')
        results_df.head(50).to_csv(csv_path, index=False)
        print(f"Saved: {csv_path}")
    
    return results_df


def run_wfo_validation(
    chart_paths: list[str],
    best_params: dict,
    train_months: int = 24,
    valid_months: int = 3,
    n_trials_per_window: int = 100,
    output_dir: str = None,
) -> dict:
    """Run WFO validation on best parameters."""
    print(f"\n{'='*60}")
    print(f"WALK-FORWARD OPTIMIZATION VALIDATION")
    print(f"Charts: {len(chart_paths)}")
    print(f"Train: {train_months} months, Valid: {valid_months} months")
    print(f"Trials per window: {n_trials_per_window}")
    print(f"{'='*60}")
    
    all_wfo_results = {}
    
    for chart_idx, chart_path in enumerate(chart_paths):
        chart_name = os.path.basename(chart_path)
        print(f"\n[{chart_idx+1}/{len(chart_paths)}] WFO on: {chart_name}")
        
        try:
            price = load_chart_from_path(chart_path)
            print(f"  Loaded {len(price)} bars")
        except Exception as e:
            print(f"  ERROR loading chart: {e}")
            continue
        
        # Create param ranges around best params for WFO optimization
        wfo_ranges = {}
        for k, v in best_params.items():
            if isinstance(v, (int, float)):
                # Create small range around best value
                if isinstance(v, int):
                    wfo_ranges[k] = list(range(max(1, v - 2), v + 3))
                else:
                    step = 0.1 if 'mult' in k else 0.05
                    wfo_ranges[k] = list(np.arange(max(0.01, v - step * 2), v + step * 3, step))
            else:
                wfo_ranges[k] = [v]  # Keep categorical as-is
        
        # Run WFO
        try:
            wfo_result = anchored_walk_forward(
                price=price,
                param_ranges=wfo_ranges,
                toggles=TOGGLES,
                train_months=train_months,
                valid_months=valid_months,
                n_trials_per_window=n_trials_per_window,
                metric='calmar_ratio',
                seed=42 + chart_idx
            )
            
            all_wfo_results[chart_name] = wfo_result
            
            # Print summary
            if 'aggregate_stats' in wfo_result and wfo_result['aggregate_stats']:
                stats = wfo_result['aggregate_stats']
                print(f"\n  WFO Summary:")
                if 'calmar_ratio' in stats:
                    print(f"    Calmar - Median: {stats['calmar_ratio']['median']:.6f}, Mean: {stats['calmar_ratio']['mean']:.6f}")
                if 'sharpe_ratio' in stats:
                    print(f"    Sharpe - Median: {stats['sharpe_ratio']['median']:.6f}, Mean: {stats['sharpe_ratio']['mean']:.6f}")
                print(f"    Windows: {len(wfo_result.get('windows', []))}")
            
        except Exception as e:
            print(f"  ERROR in WFO: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Save WFO results
    if output_dir and all_wfo_results:
        os.makedirs(output_dir, exist_ok=True)
        wfo_path = os.path.join(output_dir, f'wfo_validation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        with open(wfo_path, 'w', encoding='utf-8') as f:
            json.dump(all_wfo_results, f, indent=2, default=str)
        print(f"\nSaved WFO results: {wfo_path}")
    
    return all_wfo_results


def main():
    parser = argparse.ArgumentParser(description='Refinement and WFO validation')
    parser.add_argument('--coarse-results', required=True, help='Path to coarse optimization JSON')
    parser.add_argument('--top-n', type=int, default=10, help='Top N results to analyze for refinement')
    parser.add_argument('--refinement-trials', type=int, default=200, help='Trials per chart for refinement')
    parser.add_argument('--wfo-train-months', type=int, default=24, help='WFO training window (months)')
    parser.add_argument('--wfo-valid-months', type=int, default=3, help='WFO validation window (months)')
    parser.add_argument('--wfo-trials', type=int, default=100, help='Trials per WFO window')
    parser.add_argument('--output', default='outputs/batch_runs', help='Output directory')
    args = parser.parse_args()
    
    print("=" * 60)
    print("REFINEMENT & WFO VALIDATION")
    print("=" * 60)
    
    # Load coarse results
    print(f"\nLoading coarse results: {args.coarse_results}")
    with open(args.coarse_results, 'r') as f:
        coarse_data = json.load(f)
    
    results = coarse_data.get('results', [])
    if not results:
        print("ERROR: No results found in coarse optimization!")
        return
    
    df = pd.DataFrame(results)
    print(f"Loaded {len(df)} trials")
    
    # Analyze top results
    print(f"\nAnalyzing top {args.top_n} results for refinement ranges...")
    narrowed_ranges = analyze_top_results(df, top_n=args.top_n)
    print(f"Narrowed {len(narrowed_ranges)} parameters")
    
    # Get chart paths from results
    charts = df['chart'].unique().tolist()
    chart_paths = []
    for chart_name in charts:
        # Find chart in active_charts
        from src.io.data_loader import list_active_chart_paths
        all_charts = list_active_chart_paths()
        for path in all_charts:
            if os.path.basename(path) == chart_name:
                chart_paths.append(path)
                break
    
    if not chart_paths:
        print("ERROR: Could not find chart files!")
        return
    
    print(f"\nFound {len(chart_paths)} charts for refinement")
    
    # Run refinement
    refinement_results = run_refinement(
        chart_paths=chart_paths,
        narrowed_ranges=narrowed_ranges,
        method='sobol',
        trials_per_chart=args.refinement_trials,
        seed=42,
        output_dir=args.output,
    )
    
    if len(refinement_results) == 0:
        print("ERROR: No refinement results!")
        return
    
    # Get best params from refinement
    best_row = refinement_results.iloc[0]
    best_params = {k[6:]: v for k, v in best_row.items() if k.startswith('param_')}
    
    print(f"\nBest refinement result:")
    print(f"  Calmar: {best_row.get('calmar_ratio', 0):.6f}")
    print(f"  Sharpe: {best_row.get('sharpe_ratio', 0):.6f}")
    print(f"  Chart: {best_row.get('chart', 'N/A')}")
    
    # Run WFO validation
    wfo_results = run_wfo_validation(
        chart_paths=chart_paths,
        best_params=best_params,
        train_months=args.wfo_train_months,
        valid_months=args.wfo_valid_months,
        n_trials_per_window=args.wfo_trials,
        output_dir=args.output,
    )
    
    print("\n" + "=" * 60)
    print("REFINEMENT & WFO COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    main()

