from __future__ import annotations

import numpy as np
import pandas as pd


def infer_timeframe(index: pd.DatetimeIndex) -> str:
    try:
        freq = pd.infer_freq(index)
        if not freq:
            # fallback: median delta
            delta = pd.Series(index).diff().median()
            mins = int(round(delta.total_seconds() / 60)) if pd.notna(delta) else 0
            if mins >= 1440:
                days = max(1, mins // 1440)
                return f"{days}d"
            if mins >= 60:
                hrs = max(1, mins // 60)
                return f"{hrs}h"
            return f"{max(1, mins)}m"
        f = freq.upper()
        if f.endswith('T'):
            return f"{int(f[:-1]) if f[:-1].isdigit() else 1}m"
        if f.endswith('H'):
            return f"{int(f[:-1]) if f[:-1].isdigit() else 1}h"
        if f.endswith('D'):
            return f"{int(f[:-1]) if f[:-1].isdigit() else 1}d"
        return f
    except Exception:
        return "unknown"


def compute_regimes(price: pd.DataFrame, *, momentum_len: int = 20, vol_len: int = 20,
                    trend_threshold: float = 0.0, vol_quantiles: tuple[float,float] = (0.33, 0.66),
                    use_mcg_trend: bool = True, hma_len: int = 20, hysteresis: int = 2) -> pd.DataFrame:
    """Compute regimes using momentum, robust volatility, and volatility-adaptive trend with hysteresis.

    Columns: 'momentum', 'volatility', 'trend', 'regime'.
    Regime strings: 'trend_up_high_vol', 'range_low_vol', etc.
    """
    close = price['Close']

    # Momentum as rolling return
    mom = close.pct_change(periods=momentum_len)

    # Robust volatility: median absolute high-low over window as a smoother ATR proxy
    hl = price['High'] - price['Low']
    vol = hl.rolling(vol_len).median() / close
    # Future-proof: replace deprecated fillna(method=...) usage
    vol = vol.bfill().fillna(0.0)

    # Trend via McGinley/HMA slope with volatility-adaptive smoothing
    if use_mcg_trend:
        try:
            from src.indicators.mcg_dma import vbt_mcg_dma_indicator
            Mcg = vbt_mcg_dma_indicator()
            # Use a fixed band for analysis to avoid parameter explosion here
            fast = Mcg.run(close, min_len=10, max_len=20, atr_len=max(10, vol_len)).real
            slow = Mcg.run(close, min_len=30, max_len=50, atr_len=max(10, vol_len)).real
            slope = (fast - slow) / slow.replace(0, np.nan)
        except Exception:
            slope = close.pct_change(hma_len)
    else:
        # Hull MA slope fallback: approximate with double-smoothed WMA via EMA proxy
        ema_fast = close.ewm(span=max(2, hma_len//2), adjust=False).mean()
        ema_slow = close.ewm(span=max(2, hma_len), adjust=False).mean()
        slope = (ema_fast - ema_slow) / ema_slow.replace(0, np.nan)

    slope = slope.fillna(0.0)

    # Hysteresis on trend classification to reduce whipsaws
    raw_trend = np.where(slope > trend_threshold, 'trend_up', np.where(slope < -trend_threshold, 'trend_down', 'range'))
    trend = raw_trend.astype(object)
    if hysteresis > 0:
        last = None
        hold = 0
        for i in range(len(trend)):
            cur = trend[i]
            if last is None:
                last, hold = cur, 0
            else:
                if cur != last:
                    hold += 1
                    if hold < hysteresis:
                        trend[i] = last
                    else:
                        last, hold = cur, 0
                else:
                    hold = 0
    trend = pd.Series(trend, index=price.index)

    # Volatility buckets by quantiles
    low_q, high_q = vol_quantiles
    vlow = float(vol.quantile(low_q))
    vhigh = float(vol.quantile(high_q))
    vb = np.where(vol <= vlow, 'low_vol', np.where(vol >= vhigh, 'high_vol', 'mid_vol'))
    regime = pd.Series([f"{t}_{vv}" for t, vv in zip(trend, vb)], index=price.index)

    return pd.DataFrame({
        'momentum': mom,
        'volatility': vol,
        'trend': trend,
        'regime': regime
    }, index=price.index)


def segment_by_regime(price: pd.DataFrame, regimes: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
    """Return contiguous regime segments as (start, end, regime_label)."""
    segs: list[tuple[pd.Timestamp, pd.Timestamp, str]] = []
    if len(price) == 0 or regimes is None:
        return segs
    # Future-proof: replace deprecated fillna(method=...) usage
    r = regimes.ffill().astype(str)
    start_idx = 0
    current = r.iloc[0]
    for i in range(1, len(r)):
        if r.iloc[i] != current:
            segs.append((price.index[start_idx], price.index[i-1], current))
            start_idx = i
            current = r.iloc[i]
    segs.append((price.index[start_idx], price.index[-1], current))
    return segs


def slice_equal_parts(price: pd.DataFrame, parts: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    n = len(price)
    parts = max(1, min(parts, n))
    idxs = [int(round(i * n / parts)) for i in range(parts + 1)]
    ranges = []
    for i in range(parts):
        a = idxs[i]
        b = max(a, idxs[i+1] - 1)
        ranges.append((price.index[a], price.index[b]))
    return ranges


def extract_price_range(price: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return price.loc[(price.index >= start) & (price.index <= end)].copy()


