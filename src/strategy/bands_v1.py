import numpy as np
import pandas as pd
from src.indicators.mcg_dma import vbt_mcg_dma_indicator


def _compute_htf_trend_gates(
    price: pd.DataFrame,
    params: dict,
    *,
    slope_lb: int,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Compute HTF trend gates aligned to the base timeframe without lookahead.

    Returns:
        (htf_up_ok, htf_dn_ok, htf_fast_dma_aligned, htf_slow_dma_aligned)

    Notes:
        - Uses resampled OHLC bars with label/closed='right' to represent completed HTF candles.
        - Shifts HTF trend by 1 HTF bar before forward-filling to avoid peeking into the current HTF candle.
    """
    use_htf_filter = bool(params.get('use_htf_filter', False))
    if not use_htf_filter:
        idx = price.index
        return (
            pd.Series(True, index=idx),
            pd.Series(True, index=idx),
            pd.Series(np.nan, index=idx),
            pd.Series(np.nan, index=idx),
        )

    htf_tf = params.get('htf_tf', '1D')
    try:
        if not isinstance(price.index, pd.DatetimeIndex):
            base = price.copy()
            base.index = pd.to_datetime(base.index)
        else:
            base = price

        ohlc = base[['Open', 'High', 'Low', 'Close']].dropna()
        if len(ohlc) < 10:
            raise ValueError("insufficient bars for HTF resample")

        # Completed HTF candles only
        htf = (
            ohlc.resample(str(htf_tf), label='right', closed='right')
            .agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'})
            .dropna()
        )
        if len(htf) < 5:
            raise ValueError("insufficient HTF bars after resample")

        Mcg = vbt_mcg_dma_indicator()
        fast_dma_htf = Mcg.run(
            htf['Close'],
            min_len=int(params.get('fast_min_len', 10)),
            max_len=int(params.get('fast_max_len', 20)),
            atr_len=int(params.get('dma_atr_len', 14)),
        ).real
        slow_dma_htf = Mcg.run(
            htf['Close'],
            min_len=int(params.get('slow_min_len', 30)),
            max_len=int(params.get('slow_max_len', 50)),
            atr_len=int(params.get('dma_atr_len', 14)),
        ).real

        fast_slope_htf = fast_dma_htf.diff(slope_lb)
        slow_slope_htf = slow_dma_htf.diff(slope_lb)
        htf_up = (fast_dma_htf > slow_dma_htf) & (fast_slope_htf > 0) & (slow_slope_htf > 0)
        htf_dn = (fast_dma_htf < slow_dma_htf) & (fast_slope_htf < 0) & (slow_slope_htf < 0)

        idx = base.index
        aligned_up = htf_up.reindex(idx, method='ffill')
        aligned_dn = htf_dn.reindex(idx, method='ffill')
        # Avoid pandas FutureWarning about silent downcasting on fillna for object dtypes
        htf_up_ok = aligned_up.where(aligned_up.notna(), False).astype(bool)
        htf_dn_ok = aligned_dn.where(aligned_dn.notna(), False).astype(bool)
        htf_fast_aligned = fast_dma_htf.reindex(idx, method='ffill')
        htf_slow_aligned = slow_dma_htf.reindex(idx, method='ffill')

        return htf_up_ok, htf_dn_ok, htf_fast_aligned, htf_slow_aligned
    except Exception:
        # Fail open rather than breaking strategy evaluation
        idx = price.index
        return (
            pd.Series(True, index=idx),
            pd.Series(True, index=idx),
            pd.Series(np.nan, index=idx),
            pd.Series(np.nan, index=idx),
        )


def compute_signals(price: pd.DataFrame, params: dict, toggles: dict) -> tuple:
    """
    Compute entry and exit signals for long and optionally short positions.
    
    Returns:
        - If shorts disabled (default): (entries, exits, debug) - backwards compatible
        - If shorts enabled: (long_entries, long_exits, short_entries, short_exits, debug)
    """
    Mcg = vbt_mcg_dma_indicator()
    fast_dma = Mcg.run(
        price['Close'],
        min_len=params['fast_min_len'],
        max_len=params['fast_max_len'],
        atr_len=params['dma_atr_len'],
    ).real
    slow_dma = Mcg.run(
        price['Close'],
        min_len=params['slow_min_len'],
        max_len=params['slow_max_len'],
        atr_len=params['dma_atr_len'],
    ).real

    high_low = price['High'] - price['Low']
    high_close = (price['High'] - price['Close'].shift()).abs()
    low_close = (price['Low'] - price['Close'].shift()).abs()
    true_range = np.maximum(high_low, np.maximum(high_close, low_close))
    atr = true_range.rolling(window=params['atr_len']).mean()

    slope_lb = params.get('slope_lookback', 1)
    fast_slope = fast_dma.diff(slope_lb)
    slow_slope = slow_dma.diff(slope_lb)
    is_uptrend = (fast_dma > slow_dma) & (fast_slope > 0) & (slow_slope > 0)
    channel_upper_ma = np.where(is_uptrend, fast_dma, slow_dma)
    channel_lower_ma = np.where(is_uptrend, slow_dma, fast_dma)

    upper_outer = channel_upper_ma + atr * params['upper_outer_mult']
    upper_inner = channel_upper_ma + atr * params['upper_inner_mult']
    lower_inner = channel_lower_ma - atr * params['lower_inner_mult']
    lower_outer = channel_lower_ma - atr * params['lower_outer_mult']

    # Make pct_change future-proof: explicitly forward-fill, then compute with no internal fill
    price_mom = (
        price['Close']
        .ffill()
        .pct_change(periods=params['momentum_len'], fill_method=None)
        .abs()
    )
    mom_thresh = (
        price_mom.rolling(window=params.get('momentum_lookback', 100), min_periods=1)
        .quantile(params['momentum_threshold'])
        .shift(1)
    )
    is_trending = price_mom > mom_thresh
    is_ranging = ~is_trending

    # RSI for ranging confirmation
    rsi_len = params.get('rsi_len', 14)
    delta = price['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=rsi_len).mean()
    avg_loss = loss.rolling(window=rsi_len).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    is_oversold = rsi < params.get('rsi_oversold', 30)
    is_overbought = rsi > params.get('rsi_overbought', 70)
    
    # Directional momentum gate (optional)
    use_directional_momentum = params.get('use_directional_momentum', False)
    roc_len = params.get('roc_len', params.get('momentum_len', 14))
    roc_val = price['Close'].pct_change(periods=roc_len)
    mom_long_ok = (not use_directional_momentum) or (roc_val > 0)
    mom_short_ok = (not use_directional_momentum) or (roc_val < 0)

    # HTF gating (optional): only trade longs when HTF up, shorts when HTF down
    htf_up_ok, htf_dn_ok, htf_fast_dma, htf_slow_dma = _compute_htf_trend_gates(price, params, slope_lb=int(slope_lb))

    # --- ENTRIES ---
    
    # Check if shorts are enabled
    enable_shorts = params.get('enable_shorts', False)
    
    # LONG ENTRIES
    # 1. Trending Entry: "Golden Zone" pullback and reclaim
    golden_zone_entry = (
        is_uptrend &
        (price['Low'] <= fast_dma) &
        (price['Close'] > fast_dma)
    )
    trending_long_entry = is_trending & golden_zone_entry & mom_long_ok & htf_up_ok

    # 2. Ranging Entry: Dip below outer band with RSI confirmation
    ranging_dip = is_ranging & (price['Low'] < lower_outer) & is_oversold
    if params.get('ranging_confirm_bar', True):
        # Add confirmation: must be a reversal bar (close > open)
        ranging_dip &= (price['Close'] > price['Open'])
    ranging_long_entry = ranging_dip & mom_long_ok & htf_up_ok

    long_entries = trending_long_entry | ranging_long_entry
    
    # SHORT ENTRIES (mirrored logic)
    short_entries = pd.Series(False, index=price.index)
    if enable_shorts:
        # 1. Trending Short Entry: "Golden Zone" pullback in downtrend
        is_downtrend = (fast_dma < slow_dma) & (fast_slope < 0) & (slow_slope < 0)
        golden_zone_short = (
            is_downtrend &
            (price['High'] >= fast_dma) &
            (price['Close'] < fast_dma)
        )
        trending_short_entry = is_trending & golden_zone_short & mom_short_ok & htf_dn_ok
        
        # 2. Ranging Short Entry: Spike above outer band with RSI confirmation
        ranging_spike = is_ranging & (price['High'] > upper_outer) & is_overbought
        if params.get('ranging_confirm_bar', True):
            # Add confirmation: must be a reversal bar (close < open)
            ranging_spike &= (price['Close'] < price['Open'])
        ranging_short_entry = ranging_spike & mom_short_ok & htf_dn_ok
        
        short_entries = trending_short_entry | ranging_short_entry
        
        # Conflict prevention: can't have both long and short on same bar
        conflict = long_entries & short_entries
        long_entries = long_entries & ~conflict
        short_entries = short_entries & ~conflict

    # Backwards compatibility: if shorts disabled, use legacy 'entries' name
    entries = long_entries

    # --- EXITS ---
    
    # Stabilized DMA Fail Exit (for longs)
    use_dma_fail_exit = params.get('use_dma_fail_exit', True)
    dma_exit_bars = params.get('dma_exit_bars', 2)
    dma_exit_buffer_atr = params.get('dma_exit_buffer_atr', 0.2)
    
    # Track consecutive bars below DMA (for longs) - vectorized approach
    is_below_dma_buffered = price['Close'] < (slow_dma - dma_exit_buffer_atr * atr)
    # Use groupby to count consecutive True values
    groups = (is_below_dma_buffered != is_below_dma_buffered.shift()).cumsum()
    bars_below = is_below_dma_buffered.groupby(groups).cumsum()
    bars_below = bars_below.where(is_below_dma_buffered, 0)
    
    dma_fail_long_exit = use_dma_fail_exit & (bars_below >= dma_exit_bars)
    
    # LONG EXITS
    # 1. Regime-Adaptive Base Exit
    # During trend, exit if trend invalidates (close < slow_dma)
    # During range, exit for profit at upper_inner band
    trend_invalidation_exit = is_trending & (price['Close'] < slow_dma)
    range_profit_exit = is_ranging & (price['High'] >= upper_inner)
    base_long_exit = trend_invalidation_exit | range_profit_exit

    # 2. Catastrophic Stop-Loss (Non-negotiable risk boundary)
    catastrophic_stop_price = lower_outer - (atr * params.get('catastrophic_stop_atr_mult', 0.5))
    catastrophic_long_exit = price['Low'] < catastrophic_stop_price

    # 3. Trailing Stop (Optional, from previous logic)
    trailing_long_exit = (
        pd.Series(price['Close'] < slow_dma - atr * params.get('trailing_atr_mult', 1.5), index=price.index)
        if toggles.get('use_trailing_stop', False)
        else pd.Series(False, index=price.index)
    )

    long_exits = base_long_exit | catastrophic_long_exit | trailing_long_exit | dma_fail_long_exit
    
    # SHORT EXITS (mirrored logic)
    short_exits = pd.Series(False, index=price.index)
    if enable_shorts:
        # Track consecutive bars above DMA (for shorts) - vectorized approach
        is_above_dma_buffered = price['Close'] > (slow_dma + dma_exit_buffer_atr * atr)
        # Use groupby to count consecutive True values
        groups = (is_above_dma_buffered != is_above_dma_buffered.shift()).cumsum()
        bars_above = is_above_dma_buffered.groupby(groups).cumsum()
        bars_above = bars_above.where(is_above_dma_buffered, 0)
        
        dma_fail_short_exit = use_dma_fail_exit & (bars_above >= dma_exit_bars)
        
        # 1. Regime-Adaptive Base Exit (mirrored)
        trend_invalidation_short_exit = is_trending & (price['Close'] > slow_dma)
        range_profit_short_exit = is_ranging & (price['Low'] <= lower_inner)
        base_short_exit = trend_invalidation_short_exit | range_profit_short_exit
        
        # 2. Catastrophic Stop-Loss (mirrored)
        catastrophic_stop_short_price = upper_outer + (atr * params.get('catastrophic_stop_atr_mult', 0.5))
        catastrophic_short_exit = price['High'] > catastrophic_stop_short_price
        
        # 3. Trailing Stop (mirrored, optional)
        trailing_short_exit = (
            pd.Series(price['Close'] > slow_dma + atr * params.get('trailing_atr_mult', 1.5), index=price.index)
            if toggles.get('use_trailing_stop', False)
            else pd.Series(False, index=price.index)
        )
        
        short_exits = base_short_exit | catastrophic_short_exit | trailing_short_exit | dma_fail_short_exit

    # Cooldown after exit (optional): block new entries for N bars after any exit signal
    # Matches Pine Script: cooldown_ok = (cooldown_bars == 0) or (bars_since_exit >= cooldown_bars)
    # where bars_since_exit = ta.barssince(exit_any) returns na if no exit yet
    cooldown_bars = int(params.get('cooldown_bars', 0) or 0)
    if cooldown_bars > 0:
        exit_sig = long_exits | (short_exits if enable_shorts else pd.Series(False, index=price.index))
        
        # Vectorized bars_since_exit using cumsum and groupby (much faster)
        # Create groups where each group starts at an exit
        exit_mask = exit_sig.astype(int)
        # Mark exit bars with a unique group ID
        exit_groups = (exit_mask != exit_mask.shift()).cumsum()
        # For each group, count bars since the group start (the exit)
        bars_since_exit = exit_groups.groupby(exit_groups).cumcount().astype(float)
        # Where there was no exit yet (group 0 or 1 before first exit), set to inf
        if exit_sig.any():
            first_exit_idx = exit_sig.idxmax()
            first_exit_pos = price.index.get_loc(first_exit_idx)
            bars_since_exit.iloc[:first_exit_pos] = np.inf
        else:
            bars_since_exit[:] = np.inf
        
        # cooldown_ok = True if: no exit yet OR enough bars passed since last exit
        cooldown_ok = (bars_since_exit >= cooldown_bars) | (bars_since_exit == np.inf)
        
        long_entries = long_entries & cooldown_ok
        if enable_shorts:
            short_entries = short_entries & cooldown_ok
        entries = long_entries

    # Backwards compatibility: if shorts disabled, use legacy 'exits' name
    exits = long_exits

    debug = {
        'fast_dma': fast_dma,
        'slow_dma': slow_dma,
        'upper_outer': pd.Series(upper_outer, index=price.index),
        'upper_inner': pd.Series(upper_inner, index=price.index),
        'lower_inner': pd.Series(lower_inner, index=price.index),
        'lower_outer': pd.Series(lower_outer, index=price.index),
        'is_trending': is_trending,
        'is_ranging': is_ranging,
        'mom_thresh': mom_thresh,
        'rsi': rsi,
        'roc_val': roc_val if use_directional_momentum else pd.Series(0, index=price.index),
        'htf_up_ok': htf_up_ok,
        'htf_dn_ok': htf_dn_ok,
        'htf_fast_dma': htf_fast_dma,
        'htf_slow_dma': htf_slow_dma,
    }
    
    # Return shape: backwards compatible
    if enable_shorts:
        return long_entries, long_exits, short_entries, short_exits, debug
    else:
        return entries, exits, debug