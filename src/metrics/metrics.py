"""Centralized metric calculations with strict definitions.

All rates returned as FRACTIONS (0.12 = 12%), not percents.
"""

import pandas as pd
import numpy as np


def cagr_frac(equity: pd.Series, dt_index: pd.DatetimeIndex) -> float:
    """Calculate CAGR as fraction (0.12 = 12%)."""
    if len(equity) < 2:
        return 0.0
    
    start_value = equity.iloc[0]
    end_value = equity.iloc[-1]
    
    if start_value <= 0:
        return 0.0
    
    total_days = (dt_index[-1] - dt_index[0]).days
    if total_days <= 0:
        return 0.0
    
    years = total_days / 365.25
    return (end_value / start_value) ** (1 / years) - 1


def max_drawdown_frac(equity: pd.Series) -> float:
    """Calculate maximum drawdown as fraction."""
    if len(equity) == 0:
        return 0.0
    
    peak = equity.expanding().max()
    drawdown = (peak - equity) / peak
    return drawdown.max()


def calmar(cagr: float, maxdd: float) -> float:
    """Calculate Calmar ratio. Return NaN if maxdd <= 1e-6."""
    if maxdd <= 1e-6:
        return np.nan
    return cagr / maxdd


def profit_factor(pnl_net: pd.Series) -> float:
    """Calculate profit factor. Return inf if no negative trades."""
    positive_pnl = pnl_net[pnl_net > 0].sum()
    negative_pnl = pnl_net[pnl_net < 0].sum()
    
    if negative_pnl == 0:
        return np.inf
    
    return positive_pnl / abs(negative_pnl)


def ulcer_index(equity: pd.Series) -> float:
    """Calculate Ulcer Index from equity curve."""
    if len(equity) == 0:
        return 0.0
    
    peak = equity.expanding().max()
    drawdown_pct = (peak - equity) / peak * 100  # Convert to percent for Ulcer calculation
    return np.sqrt((drawdown_pct ** 2).mean())


def expectancy(pnl_net: pd.Series) -> float:
    """Calculate expectancy as mean PnL per trade."""
    if len(pnl_net) == 0:
        return 0.0
    return pnl_net.mean()


def avg_hold_hours(trades_df: pd.DataFrame) -> float:
    """Calculate average holding time in hours."""
    if len(trades_df) == 0 or 'open_time' not in trades_df.columns or 'close_time' not in trades_df.columns:
        return np.nan
    
    open_times = pd.to_datetime(trades_df['open_time'])
    close_times = pd.to_datetime(trades_df['close_time'])
    
    hold_times = (close_times - open_times).dt.total_seconds() / 3600
    return hold_times.mean()
