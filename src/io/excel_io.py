"""Excel IO utilities for centralized append-only workbook writes.

Implements:
- strip_timezones(df)
- order_columns(df)
- write_sorted_sheet(writer, df, sheet_name, sort_by)
- append_with_retry(path, frames_by_sheet)
"""

from __future__ import annotations

import os
import tempfile
from typing import Dict, Iterable, Tuple

import pandas as pd

from .schema import order_columns, strip_timezones


def write_sorted_sheet(
    writer: pd.ExcelWriter,
    df: pd.DataFrame,
    sheet_name: str,
    sort_by: Tuple[str, ...] | None = None,
) -> None:
    if df is None or len(df) == 0:
        return
    frame = strip_timezones(order_columns(df))
    if sort_by and set(sort_by).issubset(frame.columns):
        frame = frame.sort_values(list(sort_by))
    
    # Final timezone safety check before writing
    for col in frame.columns:
        if hasattr(frame[col], 'dt'):
            try:
                if frame[col].dt.tz is not None:
                    frame[col] = frame[col].dt.tz_localize(None)
                    print(f"Final timezone strip from {col} before Excel write")
            except Exception:
                pass
        # Check for object columns with timezone-aware values
        elif frame[col].dtype == 'object':
            try:
                sample = frame[col].dropna().iloc[0] if len(frame[col].dropna()) > 0 else None
                if sample is not None and hasattr(sample, 'tzinfo') and sample.tzinfo is not None:
                    frame[col] = frame[col].apply(lambda x: x.tz_localize(None) if hasattr(x, 'tz_localize') and x is not None else x)
                    print(f"Final timezone strip from object column {col} before Excel write")
            except Exception:
                pass
    
    # Write the data
    frame.to_excel(writer, index=False, sheet_name=sheet_name)
    
    # Auto-adjust column widths to fix "########" display issues
    try:
        worksheet = writer.sheets[sheet_name]
        
        # Define column width rules
        for idx, column in enumerate(frame.columns):
            # Convert column index to Excel column letter (A, B, C, ..., Z, AA, AB, ...)
            if idx < 26:
                column_letter = chr(65 + idx)
            else:
                first_letter = chr(65 + (idx // 26) - 1)
                second_letter = chr(65 + (idx % 26))
                column_letter = first_letter + second_letter
            
            # Set appropriate widths based on column type
            if column in ['run_id', 'trial_uid']:
                width = 18
            elif column in ['chart']:
                width = 25
            elif column.startswith('param_'):
                width = 12
            elif column in ['total_return', 'sharpe_ratio', 'sortino_ratio', 'max_drawdown']:
                width = 14
            elif column in ['calmar_robust', 'profit_factor', 'expectancy']:
                width = 14
            elif column in ['start_capital', 'end_capital']:
                width = 16
            elif column in ['val_start', 'val_end']:
                width = 20
            elif 'date' in column.lower() or 'time' in column.lower():
                width = 18
            else:
                # Auto-calculate width based on content
                max_length = max(
                    len(str(column)),  # Header length
                    frame[column].astype(str).str.len().max() if len(frame) > 0 else 0
                )
                width = min(max_length + 2, 30)  # Add padding, cap at 30
            
            worksheet.column_dimensions[column_letter].width = width
            
    except Exception:
        # If formatting fails, continue without it
        pass


def append_with_retry(
    xlsx_path: str,
    frames_by_sheet: Dict[str, pd.DataFrame],
    mode: str = "a",
    if_sheet_exists: str = "replace",
    max_retries: int = 3,
) -> str:
    """Append/replace sheets in an Excel file with robust retry/atomic replace.

    Returns the path of the successfully written file (may be timestamped fallback).
    If the target is locked or corrupted, writes to a temporary file and
    atomically replaces the destination.
    """
    import time
    import random
    
    attempt = 0
    last_err = None
    tmp_dir = os.path.dirname(xlsx_path)
    base = os.path.basename(xlsx_path)
    
    # Clean up any stale temp files first
    _cleanup_stale_temp_files(tmp_dir, base)
    
    while attempt <= max_retries:
        try:
            exists = os.path.exists(xlsx_path)
            writer_mode = mode if exists else "w"
            sheet_exists_param = if_sheet_exists if writer_mode == "a" else None
            
            # Try direct write first (fastest path)
            writer_kwargs = {"engine": "openpyxl", "mode": writer_mode}
            if sheet_exists_param:
                writer_kwargs["if_sheet_exists"] = sheet_exists_param
                
            with pd.ExcelWriter(xlsx_path, **writer_kwargs) as writer:
                for sheet, frame in frames_by_sheet.items():
                    write_sorted_sheet(writer, frame, sheet_name=sheet, sort_by=None)
            print(f"Excel file successfully written: {xlsx_path}")
            return xlsx_path
            
        except (PermissionError, OSError) as e:
            last_err = e
            attempt += 1
            
            if attempt <= max_retries:
                # Progressive backoff with jitter
                delay = min(2.0 ** attempt + random.uniform(0, 1), 10.0)
                print(f"Excel write attempt {attempt} failed, retrying in {delay:.1f}s: {e}")
                time.sleep(delay)
                continue
            
            # Final attempt: atomic write via temp file
            print(f"Direct write failed after {max_retries} attempts, trying atomic replacement...")
            return _atomic_write_fallback(xlsx_path, frames_by_sheet, tmp_dir, base)
            
        except Exception as e:
            last_err = e
            attempt += 1
            if attempt <= max_retries:
                delay = min(1.0 * attempt, 5.0)
                print(f"Excel write attempt {attempt} failed, retrying in {delay:.1f}s: {e}")
                time.sleep(delay)
            else:
                # Try atomic fallback for any other errors too
                try:
                    return _atomic_write_fallback(xlsx_path, frames_by_sheet, tmp_dir, base)
                except Exception:
                    pass
    
    raise RuntimeError(f"Failed to write Excel file after all attempts at {xlsx_path}: {last_err}")


def _cleanup_stale_temp_files(tmp_dir: str, base: str) -> None:
    """Remove stale temporary files that might be blocking writes."""
    import glob
    import time
    
    patterns = [
        f"._tmp_{base}*",
        f"{os.path.splitext(base)[0]}_*.xlsx.tmp",
        f"~${base}*"  # Excel lock files
    ]
    
    for pattern in patterns:
        for stale_file in glob.glob(os.path.join(tmp_dir, pattern)):
            try:
                # Only remove files older than 5 minutes
                if time.time() - os.path.getmtime(stale_file) > 300:
                    os.remove(stale_file)
                    print(f"Cleaned up stale temp file: {stale_file}")
            except Exception:
                pass


def _atomic_write_fallback(xlsx_path: str, frames_by_sheet: Dict[str, pd.DataFrame], tmp_dir: str, base: str) -> str:
    """Fallback atomic write mechanism with better error handling."""
    import time
    import uuid
    
    # Use UUID to avoid conflicts with concurrent processes
    unique_id = str(uuid.uuid4())[:8]
    tmp_path = os.path.join(tmp_dir, f"._tmp_{unique_id}_{base}")
    
    try:
        # Write to unique temp file
        with pd.ExcelWriter(tmp_path, engine="openpyxl", mode="w") as writer:
            for sheet, frame in frames_by_sheet.items():
                write_sorted_sheet(writer, frame, sheet_name=sheet, sort_by=None)
        
        # Try atomic replacement
        try:
            if os.path.exists(xlsx_path):
                # On Windows, need to remove target first
                backup_path = f"{xlsx_path}.backup_{int(time.time())}"
                os.rename(xlsx_path, backup_path)
                try:
                    os.rename(tmp_path, xlsx_path)
                    # Success! Remove backup
                    os.remove(backup_path)
                    print(f"Excel file successfully written via atomic replacement: {xlsx_path}")
                    return xlsx_path
                except Exception:
                    # Restore backup if rename failed
                    os.rename(backup_path, xlsx_path)
                    raise
            else:
                os.rename(tmp_path, xlsx_path)
                print(f"Excel file successfully written via atomic replacement: {xlsx_path}")
                return xlsx_path
                
        except (PermissionError, OSError):
            # Final fallback: timestamped file
            timestamp = int(time.time())
            fallback_path = os.path.join(tmp_dir, f"{os.path.splitext(base)[0]}_{timestamp}.xlsx")
            os.rename(tmp_path, fallback_path)
            print(f"WARNING: Main Excel file locked, saved to timestamped fallback: {fallback_path}")
            return fallback_path
            
    finally:
        # Cleanup temp file if it still exists
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    
    raise RuntimeError("Atomic write fallback failed")



