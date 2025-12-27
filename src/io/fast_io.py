"""
High-performance I/O operations optimized for antivirus environments.

Key optimizations:
- Minimal file operations to reduce antivirus scanning
- Batch processing for DataFrame operations
- Efficient memory management
- Vectorized operations instead of .map()/.apply()
"""
import os
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional


def batch_datetime_conversion(dfs: List[pd.DataFrame], 
                            datetime_cols: List[str] = ['Entry Date', 'Exit Date']) -> List[pd.DataFrame]:
    """Convert datetime columns across multiple DataFrames in batch for efficiency."""
    if not dfs:
        return dfs
    
    processed = []
    for df in dfs:
        if df is None or len(df) == 0:
            processed.append(df)
            continue
        
        df_copy = None
        for col in datetime_cols:
            if col in df.columns and not pd.api.types.is_datetime64_any_dtype(df[col]):
                if df_copy is None:
                    df_copy = df.copy()
                
                try:
                    # Fast datetime conversion
                    df_copy[col] = pd.to_datetime(df_copy[col], errors='coerce', cache=True)
                    
                    # Strip timezone if present
                    if hasattr(df_copy[col], 'dt') and df_copy[col].dt.tz is not None:
                        df_copy[col] = df_copy[col].dt.tz_localize(None)
                except:
                    pass
        
        processed.append(df_copy if df_copy is not None else df)
    
    return processed


def vectorized_trial_uid_creation(trial_ids: pd.Series, run_id: str) -> pd.Series:
    """Create trial UIDs using vectorized operations instead of slow .map()."""
    if trial_ids is None or len(trial_ids) == 0:
        return pd.Series(dtype=str)
    
    # Convert to numpy for vectorized operations
    ids_array = trial_ids.to_numpy()
    
    # Handle NaN/None efficiently
    valid_mask = pd.notna(ids_array)
    
    # Pre-allocate result
    result = np.full(len(ids_array), '', dtype=object)
    
    # Vectorized UID creation for valid IDs
    if valid_mask.any():
        valid_ids = ids_array[valid_mask].astype(int)
        result[valid_mask] = np.array([f"{run_id}:{id_val}" for id_val in valid_ids])
    
    return pd.Series(result, index=trial_ids.index, name='trial_uid')


def smart_dataframe_sort(df: pd.DataFrame, 
                        sort_cols: List[str], 
                        max_rows: int = 50000,
                        ascending: bool = True) -> pd.DataFrame:
    """Smart sorting that skips expensive operations on large datasets."""
    if df is None or len(df) == 0:
        return df
    
    # Skip sorting for very large datasets to avoid CPU bottlenecks
    if len(df) > max_rows:
        print(f"Skipping sort for large dataset ({len(df)} rows > {max_rows})")
        return df
    
    # Filter to available columns
    available_cols = [col for col in sort_cols if col in df.columns]
    if not available_cols:
        return df
    
    try:
        return df.sort_values(available_cols, ascending=ascending, kind='mergesort')
    except Exception as e:
        print(f"Sort failed: {e}")
        return df


def efficient_excel_write(filepath: str, 
                         sheets_data: Dict[str, pd.DataFrame],
                         max_file_size_mb: float = 20.0) -> Optional[str]:
    """Write Excel file with antivirus-friendly optimizations."""
    import time
    
    # Check if we should use lightweight mode
    lightweight_mode = False
    if os.path.exists(filepath):
        try:
            file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
            if file_size_mb > max_file_size_mb:
                lightweight_mode = True
                print(f"Large file detected ({file_size_mb:.1f}MB) - using lightweight mode")
        except:
            pass
    
    try:
        # Single write operation to minimize antivirus scanning
        write_mode = "w"  # Always overwrite in lightweight mode to avoid reading existing data
        
        with pd.ExcelWriter(filepath, engine="openpyxl", mode=write_mode) as writer:
            for sheet_name, df in sheets_data.items():
                if df is not None and len(df) > 0:
                    # Remove timezone-aware columns that cause Excel issues
                    df_clean = df.copy()
                    for col in df_clean.columns:
                        if pd.api.types.is_datetime64_any_dtype(df_clean[col]):
                            try:
                                if hasattr(df_clean[col], 'dt') and df_clean[col].dt.tz is not None:
                                    df_clean[col] = df_clean[col].dt.tz_localize(None)
                            except:
                                pass
                    
                    # Write without index for faster operation
                    df_clean.to_excel(writer, sheet_name=sheet_name, index=False)
        
        return filepath
        
    except Exception as e:
        # Fallback: timestamped file
        timestamp = int(time.time())
        dir_path = os.path.dirname(filepath)
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        fallback_path = os.path.join(dir_path, f"{base_name}_{timestamp}.xlsx")
        
        try:
            with pd.ExcelWriter(fallback_path, engine="openpyxl", mode="w") as writer:
                for sheet_name, df in sheets_data.items():
                    if df is not None and len(df) > 0:
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            print(f"Fallback file created: {fallback_path}")
            return fallback_path
            
        except Exception as e2:
            print(f"Excel write completely failed: {e2}")
            return None


def optimize_dataframe_memory(df: pd.DataFrame) -> pd.DataFrame:
    """Optimize DataFrame memory usage by downcasting numeric types."""
    if df is None or len(df) == 0:
        return df
    
    df_optimized = df.copy()
    
    # Downcast integers
    int_cols = df_optimized.select_dtypes(include=['int64']).columns
    for col in int_cols:
        try:
            df_optimized[col] = pd.to_numeric(df_optimized[col], downcast='integer')
        except:
            pass
    
    # Downcast floats
    float_cols = df_optimized.select_dtypes(include=['float64']).columns
    for col in float_cols:
        try:
            df_optimized[col] = pd.to_numeric(df_optimized[col], downcast='float')
        except:
            pass
    
    return df_optimized


def single_concat_operation(dfs: List[pd.DataFrame], 
                          ignore_index: bool = True,
                          sort: bool = False) -> Optional[pd.DataFrame]:
    """Perform single concatenation instead of incremental concatenations."""
    if not dfs:
        return None
    
    # Filter out None and empty DataFrames
    valid_dfs = [df for df in dfs if df is not None and len(df) > 0]
    
    if not valid_dfs:
        return None
    
    if len(valid_dfs) == 1:
        return valid_dfs[0].copy()
    
    try:
        # Single concatenation operation - major performance improvement
        result = pd.concat(valid_dfs, ignore_index=ignore_index, sort=sort)
        return result
    except Exception as e:
        print(f"Concatenation failed: {e}")
        return None


def efficient_csv_export(df: pd.DataFrame, 
                        filepath: str,
                        max_rows_per_file: int = 100000) -> List[str]:
    """Export large DataFrames to CSV with chunking if necessary."""
    if df is None or len(df) == 0:
        return []
    
    exported_files = []
    
    try:
        if len(df) <= max_rows_per_file:
            # Single file export
            df.to_csv(filepath, index=False)
            exported_files.append(filepath)
        else:
            # Split into chunks
            base_path = os.path.splitext(filepath)[0]
            ext = os.path.splitext(filepath)[1]
            
            num_chunks = (len(df) + max_rows_per_file - 1) // max_rows_per_file
            
            for i in range(num_chunks):
                start_idx = i * max_rows_per_file
                end_idx = min((i + 1) * max_rows_per_file, len(df))
                
                chunk_df = df.iloc[start_idx:end_idx]
                chunk_path = f"{base_path}_part{i+1}{ext}"
                
                chunk_df.to_csv(chunk_path, index=False)
                exported_files.append(chunk_path)
            
            print(f"Large dataset split into {num_chunks} files")
        
        return exported_files
        
    except Exception as e:
        print(f"CSV export failed: {e}")
        return []


class FastResultsProcessor:
    """High-performance results processor for optimization runs."""
    
    def __init__(self, max_memory_mb: float = 500.0):
        self.max_memory_mb = max_memory_mb
        self.lightweight_mode = False
    
    def process_results(self, 
                       all_rows: List[Dict[str, Any]],
                       trades_dfs: List[pd.DataFrame],
                       run_id: str,
                       metric: str = 'total_return') -> tuple:
        """Process optimization results with performance optimizations."""
        
        print(f"Processing {len(all_rows)} result rows and {len(trades_dfs)} trade DataFrames...")
        
        # Create results DataFrame efficiently
        results_df = pd.DataFrame(all_rows)
        
        if len(results_df) > 0:
            # Optimize memory usage
            results_df = optimize_dataframe_memory(results_df)
            
            # Add trial UIDs efficiently
            if 'trial_id' in results_df.columns:
                results_df['trial_uid'] = vectorized_trial_uid_creation(results_df['trial_id'], run_id)
            
            # Smart sorting
            if metric in results_df.columns:
                results_df = smart_dataframe_sort(results_df, [metric], ascending=False)
        
        # Process trades with single concatenation
        trades_df_all = None
        if trades_dfs:
            # Batch process datetime columns first
            trades_processed = batch_datetime_conversion(trades_dfs)
            
            # Single concatenation operation (major bottleneck fix)
            trades_df_all = single_concat_operation(trades_processed)
            
            if trades_df_all is not None:
                # Add trial UIDs to trades
                if 'trial_id' in trades_df_all.columns:
                    trades_df_all['trial_uid'] = vectorized_trial_uid_creation(
                        trades_df_all['trial_id'], run_id)
                
                # Calculate duration efficiently
                if all(col in trades_df_all.columns for col in ['Entry Date', 'Exit Date']):
                    try:
                        entry_dates = pd.to_datetime(trades_df_all['Entry Date'], errors='coerce')
                        exit_dates = pd.to_datetime(trades_df_all['Exit Date'], errors='coerce')
                        trades_df_all['duration_hours'] = (exit_dates - entry_dates).dt.total_seconds() / 3600.0
                    except:
                        pass
                
                # Optimize memory
                trades_df_all = optimize_dataframe_memory(trades_df_all)
        
        return results_df, trades_df_all
