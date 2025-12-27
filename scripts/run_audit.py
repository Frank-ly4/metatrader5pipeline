"""Ratio sanity audit script - prints BEFORE/AFTER comparison tables."""

import pandas as pd
import numpy as np
from src.io.data_loader import load_first_chart
from src.optimizer.search import _evaluate
from config.strategy_params import BASELINE_PARAMS


def run_audit():
    """Run ratio audit with BEFORE/AFTER comparison."""
    print("=== RATIO SANITY AUDIT ===\n")
    
    # Load representative chart
    price = load_first_chart()
    if price is None or len(price) < 100:
        print("ERROR: Insufficient price data for audit")
        return
    
    print(f"Using chart: {len(price)} bars\n")
    
    # BEFORE: shift OFF, no costs
    toggles_before = {
        'enable_decision_shift': False,
        'fee_bps_round_trip': 0.0,
        'slippage_bps': 0.0,
        'rng_seed': 42
    }
    
    # AFTER: shift ON, realistic costs
    toggles_after = {
        'enable_decision_shift': True,
        'fee_bps_round_trip': 10.0,
        'slippage_bps': 1.0,
        'rng_seed': 42
    }
    
    print("Running BEFORE (shift OFF, no costs)...")
    result_before = _evaluate(price, BASELINE_PARAMS, toggles_before)
    
    print("Running AFTER (shift ON, realistic costs)...")
    result_after = _evaluate(price, BASELINE_PARAMS, toggles_after)
    
    if result_before is None or result_after is None:
        print("ERROR: Failed to generate results")
        return
    
    # Print comparison table
    print("\n=== BEFORE vs AFTER COMPARISON ===")
    
    comparison_data = {
        'Metric': ['Sharpe', 'Win%', 'Profit Factor', 'Calmar', 'Ulcer Index', 'Avg Hold Hours'],
        'BEFORE': [
            f"{result_before.get('sharpe_ratio', 0):.3f}",
            f"{result_before.get('win_rate', 0):.1%}",
            f"{result_before.get('profit_factor', 0):.2f}",
            f"{result_before.get('calmar_ratio', 0):.3f}",
            f"{result_before.get('ulcer_index', 0):.2f}",
            f"{result_before.get('avg_hold_hours', 0):.1f}" if not pd.isna(result_before.get('avg_hold_hours')) else "null"
        ],
        'AFTER': [
            f"{result_after.get('sharpe_ratio', 0):.3f}",
            f"{result_after.get('win_rate', 0):.1%}",
            f"{result_after.get('profit_factor', 0):.2f}",
            f"{result_after.get('calmar_ratio', 0):.3f}",
            f"{result_after.get('ulcer_index', 0):.2f}",
            f"{result_after.get('avg_hold_hours', 0):.1f}" if not pd.isna(result_after.get('avg_hold_hours')) else "null"
        ]
    }
    
    comparison_df = pd.DataFrame(comparison_data)
    print(comparison_df.to_string(index=False))
    
    # Print suspect flags
    print(f"\n=== SUSPECT FLAGS ===")
    print(f"BEFORE - Suspect: {result_before.get('suspect', False)}, Reason: {result_before.get('suspect_reason', 'none')}")
    print(f"AFTER  - Suspect: {result_after.get('suspect', False)}, Reason: {result_after.get('suspect_reason', 'none')}")
    
    # Execution details
    print(f"\n=== EXECUTION DETAILS ===")
    print(f"BEFORE - Mode: {result_before.get('execution_mode', 'unknown')}, Fees: {result_before.get('fee_bps', 0):.1f}bps, Slippage: {result_before.get('slippage_bps', 0):.1f}bps")
    print(f"AFTER  - Mode: {result_after.get('execution_mode', 'unknown')}, Fees: {result_after.get('fee_bps', 0):.1f}bps, Slippage: {result_after.get('slippage_bps', 0):.1f}bps")
    
    # Fee sweep test
    print(f"\n=== FEE SWEEP (Shift ON) ===")
    
    fee_levels = [0, 10, 25]
    sweep_results = []
    
    for fee_bps in fee_levels:
        toggles_sweep = toggles_after.copy()
        toggles_sweep['fee_bps_round_trip'] = fee_bps
        
        result = _evaluate(price, BASELINE_PARAMS, toggles_sweep)
        if result is not None:
            sweep_results.append({
                'Fee (bps)': fee_bps,
                'Profit Factor': f"{result.get('profit_factor', 0):.3f}",
                'Sharpe': f"{result.get('sharpe_ratio', 0):.3f}"
            })
    
    if sweep_results:
        sweep_df = pd.DataFrame(sweep_results)
        print(sweep_df.to_string(index=False))
        
        # Check monotone degradation
        pf_values = [float(r['Profit Factor']) for r in sweep_results if r['Profit Factor'] != 'inf']
        if len(pf_values) >= 2:
            monotone_ok = True
            for i in range(1, len(pf_values)):
                if pf_values[i] > pf_values[i-1] * 1.01:  # 1% tolerance
                    monotone_ok = False
                    break
            print(f"\nMonotone degradation check: {'PASS' if monotone_ok else 'FAIL'}")
    
    print(f"\n=== AUDIT COMPLETE ===")


if __name__ == '__main__':
    run_audit()
