# Deprecated: Use config/settings.py for unified configuration
# Keeping this file for backward compatibility with warning
import warnings

warnings.warn(
    'config/backtest_user_inputs.py is deprecated. Use config/settings.py instead.',
    DeprecationWarning
)

# Legacy portfolio config to maintain compatibility
BACKTEST_CONFIG = {
    'data_freq': '2h',
    'init_cash': 50000.0,
    'fees': 0.00045,
    'size': 0.40,            # 30% of portfolio per position
    'size_type': 'percent',  # vectorbt percent sizing
    'max_orders': None,      # let vectorbt manage orders; set int to cap
    'max_layers': 3          # controlled pyramiding layers
}


