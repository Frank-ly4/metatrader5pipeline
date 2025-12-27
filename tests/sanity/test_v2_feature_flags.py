import numpy as np
import pandas as pd

from src.strategy.bands_v2 import (
    _prepare_dynamic_length_series,
    manage_position,
    equity_heat_guard,
    compute_signals,
)


def _make_price(n=200, start=100.0, drift=0.05, vol=0.2):
    """Synthetic OHLC series with gentle uptrend for deterministic tests."""
    idx = pd.date_range('2024-01-01', periods=n, freq='H')
    close = start + np.cumsum(np.full(n, drift)) + np.sin(np.linspace(0, 8*np.pi, n)) * vol
    high = close + 0.2
    low = close - 0.2
    open_ = np.concatenate([[start], close[:-1]])
    df = pd.DataFrame({'Open': open_, 'High': high, 'Low': low, 'Close': close}, index=idx)
    return df


def test_no_bfill_in_dynamic_len_helper():
    s = pd.Series([np.nan, np.nan, 10.0, 9.5, 9.0, np.nan, 8.0])
    out = _prepare_dynamic_length_series(s, low=2, high=100, fill_value=20, avoid_bfill=True)
    # leading NaNs remain NaN (no backward fill)
    assert pd.isna(out.iloc[0]) and pd.isna(out.iloc[1])
    # forward-filled later NaN (at index 5) should become 9.0 (from index 4), not 20.0
    assert out.iloc[5] == round(9.0)


def test_same_bar_exit_entry_suppression():
    price = _make_price(150)
    params = {
        # use defaults; state machine on by default from config
        'max_holding_period': 25,
    }
    toggles = {
        # ensure features enabled
    }
    entries, exits, _ = compute_signals(price, params, toggles)
    # No bar should have both an exit and an entry (same-bar reentry blocked)
    assert not bool(((entries & exits).any()))


def test_equity_heat_guard_unit():
    # With size 0.7 and cap 1.0, a second layer would exceed
    assert equity_heat_guard(open_layers=0, size_frac=0.7, max_heat_pct=1.0) is True
    assert equity_heat_guard(open_layers=1, size_frac=0.7, max_heat_pct=1.0) is False
    # With size 0.25 and cap 2.0, up to 8 layers are allowed
    assert equity_heat_guard(open_layers=7, size_frac=0.25, max_heat_pct=2.0) is True
    assert equity_heat_guard(open_layers=8, size_frac=0.25, max_heat_pct=2.0) is False


def test_partial_moves_stop_to_be_minus_buffer():
    entry_price = 100.0
    atr_val = 1.0
    stop_price = entry_price - 1.5 * atr_val  # init_atr_mult = 1.5
    highest_high = entry_price + 1.5  # reaches >= 1R
    fast_dma = 100.0
    slow_dma = 99.0
    cha_atr_val = 1.0
    adx_val = 30.0
    params = {
        'be_buffer': 0.2,
        'chandelier_atr_multiplier': 3.0,
    }
    new_stop, partial_taken, chandelier_stop, r_value = manage_position(
        i=10,
        entry_price=entry_price,
        stop_price=stop_price,
        highest_high=highest_high,
        fast_dma=fast_dma,
        slow_dma=slow_dma,
        atr_val=atr_val,
        cha_atr_val=cha_atr_val,
        adx_val=adx_val,
        partial_taken=False,
        params=params,
    )
    expected_be = entry_price - params['be_buffer'] * atr_val
    assert partial_taken is True
    assert new_stop >= expected_be - 1e-9


