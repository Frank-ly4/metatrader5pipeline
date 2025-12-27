"""Utility helpers for sanity tests."""

from __future__ import annotations

import pandas as pd
from typing import Tuple
import numpy as np


def run_single_backtest(price: pd.DataFrame, params: dict, toggles: dict):
    """Run a single backtest and return (metrics_row, trades_df).

    This uses the same evaluate_collect function as the main optimizer to keep
    strategy logic identical. We purposely avoid k-fold to keep runtime small.
    """
    from src.optimizer.search import evaluate_collect

    row, trades_df = evaluate_collect(price, params, toggles)
    return row, trades_df


def calc_basic_metrics(row: dict) -> Tuple[float, float, float]:
    """Return (sharpe, total_return_pct, profit_factor)."""
    sharpe = float(row.get("sharpe_ratio", 0.0) or 0.0)
    total_return = float(row.get("total_return", 0.0) or 0.0)
    pf = float(row.get("profit_factor", 0.0) or 0.0)
    return sharpe, total_return, pf


def calc_profit_factor(trades_df):
    """Compute profit factor from trades DataFrame using PnL or Return columns."""
    if trades_df is None or len(trades_df) == 0:
        return 0.0
    if 'PnL' in trades_df.columns:
        pnl = trades_df['PnL']
    elif 'Return' in trades_df.columns:
        pnl = trades_df['Return'] * 1.0  # returns in decimal
    elif {'Entry Price', 'Exit Price'}.issubset(trades_df.columns):
        pnl = trades_df['Exit Price'] - trades_df['Entry Price']
    else:
        return 0.0

    gains = pnl[pnl > 0].sum()
    losses = pnl[pnl < 0].abs().sum()
    if losses == 0:
        return np.inf
    return gains / losses
