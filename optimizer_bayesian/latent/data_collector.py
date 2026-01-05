"""Data collection and preparation for latent-space training."""

import json
import os
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from pathlib import Path


def collect_historical_data(runs_dir: str) -> pd.DataFrame:
    """Extract parameter-performance pairs from existing JSON files.
    
    Args:
        runs_dir: Path to outputs/runs directory
        
    Returns:
        DataFrame with columns: parameters + performance metrics
    """
    json_files = list(Path(runs_dir).glob("*.json"))
    if not json_files:
        raise ValueError(f"No JSON files found in {runs_dir}")
    
    all_records = []
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract results array
            results = data.get('results', []) if isinstance(data, dict) else data
            if not results:
                continue
                
            for record in results:
                if not isinstance(record, dict):
                    continue
                    
                # Extract performance metrics
                metrics = {
                    'total_return': record.get('total_return', 0.0),
                    'sharpe_ratio': record.get('sharpe_ratio', 0.0),
                    'calmar_ratio': record.get('calmar_ratio', 0.0),
                    'max_drawdown': record.get('max_drawdown', 0.0),
                    'total_trades': record.get('total_trades', 0),
                    'win_rate': record.get('win_rate', 0.0),
                    'profit_factor': record.get('profit_factor', 0.0),
                }
                
                # Extract parameters (both param_ prefixed and non-prefixed)
                params = {}
                skip_cols = {
                    '_source_file', 'fold_id', 'bars_total', 'bars_train', 'bars_embargo',
                    'bars_val', 'val_start', 'val_end', 'chart', 'trial_id', 'method', 
                    'trial_uid', 'uid', 'score', 'is_pareto', 'stability_score', 'group_rank'
                }
                
                for key, value in record.items():
                    if key.startswith('param_'):
                        params[key[6:]] = value  # Remove param_ prefix
                    elif key not in skip_cols and key not in metrics:
                        params[key] = value
                
                if params and any(v is not None for v in metrics.values()):
                    row = {**params, **metrics}
                    row['_source_file'] = json_file.name
                    all_records.append(row)
                    
        except Exception as e:
            print(f"Warning: Failed to process {json_file}: {e}")
            continue
    
    if not all_records:
        raise ValueError("No valid records found in JSON files")
    
    return pd.DataFrame(all_records)


def prepare_training_data(df: pd.DataFrame, 
                         quality_filter: bool = True) -> Tuple[pd.DataFrame, List[str]]:
    """Prepare and clean data for VAE training.
    
    Args:
        df: Raw data from collect_historical_data
        quality_filter: Whether to filter for quality trials
        
    Returns:
        Tuple of (cleaned_df, parameter_names)
    """
    # Quality filtering
    if quality_filter:
        # Remove degenerate trials
        df = df[df['total_trades'] >= 10].copy()
        df = df[df['max_drawdown'] <= 50.0].copy()  # Remove extreme drawdowns
        df = df[df['calmar_ratio'].notna()].copy()
    
    # Identify parameter columns
    metric_cols = {'total_return', 'sharpe_ratio', 'calmar_ratio', 'max_drawdown', 
                   'total_trades', 'win_rate', 'profit_factor', '_source_file'}
    param_cols = [col for col in df.columns if col not in metric_cols]
    
    # Handle missing parameter values
    for col in param_cols:
        if df[col].dtype in ['object', 'string']:
            # Categorical parameters - fill with mode
            df[col] = df[col].fillna(df[col].mode().iloc[0] if not df[col].mode().empty else 'default')
        else:
            # Numeric parameters - fill with median
            df[col] = df[col].fillna(df[col].median())
    
    # Normalize numeric parameters to [0, 1] range for VAE
    normalized_df = df.copy()
    for col in param_cols:
        if df[col].dtype in ['int64', 'float64']:
            min_val, max_val = df[col].min(), df[col].max()
            if max_val > min_val:
                normalized_df[col] = (df[col] - min_val) / (max_val - min_val)
            else:
                normalized_df[col] = 0.5  # Constant value
    
    return normalized_df, param_cols


def save_training_data(df: pd.DataFrame, param_cols: List[str], output_dir: str) -> str:
    """Save prepared training data for model training.
    
    Returns:
        Path to saved training data file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Save main training data
    data_path = os.path.join(output_dir, "training_data.parquet")
    df.to_parquet(data_path, index=False)
    
    # Save metadata
    meta_path = os.path.join(output_dir, "training_metadata.json")
    metadata = {
        "param_columns": param_cols,
        "total_records": len(df),
        "data_sources": df['_source_file'].unique().tolist() if '_source_file' in df.columns else [],
        "performance_stats": {
            "calmar_mean": float(df['calmar_ratio'].mean()),
            "calmar_std": float(df['calmar_ratio'].std()),
            "best_calmar": float(df['calmar_ratio'].max()),
        }
    }
    
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    return data_path


def load_training_data(output_dir: str) -> Tuple[pd.DataFrame, List[str]]:
    """Load previously prepared training data.
    
    Returns:
        Tuple of (training_df, parameter_columns)
    """
    data_path = os.path.join(output_dir, "training_data.parquet")
    meta_path = os.path.join(output_dir, "training_metadata.json")
    
    if not os.path.exists(data_path) or not os.path.exists(meta_path):
        raise FileNotFoundError("Training data not found. Run data collection first.")
    
    df = pd.read_parquet(data_path)
    
    with open(meta_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    param_cols = metadata['param_columns']
    
    return df, param_cols


if __name__ == "__main__":
    # Example usage
    runs_dir = os.path.join(os.path.dirname(__file__), "..", "..", "outputs", "runs")
    output_dir = os.path.join(os.path.dirname(__file__), "..", "..", "outputs", "latent_models")
    
    print("Collecting historical optimization data...")
    df = collect_historical_data(runs_dir)
    print(f"Found {len(df)} records from {df['_source_file'].nunique()} files")
    
    print("Preparing training data...")
    clean_df, param_cols = prepare_training_data(df)
    print(f"Prepared {len(clean_df)} clean records with {len(param_cols)} parameters")
    
    print("Saving training data...")
    data_path = save_training_data(clean_df, param_cols, output_dir)
    print(f"Saved to: {data_path}")
