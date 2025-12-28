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
# These are lists of values to sweep during optimization.
# To test a single value, use a list with one element: [value]
# To test a range, use a list: [val1, val2, val3, ...]
# Example: "atr_len": [14] → test only 14
# Example: "atr_len": [10, 12, 14, 16] → test all four
# ---------------------------

TEST_RANGES: Dict[str, List[Union[int, float]]] = {
    # Phase 1: Dynamic Bands (Capture Mean Reversion vs Momentum)
    "base_fast_len": stepped(12, 30, 2),        # Filtering noise in exotics (H1/H4)
    "base_slow_len": stepped(40, 100, 10),      # Robust trend baseline for SEK/THB
    "volatility_atr_short": stepped(5, 15, 5),  # Sensitive to local variance shifts
    "volatility_atr_long":  stepped(60, 180, 20), # Macro-regime normalization

    # Phase 2: Exit Logic (Protecting Convexity)
    "max_holding_period": [120, 240, 480],      # 1wk to 1mo (approx H1 bars) for swing traits
    "adx_period": stepped(10, 20, 2),           # Trend strength window
    "adx_threshold": stepped(20, 35, 5),        # Threshold for trend confirmation
    "chandelier_atr_period": stepped(14, 28, 2),
    "chandelier_atr_multiplier": [2.5, 3.0, 3.5],

    # Phase 3: Entry Logic (Statistical Extremes in Exotics)
    "ranging_trigger_window": [2, 3, 5],
    "stoch_k": stepped(10, 20, 2),
    "stoch_d": [3.0, 5.0, 7.0],
    "stoch_smooth": [1.5, 2.0, 3.0],

    # Original V1 Parameters (Tail Risk Management)
    "atr_len": stepped(10, 20, 2),
    "upper_outer_mult": [2.25, 2.5, 3.0],       # Accounting for fat tails in EM/Exotics
    "lower_outer_mult": [2.25, 2.5, 3.0],
    "upper_inner_mult": [1.0, 1.25, 1.5],
    "lower_inner_mult": [1.0, 1.25, 1.5],
    "rsi_len": stepped(10, 20, 2),
    "rsi_oversold": stepped(20, 40, 5),
    "catastrophic_stop_atr_mult": [2.5, 3.0, 4.0], # Wider EM stops for gap risk

    # Operational/Regime Parameters
    "slope_len": stepped(10, 30, 5),
    "adx_floor": stepped(10, 20, 5),
    "cooldown_bars": [0, 8, 24, 48],            # Prevent revenge trading on vol spikes
    "atr_pct_floor": [0.0005, 0.001],           # Ensure minimal liquidity/vol
    "atr_pct_cap": [0.01, 0.02],                # Cap entry during panic volatility
    "session_start": ["08:00"],
    "session_end": ["20:00"],                   # End of London/NY crossover
    "init_atr_mult": [1.5, 2.0],
    "dma_buffer_mult": [0.5, 1.0, 1.5],
    "partial_pct": [0.25, 0.5, 0.75],
    "be_buffer": [0.1, 0.25, 0.5],
    "trail_dma_buffer": [0.5, 0.75, 1.0],
    "dead_bars": [4, 8, 12],
    "adx_dead_threshold": [15, 20, 25],
    "max_equity_heat_pct": [1.0, 2.0, 3.0],     # Strict capital preservation
    "max_consec_losses": [3, 5, 8],
    "friday_cutoff_bars": [4, 8, 12],           # Early exit for weekend risk
    "min_addon_distance_ATR": [1.0, 1.5, 2.0],
}


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
