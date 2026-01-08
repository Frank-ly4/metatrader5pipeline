from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def _max_flat_streak(close: pd.Series) -> int:
    """Max consecutive identical close streak (ignores NaNs)."""
    if close is None or close.empty:
        return 0
    s = close.dropna()
    if s.empty:
        return 0
    # streaks break when value changes
    change = s.ne(s.shift()).cumsum()
    return int(s.groupby(change).size().max())


def _tf_to_minutes(timeframe: str | None) -> int | None:
    if not timeframe:
        return None
    tf = timeframe.strip().lower()
    try:
        if tf.endswith("m") and tf[:-1].isdigit():
            return int(tf[:-1])
        if tf.endswith("h") and tf[:-1].isdigit():
            return int(tf[:-1]) * 60
        if tf.endswith("d") and tf[:-1].isdigit():
            return int(tf[:-1]) * 1440
    except Exception:
        return None
    return None


def flat_streak_threshold(timeframe: str | None) -> int:
    """Reasonable default thresholds; tuned to catch synthetic/ffill artifacts fast."""
    minutes = _tf_to_minutes(timeframe)
    if minutes is None:
        return 40  # conservative default
    # Hand-tuned per cadence. Key requirement: 15m threshold ~40 (per user).
    mapping = {
        1: 300,
        3: 200,
        5: 120,
        15: 40,
        30: 25,
        60: 15,
        120: 10,
        240: 6,
        1440: 3,
    }
    return mapping.get(minutes, max(3, int(round(600 / minutes))))


@dataclass(frozen=True)
class ChartGuardrailResult:
    ok: bool
    weekend_bars: int
    max_gap_minutes: int
    max_flat_streak: int
    missing_bars: int | None
    threshold_flat: int
    bar_count: int


def validate_chart_guardrails(
    price: pd.DataFrame,
    *,
    chart_name: str,
    symbol: str | None = None,
    timeframe: str | None = None,
    require_no_weekend_bars: bool = True,
    min_bars: int = 500,
) -> ChartGuardrailResult:
    """Fail-fast gate to prevent synthetic-bar pollution from entering optimization."""
    if price is None or len(price) == 0:
        raise ValueError(f"[GUARD] {chart_name}: empty price data")
    if "Close" not in price.columns:
        raise ValueError(f"[GUARD] {chart_name}: missing Close column")

    idx = pd.to_datetime(price.index, errors="coerce")
    if idx.isna().any():
        raise ValueError(f"[GUARD] {chart_name}: invalid timestamps present")

    weekend_bars = int(((idx.dayofweek >= 5)).sum())

    diffs = idx.to_series().diff().dropna()
    max_gap_minutes = int(diffs.max().total_seconds() // 60) if not diffs.empty else 0

    max_flat = _max_flat_streak(price["Close"])
    th_flat = flat_streak_threshold(timeframe)

    missing_bars = None
    tf_min = _tf_to_minutes(timeframe)
    if tf_min and len(idx) >= 2:
        try:
            expected = pd.date_range(idx.min(), idx.max(), freq=f"{tf_min}min")
            missing_bars = int(len(expected.difference(idx)))
        except Exception:
            missing_bars = None

    ok = True
    bar_count = len(price)
    if bar_count < min_bars:
        ok = False
        print(f"  ✗ Too few bars ({bar_count} < {min_bars} minimum).")
    if require_no_weekend_bars and weekend_bars > 0:
        ok = False
    if max_flat > th_flat:
        ok = False

    msg = (
        f"[GUARD] {chart_name}"
        f" symbol={symbol or ''}"
        f" tf={timeframe or ''}"
        f" weekend_bars={weekend_bars}"
        f" max_gap_min={max_gap_minutes}"
        f" max_flat={max_flat}"
        f" flat_th={th_flat}"
    )
    if missing_bars is not None:
        msg += f" missing_bars={missing_bars}"

    print(msg)
    if require_no_weekend_bars and weekend_bars > 0:
        print("  ✗ Weekend bars detected (should be gaps; no Sat/Sun synthetic bars).")
    if max_flat > th_flat:
        print("  ✗ Flat-streak too large for timeframe (likely ffill/synthetic artifacts).")

    return ChartGuardrailResult(
        ok=ok,
        weekend_bars=weekend_bars,
        max_gap_minutes=max_gap_minutes,
        max_flat_streak=max_flat,
        missing_bars=missing_bars,
        threshold_flat=th_flat,
        bar_count=bar_count,
    )


