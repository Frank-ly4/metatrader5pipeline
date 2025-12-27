import pandas as pd
import numpy as np
import vectorbt as vbt
from config.backtest_user_inputs import BACKTEST_CONFIG as DEFAULT_BACKTEST_CONFIG
from src.strategy.pyramiding import layered_entries


def _resolve_backtest_config(backtest_overrides: dict | None) -> dict:
    base = DEFAULT_BACKTEST_CONFIG.copy()
    if backtest_overrides:
        base.update({
            'data_freq': backtest_overrides.get('data_freq', base['data_freq']),
            'init_cash': backtest_overrides.get('init_cash', base['init_cash']),
            'fees': backtest_overrides.get('fees', base['fees']),
            'size': backtest_overrides.get('position_size', base['size']),
            'max_layers': backtest_overrides.get('max_layers', base['max_layers']),
        })
    return base


def run_backtest(
    price: pd.DataFrame,
    entries: pd.Series,
    exits: pd.Series,
    *,
    short_entries: pd.Series | None = None,
    short_exits: pd.Series | None = None,
    backtest_overrides: dict | None = None,
) -> vbt.Portfolio:
    """
    Run backtest with long and optionally short positions.
    
    Args:
        price: Price DataFrame with OHLC columns
        entries: Long entry signals
        exits: Long exit signals
        short_entries: Optional short entry signals (if None, shorts disabled)
        short_exits: Optional short exit signals (if None, shorts disabled)
        backtest_overrides: Optional config overrides
    
    Returns:
        vectorbt Portfolio object
    """
    cfg = _resolve_backtest_config(backtest_overrides)
    # Auto-detect native frequency; don't force frequency on sliced windows
    inferred_freq = pd.infer_freq(pd.DatetimeIndex(price.index))
    freq = inferred_freq or cfg['data_freq']
    
    # Create close series without forcing frequency (prevents validation errors on sliced data)
    close_series = pd.Series(
        price['Close'].values,
        index=pd.DatetimeIndex(price.index)  # Let pandas handle frequency naturally
    )
    
    # Check if shorts are enabled
    enable_shorts = short_entries is not None and short_exits is not None
    
    # Layered entries (Option B) and accumulate=True - apply per side
    layered_long = layered_entries(entries, exits, max_layers=cfg.get('max_layers', 3))
    
    kwargs = dict(
        close=close_series,
        entries=layered_long,
        exits=exits,
        freq=freq,
        init_cash=cfg['init_cash'],
        fees=cfg['fees'],
        size=cfg['size'],
        size_type=DEFAULT_BACKTEST_CONFIG['size_type'],
        accumulate=True,
    )
    
    # Add short side if enabled
    if enable_shorts:
        layered_short = layered_entries(short_entries, short_exits, max_layers=cfg.get('max_layers', 3))
        kwargs['short_entries'] = layered_short
        kwargs['short_exits'] = short_exits
        kwargs['direction'] = 'both'
    
    max_orders = DEFAULT_BACKTEST_CONFIG.get('max_orders')
    if isinstance(max_orders, int) and max_orders > 0:
        kwargs['max_orders'] = max_orders
    
    pf = vbt.Portfolio.from_signals(**kwargs)
    return pf


