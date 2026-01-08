import os
import re
import json
import csv
import shutil
from typing import Dict, Any, List
from pathlib import Path

# Reuse your existing window keys (integer-only windows)
from config.strategy_params_v2 import WINDOW_KEYS


METRIC_KEYS = {
    'total_return','sharpe_ratio','sortino_ratio','calmar_ratio','max_drawdown',
    'total_trades','win_rate','profit_factor','expectancy','start_capital',
    'end_capital','avg_hold_hours','ulcer_index','omega_0','omega_fees',
    'chart','trial_id','method','trial_uid','uid','score','is_pareto',
    'stability_score','group_rank','fold_id','_source_file','bars_total',
    'bars_train','bars_embargo','bars_val','val_start','val_end',
    # meta columns added in optimizer outputs
    'symbol','timeframe',
    'long_trades','short_trades','long_win_rate','short_win_rate',
    'long_expectancy','short_expectancy',
}

# Factory defaults for parameters that might be missing in old results
# These values match src/strategy/bands_v2.py defaults
FACTORY_DEFAULTS = {
    'base_fast_len': 20,
    'base_slow_len': 50,
    'volatility_atr_short': 5,
    'volatility_atr_long': 100,
    'atr_len': 14,
    'rsi_len': 14,
    'adx_period': 14,
    'stoch_k': 14,
    'stoch_d': 3,
    'stoch_smooth': 3,
    'adx_threshold': 25,
    'adx_floor': 18,
    'adx_dead_threshold': 15,
    'rsi_oversold': 30,
    'atr_pct_cap': 0.015,
    'atr_pct_floor': 0.0006,
    'chandelier_atr_period': 22,
    'chandelier_atr_multiplier': 3.0,
    'dma_atr_len': 14,
    'momentum_len': 14,
    'momentum_lookback': 14,
    'slope_lookback': 2,
    'fast_min_len': 5,
    'fast_max_len': 30,
    'slow_min_len': 30,
    'slow_max_len': 100,
    'ranging_trigger_window': 3,
    'cooldown_bars': 10,
    'dead_bars': 0,
    'friday_cutoff_bars': 0,
    'dma_buffer_mult': 0.5,
    'trail_dma_buffer': 0.5,
    'init_atr_mult': 1.5,
    'catastrophic_stop_atr_mult': 2.0,
    'max_consec_losses': 4,
    'max_holding_period': 100,
    'max_equity_heat_pct': 1.0,
    'min_addon_distance_ATR': 1.0,
    'partial_pct': 0.5,
    'be_buffer': 0.2,
    'upper_outer_mult': 2.0,
    'lower_outer_mult': 2.0,
    'upper_inner_mult': 1.2,
    'lower_inner_mult': 1.2,
}


def load_records(path: str) -> List[Dict[str, Any]]:
    if path.lower().endswith('.json'):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('results', data if isinstance(data, list) else [])
    elif path.lower().endswith('.csv'):
        with open(path, 'r', encoding='utf-8', newline='') as f:
            return list(csv.DictReader(f))
    else:
        raise ValueError('Provide a .json or .csv exported from Query GUI')


def extract_params(row: Dict[str, Any]) -> Dict[str, Any]:
    """Extract parameter-like columns from a row.

    - Columns starting with param_ lose the prefix
    - Non-metric columns are also treated as potential parameters
    """
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if k.startswith('param_'):
            out[k[6:]] = v
        elif k not in METRIC_KEYS:
            out[k] = v
    return out


def build_ranges(rows: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    ranges: Dict[str, List[Any]] = {}
    for r in rows:
        params = extract_params(r)
        for k, v in params.items():
            if v in (None, ''):
                continue
            ranges.setdefault(k, [])
            if v not in ranges[k]:
                ranges[k].append(v)

    # Inject missing factory defaults for critical parameters
    injected_count = 0
    for k, default_val in FACTORY_DEFAULTS.items():
        if k not in ranges:
            ranges[k] = [default_val]
            injected_count += 1
    
    if injected_count > 0:
        print(f"ℹ️  Injected {injected_count} missing parameters using factory defaults.")

    # Coerce integer-only window keys to integers and sort unique
    for k in list(ranges):
        if k in WINDOW_KEYS:
            coerced: List[int] = []
            for v in ranges[k]:
                try:
                    coerced.append(int(round(float(v))))
                except Exception:
                    pass
            ranges[k] = sorted(set(coerced))
    return ranges


def format_ranges_text(ranges: Dict[str, List[Any]]) -> str:
    lines = ["TEST_RANGES: Dict[str, List[Union[int, float]]] = {"]
    for k in sorted(ranges.keys()):
        vals = ranges[k]
        fmt: List[str] = []
        for v in vals:
            if isinstance(v, int) or (isinstance(v, float) and float(v).is_integer()):
                fmt.append(str(int(v)))
            elif isinstance(v, float):
                fmt.append(f"{float(v):.6g}")
            else:
                fmt.append(f"\"{str(v)}\"")
        lines.append(f"    \"{k}\": [{', '.join(fmt)}],")
    lines.append("}")
    return "\n".join(lines)


def write_test_ranges(config_path: str, new_text: str) -> None:
    with open(config_path, 'r', encoding='utf-8') as f:
        txt = f.read()
    # Backup
    backup_path = f"{config_path}.backup"
    shutil.copy2(config_path, backup_path)

    pattern = r"TEST_RANGES:\s*Dict\[.*?\]\s*=\s*\{[\s\S]*?\}"
    updated = re.sub(pattern, new_text, txt, count=1)
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(updated)


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python scripts\\build_ranges_from_selection.py <exported.json|csv>")
        raise SystemExit(2)

    selection_path = sys.argv[1]
    records = load_records(selection_path)
    if not records:
        print("No records found in selection.")
        raise SystemExit(1)

    ranges = build_ranges(records)
    block_text = format_ranges_text(ranges)

    cfg = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'config', 'strategy_params_v2.py'))
    write_test_ranges(cfg, block_text)
    print(f"Updated TEST_RANGES with {len(ranges)} parameters from selection. Backup created: {cfg}.backup")
