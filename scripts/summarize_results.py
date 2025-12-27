import pandas as pd
import json

# Check refinement results
ref_df = pd.read_csv('outputs/batch_runs/refinement_20251225_211601_summary.csv')
print('TOP 5 REFINEMENT RESULTS:')
print(ref_df[['trial_id','chart','calmar_ratio','sharpe_ratio','total_return','total_trades','param_htf_tf','param_cooldown_bars']].head(5))

# Check WFO results
with open('outputs/batch_runs/wfo_validation_20251225_211828.json') as f:
    wfo = json.load(f)

print('\n\nWFO VALIDATION SUMMARY:')
for chart, results in wfo.items():
    if 'aggregate_stats' in results and results['aggregate_stats']:
        stats = results['aggregate_stats']
        print(f'\n{chart}:')
        if 'calmar_ratio' in stats:
            c = stats['calmar_ratio']
            print(f'  Calmar - Median: {c["median"]:.6f}, Mean: {c["mean"]:.6f}, Std: {c["std"]:.6f}')
        if 'sharpe_ratio' in stats:
            s = stats['sharpe_ratio']
            print(f'  Sharpe - Median: {s["median"]:.6f}, Mean: {s["mean"]:.6f}')
        print(f'  Windows: {len(results.get("windows", []))}')

