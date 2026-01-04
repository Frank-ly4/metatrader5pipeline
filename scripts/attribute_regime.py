"""
Regime Attribution Analysis Script

This script joins optimizer trade logs with the underlying Parquet chart data
to attribute performance across different market regimes (Volatility, Trend Strength, etc.).

Usage:
    python scripts/attribute_regime.py --run outputs/runs/interactive_random_100_...json --chart USDJPY_4h_cl_1.csv
"""

import argparse
import json
import pandas as pd
import numpy as np
import os
from datetime import timedelta

def load_trades_from_run(run_path: str) -> pd.DataFrame:
    """Load all trades from a specific JSON run file."""
    if not os.path.exists(run_path):
        raise FileNotFoundError(f"Run file not found: {run_path}")
    
    with open(run_path, 'r') as f:
        data = json.load(f)
        
    trades_list = []
    # If the JSON structure supports detailed trade logs (some might not)
    # Ideally, we look for a companion CSV or if trades are embedded.
    # For now, we assume the run might point to a trades file or we analyze trial aggregate stats.
    # Wait, the current JSONs only have aggregate stats per trial.
    # We need to re-run the backtest for the top trials to get the trade-level data.
    
    print("NOTE: Detailed trade logs are not in the summary JSON.")
    print("      We will Re-Run the top 5 trials to generate trade attribution.")
    
    results = data.get('results', [])
    df = pd.DataFrame(results)
    return df

def load_parquet_indicators(chart_name: str) -> pd.DataFrame:
    """Load the parquet file with pre-computed indicators."""
    # Assuming parquet files are in data/active_charts/
    # If extension is .csv in the JSON, swap to .parquet
    base_name = chart_name.replace('.csv', '.parquet')
    path = os.path.join('data', 'active_charts', base_name)
    
    if not os.path.exists(path):
        # Fallback to loading CSV and computing simple regimes
        csv_path = os.path.join('data', 'active_charts', chart_name)
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Chart data not found: {path} or {csv_path}")
        print(f"Loading CSV: {csv_path}")
        df = pd.read_csv(csv_path, parse_dates=['time'], index_col='time')
        return df
        
    print(f"Loading Parquet: {path}")
    df = pd.read_parquet(path)
    return df

def analyze_regime_performance(trades: pd.DataFrame, indicators: pd.DataFrame):
    """Join trades with indicators on Entry Time."""
    # Ensure timezone awareness matches
    if trades['entry_time'].dt.tz is None and indicators.index.tz is not None:
        trades['entry_time'] = trades['entry_time'].dt.tz_localize(indicators.index.tz)
    
    # Merge using 'asof' to find the indicators at (or just before) entry
    merged = pd.merge_asof(
        trades.sort_values('entry_time'),
        indicators.sort_index(),
        left_on='entry_time',
        right_index=True,
        direction='backward'
    )
    
    # Now we attribute performance
    print("\n--- Performance by Volatility Regime (ATR) ---")
    if 'atr' in merged.columns:
        merged['vol_bucket'] = pd.qcut(merged['atr'], 4, labels=['Low', 'Med-Low', 'Med-High', 'High'])
        print(merged.groupby('vol_bucket')['return'].describe())
        
    print("\n--- Performance by Trend Strength (ADX) ---")
    if 'adx' in merged.columns:
        merged['trend_bucket'] = pd.qcut(merged['adx'], 4, labels=['Weak', 'Moderate', 'Strong', 'Extreme'])
        print(merged.groupby('trend_bucket')['return'].describe())

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="Path to optimization run JSON")
    args = parser.parse_args()
    
    # logic to be expanded...
    print("Regime attribution script initialized.")

