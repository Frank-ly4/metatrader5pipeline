"""Strategy parameter surface for baseline runs and optimizer search.

This module is the single place for users to:
- Inspect and modify the default parameters used by `scripts/run_backtest.py`
- Control the ranges sampled by the optimizer
"""

from __future__ import annotations

# Baseline parameters used by single backtest script
BASELINE_PARAMS: dict[str, float | int | bool] = {
    "fast_min_len": 10,
    "fast_max_len": 20,
    "slow_min_len": 30,
    "slow_max_len": 50,
    "dma_atr_len": 14,
    "atr_len": 14,
    "upper_outer_mult": 2.0,
    "lower_outer_mult": 2.0,
    "upper_inner_mult": 1.2,
    "lower_inner_mult": 1.2,
    "momentum_len": 14,
    "momentum_threshold": 0.70,
    "momentum_lookback": 75,
    "slope_lookback": 1,
    "rsi_len": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,  # New: mirror of rsi_oversold for shorts
    "trailing_atr_mult": 1.5,
    "catastrophic_stop_atr_mult": 0.5,
    "ranging_confirm_bar": True,

    # HTF gating (optional)
    "use_htf_filter": False,
    "htf_tf": "1D",

    # Anti-chop control
    "cooldown_bars": 0,
    # Bidirectional support
    "enable_shorts": False,  # Set to True to enable short positions
    "use_dma_fail_exit": True,  # Stabilized DMA fail exit
    "dma_exit_bars": 2,  # Consecutive bars required for DMA fail exit
    "dma_exit_buffer_atr": 0.2,  # ATR buffer for DMA fail exit
    # Optional directional momentum gate
    "use_directional_momentum": False,  # Filter entries by ROC direction
    "roc_len": 22,  # ROC period for directional momentum (defaults to momentum_len if not set)
}

# Parameter ranges used by optimizer (random/grid/lhs/sobol)
PARAM_RANGES: dict[str, list] = {
    "fast_min_len": [8, 10, 12],
    "fast_max_len": [18, 20, 22],
    "slow_min_len": [28, 30, 32],
    "slow_max_len": [48, 50, 55],
    "dma_atr_len": [12, 14, 16],
    "atr_len": [12, 14, 16],
    "upper_outer_mult": [1.8, 2.0, 2.2],
    "lower_outer_mult": [1.8, 2.0, 2.2],
    "upper_inner_mult": [1.0, 1.2],
    "lower_inner_mult": [1.0, 1.2, 1.4],
    "momentum_len": [12, 14, 16],
    "momentum_threshold": [0.65, 0.70, 0.75],
    "momentum_lookback": [50, 75, 100],
    "slope_lookback": [1, 2],
    "rsi_len": [12, 14, 16],
    "rsi_oversold": [25, 30, 35],
    "rsi_overbought": [65, 70, 75],  # New: conservative range for shorts
    "trailing_atr_mult": [1.0, 1.5, 2.0],
    "catastrophic_stop_atr_mult": [0.25, 0.5, 1.0],
    "ranging_confirm_bar": [True, False],
    # Bidirectional parameters (conservative ranges to reduce overfit)
    "enable_shorts": [False, True],  # Allow optimizer to test with/without shorts
    "use_dma_fail_exit": [True],  # Keep enabled by default
    "dma_exit_bars": [1, 2, 3],  # Small range for stability
    "dma_exit_buffer_atr": [0.1, 0.2, 0.3],  # Small range
    "use_directional_momentum": [False, True],  # Optional gate
    "roc_len": [14, 22],  # Conservative range

    # HTF gating - categorical (optimizer can now sample these)
    "use_htf_filter": [False, True],
    "htf_tf": ["8H", "12H", "1D", "2D", "1W"],

    # Anti-chop cooldown
    "cooldown_bars": [0, 3, 5, 10],
}



# Compatibility aliases (used by interactive optimizer)
DEFAULT_PARAMS = BASELINE_PARAMS
TEST_RANGES = PARAM_RANGES

