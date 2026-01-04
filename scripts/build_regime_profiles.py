#!/usr/bin/env python3
"""
Build regime specialist profiles from optimization run results.

Extracts parameter sets that excel in specific market regimes (trend/volatility buckets)
and creates deployment-ready profiles for MT5 EA runtime switching.
"""

import os
import json
import argparse
import glob
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict

# Import regime utilities from query_results
import sys
sys.path.insert(0, os.path.dirname(__file__))
from query_results import flatten_regime_stats, regime_score, filter_by_regime


def load_runs(run_paths: List[str]) -> pd.DataFrame:
    """Load and combine multiple run JSON files into a single DataFrame."""
    all_results = []
    
    for run_path in run_paths:
        if not os.path.exists(run_path):
            print(f"⚠️  Warning: {run_path} not found, skipping")
            continue
        
        try:
            with open(run_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            results = data.get('results', [])
            if not results:
                print(f"⚠️  Warning: {run_path} has no results, skipping")
                continue
            
            # Add source run metadata
            for result in results:
                result['_source_run'] = os.path.basename(run_path)
            
            all_results.extend(results)
            print(f"✅ Loaded {len(results)} trials from {os.path.basename(run_path)}")
        except Exception as e:
            print(f"❌ Error loading {run_path}: {e}")
            continue
    
    if not all_results:
        raise ValueError("No results loaded from any run files")
    
    df = pd.DataFrame(all_results)
    df = flatten_regime_stats(df)
    
    return df


def extract_param_dict(row: pd.Series, prefix: str = 'param_') -> Dict[str, Any]:
    """Extract parameter dictionary from a trial row, removing prefix."""
    params = {}
    for col in row.index:
        if col.startswith(prefix):
            param_name = col[len(prefix):]
            params[param_name] = row[col]
    return params


def compute_median_params(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute median parameter values across candidate trials (robust to outliers)."""
    if not candidates:
        return {}
    
    # Collect all param keys
    all_param_keys = set()
    for cand in candidates:
        all_param_keys.update(cand.get('params', {}).keys())
    
    median_params = {}
    
    for key in sorted(all_param_keys):
        values = []
        for cand in candidates:
            params = cand.get('params', {})
            if key in params:
                val = params[key]
                # Skip None/NaN
                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                    values.append(val)
        
        if values:
            # Use median for numeric, mode for categorical
            if all(isinstance(v, (int, float)) for v in values):
                median_params[key] = float(np.median(values))
            else:
                # Mode for non-numeric (e.g., session_start/end strings)
                from collections import Counter
                mode_val = Counter(values).most_common(1)[0][0]
                median_params[key] = mode_val
    
    return median_params


def build_regime_profiles(
    df: pd.DataFrame,
    top_k: int = 5,
    dd_max: float = 0.045,
    min_regime_trades: int = 20,
    use_median: bool = True
) -> Dict[str, Any]:
    """
    Build specialist profiles per regime bucket.
    
    Returns:
        Dictionary with structure:
        {
            "meta": {...},
            "profiles": {
                "trend_strong": {
                    "chosen": {...params...},
                    "candidates": [...],
                    "meta": {...}
                },
                ...
            }
        }
    """
    profiles = {}
    
    # Define regime buckets to extract
    regime_buckets = [
        ('trend', 'weak'),
        ('trend', 'moderate'),
        ('trend', 'strong'),
        ('trend', 'extreme'),
        ('vol', 'low'),
        ('vol', 'medlow'),
        ('vol', 'medhigh'),
        ('vol', 'high'),
    ]
    
    for dim, bucket in regime_buckets:
        regime_key = f"{dim}_{bucket}"
        regime_str = f"{dim}:{bucket}"
        
        try:
            # Filter by regime
            filtered_df = filter_by_regime(df, regime_str, min_regime_trades, dd_max)
            
            if filtered_df.empty:
                print(f"⚠️  No candidates for {regime_key}")
                continue
            
            # Sort by regime_score
            filtered_df = filtered_df.sort_values(by='regime_score', ascending=False)
            
            # Extract top K candidates
            top_candidates = filtered_df.head(top_k)
            
            # Build candidate list with metadata
            candidates = []
            for idx, row in top_candidates.iterrows():
                params = extract_param_dict(row)
                candidate = {
                    'trial_id': row.get('trial_id', 'unknown'),
                    'trial_uid': row.get('trial_uid', 'unknown'),
                    'chart': row.get('chart', 'unknown'),
                    'params': params,
                    'regime_score': float(row['regime_score']),
                    'regime_trades': int(row[f'{dim}_{bucket}_trades']),
                    'regime_avg_return': float(row[f'{dim}_{bucket}_avg_return']),
                    'total_return': float(row.get('total_return', 0)),
                    'sharpe_ratio': float(row.get('sharpe_ratio', 0)),
                    'max_drawdown': float(row.get('max_drawdown', 0)),
                    'source_run': row.get('_source_run', 'unknown'),
                }
                candidates.append(candidate)
            
            # Choose "chosen" profile
            if use_median:
                chosen_params = compute_median_params(candidates)
            else:
                # Use best single trial
                best_candidate = candidates[0]
                chosen_params = best_candidate['params']
            
            # Build profile entry
            profiles[regime_key] = {
                'chosen': chosen_params,
                'candidates': candidates,
                'meta': {
                    'regime': regime_str,
                    'num_candidates': len(candidates),
                    'best_score': candidates[0]['regime_score'] if candidates else None,
                    'best_trial_id': candidates[0]['trial_id'] if candidates else None,
                    'median_trades': float(np.median([c['regime_trades'] for c in candidates])) if candidates else None,
                    'median_avg_return': float(np.median([c['regime_avg_return'] for c in candidates])) if candidates else None,
                }
            }
            
            print(f"✅ {regime_key}: {len(candidates)} candidates, best score={candidates[0]['regime_score']:.3f}")
            
        except Exception as e:
            print(f"❌ Error processing {regime_key}: {e}")
            continue
    
    return profiles


def export_mt5_set_file(profile_name: str, params: Dict[str, Any], output_dir: str):
    """Export MT5 .set file for a profile."""
    os.makedirs(output_dir, exist_ok=True)
    
    set_filename = f"{profile_name}.set"
    set_path = os.path.join(output_dir, set_filename)
    
    # MT5 .set file format: key=value pairs, one per line
    with open(set_path, 'w', encoding='utf-8') as f:
        f.write(f"; MT5 Expert Advisor Settings for {profile_name}\n")
        f.write(f"; Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(";\n")
        
        # Write parameters (MT5 expects param_ prefix in input names)
        for key, value in sorted(params.items()):
            if value is None:
                continue
            
            # Format value appropriately
            if isinstance(value, bool):
                val_str = 'true' if value else 'false'
            elif isinstance(value, float):
                val_str = f"{value:.10f}".rstrip('0').rstrip('.')
            else:
                val_str = str(value)
            
            f.write(f"param_{key}={val_str}\n")
    
    return set_path


def main():
    parser = argparse.ArgumentParser(
        description='Build regime specialist profiles from optimization runs',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--runs',
        type=str,
        nargs='+',
        required=True,
        help='Run JSON file(s) or glob pattern (e.g., "outputs/runs/*.json")'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='config/regime_profiles.json',
        help='Output path for regime_profiles.json (default: config/regime_profiles.json)'
    )
    parser.add_argument(
        '--top-k',
        type=int,
        default=5,
        help='Number of top candidates per regime (default: 5)'
    )
    parser.add_argument(
        '--dd-max',
        type=float,
        default=0.045,
        help='Maximum drawdown threshold (default: 0.045)'
    )
    parser.add_argument(
        '--min-regime-trades',
        type=int,
        default=20,
        help='Minimum trades in regime (default: 20)'
    )
    parser.add_argument(
        '--use-best',
        action='store_true',
        help='Use best single trial instead of median (default: use median)'
    )
    parser.add_argument(
        '--export-sets',
        action='store_true',
        help='Export MT5 .set files to mt5/sets/'
    )
    
    args = parser.parse_args()
    
    # Expand glob patterns
    run_paths = []
    for pattern in args.runs:
        if '*' in pattern or '?' in pattern:
            run_paths.extend(glob.glob(pattern))
        else:
            run_paths.append(pattern)
    
    if not run_paths:
        print("❌ No run files found")
        return 1
    
    print(f"📁 Processing {len(run_paths)} run file(s)...")
    
    # Load runs
    try:
        df = load_runs(run_paths)
        print(f"\n✅ Loaded {len(df)} total trials")
    except Exception as e:
        print(f"❌ Error loading runs: {e}")
        return 1
    
    # Build profiles
    print(f"\n🔍 Building regime profiles (top_k={args.top_k}, dd_max={args.dd_max}, min_trades={args.min_regime_trades})...")
    profiles_dict = build_regime_profiles(
        df,
        top_k=args.top_k,
        dd_max=args.dd_max,
        min_regime_trades=args.min_regime_trades,
        use_median=not args.use_best
    )
    
    if not profiles_dict:
        print("❌ No profiles generated")
        return 1
    
    # Build final output structure
    output_data = {
        'meta': {
            'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_runs': [os.path.basename(p) for p in run_paths],
            'total_trials': len(df),
            'dd_max_constraint': args.dd_max,
            'min_regime_trades': args.min_regime_trades,
            'top_k': args.top_k,
            'selection_method': 'best_single' if args.use_best else 'median',
        },
        'profiles': profiles_dict
    }
    
    # Write JSON
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Written: {args.output}")
    print(f"   Generated {len(profiles_dict)} regime profiles")
    
    # Export MT5 .set files if requested
    if args.export_sets:
        sets_dir = os.path.join(os.path.dirname(__file__), '..', 'mt5', 'sets')
        exported = []
        
        for regime_key, profile_data in profiles_dict.items():
            chosen_params = profile_data['chosen']
            set_path = export_mt5_set_file(regime_key, chosen_params, sets_dir)
            exported.append(set_path)
        
        print(f"\n✅ Exported {len(exported)} MT5 .set files to {sets_dir}")
        for path in exported:
            print(f"   - {os.path.basename(path)}")
    
    return 0


if __name__ == '__main__':
    exit(main())

