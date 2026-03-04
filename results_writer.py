import os
import json
import pandas as pd
import numpy as np
from datetime import datetime

def _convert_to_json_serializable(obj):
    """Helper to convert numpy/pandas types to native Python types for JSON."""
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)

def save_results(
    results_df: pd.DataFrame,
    run_id: str,
    settings: dict,
    output_formats: list[str],
    base_output_dir: str = 'outputs'
):
    """
    Saves optimization results in requested formats (CSV, JSON, Excel).
    """
    if results_df.empty:
        print("No results to save.")
        return

    # Ensure base directories exist
    os.makedirs(base_output_dir, exist_ok=True)

    # 1. CSV Output
    if 'CSV' in output_formats:
        csv_dir = os.path.join(base_output_dir, 'csv')
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, f'run_{run_id}.csv')
        results_df.to_csv(csv_path, index=False)
        print(f"Saved CSV: {csv_path}")

    # 2. JSON Output
    if 'JSON' in output_formats:
        json_dir = os.path.join(base_output_dir, 'runs')
        os.makedirs(json_dir, exist_ok=True)
        json_path = os.path.join(json_dir, f'run_{run_id}.json')
        
        # Construct payload with metadata
        payload = {
            'run_id': run_id,
            'timestamp': datetime.utcnow().isoformat(),
            'settings': settings,
            'results': results_df.to_dict(orient='records')
        }
        
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, default=_convert_to_json_serializable)
            print(f"Saved JSON: {json_path}")
        except Exception as e:
            print(f"Failed to save JSON: {e}")

    # 3. Excel Output
    if 'Excel' in output_formats:
        excel_dir = os.path.join(base_output_dir, 'excel')
        os.makedirs(excel_dir, exist_ok=True)
        excel_path = os.path.join(excel_dir, f'run_{run_id}.xlsx')
        
        try:
            # Attempt to use openpyxl (standard for pandas)
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                results_df.to_excel(writer, sheet_name='Results', index=False)
                # Save settings as a separate sheet for reference
                settings_df = pd.DataFrame([settings])
                settings_df.to_excel(writer, sheet_name='Settings', index=False)
            print(f"Saved Excel: {excel_path}")
        except ImportError:
            print("Could not save Excel: 'openpyxl' library not found. Install with: pip install openpyxl")
        except Exception as e:
            print(f"Failed to save Excel: {e}")