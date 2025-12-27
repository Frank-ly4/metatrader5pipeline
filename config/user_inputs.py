# Deprecated: Use config/settings.py for unified configuration
import warnings

warnings.warn(
    'config/user_inputs.py is deprecated. Use config/settings.py instead.',
    DeprecationWarning
)

# Legacy user inputs
BACKTEST_CONFIG = {
    # Trading and accounting
    "fees": 0.0005,            # commission per trade (fractional)
    "position_size": 0.80,     # 30% of portfolio for each entry layer
    "starting_capital": 50000,  # initial cash
    # Data settings
    "data_freq": "1h",        # expected chart frequency
}

# UX and automation toggles
TOGGLES = {
    "move_processed_charts": False,  # move processed charts to used_charts/
            # print progress about every 1%
    "use_trailing_stop": True, # As per `bands.py`, this is still in use
    "use_take_profit": False, # As per `bands.py`, this is no longer in use, but we'll keep it as False

    # Strategy v2 feature toggles (runtime overrides; keep minimal edits)
    # Relax restrictive gates for optimization exploration; re-tighten later
    "feature_equity_heat_guard": False,
    "feature_session_filter": False,
    "feature_pyramiding_addon_distance": False,
}



