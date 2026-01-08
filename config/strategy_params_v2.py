"""Strategy parameter surface for baseline runs and optimizer search.

This module is the single place for users to:
- Inspect and modify the default parameters used by `scripts/run_backtest.py`
- Control the ranges sampled by the optimizer
- Import small helpers to safely coerce window-like parameters to valid ints
"""

from __future__ import annotations
from decimal import Decimal
from typing import Dict, List, Union, Iterable

Number = Union[int, float]


# ---------------------------
# Helpers (safe stepping & casts)
# ---------------------------

def stepped(start: Number, stop: Number, step: Number, *, inclusive: bool = True, ndigits: int | None = None) -> List[float]:
    """Build a stepwise sequence (works for ints/floats/Decimals) without np.arange quirks.
    - inclusive=True includes the stop if it lands on the grid.
    - ndigits rounds floats to avoid artifacts like 1.2000000000002.
    Returns floats for compatibility with JSON serialization.
    """
    # Use Decimal if any arg is a str/Decimal to improve precision
    if any(isinstance(x, (str, Decimal)) for x in (start, stop, step)):
        a, b, s = Decimal(str(start)), Decimal(str(stop)), Decimal(str(step))
        vals: List[Decimal] = []
        x = a
        cmp = (lambda u, v: u <= v) if inclusive else (lambda u, v: u < v)
        while cmp(x, b):
            vals.append(x)
            x += s
        return [float(round(v, ndigits) if ndigits is not None else v) for v in vals]

    # Fallback to float loop
    a, b, s = float(start), float(stop), float(step)
    out: List[float] = []
    x = a
    cmp = (lambda u, v: u <= v) if inclusive else (lambda u, v: u < v)
    # guard against accidental infinite loops
    for _ in range(10_000_000):
        if not cmp(x, b):
            break
        out.append(round(x, ndigits) if ndigits is not None else x)
        x = x + s
    return out


def as_pos_int(x: Number, default: int = 14) -> int:
    """Coerce any numeric to a positive integer >= 1 (rounding)."""
    try:
        v = int(round(float(x)))
        return v if v >= 1 else 1
    except Exception:
        return default


# Keys that should always be coerced to positive integers when consumed
WINDOW_KEYS: Iterable[str] = (
    "base_fast_len",
    "base_slow_len",
    "volatility_atr_short",
    "volatility_atr_long",
    "max_holding_period",
    "adx_period",
    "chandelier_atr_period",
    "ranging_trigger_window",
    "stoch_k",
    "stoch_d",          # you may keep this float if your indicator expects float; we cast ranges but you can skip cast.
    "stoch_smooth",     # same note as above
    "fast_min_len",
    "fast_max_len",
    "slow_min_len",
    "slow_max_len",
    "dma_atr_len",
    "atr_len",
    "momentum_len",
    "momentum_lookback",
    "slope_lookback",
    "rsi_len",
)


def validate_and_cast_params(params: Dict[str, Union[int, float, bool]]) -> Dict[str, Union[int, float, bool]]:
    """Central place to coerce window-like params to pos-int; leave multipliers/thresholds as float."""
    fixed: Dict[str, Union[int, float, bool]] = {}
    for k, v in params.items():
        if k in WINDOW_KEYS:
            fixed[k] = as_pos_int(v)
        else:
            # keep multipliers/thresholds as floats if numeric, otherwise pass through
            try:
                fixed[k] = float(v) if isinstance(v, (int, float)) else v
            except Exception:
                fixed[k] = v
    return fixed


# ---------------------------
# Default parameters (single backtest defaults)
# These are scalar values used when running a single backtest.
# The Query GUI "Set as Optimizer Baseline" writes here.
# ---------------------------

DEFAULT_PARAMS: Dict[str, Union[float, int, bool]] = {
    # Generated from query interface on 2025-10-19 21:53:31
    # Source: trial_lhs_400_20251008_124610.json
    # Chart: XAUUSD_1h_cl_2.csv, Fold: 3
    # Performance: Calmar=0.0356, Sharpe=2.1645, MDD=3.88%
    "param_adx_dead_threshold": 21,
    "param_adx_floor": 20,
    "param_adx_period": 16,
    "param_adx_threshold": 22,
    "param_atr_len": 15,
    "param_atr_pct_cap": 0.02491941149165275,
    "param_atr_pct_floor": 0.0013680886747604653,
    "param_base_fast_len": 16,
    "param_base_slow_len": 55,
    "param_be_buffer": 0.30315276136647706,
    "param_catastrophic_stop_atr_mult": 0.8135858567804528,
    "param_chandelier_atr_multiplier": 2.841304959753314,
    "param_chandelier_atr_period": 30,
    "param_cooldown_bars": 32,
    "param_dead_bars": 9,
    "param_dma_buffer_mult": 0.6171125775171253,
    "param_friday_cutoff_bars": 3,
    "param_init_atr_mult": 1.3794028352927687,
    "param_lower_inner_mult": 0.8932655661698212,
    "param_lower_outer_mult": 1.7348466651076797,
    "param_max_consec_losses": 6,
    "param_max_equity_heat_pct": 2.9178924054437383,
    "param_max_holding_period": 247,
    "param_min_addon_distance_ATR": 0.7929832861941277,
    "param_partial_pct": 0.31956368067189206,
    "param_ranging_trigger_window": 2,
    "param_rsi_len": 16,
    "param_rsi_oversold": 32,
    "param_slope_len": 30,
    "param_stoch_d": 4.768578518235412,
    "param_stoch_k": 10,
    "param_stoch_smooth": 1.5180693764750435,
    "param_trail_dma_buffer": 0.7328741509129967,
    "param_upper_inner_mult": 0.8793539882760292,
    "param_upper_outer_mult": 1.8969918081543056,
    "param_volatility_atr_long": 80,
    "param_volatility_atr_short": 5,
}


# ---------------------------
# Test ranges (optimizer search space)
# These are CATEGORICAL lists of candidate values to sweep during optimization.
#
# IMPORTANT:
# - A Python list here MUST be treated as "try each value", never as [start, stop, step].
# - If you want stepped ranges, generate them explicitly (e.g., stepped(...)) and store the
#   resulting expanded list here, or use an explicit schema elsewhere.
# ---------------------------

from typing import Dict, List, Union, Iterable
import math
import re

Number = Union[int, float]
ParamValue = Union[int, float, str]

# Keys that should always be treated as positive integer "window-like" parameters
WINDOW_KEYS: Iterable[str] = (
    "base_fast_len",
    "base_slow_len",
    "volatility_atr_short",
    "volatility_atr_long",
    "max_holding_period",
    "adx_period",
    "chandelier_atr_period",
    "ranging_trigger_window",
    "stoch_k",
    "stoch_d",
    "stoch_smooth",
    "fast_min_len",
    "fast_max_len",
    "slow_min_len",
    "slow_max_len",
    "dma_atr_len",
    "atr_len",
    "momentum_len",
    "momentum_lookback",
    "slope_len",
    "slope_lookback",
    "rsi_len",
)

_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _as_pos_int(x: Number) -> int:
    v = int(round(float(x)))
    return v if v >= 1 else 1


def sanitize_test_ranges(ranges: Dict[str, List[ParamValue]]) -> Dict[str, List[ParamValue]]:
    """
    Sanitize TEST_RANGES to prevent silent null/degenerate runs:
    - WINDOW_KEYS: coerce to int >= 1, drop non-finite, dedupe, sort
    - numeric keys: drop non-finite, dedupe, sort
    - session_* keys: validate HH:MM strings, dedupe, sort
    Fails fast if any key becomes empty.
    """
    out: Dict[str, List[ParamValue]] = {}

    for k, vals in ranges.items():
        if not isinstance(vals, list):
            raise TypeError(f"TEST_RANGES[{k}] must be a list, got {type(vals)}")

        # Session time keys (strings)
        if k in ("session_start", "session_end"):
            cleaned: List[str] = []
            for v in vals:
                if not isinstance(v, str):
                    raise TypeError(f"{k} must contain strings like 'HH:MM', got {type(v)}: {v}")
                if not _TIME_RE.match(v.strip()):
                    raise ValueError(f"{k} invalid time format: {v} (expected 'HH:MM')")
                cleaned.append(v.strip())
            cleaned = sorted(set(cleaned))
            if not cleaned:
                raise ValueError(f"{k} has no valid values after sanitization")
            out[k] = cleaned
            continue

        # Numeric-ish keys
        cleaned_nums: List[Number] = []
        for v in vals:
            if isinstance(v, (int, float)):
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    continue
                cleaned_nums.append(v)
            else:
                raise TypeError(f"{k} must contain only numbers (int/float). Got {type(v)}: {v}")

        # Window coercion
        if k in WINDOW_KEYS:
            coerced = [_as_pos_int(x) for x in cleaned_nums]
            coerced = sorted(set(coerced))
            if not coerced:
                raise ValueError(f"{k} has no valid values after sanitization")
            out[k] = coerced
        else:
            # General numeric: keep floats/ints, dedupe, sort
            # (Sorting mixes int/float fine in Python)
            cleaned = sorted(set(cleaned_nums))
            if not cleaned:
                raise ValueError(f"{k} has no valid values after sanitization")
            out[k] = cleaned

    return out


TEST_RANGES: Dict[str, List[Union[int, float]]] = {
    # Generated via Query GUI on 2026-01-08 16:42:08 from 4 selected row(s)
    "adx_dead_threshold": [19, 17, 3, 22],
    "adx_floor": [11, 15, 16, 17],
    "adx_period": [1, 2, 4, 15],
    "adx_threshold": [30, 4, 24, 5],
    "atr_len": [1, 10, 15, 16],
    "atr_pct_cap": [0.0149638, 0.0145374, 0.0160041, 0.0135641],
    "atr_pct_floor": [0.000523204, 0.000631698, 0.000947539, 0.000503016],
    "base_fast_len": [14, 18, 25, 28],
    "base_slow_len": [61, 79, 81],
    "be_buffer": [0.19626, 0.149556, 0.1, 0.487344],
    "catastrophic_stop_atr_mult": [3.12882, 3.22586, 2.66998, 3.15391],
    "chandelier_atr_multiplier": [3.32011, 2.8, 2.67366, 2.93248],
    "chandelier_atr_period": [16, 22],
    "cooldown_bars": [1, 13, 15, 14],
    "dead_bars": [3, 6, 11],
    "dma_atr_len": [14],
    "dma_buffer_mult": [1.39245, 1.02553, 1.22717, 0.812327],
    "fast_max_len": [30],
    "fast_min_len": [5],
    "friday_cutoff_bars": [4, 9],
    "init_atr_mult": [1.53696, 1.5757, 2, 1.99184],
    "lower_inner_mult": [1.32242, 1.3947, 1.27838, 1.45306],
    "lower_outer_mult": [2.38347, 2.98387, 2.31794],
    "max_consec_losses": [3, 5, 4],
    "max_equity_heat_pct": [1.27803, 1.04811, 3, 1],
    "max_holding_period": [143, 155, 246, 301],
    "min_addon_distance_ATR": [1.67578, 1.15997, 1.95849, 1.33762],
    "momentum_len": [14],
    "momentum_lookback": [14],
    "partial_pct": [0.57, 0.303622, 0.486804, 0.30134],
    "ranging_trigger_window": [3, 4, 5],
    "rsi_len": [2, 11, 17, 19],
    "rsi_oversold": [34, 30, 21],
    "session_end": ["20:00", "22:00"],
    "session_start": ["08:00"],
    "slope_len": [7, 10, 19],
    "slope_lookback": [2],
    "slow_max_len": [100],
    "slow_min_len": [30],
    "stoch_d": [4, 5, 6],
    "stoch_k": [1, 4, 15, 17],
    "stoch_smooth": [2, 3],
    "trail_dma_buffer": [0.642969, 0.704058, 0.914303],
    "upper_inner_mult": [1.46974, 1.08551, 1.48069, 1.15],
    "upper_outer_mult": [2.44159, 2.23, 2.65777, 2.83098],
    "volatility_atr_long": [46, 67, 153],
    "volatility_atr_short": [5, 10, 11],
}

# Optional: sanitize at import time (recommended), or call right before optimization.
TEST_RANGES = sanitize_test_ranges(TEST_RANGES)



# ---------------------------
# Feature flags (defaults preserve legacy behavior)
# ---------------------------

# Note: We keep all advanced features disabled by default to ensure the
# "v2 legacy" behavior is unchanged unless explicitly enabled by the user.
# Users can toggle these flags via the `toggles` argument passed to
# `compute_signals(...)`.

FEATURE_FLAGS_V2: Dict[str, bool] = {
    # Core state machine and hierarchical exits
    "feature_state_machine": True,
    "feature_hierarchical_exits": True,

    # Filters
    "feature_volatility_filter": True,
    "feature_session_filter": False,  # default False per spec
    "feature_htf_confirm": False,     # default False per spec

    # Risk & execution controls
    "feature_cooldowns": True,
    "feature_equity_heat_guard": True,
    "feature_pyramiding_addon_distance": True,

    # Technical correctness improvements
    "feature_no_bfill_dynamic_len": True,  # remove bfill on dynamic lengths
    "feature_exit_before_entry": True,
    "feature_block_reentry_same_bar": True,
}


# ---------------------------
# Optional: quick sanity self-test (can be removed)
# ---------------------------

if __name__ == "__main__":
    # Ensure integer-only windows are indeed ints in the ranges
    int_keys = ("base_fast_len", "base_slow_len", "volatility_atr_short", "volatility_atr_long",
                "max_holding_period", "adx_period", "chandelier_atr_period", "stoch_k",
                "atr_len", "rsi_len")
    for k in int_keys:
        seq = TEST_RANGES[k]
        assert all(isinstance(x, (int, float)) for x in seq), f"{k} must be numeric"

    # Example: demonstrate helper usage
    example = {
        "volatility_atr_short": 6.9,   # will become 7
        "upper_outer_mult": 2.5,       # stays float
        "rsi_len": 13.2,               # -> 13
    }
    casted = validate_and_cast_params(example)
    print("Casted example:", casted)
