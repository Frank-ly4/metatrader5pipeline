import os
import json
import pandas as pd
from .schema import order_columns, strip_timezones
from .excel_io import append_with_retry


def ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def sanitize_sheet_name(name: str) -> str:
    # Excel sheet name max 31 chars, disallow : \ / ? * [ ]
    bad = {':', '\\', '/', '?', '*', '[', ']'}
    cleaned = ''.join(ch for ch in name if ch not in bad)
    return cleaned[:31]


def append_run_to_notebook(
    outputs_dir: str,
    notebook_name: str,
    run_id: str,
    metadata: dict,
    results_df: pd.DataFrame,
    trades_df_all: pd.DataFrame | None,
) -> str:
    """Append a run's data to a central optimizer workbook under outputs/notebooks/.

    Creates/updates sheets:
      - Runs (registry of runs)
      - AllResults (all runs combined)
      - AllTrades (all runs combined)
      - run_<run_id>_summary
      - run_<run_id>_trades
      - run_<run_id>_<chart> (per chart trials)
    """
    notebooks_dir = os.path.join(outputs_dir, 'notebooks')
    ensure_dir(notebooks_dir)
    xlsx_path = os.path.abspath(os.path.join(notebooks_dir, f"{notebook_name}.xlsx"))
    
    # Migration: check for legacy notebook files and inform user
    legacy_notebooks = [
        'gold_2h_optimizer.xlsx',
        'gold_2h_optimizer_*.xlsx'  # timestamped versions
    ]
    
    for legacy_name in legacy_notebooks:
        if '*' in legacy_name:
            import glob
            legacy_files = glob.glob(os.path.join(notebooks_dir, legacy_name))
            if legacy_files:
                print(f"INFO: Found {len(legacy_files)} legacy notebook files. All new results will go to {notebook_name}.xlsx")
        else:
            legacy_path = os.path.join(notebooks_dir, legacy_name)
            if os.path.exists(legacy_path) and legacy_name != f"{notebook_name}.xlsx":
                print(f"INFO: Legacy notebook found at {legacy_name}. All new results will go to {notebook_name}.xlsx")

    # Prepare frames with run_id column and standardized column order
    results_df = results_df.copy()
    results_df.insert(0, 'run_id', run_id)
    
    # Clean up columns for better notebook display
    columns_to_remove = []
    
    # Remove redundant calmar_ratio column if both calmar_ratio and calmar_robust exist
    if 'calmar_ratio' in results_df.columns and 'calmar_robust' in results_df.columns:
        columns_to_remove.append('calmar_ratio')
    
    # Remove val_start and val_end columns (not needed for display)
    for col in ['val_start', 'val_end']:
        if col in results_df.columns:
            columns_to_remove.append(col)
    
    # Remove debug columns that aren't needed in the main view
    debug_cols = ['val_days', 'cagr_adj', 'maxdd_obs_frac', 'dd_floor', 'dd_adj']
    for col in debug_cols:
        if col in results_df.columns:
            columns_to_remove.append(col)
    
    # Remove additional unwanted columns for cleaner display
    unwanted_cols = ['fold_id', 'bars_total', 'bars_train', 'bars_embargo', 'bars_val', 'trial_id']
    for col in unwanted_cols:
        if col in results_df.columns:
            columns_to_remove.append(col)
    
    if columns_to_remove:
        results_df = results_df.drop(columns_to_remove, axis=1)
        print(f"Cleaned up notebook columns (removed: {', '.join(columns_to_remove)})")
    
    # Round numeric columns to 3 decimal places for better readability
    numeric_columns = results_df.select_dtypes(include=['float64', 'float32', 'int64', 'int32']).columns
    for col in numeric_columns:
        # Skip columns that should remain as integers
        if col in ['total_trades', 'run_id', 'trial_id', 'trial_uid'] or col.startswith('bars_') or col.startswith('param_'):
            continue
        try:
            results_df[col] = results_df[col].round(3)
        except Exception:
            # Skip any columns that can't be rounded
            pass
    
    # Add trial_uid for global identification (tolerate missing/NaN)
    if 'trial_id' in results_df.columns and 'trial_uid' not in results_df.columns:
        def _mk_uid(x):
            try:
                # Handle NaN, None, and NaTType values safely
                if pd.isna(x) or x is None:
                    return ''
                xi = int(float(x))  # Convert through float to handle edge cases
                return f"{run_id}:{xi}"
            except (ValueError, TypeError, OverflowError):
                return ''
        results_df['trial_uid'] = results_df['trial_id'].map(_mk_uid)
    results_df = order_columns(results_df)

    if trades_df_all is not None and len(trades_df_all) > 0:
        trades_df_all = trades_df_all.copy()
        # Excel can't handle tz-aware datetimes; strip timezone
        trades_df_all = strip_timezones(trades_df_all)
        trades_df_all.insert(0, 'run_id', run_id)
        
        # Round numeric columns to 3 decimal places for better readability
        numeric_columns = trades_df_all.select_dtypes(include=['float64', 'float32', 'int64', 'int32']).columns
        for col in numeric_columns:
            # Skip columns that should remain as integers or IDs
            if col in ['run_id', 'trial_id', 'trial_uid', 'trade_index', 'fold_id']:
                continue
            try:
                trades_df_all[col] = trades_df_all[col].round(3)
            except Exception:
                # Skip any columns that can't be rounded
                pass
        if 'trial_id' in trades_df_all.columns and 'trial_uid' not in trades_df_all.columns:
            def _mk_uid2(x):
                try:
                    # Handle NaN, None, and NaTType values safely
                    if pd.isna(x) or x is None:
                        return ''
                    xi = int(float(x))  # Convert through float to handle edge cases
                    return f"{run_id}:{xi}"
                except (ValueError, TypeError, OverflowError):
                    return ''
            trades_df_all['trial_uid'] = trades_df_all['trial_id'].map(_mk_uid2)
        trades_df_all = order_columns(trades_df_all)

    # Build/append registry and combined sheets
    runs_row = {
        'run_id': run_id,
        **{k: v for k, v in metadata.items() if k not in ('portfolio', 'charts_processed')},
        'charts_processed': ','.join(metadata.get('charts_processed', [])),
        'portfolio_json': json.dumps(metadata.get('portfolio', {}))
    }

    # Load existing workbook data if exists - with performance optimizations
    existing_runs = None
    existing_results = None
    existing_trades = None
    existing_file_mb = 0.0
    
    if os.path.exists(xlsx_path):
        try:
            existing_file_mb = max(0.0, os.path.getsize(xlsx_path) / (1024.0 * 1024.0))
        except Exception:
            existing_file_mb = 0.0
        
        print(f"Existing notebook size: {existing_file_mb:.1f} MB")
        
        # Test if existing file is corrupted before attempting to read
        file_corrupted = False
        try:
            # Quick corruption test by trying to read just the sheet names
            pd.ExcelFile(xlsx_path).sheet_names
        except Exception as e:
            file_corrupted = True
            error_msg = str(e)
            if "Bad CRC-32" in error_msg or "corrupted" in error_msg.lower():
                print(f"WARNING: Existing Excel file appears corrupted ({error_msg})")
                print("         Creating backup and starting fresh...")
                # Create backup of corrupted file
                import time
                backup_path = f"{xlsx_path}.corrupted_backup_{int(time.time())}"
                try:
                    import shutil
                    shutil.move(xlsx_path, backup_path)
                    print(f"         Corrupted file backed up to: {os.path.basename(backup_path)}")
                except Exception:
                    # If we can't move it, try to delete it
                    try:
                        os.remove(xlsx_path)
                        print("         Corrupted file removed")
                    except Exception:
                        print("         Could not remove corrupted file - will overwrite")
        
        # Always load runs registry (small and essential) - only if file is not corrupted
        if not file_corrupted:
            try:
                existing_runs = pd.read_excel(xlsx_path, sheet_name='Runs')
            except Exception:
                existing_runs = None
        else:
            existing_runs = None
        
        # Smart thresholds based on file size and new data volume
        num_new_results = len(results_df) if results_df is not None else 0
        num_new_trades = len(trades_df_all) if trades_df_all is not None else 0
        
        # More conservative thresholds to avoid memory issues
        # Only try to update existing data if file is not corrupted
        should_update_all_results = (
            not file_corrupted
            and existing_file_mb < 50.0  # Reduced from 80MB
            and num_new_results < 10000  # Avoid huge result sets
        )
        
        should_update_all_trades = (
            not file_corrupted
            and trades_df_all is not None
            and num_new_trades > 0
            and existing_file_mb < 30.0  # Much more conservative for trades
            and num_new_trades < 50000  # Reduced threshold
        )
        
        print(f"Will update AllResults: {should_update_all_results}, AllTrades: {should_update_all_trades}")
        
        if should_update_all_results:
            try:
                print("Loading existing AllResults...")
                existing_results = pd.read_excel(xlsx_path, sheet_name='AllResults')
            except Exception as e:
                print(f"Could not load AllResults: {e}")
                existing_results = None
        
        if should_update_all_trades:
            try:
                print("Loading existing AllTrades...")
                existing_trades = pd.read_excel(xlsx_path, sheet_name='AllTrades')
            except Exception as e:
                print(f"Could not load AllTrades: {e}")
                existing_trades = None

    runs_df = pd.DataFrame([runs_row])
    if existing_runs is not None and len(existing_runs) > 0:
        runs_df = pd.concat([existing_runs, runs_df], ignore_index=True)

    all_results_df = results_df
    if existing_results is not None and len(existing_results) > 0:
        all_results_df = pd.concat([existing_results, results_df], ignore_index=True)

    all_trades_df = trades_df_all
    if trades_df_all is not None and existing_trades is not None and len(existing_trades) > 0:
        all_trades_df = pd.concat([existing_trades, trades_df_all], ignore_index=True)

    # Write workbook (replace or create)
    try:
        # Consolidate frames to write by sheet - with optimized sorting
        frames = {}
        print("Preparing sheets for Excel write...")
        
        # Sorted combined sheets (only when we chose to update them)
        if existing_results is not None:
            print("Preparing AllResults sheet...")
            ar = all_results_df
            # Only sort if dataset is manageable
            if len(ar) <= 50000 and {'run_id','chart','trial_id'}.issubset(ar.columns):
                ar = ar.sort_values(['run_id','chart','trial_id'])
            frames['AllResults'] = ar
        
        if all_trades_df is not None and len(all_trades_df) > 0 and existing_trades is not None:
            print("Preparing AllTrades sheet...")
            at = all_trades_df
            # Much more conservative sorting for trades (expensive operation)
            if len(at) <= 20000 and {'run_id','chart','trial_id','trade_index'}.issubset(at.columns):
                at = at.sort_values(['run_id','chart','trial_id','trade_index'])
            frames['AllTrades'] = at
        
        frames['Runs'] = runs_df

        # Per-run sheets (always manageable size)
        print("Preparing per-run sheets...")
        rs = results_df.copy()
        if {'chart','trial_id'}.issubset(rs.columns):
            rs = rs.sort_values(['chart','trial_id'])
        frames[sanitize_sheet_name(f"run_{run_id}_summary")] = rs
        
        if trades_df_all is not None and len(trades_df_all) > 0:
            ts = trades_df_all.copy()
            if len(ts) <= 10000 and {'chart','trial_id','trade_index'}.issubset(ts.columns):
                ts = ts.sort_values(['chart','trial_id','trade_index'])
            frames[sanitize_sheet_name(f"run_{run_id}_trades")] = ts

        # Leaderboards per run (top 5 by Sharpe [1,2], Total Return, Sortino)
        try:
            base = results_df.copy()
            # Normalize metric names
            base = base.rename(columns={'sharpe_ratio': 'Sharpe', 'sortino_ratio': 'Sortino', 'total_return': 'TotalReturn'})
            # Select useful columns
            param_cols = [c for c in base.columns if c.startswith('param_')]
            id_cols = [c for c in ['trial_uid','chart','method'] if c in base.columns]
            metric_cols = [c for c in ['Sharpe','TotalReturn','Sortino','max_drawdown'] if c in base.columns]
            # Top Sharpe within [1,2]
            sharpe_df = base.copy()
            if 'Sharpe' in sharpe_df.columns:
                sharpe_df = sharpe_df[sharpe_df['Sharpe'].notna() & (sharpe_df['Sharpe'] >= 1.0) & (sharpe_df['Sharpe'] <= 2.0)]
                sharpe_df = sharpe_df.sort_values('Sharpe', ascending=False).head(5)
                frames[sanitize_sheet_name(f"run_{run_id}_top_sharpe")] = sharpe_df[id_cols + metric_cols + param_cols]
            # Top Total Return
            if 'TotalReturn' in base.columns:
                trets = base[base['TotalReturn'].notna()].sort_values('TotalReturn', ascending=False).head(5)
                frames[sanitize_sheet_name(f"run_{run_id}_top_return")] = trets[id_cols + metric_cols + param_cols]
            # Top Sortino
            if 'Sortino' in base.columns:
                sortdf = base[base['Sortino'].notna()].sort_values('Sortino', ascending=False).head(5)
                frames[sanitize_sheet_name(f"run_{run_id}_top_sortino")] = sortdf[id_cols + metric_cols + param_cols]
        except Exception:
            pass

        # Per-chart sheets
        if 'chart' in results_df.columns:
            for chart_name, chart_df in results_df.groupby('chart'):
                sheet = sanitize_sheet_name(f"run_{run_id}_{os.path.splitext(chart_name)[0]}")
                cs = chart_df
                if 'trial_id' in chart_df.columns:
                    cs = chart_df.sort_values(['trial_id'])
                frames[sheet] = cs

        actual_path = append_with_retry(xlsx_path, frames)
        if actual_path != xlsx_path:
            print(f"NOTE: Excel file written to fallback location: {actual_path}")
        return actual_path
    except Exception as e:
        raise RuntimeError(f"Failed to write optimizer notebook at {xlsx_path}: {e}")

    # Skipping post-processing with openpyxl to avoid engine conflicts in some environments.


