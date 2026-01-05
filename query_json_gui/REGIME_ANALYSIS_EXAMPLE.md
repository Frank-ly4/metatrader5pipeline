# Regime Analysis - Expected Output Example

When regime analysis works correctly with chart analysis loaded, you should see output like this:

```
================================================================================
REGIME PERFORMANCE ANALYSIS
================================================================================
Generated: 2025-10-19 22:30:00
Trial UID: 20251008_124610:1918
Chart: XAUUSD_1h_cl_2.csv
Fold: 3

Backtest Configuration:
  Capital: $50,000.00
  Fees: 0.045%
  Max Positions: 3

--------------------------------------------------------------------------------
OVERALL PERFORMANCE
--------------------------------------------------------------------------------
  Total Return: 14.23%
  Sharpe Ratio: 2.2419
  Sortino Ratio: 3.0812
  Calmar Ratio: 3.7370
  Max Drawdown: 4.08%
  Total Trades: 130
  Win Rate: 65.89%
  Profit Factor: 4.05

--------------------------------------------------------------------------------
BREAKDOWN BY REGIME
--------------------------------------------------------------------------------

TREND_UP_HIGH_VOL:
  Trades: 45 (34.6% of total)
  Winners: 30 | Losers: 15
  Win Rate: 66.67%
  Total PnL: $3,450.25
  Avg PnL/trade: $76.67
  Top 3 Trades:
    1. $320.50 (2.15%) | Long | Entry: 2024-05-15 14:00:00
    2. $285.75 (1.88%) | Long | Entry: 2024-06-22 09:00:00
    3. $245.00 (1.65%) | Long | Entry: 2024-07-08 16:00:00
  Worst 3 Trades:
    1. $-120.25 (-0.82%) | Long | Entry: 2024-05-28 11:00:00
    2. $-95.50 (-0.65%) | Long | Entry: 2024-06-10 15:00:00
    3. $-75.00 (-0.51%) | Long | Entry: 2024-07-15 08:00:00

TREND_DOWN_HIGH_VOL:
  Trades: 35 (26.9% of total)
  Winners: 25 | Losers: 10
  Win Rate: 71.43%
  Total PnL: $2,890.75
  Avg PnL/trade: $82.59
  ...

TREND_UP_MID_VOL:
  Trades: 28 (21.5% of total)
  Winners: 18 | Losers: 10
  Win Rate: 64.29%
  Total PnL: $1,450.00
  Avg PnL/trade: $51.79
  ...

[Additional regimes would appear here...]

================================================================================
END OF REPORT
================================================================================
```

## Key Features of Regime Breakdown:

1. **Trade Count by Regime**: Shows how many trades occurred in each market regime
2. **Winners vs Losers**: Explicit count of profitable vs unprofitable trades
3. **Win Rate**: Percentage of winning trades for each regime
4. **Total & Average PnL**: Financial performance metrics per regime
5. **Top/Worst Trades**: Specific examples of best and worst performers

## Troubleshooting:

If you see "REGIME BREAKDOWN: Not Available", check:

1. **Chart Analysis Exists**: Verify the JSON file exists in `outputs/analyses/`
2. **Trade Extraction**: Check stderr/logs for trade count
3. **Column Mapping**: VectorBT uses different column names than expected

Run the debug script to verify:
```bash
cd "4.2.5 - After trying to fix ratios 090925"
python scripts\debug_regime_trades.py
```
