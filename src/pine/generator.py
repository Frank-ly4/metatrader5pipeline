"""PineScript v6 generator for the McGinley DMA bands strategy (Option B pyramiding).

Given a params dict (keys without the `param_` prefix), returns a Pine v6
strategy script with:
- Layered pyramiding (pyramiding=3, 30% per layer)
- McGinley DMA fast/slow computed with dynamic length
- ATR-based envelopes (inner/outer)
- Bidirectional entry/exit logic (long + short) matching Python `compute_signals` v1
- Stabilized DMA fail exits
"""

from __future__ import annotations

from textwrap import dedent


def _header(title: str, initial_capital: float, fees_frac: float) -> str:
    # Pine wants commission_value in percent (e.g., 0.045 for 0.045%)
    commission_percent = fees_frac * 100.0
    return (
        f"//@version=6\n"
        f"strategy(title=\"{title}\", overlay=true, initial_capital={initial_capital}, "
        f"commission_type=strategy.commission.percent, commission_value={commission_percent:.6f}, "
        f"default_qty_type=strategy.percent_of_equity, default_qty_value=30, pyramiding=3)\n"
    )


def _format_float(value: float) -> str:
    return ("%.10g" % float(value))


def generate_pinescript(params: dict, *, meta: dict | None = None) -> str:
    """Build a PineScript v6 string from params (bidirectional v4.3+).

    params keys expected:
      fast_min_len, fast_max_len, slow_min_len, slow_max_len,
      dma_atr_len, atr_len,
      upper_outer_mult, lower_outer_mult, upper_inner_mult, lower_inner_mult,
      momentum_len, momentum_threshold,
      enable_shorts, rsi_overbought, use_dma_fail_exit, dma_exit_bars, dma_exit_buffer_atr,
      use_directional_momentum, roc_len, rsi_len, rsi_oversold
    """
    meta = meta or {}
    version = "v4.3" if params.get('enable_shorts', False) else "v4.2"
    title = meta.get("title", f"Gold Bands {version} – {meta.get('run_id','run')}/{meta.get('trial_id','trial')}")
    initial_capital = meta.get("initial_capital", 500.0)
    fees = meta.get("fees", 0.0005)

    # Unpack with defaults
    p = {
        'fast_min_len': params.get('fast_min_len', 10),
        'fast_max_len': params.get('fast_max_len', 20),
        'slow_min_len': params.get('slow_min_len', 30),
        'slow_max_len': params.get('slow_max_len', 50),
        'dma_atr_len': params.get('dma_atr_len', 14),
        'atr_len': params.get('atr_len', 14),
        'upper_outer_mult': params.get('upper_outer_mult', 2.0),
        'lower_outer_mult': params.get('lower_outer_mult', 2.0),
        'upper_inner_mult': params.get('upper_inner_mult', 1.2),
        'lower_inner_mult': params.get('lower_inner_mult', 1.2),
        'momentum_len': params.get('momentum_len', 14),
        'momentum_threshold': params.get('momentum_threshold', 0.70),
        'momentum_lookback': params.get('momentum_lookback', 75),
        'slope_lookback': params.get('slope_lookback', 1),
        'rsi_len': params.get('rsi_len', 14),
        'rsi_oversold': params.get('rsi_oversold', 30),
        'rsi_overbought': params.get('rsi_overbought', 70),
        'enable_shorts': params.get('enable_shorts', False),
        'use_dma_fail_exit': params.get('use_dma_fail_exit', True),
        'dma_exit_bars': params.get('dma_exit_bars', 2),
        'dma_exit_buffer_atr': params.get('dma_exit_buffer_atr', 0.2),
        'use_directional_momentum': params.get('use_directional_momentum', False),
        'roc_len': params.get('roc_len', params.get('momentum_len', 14)),
        'ranging_confirm_bar': params.get('ranging_confirm_bar', True),
        # HTF gating
        'use_htf_filter': params.get('use_htf_filter', False),
        'htf_tf': params.get('htf_tf', '1D'),
        # Anti-chop cooldown
        'cooldown_bars': params.get('cooldown_bars', 0),
    }

    # Compose script
    enable_shorts_str = "true" if p['enable_shorts'] else "false"
    use_dma_fail_str = "true" if p['use_dma_fail_exit'] else "false"
    use_dir_mom_str = "true" if p['use_directional_momentum'] else "false"
    ranging_confirm_str = "true" if p['ranging_confirm_bar'] else "false"
    use_htf_str = "true" if p['use_htf_filter'] else "false"
    
    script = f"""
{_header(title, float(initial_capital), float(fees))}

// --- Identifiers / metadata
var string run_id = "{meta.get('run_id','')}"
var string trial_id = "{meta.get('trial_id','')}"
var string chart_name = "{meta.get('chart','')}"

// --- Inputs (fixed to selected params)
fast_min_len = input.int(defval={int(p['fast_min_len'])}, title='fast_min_len')
fast_max_len = input.int(defval={int(p['fast_max_len'])}, title='fast_max_len')
slow_min_len = input.int(defval={int(p['slow_min_len'])}, title='slow_min_len')
slow_max_len = input.int(defval={int(p['slow_max_len'])}, title='slow_max_len')

dma_atr_len  = input.int(defval={int(p['dma_atr_len'])},  title='dma_atr_len')
atr_len      = input.int(defval={int(p['atr_len'])},      title='atr_len')

upper_outer_mult = input.float(defval={_format_float(p['upper_outer_mult'])}, title='upper_outer_mult')
lower_outer_mult = input.float(defval={_format_float(p['lower_outer_mult'])}, title='lower_outer_mult')
upper_inner_mult = input.float(defval={_format_float(p['upper_inner_mult'])}, title='upper_inner_mult')
lower_inner_mult = input.float(defval={_format_float(p['lower_inner_mult'])}, title='lower_inner_mult')

momentum_len        = input.int(defval={int(p['momentum_len'])}, title='momentum_len')
momentum_threshold  = input.float(defval={_format_float(p['momentum_threshold'])}, title='momentum_threshold (quantile)')
momentum_lookback   = input.int(defval={int(p['momentum_lookback'])}, title='momentum_lookback')
slope_lookback      = input.int(defval={int(p['slope_lookback'])}, title='slope_lookback')

rsi_len        = input.int(defval={int(p['rsi_len'])}, title='rsi_len')
rsi_oversold   = input.int(defval={int(p['rsi_oversold'])}, title='rsi_oversold')
rsi_overbought  = input.int(defval={int(p['rsi_overbought'])}, title='rsi_overbought')

// Bidirectional settings
enable_shorts = input.bool(defval={enable_shorts_str}, title='Enable Shorts')
use_dma_fail_exit = input.bool(defval={use_dma_fail_str}, title='Use DMA Fail Exit')
dma_exit_bars = input.int(defval={int(p['dma_exit_bars'])}, title='DMA Exit: Req. Consecutive Bars', minval=1)
dma_exit_buffer_atr = input.float(defval={_format_float(p['dma_exit_buffer_atr'])}, title='DMA Exit: Buffer (ATR)', step=0.1)

use_directional_momentum = input.bool(defval={use_dir_mom_str}, title='Use Directional Momentum Filter')
roc_len = input.int(defval={int(p['roc_len'])}, title='ROC Length')

ranging_confirm_bar = input.bool(defval={ranging_confirm_str}, title='Ranging: Require Reversal Bar')

// HTF gating (optional)
use_htf_filter = input.bool(defval={use_htf_str}, title='Use HTF Trend Filter')
htf_tf = input.timeframe(defval="{p['htf_tf']}", title='HTF Timeframe')

// Anti-chop cooldown
cooldown_bars = input.int(defval={int(p['cooldown_bars'])}, title='Cooldown Bars After Exit', minval=0)

// --- Helper: Simple TR-based ATR (SMA of TR)
tr_hl = high - low
tr_hc = math.abs(high - close[1])
tr_lc = math.abs(low - close[1])
tr = math.max(tr_hl, math.max(tr_hc, tr_lc))
atr_sma = ta.sma(tr, atr_len)

// --- McGinley DMA dynamic length, approximated with volatility index
f_mcg_dma(src, min_len, max_len, atr_len) =>
    // Compute local TR in the current timeframe context (works under request.security too)
    tr_hl_local = high - low
    tr_hc_local = math.abs(high - close[1])
    tr_lc_local = math.abs(low - close[1])
    tr_local = math.max(tr_hl_local, math.max(tr_hc_local, tr_lc_local))
    volatility = ta.sma(tr_local, atr_len) / src
    vol_low = ta.lowest(volatility, 100)
    vol_high = ta.highest(volatility, 100)
    vol_range = math.max(vol_high - vol_low, 1e-9)
    vol_index = (volatility - vol_low) / vol_range
    dyn_len = max_len - (max_len - min_len) * vol_index
    final_len = math.round(dyn_len)
    alpha = 2.0 / (final_len + 1)
    var float dma = na
    dma := na(dma[1]) ? src : alpha * src + (1 - alpha) * dma[1]
    dma

fast_dma = f_mcg_dma(close, fast_min_len, fast_max_len, dma_atr_len)
slow_dma = f_mcg_dma(close, slow_min_len, slow_max_len, dma_atr_len)

// HTF trend gate (no-lookahead: shift by 1 HTF bar)
htf_fast_dma = request.security(syminfo.tickerid, htf_tf, f_mcg_dma(close, fast_min_len, fast_max_len, dma_atr_len), barmerge.gaps_off, barmerge.lookahead_off)
htf_slow_dma = request.security(syminfo.tickerid, htf_tf, f_mcg_dma(close, slow_min_len, slow_max_len, dma_atr_len), barmerge.gaps_off, barmerge.lookahead_off)
htf_fast_slope = htf_fast_dma - htf_fast_dma[slope_lookback]
htf_slow_slope = htf_slow_dma - htf_slow_dma[slope_lookback]
htf_up_ok = (htf_fast_dma > htf_slow_dma) and (htf_fast_slope > 0) and (htf_slow_slope > 0)
htf_dn_ok = (htf_fast_dma < htf_slow_dma) and (htf_fast_slope < 0) and (htf_slow_slope < 0)

// Trend detection with slope
fast_slope = fast_dma - fast_dma[slope_lookback]
slow_slope = slow_dma - slow_dma[slope_lookback]
is_uptrend = (fast_dma > slow_dma) and (fast_slope > 0) and (slow_slope > 0)
is_downtrend = (fast_dma < slow_dma) and (fast_slope < 0) and (slow_slope < 0)

channel_upper_ma = is_uptrend ? fast_dma : slow_dma
channel_lower_ma = is_uptrend ? slow_dma : fast_dma

upper_outer = channel_upper_ma + atr_sma * upper_outer_mult
upper_inner = channel_upper_ma + atr_sma * upper_inner_mult
lower_inner = channel_lower_ma - atr_sma * lower_inner_mult
lower_outer = channel_lower_ma - atr_sma * lower_outer_mult

// --- Momentum filter (approximate percentile)
mom = math.abs(close / close[momentum_len] - 1)
mom_thresh = momentum_threshold * 100.0
mom_prank = ta.percentrank(mom, momentum_lookback)
is_trending = mom_prank > mom_thresh
is_ranging = not is_trending

// --- RSI
rsi = ta.rsi(close, rsi_len)
is_oversold_rsi = rsi < rsi_oversold
is_overbought_rsi = rsi > rsi_overbought

// --- Directional momentum gate (optional)
roc_val = ta.roc(close, roc_len)
mom_long_ok = (not use_directional_momentum) or (roc_val > 0)
mom_short_ok = (not use_directional_momentum) or (roc_val < 0)

// --- LONG ENTRIES
// 1. Trending Entry: Golden Zone pullback
golden_zone_entry = is_uptrend and (low <= fast_dma) and (close > fast_dma)
trending_long_entry = is_trending and golden_zone_entry and mom_long_ok

// 2. Ranging Entry: Dip below outer band with RSI confirmation
ranging_dip = is_ranging and (low < lower_outer) and is_oversold_rsi
if ranging_confirm_bar
    ranging_dip := ranging_dip and (close > open)
ranging_long_entry = ranging_dip and mom_long_ok

// Apply HTF gate (optional)
long_entries = (trending_long_entry or ranging_long_entry) and (not use_htf_filter or htf_up_ok)

// --- SHORT ENTRIES (mirrored logic)
short_entries = false
if enable_shorts
    // 1. Trending Short Entry: Golden Zone pullback in downtrend
    golden_zone_short = is_downtrend and (high >= fast_dma) and (close < fast_dma)
    trending_short_entry = is_trending and golden_zone_short and mom_short_ok
    
    // 2. Ranging Short Entry: Spike above outer band with RSI confirmation
    ranging_spike = is_ranging and (high > upper_outer) and is_overbought_rsi
    if ranging_confirm_bar
        ranging_spike := ranging_spike and (close < open)
    ranging_short_entry = ranging_spike and mom_short_ok
    
    short_entries := (trending_short_entry or ranging_short_entry) and (not use_htf_filter or htf_dn_ok)
    
    // Conflict prevention
    if long_entries and short_entries
        long_entries := false
        short_entries := false

// --- LONG EXITS
// Stabilized DMA Fail Exit
is_below_dma_buffered = close < (slow_dma - dma_exit_buffer_atr * atr_sma)
var int bars_below = 0
if is_below_dma_buffered
    bars_below := bars_below[1] + 1
else
    bars_below := 0
dma_fail_long_exit = use_dma_fail_exit and (bars_below >= dma_exit_bars)

// Base exits
trend_invalidation_exit = is_trending and (close < slow_dma)
range_profit_exit = is_ranging and (high >= upper_inner)
base_long_exit = trend_invalidation_exit or range_profit_exit

long_exits = base_long_exit or dma_fail_long_exit

// --- SHORT EXITS (mirrored logic)
short_exits = false
if enable_shorts
    // Stabilized DMA Fail Exit (mirrored)
    is_above_dma_buffered = close > (slow_dma + dma_exit_buffer_atr * atr_sma)
    var int bars_above = 0
    if is_above_dma_buffered
        bars_above := bars_above[1] + 1
    else
        bars_above := 0
    dma_fail_short_exit = use_dma_fail_exit and (bars_above >= dma_exit_bars)
    
    // Base exits (mirrored)
    trend_invalidation_short_exit = is_trending and (close > slow_dma)
    range_profit_short_exit = is_ranging and (low <= lower_inner)
    base_short_exit = trend_invalidation_short_exit or range_profit_short_exit
    
    short_exits := base_short_exit or dma_fail_short_exit

// Cooldown after exit (optional): blocks entries for N bars after any exit
exit_any = long_exits or (enable_shorts and short_exits)
bars_since_exit = ta.barssince(exit_any)
cooldown_ok = (cooldown_bars == 0) or (bars_since_exit >= cooldown_bars)

long_entries := long_entries and cooldown_ok
if enable_shorts
    short_entries := short_entries and cooldown_ok

// --- Orders (Option B pyramiding, 30% layers via default_qty_type)
if long_entries
    strategy.entry("L", strategy.long)
if long_exits
    strategy.close("L", comment="long-exit")

if enable_shorts
    if short_entries
        strategy.entry("S", strategy.short)
    if short_exits
        strategy.close("S", comment="short-exit")

// --- Plots
plot(fast_dma, color=color.new(color.orange, 0), title='fast_dma')
plot(slow_dma, color=color.new(color.blue, 0), title='slow_dma')
plot(upper_outer, color=color.new(color.red, 30), title='upper_outer')
plot(upper_inner, color=color.new(color.red, 70), title='upper_inner')
plot(lower_inner, color=color.new(color.green, 70), title='lower_inner')
plot(lower_outer, color=color.new(color.green, 30), title='lower_outer')

// Signal markers
plotshape(long_entries, title="Long Entry", style=shape.triangleup, location=location.belowbar, size=size.tiny, color=color.new(color.green, 0))
plotshape(long_exits, title="Long Exit", style=shape.xcross, location=location.abovebar, size=size.tiny, color=color.new(color.red, 0))
if enable_shorts
    plotshape(short_entries, title="Short Entry", style=shape.triangledown, location=location.abovebar, size=size.tiny, color=color.new(color.fuchsia, 0))
    plotshape(short_exits, title="Short Exit", style=shape.xcross, location=location.belowbar, size=size.tiny, color=color.new(color.orange, 0))
"""
    return dedent(script)



