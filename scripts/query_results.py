import os
import json
import pandas as pd
from typing import Dict, List, Optional

def find_runs() -> List[Dict]:
    """Find and parse metadata from all JSON run files."""
    runs_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'runs')
    if not os.path.exists(runs_dir):
        return []
    
    runs = []
    for filename in sorted(os.listdir(runs_dir), reverse=True):
        if filename.lower().endswith('.json'):
            try:
                filepath = os.path.join(runs_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    # Only load metadata to be fast
                    data = json.load(f)
                    metadata = data.get('metadata', {})
                
                runs.append({
                    'filename': filename,
                    'filepath': filepath,
                    'run_id': metadata.get('run_id', 'N/A'),
                    'method': metadata.get('method', 'N/A'),
                    'timestamp': metadata.get('timestamp', 'N/A'),
                    'num_results': len(data.get('results', [])),
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return runs

def select_run(runs: List[Dict]) -> Optional[Dict]:
    """Display a list of runs and prompt the user to select one."""
    if not runs:
        print("❌ No optimization runs found in outputs/runs/")
        return None
    
    print("📁 AVAILABLE OPTIMIZATION RUNS (most recent first)")
    print("=" * 80)
    for i, run in enumerate(runs[:15], 1): # Show 15 most recent
        print(f"{i:2d}. {run['timestamp']} | {run['run_id']} | {run['method'].upper():<7} | {run['num_results']} results")
    print("=" * 80)

    while True:
        try:
            choice = input(f"Select a run to analyze (1-{min(15, len(runs))}) or 'q' to quit: ").strip()
            if choice.lower() == 'q':
                return None
            idx = int(choice) - 1
            if 0 <= idx < min(15, len(runs)):
                return runs[idx]
            else:
                print("Invalid selection.")
        except ValueError:
            print("Please enter a valid number.")

def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Interactively apply filters to the results DataFrame."""
    filtered_df = df.copy()
    
    while True:
        print("\n🔎 APPLY FILTERS (e.g., 'sharpe_ratio > 1.5', 'total_trades >= 10')")
        print("   Enter a filter expression, or type 'done' to finish, 'reset' to clear filters.")
        
        filter_str = input("Filter: ").strip()
        
        if filter_str.lower() == 'done':
            break
        if filter_str.lower() == 'reset':
            filtered_df = df.copy()
            print("Filters reset.")
            continue
        
        try:
            # Use pandas.eval for safe evaluation of the query
            filtered_df = filtered_df.eval(filter_str, engine='python')
            print(f"✅ Filter applied. {len(filtered_df)} rows remaining.")
        except Exception as e:
            print(f"❌ Invalid filter expression: {e}")
            print("   Example: 'sharpe_ratio > 1.5 and total_trades > 20'")
            print(f"   Available columns: {list(df.columns)}")
            
    return filtered_df

def main():
    """Main interactive query tool."""
    while True:
        runs = find_runs()
        selected_run = select_run(runs)
        
        if not selected_run:
            break
            
        print(f"\nLoading run: {selected_run['filename']}...")
        with open(selected_run['filepath'], 'r', encoding='utf-8') as f:
            full_data = json.load(f)
        
        results_df = pd.DataFrame(full_data.get('results', []))
        if results_df.empty:
            print("This run contains no results.")
            continue
            
        # Apply filters
        filtered_df = apply_filters(results_df)
        
        if filtered_df.empty:
            print("No results match the current filters.")
            continue
            
        # Get sorting and display preferences
        print("\n📊 SORT & DISPLAY")
        sort_metric = input(f"Sort by which metric? [sharpe_ratio]: ").strip() or 'sharpe_ratio'
        if sort_metric not in filtered_df.columns:
            print(f"Metric '{sort_metric}' not found. Defaulting to 'sharpe_ratio'.")
            sort_metric = 'sharpe_ratio'
            
        top_n_str = input("How many top results to display? [10]: ").strip() or '10'
        top_n = int(top_n_str)
        
        # Sort and display results
        sorted_df = filtered_df.sort_values(by=sort_metric, ascending=False).head(top_n)
        
        print(f"\n🏆 TOP {len(sorted_df)} RESULTS (sorted by {sort_metric})")
        
        display_cols = ['trial_uid', 'chart', 'total_return', 'sharpe_ratio', 'sortino_ratio', 'calmar_ratio', 'max_drawdown', 'total_trades', 'win_rate']
        available_cols = [col for col in display_cols if col in sorted_df.columns]
        
        # Pretty print with formatting
        formatted_df = sorted_df[available_cols].copy()
        for col in ['total_return', 'max_drawdown', 'win_rate']:
            if col in formatted_df.columns:
                formatted_df[col] = formatted_df[col].map('{:.2f}%'.format)
        for col in ['sharpe_ratio', 'sortino_ratio', 'calmar_ratio']:
            if col in formatted_df.columns:
                formatted_df[col] = formatted_df[col].map('{:.3f}'.format)
        
        print(formatted_df.to_string())

        another_run = input("\nAnalyze another run? (y/n) [y]: ").strip().lower()
        if another_run == 'n':
            break

if __name__ == '__main__':
    main()


