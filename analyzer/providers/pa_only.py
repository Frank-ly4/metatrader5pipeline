"""
Deterministic Price-Action Only Trend Provider (pa_only)
-------------------------------------------------------

Computes swing pivots using fixed left/right windows and derives:
- swing_hh, swing_hl, swing_lh, swing_ll (0/1 flags)
- pivot_high, pivot_low (0/1 flags)
- trend_label in {up, down, range} based on confirmation:
  up   => latest high is HH and latest low is HL
  down => latest high is LH and latest low is LL
  else => range

No external indicators. Deterministic given (left, right).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _detect_pivots(price: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame:
    high = pd.Series(price['High'].values, index=price.index)
    low = pd.Series(price['Low'].values, index=price.index)

    # Rolling max/min centered requires enough window; implement via stride comparisons
    window = left + right + 1
    # For each index i, consider slice [i-left, i+right]
    # Efficient approach: use rolling with center=True when available
    try:
        maxc = high.rolling(window=window, center=True, min_periods=window).max()
        minc = low.rolling(window=window, center=True, min_periods=window).min()
    except Exception:
        # Fallback: no pivot detection if rolling center not available
        maxc = pd.Series(np.nan, index=high.index)
        minc = pd.Series(np.nan, index=low.index)

    pivot_high = (high == maxc) & maxc.notna()
    pivot_low = (low == minc) & minc.notna()

    out = pd.DataFrame({'pivot_high': pivot_high.astype(int), 'pivot_low': pivot_low.astype(int)}, index=price.index)
    return out


def _classify_swings(price: pd.DataFrame, pivots: pd.DataFrame) -> pd.DataFrame:
    high = pd.Series(price['High'].values, index=price.index)
    low = pd.Series(price['Low'].values, index=price.index)

    swing_hh = np.zeros(len(price), dtype=np.int8)
    swing_hl = np.zeros(len(price), dtype=np.int8)
    swing_lh = np.zeros(len(price), dtype=np.int8)
    swing_ll = np.zeros(len(price), dtype=np.int8)

    last_piv_high_val = np.nan
    last_piv_low_val = np.nan

    for i in range(len(price)):
        if pivots['pivot_high'].iat[i] == 1:
            cur_high = float(high.iat[i])
            if np.isnan(last_piv_high_val):
                # First high pivot has no classification
                pass
            else:
                if cur_high > last_piv_high_val:
                    swing_hh[i] = 1
                else:
                    swing_lh[i] = 1
            last_piv_high_val = cur_high

        if pivots['pivot_low'].iat[i] == 1:
            cur_low = float(low.iat[i])
            if np.isnan(last_piv_low_val):
                pass
            else:
                if cur_low > last_piv_low_val:
                    swing_hl[i] = 1
                else:
                    swing_ll[i] = 1
            last_piv_low_val = cur_low

    return pd.DataFrame(
        {
            'swing_hh': swing_hh,
            'swing_hl': swing_hl,
            'swing_lh': swing_lh,
            'swing_ll': swing_ll,
        },
        index=price.index,
    )


def compute_pa_trend(price: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame:
    """Compute deterministic swing-based trend and swing flags.

    Returns DataFrame with columns:
    - pivot_high, pivot_low (0/1)
    - swing_hh, swing_hl, swing_lh, swing_ll (0/1)
    - trend_label in {'up','down','range'}
    """
    if not all(col in price.columns for col in ['High', 'Low']):
        raise ValueError('price must have High and Low columns')

    piv = _detect_pivots(price, left=left, right=right)
    swing = _classify_swings(price, piv)

    # Maintain last seen high-type and low-type
    last_high_type = None  # 'HH' or 'LH'
    last_low_type = None   # 'HL' or 'LL'
    trend_vals: list[str] = []

    for i in range(len(price)):
        if piv['pivot_high'].iat[i] == 1:
            if swing['swing_hh'].iat[i] == 1:
                last_high_type = 'HH'
            elif swing['swing_lh'].iat[i] == 1:
                last_high_type = 'LH'
        if piv['pivot_low'].iat[i] == 1:
            if swing['swing_hl'].iat[i] == 1:
                last_low_type = 'HL'
            elif swing['swing_ll'].iat[i] == 1:
                last_low_type = 'LL'

        if last_high_type == 'HH' and last_low_type == 'HL':
            trend_vals.append('up')
        elif last_high_type == 'LH' and last_low_type == 'LL':
            trend_vals.append('down')
        else:
            trend_vals.append('range')

    out = pd.DataFrame(index=price.index)
    out['pivot_high'] = piv['pivot_high']
    out['pivot_low'] = piv['pivot_low']
    out = pd.concat([out, swing], axis=1)
    out['trend_label'] = trend_vals
    return out


