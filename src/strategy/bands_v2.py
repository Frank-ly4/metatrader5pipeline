import numpy as np
import pandas as pd
from datetime import time as _time

EPS = 1e-12

from src.indicators.mcg_dma import vbt_mcg_dma_indicator
from config.strategy_params_v2 import FEATURE_FLAGS_V2 as DEFAULT_FEATURE_FLAGS

# Initialize the custom indicator
mcg_dma = vbt_mcg_dma_indicator()


# ---------------------------
# Helpers
# ---------------------------

def _as_pos_int(x, default=1):
    """Coerce any numeric to a positive integer >=1."""
    try:
        v = int(round(float(x)))
        return v if v >= 1 else 1
    except Exception:
        return default

def _safe_div(numer: pd.Series, denom: pd.Series, eps: float = EPS) -> pd.Series:
    """Safe division: guards against 0/NaN, removes infs."""
    d = denom.copy()
    d = d.where(d.abs() > eps, np.nan)
    out = numer / d
    return out.replace([np.inf, -np.inf], np.nan)

def _clean_series_for_int_windows(s: pd.Series, low: int, high: int, fill_value: int) -> pd.Series:
    """
    Clean a float series so it can be safely cast to int windows:
    - replace inf with NaN
    - forward/back fill remaining NaNs
    - fill any leftover with fill_value
    - clip to [low, high]
    - round and cast to int
    """
    cleaned = (
        s.replace([np.inf, -np.inf], np.nan)
         .ffill()
         .bfill()
         .fillna(float(fill_value))
         .clip(lower=float(low), upper=float(high))
    )
    return cleaned.round().astype(int)


def _prepare_dynamic_length_series(
    s: pd.Series,
    low: int,
    high: int,
    fill_value: int,
    *,
    avoid_bfill: bool = False,
) -> pd.Series:
    """Clean dynamic length series with optional no-bfill semantics.

    When avoid_bfill=True, we eliminate any backward-fill to avoid look-ahead.
    Early NaNs are allowed and only forward-fill within known history is used.
    The result remains float so NaNs are preserved; EMA routine accepts floats.
    """
    s = s.replace([np.inf, -np.inf], np.nan)
    if avoid_bfill:
        cleaned = s.ffill().clip(lower=float(low), upper=float(high))
        # keep NaNs at the head; do not coerce to int to preserve NaNs
        return cleaned.round()
    # legacy behavior (with bfill and full fillna)
    return _clean_series_for_int_windows(s, low=low, high=high, fill_value=fill_value)


# ---------------------------
# Indicators
# ---------------------------

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    """Average True Range with safe window and min_periods."""
    length = _as_pos_int(length, default=14)
    tr1 = (high - low).abs()
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low  - close.shift(1)).abs()
    true_range = tr1.combine(tr2, max).combine(tr3, max)
    # Use min_periods=length so early values are NaN (expected)
    return true_range.rolling(window=length, min_periods=length).mean()

def calculate_rsi(close: pd.Series, length: int) -> pd.Series:
    """Relative Strength Index (simple rolling-mean version)."""
    length = _as_pos_int(length, default=14)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(window=length, min_periods=length).mean()
    avg_loss = loss.rolling(window=length, min_periods=length).mean()
    rs = _safe_div(avg_gain, avg_loss)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    """Average Directional Index (simplified; smoothed with rolling mean)."""
    length = _as_pos_int(length, default=14)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = (high - low).abs()
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low  - close.shift(1)).abs()
    tr = tr1.combine(tr2, max).combine(tr3, max)

    # Smoothed values
    smoothed_tr = tr.rolling(window=length, min_periods=length).mean()
    smoothed_plus_dm = plus_dm.rolling(window=length, min_periods=length).mean()
    smoothed_minus_dm = minus_dm.rolling(window=length, min_periods=length).mean()

    plus_di = 100.0 * _safe_div(smoothed_plus_dm, smoothed_tr)
    minus_di = 100.0 * _safe_div(smoothed_minus_dm, smoothed_tr)

    dx = 100.0 * _safe_div((plus_di - minus_di).abs(), (plus_di + minus_di).abs())
    adx = dx.rolling(window=length, min_periods=length).mean()
    return adx

def calculate_stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, k_length: int, d_length: int, smooth: int
) -> tuple[pd.Series, pd.Series]:
    """Stochastic Oscillator with safe windows and zero-division guard."""
    k_length = _as_pos_int(k_length, default=14)
    d_length = _as_pos_int(d_length, default=3)
    smooth = _as_pos_int(smooth, default=3)

    lowest_low = low.rolling(window=k_length, min_periods=k_length).min()
    highest_high = high.rolling(window=k_length, min_periods=k_length).max()
    denom = (highest_high - lowest_low).where((highest_high - lowest_low).abs() > EPS, np.nan)
    stoch_k = 100.0 * _safe_div(close - lowest_low, denom)

    if smooth > 1:
        stoch_k = stoch_k.rolling(window=smooth, min_periods=smooth).mean()

    stoch_d = stoch_k.rolling(window=d_length, min_periods=d_length).mean()
    return stoch_k, stoch_d


def _calculate_dynamic_ema(source: pd.Series, length_series: pd.Series) -> pd.Series:
    """
    Exponential Moving Average with bar-by-bar dynamic lookback.
    length_series must be integer-like and >=1 after cleaning.
    """
    # Optimized: operate on numpy arrays to avoid per-iteration pandas overhead
    values = source.to_numpy(dtype=float, copy=False)
    lens = length_series.to_numpy(dtype=float, copy=False)
    n = values.shape[0]
    out = np.empty(n, dtype=float)
    if n == 0:
        return pd.Series(index=source.index, dtype=float)
    out[0] = values[0]
    prev = out[0]
    for i in range(1, n):
        L = lens[i]
        if not np.isfinite(L) or L <= 1.0:
            alpha = 1.0
        else:
            alpha = 2.0 / (float(L) + 1.0)
        prev = alpha * values[i] + (1.0 - alpha) * prev
        out[i] = prev
    return pd.Series(out, index=source.index)


# ---------------------------
# Main compute functions
# ---------------------------

def compute_indicators(price: pd.DataFrame, params: dict, toggles: dict) -> dict:
    """Compute all necessary indicators (safe against NaN/inf and bad windows)."""
    # --- Coerce window-like params to ints upfront ---
    # (Keeps multipliers/thresholds as floats)
    params = {
        **params,
        'base_fast_len':        _as_pos_int(params.get('base_fast_len', 20)),
        'base_slow_len':        _as_pos_int(params.get('base_slow_len', 50)),
        'volatility_atr_short': _as_pos_int(params.get('volatility_atr_short', 5)),
        'volatility_atr_long':  _as_pos_int(params.get('volatility_atr_long', 100)),
        'atr_len':              _as_pos_int(params.get('atr_len', 14)),
        'rsi_len':              _as_pos_int(params.get('rsi_len', 14)),
        'adx_period':           _as_pos_int(params.get('adx_period', 14)),
        'stoch_k':              _as_pos_int(params.get('stoch_k', 14)),
        'stoch_d':              _as_pos_int(params.get('stoch_d', 3)),
        'stoch_smooth':         _as_pos_int(params.get('stoch_smooth', 3)),
    }

    close = price['Close']
    high = price['High']
    low = price['Low']

    # --- Phase 1: Dynamic Bands Core Calculation (Sunny Harris Method) ---
    # Compute True Range once, reuse for multiple ATR windows to reduce overhead
    tr1 = (high - low).abs()
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low  - close.shift(1)).abs()
    true_range = tr1.combine(tr2, max).combine(tr3, max)

    atr_short = true_range.rolling(window=params['volatility_atr_short'], min_periods=params['volatility_atr_short']).mean()
    atr_long  = true_range.rolling(window=params['volatility_atr_long'],  min_periods=params['volatility_atr_long']).mean()

    # Volatility ratio with guards
    volatility_index = _safe_div(atr_short, atr_long).clip(lower=0.25, upper=4.0)
    # Fallback reasonable default for early NaNs
    volatility_index = volatility_index.fillna(1.0)

    # Dynamic target lengths (float first)
    raw_fast_len = params['base_fast_len'] / (volatility_index + EPS)
    raw_slow_len = params['base_slow_len'] * (volatility_index + EPS)

    # Clean for int-casting (bounds avoid extreme swings)
    flags = {**DEFAULT_FEATURE_FLAGS}
    if isinstance(toggles, dict):
        for k in DEFAULT_FEATURE_FLAGS:
            if k in toggles:
                try:
                    flags[k] = bool(toggles[k])
                except Exception:
                    pass
    fast_dynamic_len = _prepare_dynamic_length_series(
        raw_fast_len,
        low=2,
        high=max(params['base_slow_len'], params['base_fast_len'], 2),
        fill_value=params['base_fast_len'],
        avoid_bfill=flags.get('feature_no_bfill_dynamic_len', False),
    )
    slow_dynamic_len = _prepare_dynamic_length_series(
        raw_slow_len,
        low=max(params['base_fast_len'], 2),
        high=10_000,
        fill_value=params['base_slow_len'],
        avoid_bfill=flags.get('feature_no_bfill_dynamic_len', False),
    )

    # Dynamic EMAs
    fast_dma = _calculate_dynamic_ema(close, fast_dynamic_len)
    slow_dma = _calculate_dynamic_ema(close, slow_dynamic_len)

    # --- V1 Indicators (some are still used) ---
    atr = true_range.rolling(window=params['atr_len'], min_periods=params['atr_len']).mean()
    cha_len = _as_pos_int(params.get('chandelier_atr_period', params['atr_len']))
    cha_atr = true_range.rolling(window=cha_len, min_periods=cha_len).mean()
    rsi = calculate_rsi(close, params['rsi_len'])

    # --- Phase 2 & 3 Indicators ---
    adx = calculate_adx(high, low, close, params['adx_period'])
    stoch_k, stoch_d = calculate_stochastic(
        high, low, close, params['stoch_k'], params['stoch_d'], params['stoch_smooth']
    )

    return {
        'fast_dma': fast_dma,
        'slow_dma': slow_dma,
        'atr': atr,
        'cha_atr': cha_atr,
        'rsi': rsi,
        'adx': adx,
        'stoch_k': stoch_k,
        'stoch_d': stoch_d,
        'fast_len_series': fast_dynamic_len,  # optional debug
        'slow_len_series': slow_dynamic_len,  # optional debug
        'volatility_index': volatility_index, # optional debug
    }


# ---------------------------
# Feature-flagged pure functions
# ---------------------------

def _resolve_flags(toggles: dict | None) -> dict:
    flags = {**DEFAULT_FEATURE_FLAGS}
    if isinstance(toggles, dict):
        for k in list(flags.keys()):
            if k in toggles:
                try:
                    flags[k] = bool(toggles[k])
                except Exception:
                    pass
    return flags


def compute_regime(is_trending: pd.Series, adx: pd.Series, params: dict) -> pd.Series:
    """Classify simple regimes using trend condition and ADX floor."""
    adx_floor = float(params.get('adx_floor', 18))
    reg = np.where(is_trending & (adx >= adx_floor), 'trend', 'range')
    return pd.Series(reg, index=is_trending.index)


def apply_vol_filter(atr: pd.Series, close: pd.Series, params: dict) -> pd.Series:
    """Accept bars with normalized ATR in [floor, cap]."""
    floor = float(params.get('atr_pct_floor', 0.0006))
    cap = float(params.get('atr_pct_cap', 0.015))
    atr_pct = (atr / close.replace(0.0, np.nan)).fillna(np.nan)
    ok = (atr_pct >= floor) & (atr_pct <= cap)
    return ok.fillna(False)


def _parse_hh_mm(s: str) -> tuple[int, int]:
    try:
        hh, mm = s.split(':')
        return int(hh), int(mm)
    except Exception:
        return (0, 0)


def apply_session_filter(index: pd.DatetimeIndex, params: dict) -> pd.Series:
    """Session filter on local broker time between session_start and session_end.

    Assumes naive timestamps are already in broker time. If session crosses
    midnight, treat [start..23:59] U [00:00..end].
    """
    start = str(params.get('session_start', '00:00'))
    end = str(params.get('session_end', '23:59'))
    sh, sm = _parse_hh_mm(start)
    eh, em = _parse_hh_mm(end)
    t_start = _time(sh, sm)
    t_end = _time(eh, em)
    times = index.time
    if t_start <= t_end:
        mask = (times >= t_start) & (times <= t_end)
    else:
        mask = (times >= t_start) | (times <= t_end)
    return pd.Series(mask, index=index)


def apply_friday_cutoff(index: pd.DatetimeIndex, params: dict) -> pd.Series:
    """Suppress entries during the last N bars of Friday based on session_end and bar duration.

    Estimates bar minutes from median delta. Uses session_end to approximate time
    remaining in session. If session filter is off or session_end not set,
    defaults to using 23:59 as end-of-day. No lookahead is used; decision is
    based on bar time-of-day vs configured end.
    """
    n_cut = int(params.get('friday_cutoff_bars', 0) or 0)
    if n_cut <= 0:
        return pd.Series(True, index=index)
    # infer bar minutes
    try:
        deltas = pd.Series(index).diff().dropna()
        bar_minutes = int(round(deltas.median().total_seconds() / 60.0)) if len(deltas) > 0 else 0
        bar_minutes = max(1, bar_minutes)
    except Exception:
        bar_minutes = 60
    end_str = str(params.get('session_end', '23:59'))
    eh, em = _parse_hh_mm(end_str)
    end_t = _time(eh, em)
    allowed = []
    for ts in index:
        is_friday = ts.weekday() == 4
        if not is_friday:
            allowed.append(True)
            continue
        # minutes remaining in session
        rem = (end_t.hour - ts.hour) * 60 + (end_t.minute - ts.minute)
        # if rem < 0, we already past end -> disallow
        if rem < 0:
            allowed.append(False)
            continue
        cutoff_minutes = n_cut * bar_minutes
        allowed.append(rem > cutoff_minutes)
    return pd.Series(allowed, index=index)


def compute_initial_stop(entry_price: float, atr_val: float, params: dict) -> float:
    init_mult = float(params.get('init_atr_mult', 1.5))
    return float(entry_price) - init_mult * float(atr_val)


def manage_position(
    i: int,
    entry_price: float,
    stop_price: float,
    highest_high: float,
    fast_dma: float,
    slow_dma: float,
    atr_val: float,
    cha_atr_val: float,
    adx_val: float,
    partial_taken: bool,
    params: dict,
) -> tuple[float, bool, float, float]:
    """Update stop/trail/partial based on hierarchical rules.

    Returns: (new_stop_price, partial_taken, chandelier_stop_price, r_value)
    where r_value is the current 1R distance from entry.
    """
    be_buffer = float(params.get('be_buffer', 0.2))
    trail_dma_buffer = float(params.get('trail_dma_buffer', 0.5))
    ch_mult = float(params.get('chandelier_atr_multiplier', 3.0))
    adx_dead_threshold = float(params.get('adx_dead_threshold', 15))
    # Compute 1R from initial stop snapshot
    r_value = max(1e-12, entry_price - stop_price)

    # Partial at 1R -> move stop to BE - buffer*ATR
    if not partial_taken and (highest_high >= entry_price + r_value):
        partial_taken = True
        be_stop = entry_price - be_buffer * atr_val
        stop_price = max(stop_price, be_stop)

    # DMA-based trailing
    dma_trail = fast_dma - trail_dma_buffer * atr_val
    stop_price = max(stop_price, dma_trail)

    # Chandelier trailing reference (evaluated as separate exit condition too)
    chandelier_stop = highest_high - (cha_atr_val * ch_mult)

    # Optionally, when ADX is very weak, maintain at least slow_dma as a sanity floor
    if adx_val < adx_dead_threshold:
        stop_price = max(stop_price, slow_dma)

    return float(stop_price), partial_taken, float(chandelier_stop), float(r_value)


def equity_heat_guard(open_layers: int, size_frac: float, max_heat_pct: float) -> bool:
    """Return True if adding one more layer keeps equity heat <= cap (in %)."""
    current_heat_pct = open_layers * (size_frac * 100.0)
    next_heat_pct = (open_layers + 1) * (size_frac * 100.0)
    return next_heat_pct <= float(max_heat_pct)


def compute_setup(low: float, slow_dma: float, atr: float, rsi: float, params: dict) -> bool:
    """Ranging setup: price pierces lower outer band and RSI < oversold."""
    lower_outer_val = slow_dma - float(params.get('lower_outer_mult', 2.0)) * atr
    return (low < lower_outer_val) and (rsi < float(params.get('rsi_oversold', 30.0)))


def trigger_signals(
    i: int,
    is_trend: bool,
    low: float,
    open_: float,
    close: float,
    fast_dma: float,
    atr: float,
    stoch_k: float,
    stoch_d: float,
    stoch_k_prev: float,
    stoch_d_prev: float,
    params: dict,
) -> tuple[bool, bool]:
    """Return (trending_entry, ranging_entry) boolean triggers."""
    dma_buffer_mult = float(params.get('dma_buffer_mult', 0.5))
    in_golden_zone = is_trend and (low <= (fast_dma + dma_buffer_mult * atr))
    stoch_cross_up = (stoch_k > stoch_d) and (stoch_k_prev <= stoch_d_prev)
    trending_entry = in_golden_zone and stoch_cross_up
    is_reversal_bar = close > open_
    ranging_entry = is_reversal_bar
    return bool(trending_entry), bool(ranging_entry)


def compute_signals(price: pd.DataFrame, params: dict, toggles: dict) -> tuple[pd.Series, pd.Series, dict]:
    """Compute entry and exit signals.

    When feature flags enable the new state machine, use the hierarchical exit
    and filter pipeline; otherwise fall back to legacy v2 logic.
    """
    flags = _resolve_flags(toggles)
    if flags.get('feature_state_machine', False):
        return _compute_signals_state_machine(price, params, toggles, flags)

    # ---- Legacy v2 path below ----
    # Coerce a few control params as well
    params = {
        **params,
        'max_holding_period': _as_pos_int(params.get('max_holding_period', 100)),
        'adx_threshold': float(params.get('adx_threshold', 25)),
        'chandelier_atr_multiplier': float(params.get('chandelier_atr_multiplier', 3.0)),
        'upper_outer_mult': float(params.get('upper_outer_mult', 2.0)),
        'lower_outer_mult': float(params.get('lower_outer_mult', 2.0)),
        'upper_inner_mult': float(params.get('upper_inner_mult', 1.2)),
        'lower_inner_mult': float(params.get('lower_inner_mult', 1.2)),
        'rsi_oversold': float(params.get('rsi_oversold', 30)),
        'ranging_trigger_window': _as_pos_int(params.get('ranging_trigger_window', 3)),
    }

    indicators = compute_indicators(price, params, toggles)

    # Unpack indicators
    close = price['Close']
    low = price['Low']
    high = price['High']
    fast_dma = indicators['fast_dma']
    slow_dma = indicators['slow_dma']
    atr = indicators['atr']
    rsi = indicators['rsi']
    adx = indicators['adx']
    stoch_k = indicators['stoch_k']
    stoch_d = indicators['stoch_d']

    # --- Band Calculation ---
    upper_outer = slow_dma + params['upper_outer_mult'] * atr
    lower_outer = slow_dma - params['lower_outer_mult'] * atr
    upper_inner = fast_dma + params['upper_inner_mult'] * atr
    lower_inner = fast_dma - params['lower_inner_mult'] * atr

    # --- Regime Definition ---
    is_trending = fast_dma > slow_dma

    # --- State Variables for looping (numpy-accelerated) ---
    n = len(price)
    entries_arr = np.zeros(n, dtype=bool)
    exits_arr = np.zeros(n, dtype=bool)
    in_trade = False
    bars_in_trade = 0
    highest_high_since_entry = 0.0
    ranging_entry_armed = 0  # int counter for the window

    # Pre-extract numpy views to avoid per-iteration pandas overhead
    close_a = close.to_numpy(dtype=float, copy=False)
    low_a = low.to_numpy(dtype=float, copy=False)
    high_a = high.to_numpy(dtype=float, copy=False)
    open_a = price['Open'].to_numpy(dtype=float, copy=False)
    fast_dma_a = fast_dma.to_numpy(dtype=float, copy=False)
    slow_dma_a = slow_dma.to_numpy(dtype=float, copy=False)
    atr_a = atr.to_numpy(dtype=float, copy=False)
    rsi_a = rsi.to_numpy(dtype=float, copy=False)
    adx_a = adx.to_numpy(dtype=float, copy=False)
    stoch_k_a = stoch_k.to_numpy(dtype=float, copy=False)
    stoch_d_a = stoch_d.to_numpy(dtype=float, copy=False)
    upper_outer_a = upper_outer.to_numpy(dtype=float, copy=False)
    upper_inner_a = upper_inner.to_numpy(dtype=float, copy=False)
    is_trending_a = is_trending.to_numpy(dtype=bool, copy=False)

    # --- Main Loop for Signal Generation ---
    for i in range(1, n):
        # --- ARMING LOGIC (for ranging entries) ---
        if (not is_trending_a[i]) and (low_a[i] < upper_outer_a[i] - (upper_outer_a[i] - slow_dma_a[i])) and (rsi_a[i] < params['rsi_oversold']):
            # Note: original condition used (low < lower_outer). lower_outer = slow_dma - lower_outer_mult*atr
            # To avoid extra array, compute inline as slow_dma - lower_outer_mult*atr
            lower_outer_val = slow_dma_a[i] - params['lower_outer_mult'] * atr_a[i]
            if low_a[i] < lower_outer_val:
                ranging_entry_armed = params['ranging_trigger_window']
        elif ranging_entry_armed > 0:
            ranging_entry_armed -= 1

        # --- EXIT LOGIC ---
        if in_trade:
            bars_in_trade += 1
            if high_a[i] > highest_high_since_entry:
                highest_high_since_entry = high_a[i]

            # 1) Time Stop
            time_stop_triggered = bars_in_trade >= params['max_holding_period']

            # 2) Stagnation Stop (ADX)
            adx_stop_triggered = is_trending_a[i] and (adx_a[i] < params['adx_threshold'])

            # 3) Chandelier Exit
            chandelier_stop_price = highest_high_since_entry - (atr_a[i] * params['chandelier_atr_multiplier'])
            chandelier_exit_triggered = low_a[i] < chandelier_stop_price

            # 4) Trend Invalidation
            trend_invalidation_exit = close_a[i] < slow_dma_a[i]

            # 5) Ranging profit target
            range_profit_exit = (not is_trending_a[i]) and (high_a[i] >= upper_inner_a[i])

            if time_stop_triggered or adx_stop_triggered or chandelier_exit_triggered or trend_invalidation_exit or range_profit_exit:
                exits_arr[i] = True
                in_trade = False
                ranging_entry_armed = 0

        # --- ENTRY LOGIC ---
        if not in_trade:
            # 1) Trending Entry: Golden Zone pullback with Stochastic confirmation
            in_golden_zone = is_trending_a[i] and (low_a[i] <= fast_dma_a[i])
            stoch_cross_up = (stoch_k_a[i] > stoch_d_a[i]) and (stoch_k_a[i-1] <= stoch_d_a[i-1])
            trending_entry = in_golden_zone and stoch_cross_up

            # 2) Ranging Entry: Armed trigger with confirmation bar
            is_reversal_bar = close_a[i] > open_a[i]
            ranging_entry = (ranging_entry_armed > 0) and is_reversal_bar

            if trending_entry or ranging_entry:
                entries_arr[i] = True
                in_trade = True
                bars_in_trade = 0
                highest_high_since_entry = high_a[i]
                ranging_entry_armed = 0  # Disarm on entry

    # Attach convenience fields
    entries = pd.Series(entries_arr, index=price.index)
    exits = pd.Series(exits_arr, index=price.index)
    indicators['upper_outer'] = upper_outer
    indicators['lower_outer'] = lower_outer
    indicators['upper_inner'] = upper_inner
    indicators['lower_inner'] = lower_inner
    indicators['is_trending'] = is_trending

    return entries, exits, indicators


def _compute_signals_state_machine(price: pd.DataFrame, params: dict, toggles: dict, flags: dict) -> tuple[pd.Series, pd.Series, dict]:
    """Feature-flagged state-machine implementation with hierarchical exits.

    Exits are evaluated before entries per bar. Optional re-entry block and
    cooldown are enforced. Volatility and session filters are applied to
    suppress entries outside valid conditions. Equity-heat guard controls
    pyramiding readiness (signal-level only; execution layer enforces size).
    """
    # Coerce numeric params used in logic
    p = {
        **params,
        'max_holding_period': _as_pos_int(params.get('max_holding_period', 100)),
        'adx_threshold': float(params.get('adx_threshold', 25)),
        'chandelier_atr_multiplier': float(params.get('chandelier_atr_multiplier', 3.0)),
        'upper_outer_mult': float(params.get('upper_outer_mult', 2.0)),
        'lower_outer_mult': float(params.get('lower_outer_mult', 2.0)),
        'upper_inner_mult': float(params.get('upper_inner_mult', 1.2)),
        'lower_inner_mult': float(params.get('lower_inner_mult', 1.2)),
        'rsi_oversold': float(params.get('rsi_oversold', 30)),
        'ranging_trigger_window': _as_pos_int(params.get('ranging_trigger_window', 3)),
        'cooldown_bars': _as_pos_int(params.get('cooldown_bars', 3)),
        'max_equity_heat_pct': float(params.get('max_equity_heat_pct', 2.0)),
        'min_addon_distance_ATR': float(params.get('min_addon_distance_ATR', 0.8)),
    }

    indicators = compute_indicators(price, p, toggles)
    close = price['Close']
    low = price['Low']
    high = price['High']
    open_ = price['Open']
    fast_dma = indicators['fast_dma']
    slow_dma = indicators['slow_dma']
    atr = indicators['atr']
    cha_atr = indicators['cha_atr']
    rsi = indicators['rsi']
    adx = indicators['adx']
    stoch_k = indicators['stoch_k']
    stoch_d = indicators['stoch_d']

    # Bands (upper/lower/inner mainly for range exits)
    upper_inner = fast_dma + p['upper_inner_mult'] * atr

    is_trending = fast_dma > slow_dma
    regime = compute_regime(is_trending, adx, p)

    # Filters
    valid_vol = apply_vol_filter(atr, close, p) if flags.get('feature_volatility_filter', False) else pd.Series(True, index=close.index)
    valid_sess = apply_session_filter(price.index, p) if flags.get('feature_session_filter', False) else pd.Series(True, index=close.index)
    # Dead zone filter: suppress entries if ADX below threshold for last dead_bars
    dead_bars = _as_pos_int(p.get('dead_bars', 10))
    adx_dead_threshold = float(p.get('adx_dead_threshold', 15))
    weak = (adx < adx_dead_threshold).rolling(window=dead_bars, min_periods=dead_bars).sum() == dead_bars
    not_dead_zone = ~weak
    # Friday cutoff
    valid_fri = apply_friday_cutoff(price.index, p)
    valid_bar = (valid_vol & valid_sess & not_dead_zone & valid_fri).astype(bool)

    n = len(price)
    entries_arr = np.zeros(n, dtype=bool)
    exits_arr = np.zeros(n, dtype=bool)
    block_reentry_arr = np.zeros(n, dtype=bool)

    in_trade = False
    bars_in_trade = 0
    highest_high_since_entry = 0.0
    entry_price = 0.0
    stop_price = 0.0
    partial_taken = False
    cooldown = 0
    consec_losses = 0
    ranging_entry_armed = 0
    open_layers = 0
    last_addon_price = 0.0
    max_layers = int((toggles or {}).get('max_layers', 3))

    # arrays
    close_a = close.to_numpy(dtype=float, copy=False)
    low_a = low.to_numpy(dtype=float, copy=False)
    high_a = high.to_numpy(dtype=float, copy=False)
    open_a = open_.to_numpy(dtype=float, copy=False)
    fast_dma_a = fast_dma.to_numpy(dtype=float, copy=False)
    slow_dma_a = slow_dma.to_numpy(dtype=float, copy=False)
    atr_a = atr.to_numpy(dtype=float, copy=False)
    cha_atr_a = cha_atr.to_numpy(dtype=float, copy=False)
    rsi_a = rsi.to_numpy(dtype=float, copy=False)
    adx_a = adx.to_numpy(dtype=float, copy=False)
    stoch_k_a = stoch_k.to_numpy(dtype=float, copy=False)
    stoch_d_a = stoch_d.to_numpy(dtype=float, copy=False)
    regime_a = regime.to_numpy(dtype=object, copy=False)
    valid_bar_a = valid_bar.to_numpy(dtype=bool, copy=False)

    # Debug/advanced outputs
    stop_track = np.full(n, np.nan, dtype=float)
    be_track = np.full(n, np.nan, dtype=float)
    chandelier_track = np.full(n, np.nan, dtype=float)
    entry_track = np.full(n, np.nan, dtype=float)

    for i in range(1, n):
        # --- Setup tracking ---
        # Arm ranging setup when regime is range and conditions satisfy
        if regime_a[i] == 'range' and compute_setup(low_a[i], slow_dma_a[i], atr_a[i], rsi_a[i], p):
            ranging_entry_armed = p['ranging_trigger_window']
        elif ranging_entry_armed > 0:
            ranging_entry_armed -= 1

        # --- Exits FIRST ---
        if in_trade:
            bars_in_trade += 1
            if high_a[i] > highest_high_since_entry:
                highest_high_since_entry = high_a[i]

            # Hierarchical stop/management
            new_stop, partial_taken, chandelier_stop, r_value = manage_position(
                i,
                entry_price,
                stop_price,
                highest_high_since_entry,
                fast_dma_a[i],
                slow_dma_a[i],
                atr_a[i],
                cha_atr_a[i],
                adx_a[i],
                partial_taken,
                p,
            )
            stop_price = max(stop_price, new_stop)
            stop_track[i] = stop_price
            be_track[i] = entry_price
            chandelier_track[i] = chandelier_stop

            # Exit conditions
            time_stop = bars_in_trade >= p['max_holding_period']
            adx_stop = (regime_a[i] == 'trend') and (adx_a[i] < p['adx_threshold'])
            stop_hit = low_a[i] < stop_price
            chandelier_hit = low_a[i] < chandelier_stop
            trend_invalidation = close_a[i] < slow_dma_a[i]
            range_profit_exit = (regime_a[i] != 'trend') and (high_a[i] >= upper_inner.iloc[i])

            if time_stop or adx_stop or stop_hit or chandelier_hit or trend_invalidation or range_profit_exit:
                exits_arr[i] = True
                in_trade = False
                block_reentry_arr[i] = flags.get('feature_block_reentry_same_bar', True)
                cooldown = p['cooldown_bars'] if flags.get('feature_cooldowns', True) else 0
                # loss tracking for equity guards
                if close_a[i] < entry_price:
                    consec_losses += 1
                else:
                    consec_losses = 0
                # reset state
                ranging_entry_armed = 0
                open_layers = 0
                entry_price = 0.0
                stop_price = 0.0
                partial_taken = False
                bars_in_trade = 0
                last_addon_price = 0.0

        # --- Add-on logic while in trade (before fresh entries) ---
        if in_trade and flags.get('feature_pyramiding_addon_distance', True):
            if open_layers < max_layers and regime_a[i] == 'trend':
                size_frac = float((toggles or {}).get('position_size', 0.30))
                if not flags.get('feature_equity_heat_guard', True) or equity_heat_guard(open_layers, size_frac, p['max_equity_heat_pct']):
                    # ensure distance from last add-on (or entry) by ATR multiple
                    base_ref = last_addon_price or entry_price
                    if close_a[i] >= base_ref + p['min_addon_distance_ATR'] * atr_a[i]:
                        entries_arr[i] = True
                        open_layers += 1
                        last_addon_price = close_a[i]

        # --- Entries (suppressed if exit this bar or filters not ok) ---
        if not in_trade:
            if block_reentry_arr[i]:
                continue
            if cooldown > 0:
                cooldown -= 1
                continue
            if not valid_bar_a[i]:
                continue
            # Max consecutive losses guard
            max_consec = int(p.get('max_consec_losses', 3))
            if consec_losses >= max_consec:
                continue

            is_trend = (regime_a[i] == 'trend')
            trend_trig, range_trig = trigger_signals(
                i,
                is_trend,
                low_a[i], open_a[i], close_a[i],
                fast_dma_a[i], atr_a[i],
                stoch_k_a[i], stoch_d_a[i],
                stoch_k_a[i-1], stoch_d_a[i-1],
                p,
            )

            allow_entry = False
            if is_trend and trend_trig:
                allow_entry = True
            elif (not is_trend) and (ranging_entry_armed > 0) and range_trig:
                allow_entry = True

            if allow_entry:
                # Equity heat guard
                if flags.get('feature_equity_heat_guard', True):
                    size_frac = float(toggles.get('position_size', 0.30) if isinstance(toggles, dict) else 0.30)
                    if not equity_heat_guard(open_layers, size_frac, p['max_equity_heat_pct']):
                        allow_entry = False

            if allow_entry:
                entries_arr[i] = True
                in_trade = True
                open_layers = 1
                entry_price = close_a[i]
                stop_price = compute_initial_stop(entry_price, atr_a[i], p)
                highest_high_since_entry = high_a[i]
                partial_taken = False
                cooldown = p['cooldown_bars'] if flags.get('feature_cooldowns', True) else 0
                block_reentry_arr[i] = flags.get('feature_block_reentry_same_bar', True)
                entry_track[i] = entry_price
                last_addon_price = entry_price

    entries = pd.Series(entries_arr, index=price.index)
    exits = pd.Series(exits_arr, index=price.index)
    indicators['upper_inner'] = upper_inner
    indicators['is_trending'] = is_trending
    indicators['regime'] = regime
    indicators['stop_price'] = pd.Series(stop_track, index=price.index)
    indicators['entry_price'] = pd.Series(entry_track, index=price.index)
    indicators['chandelier_stop'] = pd.Series(chandelier_track, index=price.index)
    return entries, exits, indicators
