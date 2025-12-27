# Backtester Fix Summary

## Issue Identified
The interactive backtester was failing with a `KeyError: 'size'` when trying to access the default configuration parameters.

## Root Cause
There was a mismatch between the configuration key names in `config/user_inputs.py` and what the interactive backtester script was expecting:

**In config/user_inputs.py:**
```python
BACKTEST_CONFIG = {
    "fees": 0.0005,
    "position_size": 0.30,        # ← Key name: "position_size"
    "starting_capital": 400.0,    # ← Key name: "starting_capital"
    "data_freq": "15m",
}
```

**In scripts/run_backtest_interactive.py (before fix):**
```python
defaults['size']        # ← Looking for "size" (doesn't exist)
defaults['init_cash']   # ← Looking for "init_cash" (doesn't exist)
```

## Fix Applied
Updated the interactive backtester script to use the correct key names:

### File: `scripts/run_backtest_interactive.py`

**Before:**
```python
size_input = input(f"Position size as % of capital [{defaults['size']*100:.1f}%]: ")
size = defaults['size']

capital_input = input(f"Starting capital [{defaults['init_cash']}]: ")
capital = defaults['init_cash']
```

**After:**
```python
size_input = input(f"Position size as % of capital [{defaults['position_size']*100:.1f}%]: ")
size = defaults['position_size']

capital_input = input(f"Starting capital [{defaults['starting_capital']}]: ")
capital = defaults['starting_capital']
```

## Testing
Use the provided test script to verify the fix:
```batch
test_backtester_fix.bat
```

## Result
The interactive backtester should now work properly and allow you to:
1. Select optimization runs
2. Choose specific trials
3. Select charts for backtesting
4. Configure trading parameters without errors
5. View formatted results

The configuration step should now display the correct default values and accept user input without throwing KeyError exceptions.
