# Implementation Summary - Query GUI Enhancements

## Completed: October 19, 2025

### Overview
Implemented comprehensive enhancements to the Query GUI and optimizer configuration as requested, focusing on minimal surgical changes without major refactors.

---

## Changes Implemented

### 1. ✅ Split Optimizer Configuration (DEFAULT_PARAMS + TEST_RANGES)

**File:** `C:\...\4.2.5\config\strategy_params_v2.py`

- **Renamed:** `BASELINE_PARAMS` → `DEFAULT_PARAMS`
- **Renamed:** `PARAM_RANGES` → `TEST_RANGES`
- **Added comments** explaining:
  - `DEFAULT_PARAMS`: Scalar values for single backtests (Query GUI writes here)
  - `TEST_RANGES`: Lists for optimization sweeps with usage examples

**File:** `C:\...\4.2.5\scripts\run_optimizer_cli.py`
- Updated import to use `TEST_RANGES` instead of `PARAM_RANGES`

---

### 2. ✅ Updated "Set as Optimizer Baseline" Feature

**File:** `query_json_gui\opt_console_simple.py`

- **Button location:** Row Actions section (left panel)
- **Behavior:**
  - Writes only to `DEFAULT_PARAMS` (scalars only)
  - Does NOT modify `TEST_RANGES`
  - Creates timestamped backup before overwriting
  - Adds metadata comments (source file, chart, fold, performance metrics)
- **User confirmation:** Shows chart, fold, calmar ratio before applying
- **Feedback:** Displays backup filename and parameters count on success

---

### 3. ✅ Created Backtest-on-Demand CLI

**New File:** `C:\...\4.2.5\scripts\run_backtest_on_demand.py`

**Features:**
- Non-interactive CLI that outputs JSON to stdout
- **Arguments:**
  - `--uid`: Trial UID (e.g., `20251018_112307:28`)
  - `--scope`: `fold_only`, `all_folds`, or `all_charts`
  - `--capital`: Starting capital (default: 10000)
  - `--fees`: Fees as decimal (default: 0.001 = 0.1%)
  - `--max-positions`: Max concurrent positions (default: 3)
  - `--run-json`: Optional path to run JSON file

**Output Structure:**
```json
{
  "success": true,
  "meta": { "trial_uid", "scope", "capital", "fees", "max_positions", "charts" },
  "summary_overall": { "total_return_avg", "sharpe_avg", ... },
  "summary_by_chart_fold": [ ... ],
  "trades": [ ... ],
  "equity_curves": { ... }
}
```

---

### 4. ✅ Added "Backtest this parameter set…" Button

**File:** `query_json_gui\opt_console_simple.py`

**Location:** Row Actions section (left panel)

**New Dialog:** `BacktestConfigDialog`
- Shows selected row info (Trial UID, Chart, Fold)
- **Scope selection:** This fold / All folds / All charts
- **Runtime parameters:**
  - Starting Capital (default: 10000)
  - Fees % (default: 0.1%)
  - Max Concurrent Positions (default: 3)

**Workflow:**
1. User selects row → clicks "Backtest this parameter set…"
2. Dialog opens with pre-filled defaults
3. User configures parameters and clicks "Run Backtest"
4. CLI runs in background (5min timeout)
5. Results displayed in popup report window
6. Option to save report with Trial UID in filename

**Report Contents:**
- Overall Summary: avg metrics across folds
- Breakdown by Chart/Fold: detailed metrics per fold
- Trade Summary: Top 3 and Worst 3 trades
- All data available for saving

---

### 5. ✅ Added "Export preset…" Button

**File:** `query_json_gui\opt_console_simple.py`

**Location:** Row Actions section (left panel)

**Export Format:**
```json
{
  "meta": {
    "exported_at": "2025-10-19 12:30:45",
    "trial_uid": "20251018_112307:28",
    "source_file": "interactive_random_10_20251018_112307.json",
    "chart": "XAUUSD_1h_cl_3.csv",
    "fold_id": 3
  },
  "performance": {
    "total_return": 8.54,
    "sharpe_ratio": 1.9301,
    "calmar_ratio": 0.0469,
    ...
  },
  "parameters": {
    "base_fast_len": 14,
    "base_slow_len": 6,
    ...
  }
}
```

**Default Filename:** `preset_{trial_uid}_{timestamp}.json`

**Use Cases:**
- Save improved parameter sets with performance context
- Import into optimizer as `DEFAULT_PARAMS` later (manual)
- Track evolution of parameter optimization
- Share presets with team

---

### 6. ✅ UI Improvements

**Format Options Renamed:**
- "Plain text" → "Simple"
- "Detailed (sections/tables)" → "Detailed"
- **Default:** Simple (as requested)

**Analysis Dialog Names:**
- "Run Analysis…" → Simple/Detailed performance analysis
- "Backtest this parameter set…" → Full backtest with trades
- "Export preset…" → Save parameters as JSON

---

## Files Modified

### Query JSON GUI Project
- `opt_console_simple.py` - Main application (~200 lines added)

### Optimizer Project (4.2.5)
- `config/strategy_params_v2.py` - Renamed constants, added comments
- `scripts/run_optimizer_cli.py` - Updated imports
- **NEW:** `scripts/run_backtest_on_demand.py` - CLI for on-demand backtesting

---

## Usage Examples

### Set as Optimizer Baseline
1. Load JSON results in Query GUI
2. Apply filters (e.g., calmar > 0.01, trades > 100)
3. Select best row
4. Click "Set as Optimizer Baseline"
5. Confirm → `DEFAULT_PARAMS` updated with backup

### Backtest on Demand
1. Select row with good metrics
2. Click "Backtest this parameter set…"
3. Choose scope (fold/all folds/all charts)
4. Set capital, fees, max positions
5. Click "Run Backtest"
6. View results, save report

### Export Preset
1. Select row with parameters to save
2. Click "Export preset…"
3. Choose filename and location
4. JSON file created with params + metadata

---

## Technical Notes

### Minimal Changes Philosophy
- No major refactors
- Surgical additions only
- Existing functionality preserved
- Backward compatibility maintained

### Error Handling
- All operations have try/except blocks
- User-friendly error messages
- Log area shows detailed progress
- Graceful fallbacks for missing data

### Performance
- Subprocess timeout: 5 minutes for backtests
- JSON output to stdout (no temp files)
- In-memory report generation
- Efficient pandas filtering for parameter matching

---

## Future Enhancements (Not Implemented)

### Regime Breakdown Enhancement
The basic backtest report is implemented. For detailed regime analysis:
- Mask equity curve by chart analysis segments
- Calculate per-regime risk metrics (Sharpe, Sortino, Calmar per regime)
- Show trade distribution across regimes
- Top/worst trades per regime

**Why deferred:** Requires additional integration between backtest engine and chart analyzer; current implementation provides comprehensive trade-level data that can be analyzed externally.

### Regime Shift Detector
As discussed, this will be implemented in the Expert Advisor (EA) code:
- Rolling chart analysis
- Distribution shift detection
- Drift triggers for re-optimization
- Auto-suggest (not auto-promote) baseline candidates

---

## Testing Checklist

- [x] Query GUI loads JSON results correctly
- [x] "Set as Optimizer Baseline" creates backup and updates DEFAULT_PARAMS
- [x] Backtest CLI runs and outputs valid JSON
- [x] "Backtest this parameter set" dialog opens and runs successfully
- [x] Backtest results display in report window
- [x] "Export preset" saves JSON with correct structure
- [x] Default filters pre-fill and apply on load
- [x] Format options renamed and Simple set as default
- [x] All buttons appear in Row Actions section
- [x] No breaking changes to existing functionality

---

## Questions Answered

**Q:** Does the regime shift detector auto-promote baselines?
**A:** No. It will auto-suggest candidates in the EA, but require manual approval to prevent runaway optimization.

**Q:** Where are timestamped backups saved?
**A:** Same directory as `strategy_params_v2.py` with format: `strategy_params_v2.py.backup_YYYYMMDD_HHMMSS`

**Q:** Can I still use TEST_RANGES with single values?
**A:** Yes! Use a list with one element: `"atr_len": [14]` tests only 14. Comments added to config file explain this.

**Q:** Does backtest-on-demand write files?
**A:** No. It outputs JSON to stdout which Query GUI captures in-memory. Reports are saved only when user clicks "Save Report…"

---

## End of Implementation

All requested features have been implemented following the "minimal surgical changes" approach. No major refactors were performed, and all existing functionality remains intact.

