"""
Interactive optimizer with full chart selection and parameter control.

Features:
- Choose specific charts or all charts from active_charts
- Select optimization method (random/grid/lhs/sobol)
- Configure trials, k-folds, embargo size
- Performance optimizations for antivirus environments
- All CPU bottleneck fixes included
"""
import argparse
import os
import time
import json
import numbers
import pandas as pd
import numpy as np
from config.user_inputs import BACKTEST_CONFIG as USER_BACKTEST_CONFIG, TOGGLES
from src.io.data_loader import list_active_chart_paths, load_chart_from_path
from src.io.json_io import write_run_json
from src.meta.logger import append_discovery, append_issue
from src.io.fast_io import (
    batch_datetime_conversion,
    single_concat_operation,
    vectorized_trial_uid_creation,
)
from src.io.chart_meta import parse_chart_name


def get_strategy_selection():
    """Get user's strategy selection."""
    print("\n📈 STRATEGY SELECTION")
    print("=" * 50)
    print("  1. v1 (Baseline DMA Bands)")
    print("  2. v2 (Dynamic DMA Bands - Experimental)")
    print("=" * 50)
    while True:
        try:
            choice = input("Select strategy (1 or 2) [1]: ").strip()
            if not choice or choice == '1':
                return 'v1'
            if choice == '2':
                return 'v2'
            print("❌ Invalid choice. Please select 1 or 2.")
        except Exception as e:
            print(f"❌ Error: {e}")
            return 'v1'


def show_available_charts():
    """Display available charts with numbered selection."""
    chart_paths = list_active_chart_paths()
    if not chart_paths:
        print("❌ No charts found in active_charts folder!")
        return []
    
    print("\n📊 AVAILABLE CHARTS:")
    print("=" * 50)
    for i, path in enumerate(chart_paths, 1):
        chart_name = os.path.basename(path)
        try:
            size_kb = max(1, int(os.path.getsize(path) / 1024))
            print(f"  {i:2}. {chart_name:<25} - ~{size_kb:,} KB")
        except Exception:
            print(f"  {i:2}. {chart_name:<25}")
    
    print(f"  {len(chart_paths)+1:2}. ALL CHARTS")
    print("=" * 50)
    
    return chart_paths


def get_chart_selection(chart_paths):
    """Get user's chart selection."""
    while True:
        try:
            selection = input(f"\n🎯 Select charts (1-{len(chart_paths)+1}, or comma-separated): ").strip()
            
            if not selection:
                print("❌ Please make a selection.")
                continue
            
            # Handle "all charts" selection
            if selection == str(len(chart_paths) + 1):
                return chart_paths
            
            # Handle single or multiple selections
            selected_indices = []
            for part in selection.split(','):
                part = part.strip()
                if '-' in part:
                    # Handle ranges like "1-3"
                    start, end = map(int, part.split('-'))
                    selected_indices.extend(range(start, end + 1))
                else:
                    selected_indices.append(int(part))
            
            # Validate selections
            selected_charts = []
            for idx in selected_indices:
                if 1 <= idx <= len(chart_paths):
                    selected_charts.append(chart_paths[idx - 1])
                elif idx == len(chart_paths) + 1:
                    return chart_paths  # All charts
                else:
                    print(f"❌ Invalid selection: {idx}")
                    break
            else:
                if selected_charts:
                    print(f"✅ Selected {len(selected_charts)} chart(s)")
                    return selected_charts
            
        except ValueError:
            print("❌ Invalid input. Please enter numbers or ranges.")
        except Exception as e:
            print(f"❌ Error: {e}")


def get_optimization_parameters(strategy_version='v1'):
    """Get optimization parameters from user."""
    print("\n⚙️  OPTIMIZATION PARAMETERS")
    print("=" * 50)
    
    # Method selection
    methods = ['random', 'grid', 'lhs', 'sobol']
    print("📊 Available methods:")
    for i, method in enumerate(methods, 1):
        descriptions = {
            'random': 'Random sampling (fastest, good exploration)',
            'grid': 'Grid search (WARNING: Can be extremely slow with many parameters)',
            'lhs': 'Latin Hypercube (balanced coverage)',
            'sobol': 'Sobol sequence (quasi-random, efficient) - RECOMMENDED'
        }
        print(f"  {i}. {method.upper():<8} - {descriptions[method]}")
    
    while True:
        try:
            method_choice = input(f"\nSelect method (1-4) [4=sobol]: ").strip()
            if not method_choice:
                method_choice = '4'
            method_idx = int(method_choice) - 1
            if 0 <= method_idx < len(methods):
                method = methods[method_idx]
                # Warning for grid search with v2
                if method == 'grid' and strategy_version == 'v2':
                    print("\n⚠️  WARNING: Grid search with v2 strategy can be EXTREMELY slow!")
                    print(f"   Strategy v2 has 21 parameters with billions of combinations.")
                    print(f"   Consider using Sobol or LHS instead.")
                    confirm = input("   Continue with grid? (y/n) [n]: ").strip().lower()
                    if confirm not in ('y', 'yes'):
                        continue
                break
            else:
                print("❌ Invalid choice. Please select 1-4.")
        except ValueError:
            print("❌ Please enter a number.")
    
    # Trials per chart
    while True:
        try:
            trials_input = input(f"\n🔬 Trials per chart [200]: ").strip()
            trials = int(trials_input) if trials_input else 200
            if trials > 0:
                break
            else:
                print("❌ Trials must be positive.")
        except ValueError:
            print("❌ Please enter a valid number.")
    
    # K-fold validation
    while True:
        try:
            kfold_input = input(f"\n🔀 K-fold validation (0=disabled) [0]: ").strip()
            kfold = int(kfold_input) if kfold_input else 0
            if kfold >= 0:
                break
            else:
                print("❌ K-fold must be non-negative.")
        except ValueError:
            print("❌ Please enter a valid number.")
    
    # Embargo size (if k-fold enabled)
    embargo_frac = 0.05
    if kfold > 0:
        while True:
            try:
                embargo_input = input(f"\n🚫 Embargo size (e.g., 5% or 0.05) [5%]: ").strip()
                if not embargo_input:
                    embargo_frac = 0.05
                    break
                
                if embargo_input.endswith('%'):
                    embargo_frac = float(embargo_input[:-1]) / 100.0
                else:
                    embargo_frac = float(embargo_input)
                    if embargo_frac > 1.0:
                        embargo_frac = embargo_frac / 100.0
                
                if 0.0 <= embargo_frac <= 0.9:
                    break
                else:
                    print("❌ Embargo must be between 0% and 90%.")
            except ValueError:
                print("❌ Please enter a valid percentage or decimal.")
    
    # Performance mode
    print(f"\n⚡ PERFORMANCE OPTIONS:")
    print("  1. MAXIMUM SPEED (JSON only, minimal processing)")
    print("  2. BALANCED (Excel + optimizations)")
    print("  3. FULL FEATURES (Excel with all sheets)")
    
    while True:
        try:
            perf_input = input(f"\nSelect performance mode [1]: ").strip()
            perf_mode = int(perf_input) if perf_input else 1
            if 1 <= perf_mode <= 3:
                break
            else:
                print("❌ Please select 1-3.")
        except ValueError:
            print("❌ Please enter a valid number.")
    
    # Metric selection
    metrics = ['total_return', 'sharpe_ratio', 'sortino_ratio', 'calmar_ratio']
    print(f"\n📈 OPTIMIZATION METRIC:")
    for i, metric in enumerate(metrics, 1):
        print(f"  {i}. {metric}")
    
    while True:
        try:
            metric_input = input(f"\nSelect metric (1-4) [1=total_return]: ").strip()
            metric_idx = int(metric_input) - 1 if metric_input else 0
            if 0 <= metric_idx < len(metrics):
                metric = metrics[metric_idx]
                break
            else:
                print("❌ Please select 1-4.")
        except ValueError:
            print("❌ Please enter a valid number.")
    
    return {
        'method': method,
        'trials': trials,
        'kfold': kfold,
        'embargo_frac': embargo_frac,
        'performance_mode': perf_mode,
        'metric': metric,
        'seed': 42  # Fixed for reproducibility
    }


def show_run_summary(selected_charts, params, strategy_version):
    """Display run summary before execution."""
    print("\n" + "="*60)
    print("🚀 OPTIMIZATION RUN SUMMARY")
    print("="*60)
    print(f"📈 Strategy: {strategy_version.upper()}")
    print(f"📊 Charts: {len(selected_charts)} selected")
    for chart in selected_charts:
        print(f"   • {os.path.basename(chart)}")
    print(f"\n⚙️  Method: {params['method'].upper()}")
    print(f"🔬 Trials per chart: {params['trials']:,}")
    print(f"📈 Total trials: {len(selected_charts) * params['trials']:,}")
    print(f"📊 Optimization metric: {params['metric']}")
    
    if params['kfold'] > 0:
        print(f"🔀 K-fold validation: {params['kfold']} folds")
        print(f"🚫 Embargo: {params['embargo_frac']*100:.1f}%")
    
    perf_names = {1: "MAXIMUM SPEED", 2: "BALANCED", 3: "FULL FEATURES"}
    print(f"⚡ Performance mode: {perf_names[params['performance_mode']]}")
    
    print("="*60)
    
    confirm = input("\n✅ Proceed with optimization? (y/n) [y]: ").strip().lower()
    return confirm in ('', 'y', 'yes')


def optimized_notebook_append_interactive(out_dir, notebook_name, run_id, metadata, results_df, trades_df_all, performance_mode):
    """Notebook append with performance mode selection."""
    if performance_mode == 1:  # Maximum speed - skip Excel
        print("⚡ MAXIMUM SPEED mode: Skipping Excel operations")
        return None
    
    notebooks_dir = os.path.join(out_dir, 'notebooks')
    os.makedirs(notebooks_dir, exist_ok=True)
    xlsx_path = os.path.join(notebooks_dir, f"{notebook_name}.xlsx")
    
    # Prepare data efficiently
    results_clean = results_df.copy()
    results_clean.insert(0, 'run_id', run_id)
    
    # Add trial UIDs efficiently
    if 'trial_id' in results_clean.columns:
        from src.io.fast_io import vectorized_trial_uid_creation  # lazy import
        results_clean['trial_uid'] = vectorized_trial_uid_creation(results_clean['trial_id'], run_id)
    
    # Clean unwanted columns
    unwanted_cols = ['fold_id', 'val_start', 'val_end', 'trial_id'] if performance_mode == 2 else ['fold_id']
    cols_to_drop = [col for col in unwanted_cols if col in results_clean.columns]
    if cols_to_drop:
        results_clean.drop(columns=cols_to_drop, inplace=True)
    
    # Prepare sheets
    sheets_data = {
        'Runs': pd.DataFrame([{
            'run_id': run_id,
            'timestamp': metadata.get('timestamp'),
            'method': metadata.get('method'),
            'trials_per_chart': metadata.get('trials_per_chart'),
            'num_charts': metadata.get('num_charts'),
            'total_trials': metadata.get('total_trials'),
            'charts_processed': ','.join(metadata.get('charts_processed', []))
        }]),
        f"run_{run_id}_summary": results_clean
    }
    
    # Add trades if not too large and performance mode allows
    if trades_df_all is not None and len(trades_df_all) > 0:
        if performance_mode == 3 or len(trades_df_all) < 15000:
            trades_clean = trades_df_all.copy()
            trades_clean.insert(0, 'run_id', run_id)
            if 'trial_id' in trades_clean.columns:
                trades_clean['trial_uid'] = vectorized_trial_uid_creation(trades_clean['trial_id'], run_id)
            sheets_data[f"run_{run_id}_trades"] = trades_clean
    
    # Write Excel file
    from src.io.fast_io import efficient_excel_write  # lazy import
    return efficient_excel_write(xlsx_path, sheets_data, max_file_size_mb=25.0)


def main():
    print("🚀 INTERACTIVE OPTIMIZER")
    print("Advanced optimization with full control")
    print("=" * 50)
    
    # Suppress warnings
    import warnings
    warnings.simplefilter('ignore', category=FutureWarning)
    warnings.simplefilter('ignore', category=pd.errors.PerformanceWarning)

    # Get strategy selection
    strategy_version = get_strategy_selection()
    
    # Dynamically import strategy and parameters
    try:
        strategy_module = __import__(f"src.strategy.bands_{strategy_version}", fromlist=["compute_signals"])
        compute_signals_func = strategy_module.compute_signals
        params_module = __import__(f"config.strategy_params_{strategy_version}", fromlist=["TEST_RANGES", "sanitize_test_ranges"])
        raw_ranges = getattr(params_module, "TEST_RANGES")
        if hasattr(params_module, "sanitize_test_ranges"):
            RAW_PARAM_RANGES = params_module.sanitize_test_ranges(dict(raw_ranges))
        else:
            RAW_PARAM_RANGES = dict(raw_ranges)
        # Pre-run summary
        print("\n🧼 Parameter range summary (lists are categorical; ranges require explicit schema)")
        for k, v in RAW_PARAM_RANGES.items():
            mode = "categorical"
            n = None
            v_min = None
            v_max = None
            if isinstance(v, dict):
                mode = v.get("mode", "range")
                if mode == "range":
                    n = "∞"
                    v_min, v_max = v.get("low"), v.get("high")
                elif mode == "cat":
                    vals = v.get("values", [])
                    if not vals:
                        raise ValueError(f"{k} has no candidates after sanitization")
                    n = len(vals)
                    nums = [x for x in vals if isinstance(x, numbers.Real)]
                    if nums:
                        v_min, v_max = min(nums), max(nums)
                else:
                    raise ValueError(f"{k} unknown schema mode {mode}")
            else:
                if not isinstance(v, (list, tuple, np.ndarray)):
                    raise TypeError(f"{k} must be list/tuple or schema dict after sanitization")
                if len(v) == 0:
                    raise ValueError(f"{k} has no candidates after sanitization")
                n = len(v)
                nums = [x for x in v if isinstance(x, numbers.Real)]
                if nums:
                    v_min, v_max = min(nums), max(nums)
            print(f"  - {k}: mode={mode}, candidates={n}, min={v_min}, max={v_max}")
        print("")
        print(f"✅ Loaded Strategy: {strategy_version.upper()}")
    except ImportError as e:
        print(f"❌ Failed to load strategy '{strategy_version}': {e}")
        return
    
    # Show and select charts
    chart_paths = show_available_charts()
    if not chart_paths:
        return
    
    selected_charts = get_chart_selection(chart_paths)
    if not selected_charts:
        print("❌ No charts selected. Exiting.")
        return
    
    # Get optimization parameters
    params = get_optimization_parameters(strategy_version)
    
    # Show summary and confirm
    if not show_run_summary(selected_charts, params, strategy_version):
        print("❌ Operation cancelled.")
        return
    
    # Start optimization
    print(f"\n🔄 STARTING OPTIMIZATION...")
    start_time = time.time()
    
    # Set seed for reproducibility
    np.random.seed(params['seed'])
    
    # Normalize param ranges
    from src.optimizer.search import normalize_param_ranges, sample_param_sets, evaluate_collect, evaluate_collect_kfold  # lazy imports
    PARAMS_NORM = normalize_param_ranges(RAW_PARAM_RANGES)
    
    # Initialize data collection
    all_rows = []
    trades_batch = []
    trial_counter = 0
    
    total_trials = len(selected_charts) * params['trials']
    completed = 0
    
    # Process each selected chart
    charts_meta = []
    for chart_idx, chart_path in enumerate(selected_charts):
        chart_name = os.path.basename(chart_path)
        
        price = load_chart_from_path(chart_path)
        meta = parse_chart_name(chart_path, price.index)
        meta.update({
            "bars": len(price),
            "start": str(price.index[0]) if len(price) > 0 else None,
            "end": str(price.index[-1]) if len(price) > 0 else None,
        })
        charts_meta.append(meta)
        
        print(f"\n📊 Processing chart {chart_idx+1}/{len(selected_charts)}: {chart_name}")
        
        # Generate parameters for this chart
        params_list = sample_param_sets(PARAMS_NORM, method=params['method'], 
                                      n=params['trials'], seed=params['seed'])
        
        chart_trades = []
        
        # Process trials
        for param_idx, trial_params in enumerate(params_list):
            # Build per-trial toggles so we can pass chart context downstream
            trial_toggles = dict(TOGGLES)
            trial_toggles['chart_name'] = chart_name
            trial_toggles['symbol'] = meta.get('symbol')
            trial_toggles['timeframe'] = meta.get('timeframe')

            if params['kfold'] > 0:
                rows, trades_df = evaluate_collect_kfold(
                    price, trial_params, trial_toggles, compute_signals_func,
                    k_folds=params['kfold'], embargo_frac=params['embargo_frac']
                )
                
                for fold_row in rows:
                    trial_counter += 1
                    # Efficient parameter flattening
                    fold_params = fold_row.get('params', {})
                    flat_params = {f"param_{k}": v for k, v in fold_params.items()}
                    
                    fold_row.update({
                        'chart': chart_name,
                        'symbol': meta.get('symbol'),
                        'timeframe': meta.get('timeframe'),
                        'trial_id': trial_counter,
                        'method': params['method'],
                    })
                    fold_row.pop('params', None)
                    fold_row.update(flat_params)
                    all_rows.append(fold_row)
                
                if trades_df is not None and len(trades_df) > 0:
                    chart_trades.append(trades_df)
                    
            else:
                row, trades_df = evaluate_collect(price, trial_params, trial_toggles, compute_signals_func)
                trial_counter += 1
                
                # Efficient parameter flattening
                row_params = row.get('params', {})
                flat_params = {f"param_{k}": v for k, v in row_params.items()}
                
                row.update({
                    'chart': chart_name,
                    'symbol': meta.get('symbol'),
                    'timeframe': meta.get('timeframe'),
                    'trial_id': trial_counter,
                    'method': params['method'],
                })
                row.pop('params', None)
                row.update(flat_params)
                all_rows.append(row)
                
                if trades_df is not None and len(trades_df) > 0:
                    # Add metadata to trades
                    trades_df = trades_df.copy()
                    trades_df['chart'] = chart_name
                    trades_df['trial_id'] = trial_counter
                    trades_df['metric'] = row.get(params['metric'])
                    
                    for k, v in flat_params.items():
                        trades_df[k] = v
                    
                    chart_trades.append(trades_df)
            
            completed += 1
            
            # Progress updates
            if completed % 25 == 0:
                pct = int(completed * 100 / total_trials)
                elapsed = time.time() - start_time
                eta = elapsed * (total_trials - completed) / completed if completed > 0 else 0
                print(f"   Progress: {completed}/{total_trials} ({pct}%) - ETA: {eta/60:.1f}m")
        
        # Process trades for this chart
        if chart_trades:
            processed_trades = batch_datetime_conversion(chart_trades)
            trades_batch.extend(processed_trades)
        
        print(f"   ✅ Completed: {chart_name}")
    
    # Process results
    print(f"\n🔄 PROCESSING RESULTS...")
    
    # Create results DataFrame
    results_df = pd.DataFrame(all_rows)
    if len(results_df) > 0 and params['metric'] in results_df.columns:
        # Sort by metric (descending)
        if len(results_df) <= 50000:  # Only sort if manageable
            results_df = results_df.sort_values(params['metric'], ascending=False)
    
    # Process trades with single concatenation
    trades_df_all = None
    if trades_batch:
        print(f"   Concatenating {len(trades_batch)} trade DataFrames...")
        trades_df_all = single_concat_operation(trades_batch)
        
        if trades_df_all is not None:
            # Add duration calculation
            if all(col in trades_df_all.columns for col in ['Entry Date', 'Exit Date']):
                try:
                    entry_dates = pd.to_datetime(trades_df_all['Entry Date'], errors='coerce')
                    exit_dates = pd.to_datetime(trades_df_all['Exit Date'], errors='coerce')
                    trades_df_all['duration_hours'] = (exit_dates - entry_dates).dt.total_seconds() / 3600.0
                except:
                    pass
            
            trades_df_all['trade_index'] = trades_df_all.index + 1
    
    # Generate outputs
    run_id = time.strftime('%Y%m%d_%H%M%S')
    out_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs')
    
    # Metadata
    metadata = {
        'strategy_version': strategy_version,
        'method': params['method'],
        'trials_per_chart': params['trials'],
        'num_charts': len(selected_charts),
        'total_trials': total_trials,
        'metric': params['metric'],
        'seed': params['seed'],
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'charts_processed': [os.path.basename(p) for p in selected_charts],
        'charts': charts_meta,
        'kfold': params['kfold'],
        'embargo_frac': params['embargo_frac'],
        'performance_mode': params['performance_mode']
    }
    
    # Excel output (based on performance mode)
    nb_path = None
    if params['performance_mode'] > 1:
        print(f"📊 Updating Excel notebook...")
        nb_path = optimized_notebook_append_interactive(
            out_dir, 'optimizer_central', run_id, metadata, 
            results_df, trades_df_all, params['performance_mode']
        )
        if nb_path:
            print(f"   ✅ Excel completed: {os.path.basename(nb_path)}")
    
    # JSON output
    print(f"📄 Saving JSON results...")
    try:
        best = results_df.iloc[0].to_dict() if len(results_df) > 0 else {}
        
        # Add trial UIDs for JSON
        if 'trial_id' in results_df.columns:
            results_df['trial_uid'] = vectorized_trial_uid_creation(results_df['trial_id'], run_id)
        
        payload = {
            'metadata': metadata,
            'results': results_df.to_dict('records')
        }
        
        json_name = f"interactive_{params['method']}_{params['trials']}_{run_id}.json"
        json_path = write_run_json(out_dir, json_name, payload)
        print(f"   ✅ JSON completed: {os.path.basename(json_path)}")
        
    except Exception as e:
        print(f"   ❌ JSON failed: {e}")
        json_path = None
    
    # CSV output
    if params['performance_mode'] > 1:
        print(f"📋 Exporting CSV...")
        try:
            csv_dir = os.path.join(out_dir, 'csv')
            os.makedirs(csv_dir, exist_ok=True)
            
            fname_base = f"interactive_{params['method']}_{params['trials']}_{run_id}"
            csv_path = os.path.join(csv_dir, f"{fname_base}.csv")
            results_df.to_csv(csv_path, index=False)
            print(f"   ✅ CSV completed: {os.path.basename(csv_path)}")
            
        except Exception as e:
            print(f"   ❌ CSV failed: {e}")

    # Run-level summary artifact
    try:
        runs_dir = os.path.join(out_dir, 'runs', run_id)
        os.makedirs(runs_dir, exist_ok=True)
        ts_tag = time.strftime('%Y%m%d_%H%M')

        def _dd_pct(val):
            try:
                if val is None or pd.isna(val):
                    return None
                return float(val if abs(val) > 1 else val * 100.0)
            except Exception:
                return None

        summary = {
            'run_id': run_id,
            'created_at': metadata['timestamp'],
            'strategy_version': strategy_version,
            'method': params['method'],
            'metric': params['metric'],
            'seed': params['seed'],
            'trials_per_chart': params['trials'],
            'total_trials': total_trials,
            'charts': metadata.get('charts', []),
            'filters': {
                'max_drawdown_pct': 4.0,
                'min_trades': 30,
                'min_sharpe': 1.0,
                'min_calmar': 0.5,
            },
            'top_profiles': [],
            'strong_profiles': [],
            'directional_totals': {},
        }

        def _row_extract(row):
            dd_pct = _dd_pct(row.get('max_drawdown'))
            return {
                'trial_id': row.get('trial_id'),
                'trial_uid': row.get('trial_uid'),
                'chart': row.get('chart'),
                'symbol': row.get('symbol'),
                'timeframe': row.get('timeframe'),
                'total_return': row.get('total_return'),
                'sharpe_ratio': row.get('sharpe_ratio'),
                'calmar_ratio': row.get('calmar_ratio'),
                'max_drawdown_pct': dd_pct,
                'total_trades': row.get('total_trades'),
                'long_trades': row.get('long_trades'),
                'short_trades': row.get('short_trades'),
                'long_win_rate': row.get('long_win_rate'),
                'short_win_rate': row.get('short_win_rate'),
                'long_expectancy': row.get('long_expectancy'),
                'short_expectancy': row.get('short_expectancy'),
            }

        if len(results_df) > 0:
            top_slice = results_df.head(10)
            summary['top_profiles'] = [_row_extract(r) for r in top_slice.to_dict('records')]

            dd_limit = summary['filters']['max_drawdown_pct']
            min_trades = summary['filters']['min_trades']
            min_sharpe = summary['filters']['min_sharpe']
            min_calmar = summary['filters']['min_calmar']

            def _passes(row):
                dd_pct = _dd_pct(row.get('max_drawdown'))
                if dd_pct is None or dd_pct > dd_limit:
                    return False
                if row.get('total_trades', 0) < min_trades:
                    return False
                if row.get('sharpe_ratio', 0) < min_sharpe:
                    return False
                if row.get('calmar_ratio', 0) < min_calmar:
                    return False
                return True

            strong_rows = [r for r in results_df.to_dict('records') if _passes(r)]
            summary['strong_profiles'] = [_row_extract(r) for r in strong_rows]

            # Directional totals
            for fld in ('long_trades', 'short_trades'):
                if fld in results_df.columns:
                    summary['directional_totals'][fld] = int(results_df[fld].fillna(0).sum())
            for fld in ('long_win_rate', 'short_win_rate', 'long_expectancy', 'short_expectancy'):
                if fld in results_df.columns:
                    summary['directional_totals'][f"{fld}_avg"] = float(results_df[fld].dropna().mean()) if len(results_df[fld].dropna()) else None

        summary_path = os.path.join(runs_dir, f"summary_{ts_tag}.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"   ✅ Summary: runs/{run_id}/summary_{ts_tag}.json")
    except Exception as e:
        print(f"   ❌ Summary generation failed: {e}")
    
    # Final summary
    total_time = time.time() - start_time
    print("\n" + "="*60)
    print("🎉 OPTIMIZATION COMPLETED!")
    print("="*60)
    print(f"⏱️  Total time: {total_time/60:.1f} minutes")
    print(f"📊 Charts processed: {len(selected_charts)}")
    print(f"🔬 Total trials: {total_trials:,}")
    print(f"⚡ Method: {params['method'].upper()}")
    
    if len(results_df) > 0:
        best_result = results_df.iloc[0]
        print(f"\n🏆 BEST RESULT:")
        print(f"   {params['metric'].replace('_', ' ').title()}: {best_result.get(params['metric'], 'N/A'):.3f}")
        if 'sharpe_ratio' in best_result and params['metric'] != 'sharpe_ratio':
            print(f"   Sharpe Ratio: {best_result.get('sharpe_ratio', 'N/A'):.3f}")
        if 'max_drawdown' in best_result:
            print(f"   Max Drawdown: {best_result.get('max_drawdown', 'N/A'):.3f}%")
        print(f"   Chart: {best_result.get('chart', 'N/A')}")
    
    print(f"\n📁 OUTPUT FILES:")
    if nb_path:
        print(f"   ✅ Excel: {os.path.relpath(nb_path, out_dir)}")
    if json_path:
        print(f"   ✅ JSON: {os.path.relpath(json_path, out_dir)}")
    if params['performance_mode'] > 1:
        print(f"   ✅ CSV: csv/{os.path.basename(csv_path)}")
    
    print("="*60)
    
    # Optional discovery logging
    try:
        append_discovery(
            base_outputs_dir=out_dir,
            run_id=run_id,
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
            charts=[os.path.basename(p) for p in selected_charts],
            trials=params['trials'],
            best_summary={
                params['metric']: best.get(params['metric']) if len(results_df) > 0 else None,
            },
            outputs={'json': os.path.relpath(json_path, out_dir) if json_path else ''},
            notes=f"interactive {params['method']} optimization",
        )
    except:
        pass


if __name__ == '__main__':
    main()
