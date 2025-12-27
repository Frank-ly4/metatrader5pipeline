"""
Basic candlestick and bar-structure patterns (attribution only)
---------------------------------------------------------------

Implements fixed-threshold, deterministic 0/1 flags:
- candle_engulf_bull, candle_engulf_bear
- candle_pin_bull, candle_pin_bear
- candle_doji
- inside_bar, outside_bar
- nr7 (narrowest range in last 7 bars)
- swing_hh, swing_hl, swing_lh, swing_ll (optionally reused from provider)

These are intended for attribution only and are OFF by default unless the caller requests them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _body_wick_metrics(open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series):
    body = (close - open_).abs()
    upper = high - np.maximum(open_, close)
    lower = np.minimum(open_, close) - low
    range_ = high - low
    with np.errstate(divide='ignore', invalid='ignore'):
        body_ratio = np.where(range_ > 0, body / range_, 0.0)
        upper_ratio = np.where(range_ > 0, upper / range_, 0.0)
        lower_ratio = np.where(range_ > 0, lower / range_, 0.0)
    return body, upper, lower, range_, body_ratio, upper_ratio, lower_ratio


def detect_patterns(price: pd.DataFrame, *, include_swings: bool = False, swings: pd.DataFrame | None = None) -> pd.DataFrame:
    required = ['Open','High','Low','Close']
    for col in required:
        if col not in price.columns:
            raise ValueError(f"Missing required column: {col}")
    o = pd.Series(price['Open'].values, index=price.index)
    h = pd.Series(price['High'].values, index=price.index)
    l = pd.Series(price['Low'].values, index=price.index)
    c = pd.Series(price['Close'].values, index=price.index)

    body, upper, lower, rng, body_r, upper_r, lower_r = _body_wick_metrics(o, h, l, c)

    # Engulfing: Current body engulfs previous body body-range (not just wick range).
    # Require both bodies non-trivial and polarity change.
    prev_o = o.shift(1)
    prev_c = c.shift(1)
    prev_body = (prev_c - prev_o).abs()
    cur_body = (c - o).abs()
    nontrivial_prev = prev_body > 0
    nontrivial_cur = cur_body > 0

    # Bullish engulfing: prev bear, current bull, and |cur body| > |prev body| and spans prev body range
    prev_bear = prev_c < prev_o
    cur_bull = c > o
    engulf_body = cur_body > prev_body
    spans_prev = (np.minimum(o, c) <= np.minimum(prev_o, prev_c)) & (np.maximum(o, c) >= np.maximum(prev_o, prev_c))
    candle_engulf_bull = (nontrivial_prev & nontrivial_cur & prev_bear & cur_bull & engulf_body & spans_prev).astype(int)

    # Bearish engulfing: prev bull, current bear
    prev_bull = prev_c > prev_o
    cur_bear = c < o
    candle_engulf_bear = (nontrivial_prev & nontrivial_cur & prev_bull & cur_bear & engulf_body & spans_prev).astype(int)

    # Pin bars: long wick vs body. Use 66% wick share and small body (<20% of range).
    small_body = body_r <= 0.2
    long_lower = (lower_r >= 0.66) & (upper_r <= 0.2)
    long_upper = (upper_r >= 0.66) & (lower_r <= 0.2)
    candle_pin_bull = (small_body & long_lower & (c >= o)).astype(int)
    candle_pin_bear = (small_body & long_upper & (c <= o)).astype(int)

    # Doji: very small body relative to range (<=10%).
    candle_doji = (body_r <= 0.1).astype(int)

    # Inside/outside bars
    prev_h = h.shift(1)
    prev_l = l.shift(1)
    inside_bar = ((h <= prev_h) & (l >= prev_l)).astype(int)
    outside_bar = ((h >= prev_h) & (l <= prev_l)).astype(int)

    # NR7: The smallest range of the last 7 bars (include current)
    rng7 = rng.rolling(7, min_periods=7).apply(lambda x: 1.0 if x[-1] == np.nanmin(x) else 0.0, raw=True)
    nr7 = rng7.fillna(0).astype(int)

    out = pd.DataFrame({
        'candle_engulf_bull': candle_engulf_bull,
        'candle_engulf_bear': candle_engulf_bear,
        'candle_pin_bull': candle_pin_bull,
        'candle_pin_bear': candle_pin_bear,
        'candle_doji': candle_doji,
        'inside_bar': inside_bar,
        'outside_bar': outside_bar,
        'nr7': nr7,
    }, index=price.index)

    if include_swings:
        if swings is None:
            raise ValueError('swings must be provided when include_swings=True')
        for col in ('swing_hh','swing_hl','swing_lh','swing_ll'):
            if col in swings.columns:
                out[col] = swings[col].astype(int)
            else:
                out[col] = 0

    return out


# Minimal unit-testable helpers for synthetic sequences
def _make_bar(o: float, h: float, l: float, c: float) -> dict:
    return {'Open': o, 'High': h, 'Low': l, 'Close': c}


def test_patterns_basic_cases():
    # Build a small synthetic series to trigger each pattern deterministically
    rows = [
        _make_bar(10, 11, 9, 9.5),   # bear body
        _make_bar(9.6, 11.5, 9.1, 11.2),  # bull engulf current
        _make_bar(11.2, 11.8, 10.8, 11.0),
        _make_bar(11.0, 11.1, 10.0, 10.1),  # long lower wick (pin bull)
        _make_bar(10.1, 11.2, 10.0, 10.2),
        _make_bar(10.2, 10.25, 10.15, 10.21),  # doji small body
        _make_bar(10.21, 10.3, 10.2, 10.25),
        _make_bar(10.25, 10.5, 10.0, 10.1),  # outside bar
        _make_bar(10.1, 10.15, 10.05, 10.1),  # inside bar
    ]
    df = pd.DataFrame(rows)
    idx = pd.date_range('2020-01-01', periods=len(df), freq='D')
    df.index = idx
    pats = detect_patterns(df)
    # Engulfing bull should trigger at bar 1
    assert pats['candle_engulf_bull'].iloc[1] == 1
    # Pin bull at bar 3
    assert pats['candle_pin_bull'].iloc[3] == 1
    # Doji at bar 5
    assert pats['candle_doji'].iloc[5] == 1
    # Outside bar at bar 7
    assert pats['outside_bar'].iloc[7] == 1
    # Inside bar at bar 8
    assert pats['inside_bar'].iloc[8] == 1


