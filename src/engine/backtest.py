import pandas as pd
import numpy as np
import vectorbt as vbt
import json
import os
from config.backtest_user_inputs import BACKTEST_CONFIG as DEFAULT_BACKTEST_CONFIG
from src.strategy.pyramiding import layered_entries


def load_broker_spec() -> dict:
    """Load broker specifications from JSON."""
    spec_path = os.path.join('config', 'mt5_broker_spec.json')
    if os.path.exists(spec_path):
        with open(spec_path, 'r') as f:
            return json.load(f)
    return {}


def calculate_margin_capped_size(
    price: pd.Series, 
    equity: float, 
    symbol: str, 
    spec: dict, 
    max_margin_pct: float = 0.40,
    min_free_margin_pct: float = 0.30
) -> pd.Series:
    """
    Calculate maximum allowable lots (amount) based on MQL5 margin guardrails.
    
    Formula: Max Lots = (Equity * max_margin_pct * Leverage) / (ContractSize * Price)
    Also enforces the 30% free margin buffer.
    """
    symbol_data = spec.get('symbols', {}).get(symbol, {})
    if not symbol_data:
        # Fallback to default percent sizing if no spec found
        return pd.Series(0.40, index=price.index)

    leverage = spec.get('broker', {}).get('leverage', 100)
    contract_size = symbol_data.get('contract_size', 100000)
    
    # Calculate max lots per bar based on 40% margin cap
    # We use Price (Close) to estimate margin requirement at entry
    max_margin_usd = equity * max_margin_pct
    
    # Margin = (Lots * ContractSize * Price) / Leverage
    # Lots = (Margin * Leverage) / (ContractSize * Price)
    max_lots = (max_margin_usd * leverage) / (contract_size * price)
    
    # Enforce min lots from spec
    min_lot = symbol_data.get('min_volume', 0.01)
    max_lots = max_lots.clip(lower=min_lot)
    
    # Enforce max lots per symbol (guardrail from generator)
    max_lots = max_lots.clip(upper=5.0)
    
    return max_lots


def _resolve_backtest_config(backtest_overrides: dict | None) -> dict:
    base = DEFAULT_BACKTEST_CONFIG.copy()
    if backtest_overrides:
        base.update({
            'data_freq': backtest_overrides.get('data_freq', base['data_freq']),
            'init_cash': backtest_overrides.get('init_cash', base['init_cash']),
            'fees': backtest_overrides.get('fees', base['fees']),
            'size': backtest_overrides.get('position_size', base['size']),
            'max_layers': backtest_overrides.get('max_layers', base['max_layers']),
            'symbol': backtest_overrides.get('symbol', 'USDSEK'), # Default symbol
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
    Run backtest with long and optionally short positions, aligned with MT5 margin rules.
    """
    cfg = _resolve_backtest_config(backtest_overrides)
    spec = load_broker_spec()
    
    # Auto-detect native frequency
    inferred_freq = pd.infer_freq(pd.DatetimeIndex(price.index))
    freq = inferred_freq or cfg['data_freq']
    
    close_series = pd.Series(
        price['Close'].values,
        index=pd.DatetimeIndex(price.index)
    )
    
    # Calculate margin-aware sizing (Absolute Amount in Lots)
    # Note: VectorBT 'amount' for FX is in base units (e.g., 100,000 for 1 lot)
    symbol_name = cfg.get('symbol', 'USDSEK')
    if '!' in symbol_name: symbol_name = symbol_name.replace('!', '') # clean for JSON lookup
    
    # Get max lots based on initial equity (conservative) or per bar
    # To keep it simple and aligned with 'percent' logic but converted to units:
    max_lots_series = calculate_margin_capped_size(
        close_series, 
        cfg['init_cash'], 
        symbol_name, 
        spec
    )
    
    # Convert lots to units (VectorBT 'amount' type)
    # 1 lot = 100,000 units usually
    symbol_data = spec.get('symbols', {}).get(symbol_name, {})
    units_per_lot = symbol_data.get('contract_size', 100000)
    size_units = max_lots_series * units_per_lot
    
    # Check if shorts are enabled
    enable_shorts = short_entries is not None and short_exits is not None
    
    # Layered entries
    layered_long = layered_entries(entries, exits, max_layers=cfg.get('max_layers', 3))
    
    kwargs = dict(
        close=close_series,
        entries=layered_long,
        exits=exits,
        freq=freq,
        init_cash=cfg['init_cash'],
        fees=cfg['fees'],
        size=size_units,
        size_type='amount', # Switch to absolute units for precision
        accumulate=True,
    )
    
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


