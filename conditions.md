# Trading System Conditions Analysis & Default Settings

## 🔄 BIDIRECTIONAL SUPPORT (v4.3+)

### Overview
The strategy now supports **bidirectional trading** (long + short positions) with mirrored entry/exit logic. This enables profitable trading in both uptrending and downtrending markets.

### Key Features
- **Short Entries**: Mirrored logic for downtrends and ranging markets
- **Stabilized DMA Fail Exit**: Prevents premature exits on noisy candles (requires N consecutive bars)
- **Directional Momentum Gate**: Optional filter to prevent shorts in upward impulse and longs in downward impulse
- **Conflict Prevention**: Long and short entries cannot fire on the same bar

### New Parameters (v1)
- `enable_shorts` (bool, default: False): Enable short position entries/exits
- `rsi_overbought` (int, default: 70): RSI threshold for short entries in ranging markets
- `use_dma_fail_exit` (bool, default: True): Enable stabilized DMA fail exit
- `dma_exit_bars` (int, default: 2): Consecutive bars required for DMA fail exit
- `dma_exit_buffer_atr` (float, default: 0.2): ATR buffer for DMA fail exit threshold
- `use_directional_momentum` (bool, default: False): Filter entries by ROC direction
- `roc_len` (int, default: 22): ROC period for directional momentum filter
- `use_htf_filter` (bool, default: False): Gate entries by higher-timeframe trend (reduces chop)
- `htf_tf` (string, default: "1D"): HTF timeframe used for gating (optimizer can now sample discrete HTFs)
- `cooldown_bars` (int, default: 0): Block entries for N bars after any exit (anti-whipsaw)

### Return Shape
- **Legacy (shorts disabled)**: `(entries, exits, debug)` - backwards compatible
- **Bidirectional (shorts enabled)**: `(long_entries, long_exits, short_entries, short_exits, debug)`

### Validation Workflow (Anti-Overfit)
1. **Regime Split Testing**: Test same params on:
   - Uptrend-heavy charts (e.g., XAUUSD in bull markets)
   - Downtrend-heavy charts (e.g., USDTHB in bear markets)
   - Choppy/mixed charts
2. **Walk-Forward Optimization**: Use `src/optimizer/wfo.py` to validate stability across time windows
3. **Robustness Check**: Nudge key params by small deltas (±0.2 ATR multipliers, ±2 lengths) and ensure performance doesn't collapse

---

## 🎯 ENTRY CONDITIONS

### Current Default Behavior (Located: `src/strategy/bands_v1.py`)

#### **Trending Market Entries** 
**Active Logic (Default):**
```python
# Slow DMA Pullback Strategy (Lines 43)
bullish_pullback = (is_uptrend) & (price['Low'] <= slow_dma) & (price['Close'] > slow_dma)
trending_long_entry = is_trending & bullish_pullback
```
- **Condition**: Buy when trending up, price touches slow DMA support, and closes above it
- **Parameters Used**: slow_min_len=28, slow_max_len=48

**Available Alternatives (Currently DISABLED):**
```python
# Toggle: 'use_trending_pullback_lowerinner' (Line 38)
bullish_pullback = (is_uptrend) & (price['Low'] <= lower_inner) & (price['Close'] > lower_inner)

# Toggle: 'use_trending_pullback_fastdma' (Line 40) 
bullish_pullback = (is_uptrend) & (price['Low'] <= fast_dma) & (price['Close'] > fast_dma)
```

#### **Ranging Market Entries**
**Active Logic (Default):**
```python
# Lower Outer Touch with RSI confirmation (v1)
ranging_dip = is_ranging & (price['Low'] < lower_outer) & is_oversold
if ranging_confirm_bar:
    ranging_dip &= (price['Close'] > price['Open'])  # Reversal bar confirmation
ranging_long_entry = ranging_dip & mom_long_ok
```
- **Condition**: Buy when ranging, price touches lower outer band, RSI oversold, and (optionally) reversal bar
- **Parameters Used**: lower_outer_mult=2.0, rsi_oversold=30, ranging_confirm_bar=True

#### **Short Entries (Bidirectional - v4.3+)**
**Trending Short Entry:**
```python
# Golden Zone pullback in downtrend
golden_zone_short = is_downtrend & (price['High'] >= fast_dma) & (price['Close'] < fast_dma)
trending_short_entry = is_trending & golden_zone_short & mom_short_ok
```

**Ranging Short Entry:**
```python
# Spike above outer band with RSI confirmation
ranging_spike = is_ranging & (price['High'] > upper_outer) & is_overbought
if ranging_confirm_bar:
    ranging_spike &= (price['Close'] < price['Open'])  # Reversal bar confirmation
ranging_short_entry = ranging_spike & mom_short_ok
```
- **Condition**: Short when ranging, price spikes above upper outer band, RSI overbought, and (optionally) reversal bar
- **Parameters Used**: upper_outer_mult=2.0, rsi_overbought=70, ranging_confirm_bar=True

#### **Market Regime Detection**
```python
# Momentum Calculation (Lines 33-35)
price_mom = price['Close'].rolling(momentum_len).apply(lambda x: pd.Series(x).rank().iloc[-1] / len(x))
mom_thresh = price_mom.quantile(momentum_threshold)
is_trending = price_mom > mom_thresh
is_ranging = ~is_trending
```
- **Momentum Length**: 14 periods (Range: 8-50)
- **Momentum Threshold**: 0.75 quantile (Range: 0.60-0.85)

---

## 🚪 EXIT CONDITIONS

### Current Default Behavior (Located: `src/strategy/bands_v1.py`)

#### **Long Exit Signals**
**1. Regime-Adaptive Base Exit:**
```python
trend_invalidation_exit = is_trending & (price['Close'] < slow_dma)
range_profit_exit = is_ranging & (price['High'] >= upper_inner)
base_long_exit = trend_invalidation_exit | range_profit_exit
```
- **Condition**: Exit on trend invalidation (close < slow_dma) or range profit target (high >= upper_inner)

**2. Stabilized DMA Fail Exit (v4.3+):**
```python
is_below_dma_buffered = price['Close'] < (slow_dma - dma_exit_buffer_atr * atr)
bars_below = consecutive_count(is_below_dma_buffered)  # Vectorized groupby
dma_fail_long_exit = use_dma_fail_exit & (bars_below >= dma_exit_bars)
```
- **Condition**: Exit after N consecutive bars below DMA by buffer*ATR
- **Parameters**: dma_exit_bars=2, dma_exit_buffer_atr=0.2
- **Purpose**: Prevents premature exits on single noisy candles

#### **Short Exit Signals (Bidirectional - v4.3+)**
**Mirrored Logic:**
```python
# Trend invalidation (mirrored)
trend_invalidation_short_exit = is_trending & (price['Close'] > slow_dma)
range_profit_short_exit = is_ranging & (price['Low'] <= lower_inner)

# Stabilized DMA Fail Exit (mirrored)
is_above_dma_buffered = price['Close'] > (slow_dma + dma_exit_buffer_atr * atr)
bars_above = consecutive_count(is_above_dma_buffered)
dma_fail_short_exit = use_dma_fail_exit & (bars_above >= dma_exit_bars)
```
- **Condition**: Exit shorts on trend invalidation (close > slow_dma) or range profit (low <= lower_inner)
- **DMA Fail**: Exit after N consecutive bars above DMA by buffer*ATR

---

## 💰 POSITION SIZING & PORTFOLIO SETTINGS

### ⚠️ CONFIGURATION CONFLICT DETECTED

**Primary Config** (`config/portfolio.py` - USED BY ENGINE):
```python
BACKTEST_CONFIG = {
    'data_freq': '2h',           # 2-hour timeframe
    'init_cash': 500.0,          # $500 starting capital
    'fees': 0.00045,             # 0.045% per trade (MT5 FTMO)
    'size': 0.30,                # 30% of portfolio per position
    'size_type': 'percent',      # Percentage-based sizing
    'max_orders': None,          # Unlimited orders
    'max_layers': 3              # Up to 3 pyramiding layers
}
```

**Secondary Config** (`config/user_inputs.py` - PARTIALLY USED):
```python
BACKTEST_CONFIG = {
    "fees": 0.0005,              # 0.05% per trade (HIGHER)
    "position_size": 0.30,       # 30% per entry layer  
    "starting_capital": 1000,    # $1000 starting capital (HIGHER)
    "data_freq": "15m",          # 15-minute timeframe (DIFFERENT)
}
```

### **Active Pyramiding System** (`src/strategy/pyramiding.py`)
```python
def layered_entries(base_entries, exits, max_layers=3):
    # Allows up to 3 position layers of 30% each
    # Maximum total exposure: 90% of portfolio
    # Resets all layers on any exit signal
```

---

## 🛡️ RISK MANAGEMENT

### **Python Backtester: NO TRADITIONAL SL/TP**
- **Risk Control Method**: Signal-based exits only
- **Position Limits**: 3 layers × 30% = 90% max exposure
- **Stop Loss**: None (relies on exit signals)
- **Take Profit**: None (relies on exit signals)

### **MT5 Export: TRADITIONAL SL/TP** (`src/codegen/mql5_generator.py:447-448`)
```cpp
double slDistance = atrValue * 2.0; // 2 ATR stop loss
double tpDistance = atrValue * 3.0; // 3 ATR take profit
```
- **Stop Loss**: 2 × ATR from entry price
- **Take Profit**: 3 × ATR from entry price
- **ATR Period**: 16 (configurable: 10-20)
- **Risk-Reward Ratio**: 1:1.5

---

## 📊 DEFAULT PARAMETER VALUES

### **Baseline Parameters** (`config/strategy_params_v1.py`)
```python
BASELINE_PARAMS = {
    # McGinley Dynamic Moving Averages
    "fast_min_len": 10,          # Fast DMA minimum length
    "fast_max_len": 20,          # Fast DMA maximum length
    "slow_min_len": 28,          # Slow DMA minimum length  
    "slow_max_len": 48,          # Slow DMA maximum length
    
    # ATR Settings
    "dma_atr_len": 16,           # DMA ATR lookback period
    "atr_len": 16,               # ATR calculation period
    
    # Dynamic Bands (ATR-based)
    "upper_outer_mult": 1.8,     # Upper outer band multiplier
    "lower_outer_mult": 2.2,     # Lower outer band multiplier
    "upper_inner_mult": 1,       # Upper inner band multiplier
    "lower_inner_mult": 1.2,     # Lower inner band multiplier
    
    # Market Regime Detection
    "momentum_len": 14,          # Momentum calculation period
    "momentum_threshold": 0.70,  # Momentum regime threshold (70th percentile)
    "momentum_lookback": 75,     # Lookback window for momentum percentile
    
    # RSI Settings
    "rsi_len": 14,               # RSI calculation period
    "rsi_oversold": 30,          # RSI threshold for long entries
    "rsi_overbought": 70,        # RSI threshold for short entries (v4.3+)
    
    # Bidirectional Support (v4.3+)
    "enable_shorts": False,      # Enable short positions
    "use_dma_fail_exit": True,   # Stabilized DMA fail exit
    "dma_exit_bars": 2,          # Consecutive bars for DMA fail
    "dma_exit_buffer_atr": 0.2,  # ATR buffer for DMA fail threshold
    "use_directional_momentum": False,  # Filter by ROC direction
    "roc_len": 22,               # ROC period for directional filter
    "ranging_confirm_bar": True, # Require reversal bar for ranging entries
}
```

### **Optimization Ranges** (`config/strategy_params.py:36-58`)
- **Fast DMA Lengths**: 6-14 (min) to 16-28 (max)
- **Slow DMA Lengths**: 30-60 (min) to 70-150 (max)
- **ATR Periods**: 10-20
- **Band Multipliers**: 0.8-3.0 (0.1 step increments)
- **Momentum Length**: 8-50 periods
- **Momentum Threshold**: 0.60-0.85 (0.05 step increments)

---

## 🔧 CURRENT TOGGLE STATUS

### **All Strategy Toggles: DISABLED**
```python
# Available but unused toggles:
use_trending_pullback_lowerinner = False    # Use inner band for trending entries
use_trending_pullback_fastdma = False       # Use fast DMA for trending entries  
use_ranging_reclaim = False                 # Require reclaim for ranging entries
use_protective_lowerinner_exit = False      # Add protective exit at inner band
```

### **Active Toggles** (`config/user_inputs.py:22-25`)
```python
TOGGLES = {
    "move_processed_charts": False,  # Keep charts in place after processing
    "progress_step": 0.01,          # Print progress every 1%
}
```

---

## 🏗️ CODE LOCATIONS REFERENCE

| Component | File Location | Key Lines |
|-----------|---------------|-----------|
| **Entry Logic** | `src/strategy/bands.py` | 37-52 |
| **Exit Logic** | `src/strategy/bands.py` | 54-57 |
| **Regime Detection** | `src/strategy/bands.py` | 33-35 |
| **Parameter Defaults** | `config/strategy_params.py` | 12-25 |
| **Parameter Ranges** | `config/strategy_params.py` | 36-58 |
| **Portfolio Config** | `config/portfolio.py` | 3-11 |
| **User Settings** | `config/user_inputs.py` | 11-18 |
| **Backtest Engine** | `src/engine/backtest.py` | 20-54 |
| **Pyramiding Logic** | `src/strategy/pyramiding.py` | 15-40 |
| **MT5 Risk Management** | `src/codegen/mql5_generator.py` | 447-448 |

---

## 🔍 CRITICAL ISSUES IDENTIFIED

### **1. Configuration Inconsistency**
- Two different config files with conflicting values
- Engine uses `portfolio.py` but `user_inputs.py` has different settings
- Potential for confusion and unexpected behavior

### **2. Risk Management Gap**
- Python backtester has NO stop-loss or take-profit
- Relies entirely on signal-based exits
- MT5 export includes SL/TP that backtester doesn't test

### **3. Limited Exit Strategies**
- Only one active exit condition (slow DMA cross)
- No profit-taking mechanism
- No volatility-based exits

### **4. Strategy Toggle Underutilization**
- Multiple entry/exit variants available but all disabled
- No systematic way to test different configurations

---

## 💡 IMPROVEMENT RECOMMENDATIONS

### **HIGH PRIORITY FIXES**

#### **1. Unify Configuration System**
```python
# Merge config files into single source of truth
# Add validation to ensure consistency
# Implement config hierarchy (user overrides < defaults)
```

#### **2. Add Backtester Risk Management**
```python
# Implement ATR-based stops in Python backtester
# Add trailing stops option  
# Include profit-taking mechanisms
# Match MT5 export behavior for consistency
```

#### **3. Enhanced Exit Strategies**
```python
# Add multiple exit conditions:
# - ATR-based profit targets
# - Volatility breakdowns
# - Time-based exits
# - Momentum divergence exits
```

### **MEDIUM PRIORITY ENHANCEMENTS**

#### **4. Dynamic Position Sizing**
```python
# ATR-based position sizing
# Volatility-adjusted risk per trade
# Kelly criterion optimization
# Drawdown-based size reduction
```

#### **5. Regime-Adaptive Parameters**
```python
# Different parameters for trending vs ranging
# Volatility-adjusted band multipliers  
# Market condition filters
```

#### **6. Strategy Toggle Management**
```python
# Configuration presets for different market conditions
# A/B testing framework for strategy variants
# Performance comparison tools
```

### **LOW PRIORITY OPTIMIZATIONS**

#### **7. Advanced Entry Filters**
```python
# Volume confirmation
# Multiple timeframe alignment
# Market structure analysis
# News/event filtering
```

#### **8. Portfolio Management**
```python
# Correlation-based position limits
# Sector/symbol diversification rules
# Maximum daily loss limits
# Heat map risk monitoring
```

---

## 🚀 NEXT STEPS RECOMMENDED

1. **Fix Configuration System** - Resolve config file conflicts
2. **Implement Consistent Risk Management** - Add SL/TP to backtester  
3. **Test Strategy Toggles** - Enable and optimize alternative entry/exit methods
4. **Validate Current Performance** - Run comprehensive backtest with current settings
5. **Systematic Improvement Testing** - A/B test each proposed enhancement

---

## 🔄 BIDIRECTIONAL UPGRADE (v4.3) - IMPLEMENTED

**Status**: ✅ Complete

**Changes Made**:
1. ✅ Added short entries/exits to `src/strategy/bands_v1.py` with backwards-compatible return shape
2. ✅ Extended `src/engine/backtest.py` to handle bidirectional portfolios (vectorbt `direction='both'`)
3. ✅ Updated `src/optimizer/search.py` to detect and route 3-tuple vs 5-tuple return shapes
4. ✅ Added new parameters to `config/strategy_params_v1.py` for short support
5. ✅ Updated `src/pine/generator.py` to emit bidirectional Pine scripts (v4.3+)
6. ✅ Updated documentation in `conditions.md`

**Key Improvements**:
- Strategy now works symmetrically in uptrends and downtrends
- Stabilized DMA fail exit prevents premature exits on noisy candles
- Optional directional momentum gate reduces counter-trend entries
- Pyramiding applied independently per side (long/short)

**Next Steps for Validation**:
1. Test on downtrend-heavy charts (e.g., USDTHB) with `enable_shorts=True`
2. Run walk-forward optimization to ensure stability
3. Compare performance metrics (Sharpe, Calmar) between long-only and bidirectional modes
4. Validate parameter robustness with small perturbations

---

*Generated from comprehensive codebase analysis on 4.2.5 system*
*Updated for bidirectional support (v4.3) - 2025*
