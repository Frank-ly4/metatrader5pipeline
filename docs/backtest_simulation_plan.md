# Backtest & Simulation Plan

## 1. Walk-Forward Windows

### In-Sample / Out-of-Sample Split
- **Training Window**: 3 years
- **Testing Window**: 6 months
- **Walk-Forward Step**: 1 month (rolling window)

### Example Timeline
```
Year 1-3: Training (in-sample)
Year 3.5-4: Testing (out-of-sample)
Roll forward 1 month
Year 1.08-4.08: Training
Year 4.08-4.58: Testing
...continue rolling
```

### Walk-Forward Procedure
1. Train on 3-year window
2. Test on next 6 months (unseen data)
3. Roll forward 1 month
4. Repeat until end of data
5. Aggregate out-of-sample results

---

## 2. Monte Carlo Parameters

### Number of Simulations: 1000
- Run 1000 Monte Carlo iterations per parameter set
- Use different random seeds for each iteration

### Parameters to Randomize

#### Spread Randomization
```python
import numpy as np

# Load session-based spread distribution
spread_median = broker_spec["symbols"]["USDSEK"]["spread_median"]["london"]  # 1.5 pips
spread_95th = broker_spec["symbols"]["USDSEK"]["spread_95th"]["london"]     # 3.0 pips
spread_std = (spread_95th - spread_median) / 1.645  # Approximate std from 95th percentile

# Generate random spread for each trade
spread = np.random.normal(spread_median, spread_std)
spread = max(0.1, spread)  # Floor at 0.1 pips
```

#### Slippage Randomization
```python
slippage_mean_points = 1.0
slippage_std_points = 2.0
slippage = np.random.normal(slippage_mean_points, slippage_std_points)
slippage = max(0, slippage)  # No negative slippage (favor)
```

#### Execution Latency Randomization
```python
latency_mean_ms = 100
latency_std_ms = 50
latency = np.random.normal(latency_mean_ms, latency_std_ms)
latency = max(10, latency)  # Minimum 10ms
```

#### Partial Fills (if enabled)
```python
# FOK mode: No partial fills (order fills completely or rejected)
# If partial fills enabled:
fill_probability = 0.95  # 95% chance of full fill
if np.random.random() > fill_probability:
    fill_percentage = np.random.uniform(0.5, 1.0)  # 50-100% fill
else:
    fill_percentage = 1.0  # Full fill
```

---

## 3. Simulation Model Components

### Spread Simulation
- **Distribution**: Normal (mean = session median, std = (95th - median) / 1.645)
- **Session Detection**: Use trade timestamp to determine session (Asian/London/NY)
- **Apply**: Add spread to entry/exit prices (bid for sells, ask for buys)

### Slippage Simulation
- **Distribution**: Normal (mean = 1 point, std = 2 points)
- **Apply**: Add slippage to fill price (positive for buys, negative for sells)
- **Max Slippage**: Cap at 3 points (from broker spec)

### Commission Simulation
```python
commission_per_lot = 7.0  # USD per lot round-trip
commission_per_side = 3.5  # USD per lot per side
commission = lot_size * commission_per_side  # Apply on entry and exit
```

### Swap Simulation
```python
# Apply swap daily at 00:00 UTC
swap_long = -0.5  # USD per lot per day
swap_short = 0.3  # USD per lot per day

# Calculate days held
days_held = (exit_time - entry_time).days
if position_type == "LONG":
    swap_cost = lot_size * swap_long * days_held
else:
    swap_cost = lot_size * swap_short * days_held
```

### Margin Call Simulation
```python
margin_call_threshold = 1.0  # Equity = Margin (100%)
stop_out_threshold = 0.5     # Equity = 50% of Margin

equity = account_balance + unrealized_pnl
margin_used = sum(position.margin for position in positions)
margin_level = equity / margin_used if margin_used > 0 else float('inf')

if margin_level <= stop_out_threshold:
    # Liquidate positions (FIFO)
    liquidate_positions()
elif margin_level <= margin_call_threshold:
    # Prevent new positions
    trading_disabled = True
```

### Partial Fills (FOK Mode)
- **FOK Mode**: No partial fills - order fills completely or is rejected
- **Rejection Probability**: Based on spread widening during news events
- **Simulate**: If spread > 95th percentile, reject order with probability 0.3

---

## 4. Required Performance Metrics

### Core Metrics
1. **Expectancy**: Average profit per trade
   ```
   Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
   ```

2. **Sharpe Ratio**: Risk-adjusted return
   ```
   Sharpe = (Mean Return - Risk-Free Rate) / Std Dev of Returns
   ```

3. **Sortino Ratio**: Downside risk-adjusted return
   ```
   Sortino = (Mean Return - Risk-Free Rate) / Std Dev of Negative Returns
   ```

4. **Max Drawdown**: Largest peak-to-trough decline
   ```
   Max DD = Max(Peak Equity - Trough Equity) / Peak Equity
   ```

5. **MAR Ratio**: Return over max drawdown
   ```
   MAR = Annual Return / Max Drawdown
   ```

6. **Trade Distribution**: Histogram of trade outcomes
   - Win rate
   - Average win/loss
   - Largest win/loss
   - Trade duration distribution

7. **Worst-Case Margin**: Maximum margin used during backtest
   ```
   Worst Case Margin = Max(Sum of position margins over time)
   ```

---

## 5. Sample Monte Carlo Scenario File

See `config/monte_carlo_scenario.json` below.

---

## 6. Historical Data Requirements

### Data Granularity
- **Minimum**: 1-minute bars
- **Preferred**: Tick data (if available)
- **Fallback**: 1-minute bars with spread estimates

### Required Fields
- Open, High, Low, Close (OHLC)
- Volume (if available)
- Timestamp (UTC)

### Data Sources
- MT5 History Center
- Broker-provided historical data
- Third-party data providers (if needed)

---

## 7. Simulation Execution Steps

### Step 1: Load Historical Data
```python
import pandas as pd

data = pd.read_csv("data/charts_cl/USDSEK_4h_cl_1.csv", parse_dates=["Time"])
data.set_index("Time", inplace=True)
```

### Step 2: Generate Signals
```python
signals = compute_signals(data, params)
entries = signals["entries"]
exits = signals["exits"]
```

### Step 3: Run Monte Carlo Simulation
```python
results = []
for i in range(1000):
    # Randomize execution parameters
    spread = generate_spread(session)
    slippage = generate_slippage()
    latency = generate_latency()
    
    # Simulate trades
    trades = simulate_trades(entries, exits, spread, slippage, commission, swap)
    
    # Calculate metrics
    metrics = calculate_metrics(trades)
    results.append(metrics)
```

### Step 4: Aggregate Results
```python
# Calculate percentiles
expectancy_5th = np.percentile([r["expectancy"] for r in results], 5)
expectancy_95th = np.percentile([r["expectancy"] for r in results], 95)
sharpe_median = np.median([r["sharpe"] for r in results])
max_dd_95th = np.percentile([r["max_drawdown"] for r in results], 95)
```

### Step 5: Generate Report
- Summary statistics (mean, median, std)
- Percentile distributions (5th, 25th, 50th, 75th, 95th)
- Worst-case scenarios
- Best-case scenarios
- Trade distribution histograms

---

## 8. Validation Checks

### Pre-Simulation
- [ ] Historical data covers full walk-forward window
- [ ] Symbol specifications match broker spec
- [ ] Commission and swap rates verified
- [ ] Margin calculations validated

### During Simulation
- [ ] No negative account balance (should trigger margin call)
- [ ] No positions exceed max volume
- [ ] Daily loss limits enforced
- [ ] Emergency stops trigger correctly

### Post-Simulation
- [ ] Results within expected ranges
- [ ] No anomalies in trade distribution
- [ ] Margin usage reasonable
- [ ] Performance metrics consistent across runs

