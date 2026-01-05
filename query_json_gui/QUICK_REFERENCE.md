# Query GUI - Quick Reference Guide

## New Features at a Glance

### Row Actions (Left Panel)

```
┌─────────────────────────────────┐
│  Row Actions                    │
│  Select a row in the table first│
│                                 │
│  ┌───────────────────────────┐ │
│  │ Set as Optimizer Baseline │ │
│  └───────────────────────────┘ │
│  ┌───────────────────────────┐ │
│  │ Run Analysis…             │ │
│  └───────────────────────────┘ │
│  ┌───────────────────────────┐ │
│  │ Backtest this param set…  │ │
│  └───────────────────────────┘ │
│  ┌───────────────────────────┐ │
│  │ Export preset…            │ │
│  └───────────────────────────┘ │
└─────────────────────────────────┘
```

---

## 1. Set as Optimizer Baseline

**What it does:** Copies selected row's parameters to `DEFAULT_PARAMS` in `strategy_params_v2.py`

**Steps:**
1. Select a row with good performance
2. Click "Set as Optimizer Baseline"
3. Review confirmation dialog (shows chart, fold, calmar)
4. Click "Yes"

**Result:**
- ✅ Backup created: `strategy_params_v2.py.backup_YYYYMMDD_HHMMSS`
- ✅ `DEFAULT_PARAMS` updated (scalars only)
- ✅ `TEST_RANGES` unchanged (lists preserved)
- ✅ Comments added with source info and performance

**Note:** This does NOT copy to clipboard. File is directly updated.

---

## 2. Run Analysis

**What it does:** Generates performance report from existing optimization results

**Steps:**
1. Select a row
2. Click "Run Analysis…"
3. Choose scope:
   - This fold only
   - All folds (same chart, same params)
   - All charts (same params)
4. Choose format:
   - **Simple** (default) - Plain text summary
   - **Detailed** - Structured with sections
5. Click "Generate Analysis"

**Report includes:**
- Executive Summary (if multiple folds)
- Fold/Chart Breakdown (metrics, val periods, bars)
- Chart Environment Analysis (if chart_analyzer has been run)

**Save:** Click "Save Report..." in report dialog

---

## 3. Backtest this parameter set

**What it does:** Runs full backtest with custom settings and trade details

**Steps:**
1. Select a row
2. Click "Backtest this parameter set…"
3. Configure:
   - **Scope:** Fold only / All folds / All charts
   - **Starting Capital:** e.g., 10000
   - **Fees (%):** e.g., 0.1 for 0.1%
   - **Max Positions:** e.g., 3
4. Click "Run Backtest"
5. Wait (progress shown in log area, up to 5min timeout)

**Report includes:**
- Overall Summary (avg metrics across folds)
- Breakdown by Chart/Fold
- Top 3 and Worst 3 Trades
- All trade details with PnL, fees, timestamps

**Save:** Click "Save Report..." in report dialog

**Technical:** Runs `run_backtest_on_demand.py` CLI script, captures JSON output

---

## 4. Export preset

**What it does:** Saves selected row's parameters + metadata as JSON file

**Steps:**
1. Select a row
2. Click "Export preset…"
3. Choose filename (default: `preset_{UID}_{timestamp}.json`)
4. Click "Save"

**JSON Structure:**
```json
{
  "meta": {
    "exported_at": "...",
    "trial_uid": "...",
    "source_file": "...",
    "chart": "...",
    "fold_id": "..."
  },
  "performance": {
    "total_return": 8.54,
    "sharpe_ratio": 1.9301,
    ...
  },
  "parameters": {
    "base_fast_len": 14,
    ...
  }
}
```

**Use cases:**
- Save improved parameter sets
- Track optimization evolution
- Share presets with team
- Import back to optimizer (manual copy to `DEFAULT_PARAMS`)

---

## Default Filters (Auto-Applied on Load)

When you load files, these filters are pre-filled and applied:

| Filter | Operator | Min | Max |
|--------|----------|-----|-----|
| calmar_ratio | Between | 0.01 | 0.10 |
| total_trades | ≥ | 100 | - |
| max_drawdown | Between | 1.5% | 4.2% |

**To change:** Adjust values in left panel and click "Apply Filters"

**To clear:** Click "Reset" button

---

## Optimizer Config Changes

### Before (Old):
```python
BASELINE_PARAMS = { ... }  # Scalars
PARAM_RANGES = { ... }     # Lists
```

### After (New):
```python
DEFAULT_PARAMS = { ... }   # Scalars (Query GUI writes here)
TEST_RANGES = { ... }      # Lists (unchanged by Query GUI)
```

### TEST_RANGES Usage

**Test single value:**
```python
"atr_len": [14]  # Only test 14
```

**Test multiple values:**
```python
"atr_len": [10, 12, 14, 16]  # Test all four
```

**Test range:**
```python
"base_fast_len": list(range(12, 29, 2))  # 12, 14, 16, ..., 28
```

---

## Workflow Examples

### Example 1: Find Best Parameters and Set as Baseline

```
1. Load folder: outputs/runs
2. Auto-filters applied (calmar 0.01-0.10, trades > 100, dd 1.5-4.2%)
3. Click "calmar_ratio" column header to sort descending
4. Select top row
5. Click "Run Analysis…" → All folds → Simple
6. Review performance across folds
7. If consistent, click "Set as Optimizer Baseline"
8. Run new optimization with tighter TEST_RANGES around new baseline
```

### Example 2: Deep Dive into Promising Parameter Set

```
1. Find interesting row (e.g., high Calmar, many trades)
2. Click "Run Analysis…" → All charts → Detailed
   - See how params perform across different charts
3. Click "Backtest this parameter set…"
   - Set Capital: 25000
   - Set Fees: 0.05%
   - Set Max Positions: 5
   - Scope: All charts
4. Review trade-level results
5. If satisfied, click "Export preset…" to save
6. Click "Set as Optimizer Baseline" to use in next optimization run
```

### Example 3: Build Preset Library

```
1. Apply filters for different objectives:
   - High Calmar + Low DD → Export preset_conservative.json
   - High Return + High Trades → Export preset_aggressive.json
   - Balanced metrics → Export preset_balanced.json
2. Save each to a "presets/" folder
3. Manually review JSONs to understand parameter ranges
4. Update TEST_RANGES to explore around these clusters
```

---

## Troubleshooting

### "Script Not Found" when backtesting
- **Check:** Is the Query GUI loaded from `outputs/runs` folder?
- **Path:** Script expects `../../scripts/run_backtest_on_demand.py`
- **Fix:** Load from correct folder or adjust `self.loaded_folder`

### Backtest times out (>5min)
- **Cause:** Large number of charts or heavy computation
- **Fix:** Reduce scope (use "This fold only") or optimize strategy code

### "No UID found" error
- **Cause:** Selected row doesn't have `trial_uid` or `uid` column
- **Fix:** Ensure JSON files have UID information

### DEFAULT_PARAMS not updating
- **Check:** Does `strategy_params_v2.py` exist at expected path?
- **Path:** `{loaded_folder}/../../config/strategy_params_v2.py`
- **Fix:** Verify folder structure matches 4.2.5 layout

---

## Tips & Best Practices

✅ **Always review confirmation dialogs** - Double-check chart, fold, and metrics before setting baseline

✅ **Save presets frequently** - Export interesting parameter sets as you find them

✅ **Use "Run Analysis" before backtesting** - Faster way to check consistency across folds

✅ **Start with smaller scopes** - Test "This fold only" before running "All charts"

✅ **Monitor log area** - Shows detailed progress and error messages

✅ **Keep backups** - Timestamped backups of `strategy_params_v2.py` are created automatically

✅ **Default filters are your friend** - Pre-filters noisy results on load

---

## Keyboard Shortcuts

- **Arrow Keys:** Navigate table rows
- **Enter:** (when row selected) - No action, use mouse on buttons
- **Ctrl+F:** (future enhancement idea - not implemented)

---

## Files to Know

### Query GUI Project
- `opt_console_simple.py` - Main application
- `run_simple.bat` - Launch script (Windows)

### Optimizer Project (4.2.5)
- `config/strategy_params_v2.py` - Parameter config
- `scripts/run_backtest_on_demand.py` - Backtest CLI
- `scripts/run_optimizer_cli.py` - Main optimizer
- `outputs/runs/*.json` - Optimization results
- `outputs/analyses/*.json` - Chart analysis files

---

**End of Quick Reference**

For detailed implementation notes, see `IMPLEMENTATION_SUMMARY.md`

