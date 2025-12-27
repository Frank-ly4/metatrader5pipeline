"""Schema helpers: column ordering and normalization for Excel outputs.

Contracts:
- order_columns for results and trades
- strip_timezones for DataFrame datetime columns
"""

from __future__ import annotations

from typing import Iterable
import warnings
import pandas as pd


IDS_ORDER = ["run_id", "trial_uid", "chart", "method"]
METRICS_ORDER = [
    "total_return",
    "sharpe_ratio",
    "sortino_ratio",
    "calmar_robust",  # Use the improved calmar instead of basic calmar_ratio
    "max_drawdown",
    "win_rate",
    "profit_factor",
    "expectancy",
    "start_capital",  # Starting capital amount
    "end_capital",    # Ending capital amount
    "avg_hold_hours",
    "total_trades",
    "ulcer_index",
    "omega_0",
    "omega_fees",
]


def strip_timezones(df: pd.DataFrame) -> pd.DataFrame:
    """Strip timezone information from all datetime columns to ensure Excel compatibility."""
    if df is None or len(df) == 0:
        return df
    
    out = df.copy()
    
    for col in out.columns:
        dtype_str = str(out[col].dtype)
        
        # Handle datetime64[ns, tz] columns (fast path)
        if dtype_str.startswith("datetime"):
            try:
                if hasattr(out[col], 'dt') and out[col].dt.tz is not None:
                    out[col] = out[col].dt.tz_localize(None)
                    print(f"Stripped timezone from datetime column: {col}")
            except Exception:
                pass
            continue
        
        # Handle object columns that might contain datetime objects with timezones
        if dtype_str == 'object':
            # More aggressive detection - check all object columns for datetime content
            try:
                # Sample multiple values to detect datetime content
                sample_values = []
                for val in out[col].dropna().iloc[:10]:  # Check first 10 non-null values
                    if val is not None:
                        sample_values.append(val)
                        if len(sample_values) >= 3:  # Enough samples
                            break
                
                if not sample_values:
                    continue
                
                # Check if any sample looks like a datetime
                has_datetime_content = False
                for val in sample_values:
                    if (hasattr(val, 'tzinfo') or 
                        isinstance(val, str) and any(indicator in str(val).lower() 
                                                   for indicator in ['t', ':', '-', '+', 'utc', 'gmt']) or
                        'date' in str(type(val)).lower() or 
                        'time' in str(type(val)).lower()):
                        has_datetime_content = True
                        break
                
                if has_datetime_content:
                    # Try to convert to datetime
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        try:
                            conv = pd.to_datetime(out[col], errors='coerce', utc=False)
                            
                            if str(conv.dtype).startswith('datetime'):
                                # Strip timezone if present
                                if hasattr(conv, 'dt') and conv.dt.tz is not None:
                                    conv = conv.dt.tz_localize(None)
                                    print(f"Stripped timezone from object column: {col}")
                                
                                # Replace if we successfully converted most values
                                if conv.notna().sum() >= out[col].notna().sum() * 0.3:
                                    out[col] = conv
                        except Exception:
                            # Try alternative conversion approaches
                            try:
                                # For timezone-aware timestamps, convert directly
                                if all(hasattr(val, 'tz_localize') for val in sample_values if val is not None):
                                    out[col] = out[col].apply(lambda x: x.tz_localize(None) if x is not None and hasattr(x, 'tz_localize') else x)
                                    print(f"Stripped timezone from timestamp column: {col}")
                            except Exception:
                                pass
                            
            except Exception:
                # If all conversion attempts fail, leave the column as-is
                pass
    
    return out


def _ordered_columns(existing: Iterable[str]) -> list[str]:
    existing = list(existing)
    ids = [c for c in IDS_ORDER if c in existing]
    params = sorted([c for c in existing if c.startswith("param_")])
    metrics = [c for c in METRICS_ORDER if c in existing]
    others = [c for c in existing if c not in set(ids + params + metrics)]
    return ids + params + metrics + others


def order_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = _ordered_columns(df.columns)
    return df.reindex(columns=cols)



