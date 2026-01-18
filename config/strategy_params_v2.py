"""
Strategy parameter surface for baseline runs and optimizer search.

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
    # Intraday USDJPY baseline (M30 profile)
    # Intent: slower, more selective regime detection + wider risk structure for 30m bars

    # Regime filters
    "param_adx_dead_threshold": 18,
    "param_adx_floor": 15,
    "param_adx_period": 10,
    "param_adx_threshold": 26,

    # Volatility model
    "param_atr_len": 28,
    "param_atr_pct_cap": 0.015,        # keep but not optimized initially
    "param_atr_pct_floor": 0.0006,

    # Trend frame
    "param_base_fast_len": 18,
    "param_base_slow_len": 100,

    # Trade management / risk controls
    "param_be_buffer": 0.20,           # not optimized initially
    "param_cooldown_bars": 9,
    "param_dead_bars": 4,
    "param_friday_cutoff_bars": 12,

    "param_init_atr_mult": 2.0,
    "param_catastrophic_stop_atr_mult": 4.0,

    "param_chandelier_atr_multiplier": 2.1,
    "param_chandelier_atr_period": 18,

    # DMA trail context
    "param_dma_buffer_mult": 1.1,
    "param_trail_dma_buffer": 0.90,

    # Bands (outer optimized; inner mostly fixed)
    "param_lower_inner_mult": 1.05,
    "param_lower_outer_mult": 2.20,
    "param_upper_inner_mult": 1.10,
    "param_upper_outer_mult": 2.60,

    "param_ranging_trigger_window": 4,

    "param_max_consec_losses": 4,
    "param_max_equity_heat_pct": 0.8,
    "param_max_holding_period": 336,   # ~7 days on M30 (336 bars = 7 days)

    "param_min_addon_distance_ATR": 2.0,
    "param_partial_pct": 0.25,

    # Oscillators (de-emphasized)
    "param_rsi_len": 14,
    "param_rsi_oversold": 32,
    "param_slope_len": 10,
    "param_stoch_d": 3,
    "param_stoch_k": 12,
    "param_stoch_smooth": 2,

    "param_volatility_atr_long": 100,
    "param_volatility_atr_short": 11,
}


# ---------------------------
# Test ranges (optimizer search space)
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
            cleaned = sorted(set(cleaned_nums))
            if not cleaned:
                raise ValueError(f"{k} has no valid values after sanitization")
            out[k] = cleaned

    return out


TEST_RANGES: Dict[str, List[Union[int, float]]] = {
    # USDJPY M30 — profile search space (aligned to your current 30m trials)

    # Trend frame (slower)
    "base_fast_len":        [10, 12, 14, 16, 18, 20, 22, 24],
    "base_slow_len":        [70, 85, 100, 115, 130],

    # Volatility model (longer)
    "atr_len":              [10, 14, 18, 24, 28],
    "volatility_atr_short": [5, 7, 9, 11, 13],
    "volatility_atr_long":  [70, 80, 90, 100, 110],

    # Stops & trails
    "init_atr_mult":                [1.4, 1.6, 1.8, 2.0, 2.2],
    "catastrophic_stop_atr_mult":   [2.6, 3.0, 3.3, 3.6, 4.0],
    "chandelier_atr_multiplier":    [2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6],
    "chandelier_atr_period":        [18],               # fixed

    "dma_atr_len":          [14],                       # keep stable unless you explicitly want to expand
    "dma_buffer_mult":      [0.8, 0.9, 1.0, 1.1, 1.2],
    "trail_dma_buffer":     [0.75, 0.80, 0.85, 0.90],

    # Band widths (outer varies; inner mostly fixed)
    "upper_outer_mult":     [2.0, 2.3, 2.6, 2.9, 3.0],
    "lower_outer_mult":     [1.9, 2.2, 2.5, 2.8, 3.1],
    "upper_inner_mult":     [1.10],
    "lower_inner_mult":     [1.05, 1.10],

    # Regime filters
    "adx_period":           [8, 10, 14],
    "adx_threshold":        [18, 22, 26],
    "adx_dead_threshold":   [12, 15, 18],
    "adx_floor":            [15],                       # fixed

    # Trade management (30m-scale)
    "cooldown_bars":        [5, 9, 13],
    "dead_bars":            [2, 4, 6],
    "ranging_trigger_window":[2, 4],

    "max_equity_heat_pct":  [0.6, 0.8, 1.0, 1.2],
    "max_consec_losses":    [3, 4, 5],
    "max_holding_period":   [192, 336, 480],            # ~4, 7, 10 days on M30

    # Partial & addons
    "partial_pct":          [0.25, 0.33, 0.50],
    "min_addon_distance_ATR":[1.6, 2.0, 2.4],

    # Sessions (server time; align to broker)
    "session_start":        ["07:00", "08:00", "09:00"],
    "session_end":          ["20:00", "21:00", "22:00"],

    # Friday hygiene (more conservative on 30m)
    "friday_cutoff_bars":   [6, 9, 12],

    # Oscillators (fixed/narrow)
    "rsi_len":              [14],
    "rsi_oversold":         [32],
    "slope_len":            [10],
    "stoch_k":              [12],
    "stoch_d":              [3],
    "stoch_smooth":         [2],

    # Keep for schema compatibility (not optimized now)
    "fast_min_len":         [5],
    "fast_max_len":         [30],
    "slow_min_len":         [30],
    "slow_max_len":         [100],
    "momentum_len":         [14],
    "momentum_lookback":    [14],
    "slope_lookback":       [2],

    # Retain but not emphasized
    "atr_pct_cap":          [0.015],
    "atr_pct_floor":        [0.0006],
    "be_buffer":            [0.20],
}

TEST_RANGES = sanitize_test_ranges(TEST_RANGES)


# ---------------------------
# Feature flags (defaults preserve legacy behavior)
# ---------------------------

FEATURE_FLAGS_V2: Dict[str, bool] = {
    # Core state machine and hierarchical exits
    "feature_state_machine": True,
    "feature_hierarchical_exits": True,

    # Filters
    "feature_volatility_filter": True,
    "feature_session_filter": True,
    "feature_htf_confirm": False,

    # Risk & execution controls
    "feature_cooldowns": True,
    "feature_equity_heat_guard": True,
    "feature_pyramiding_addon_distance": True,

    # Technical correctness improvements
    "feature_no_bfill_dynamic_len": True,
    "feature_exit_before_entry": True,
    "feature_block_reentry_same_bar": True,
}


if __name__ == "__main__":
    int_keys = ("base_fast_len", "base_slow_len", "volatility_atr_short", "volatility_atr_long",
                "max_holding_period", "adx_period", "chandelier_atr_period", "stoch_k",
                "atr_len", "rsi_len")
    for k in int_keys:
        seq = TEST_RANGES[k]
        assert all(isinstance(x, (int, float)) for x in seq), f"{k} must be numeric"

    example = {
        "volatility_atr_short": 6.9,   # will become 7
        "upper_outer_mult": 2.5,       # stays float
        "rsi_len": 13.2,               # -> 13
    }
    casted = validate_and_cast_params(example)
    print("Casted example:", casted)
