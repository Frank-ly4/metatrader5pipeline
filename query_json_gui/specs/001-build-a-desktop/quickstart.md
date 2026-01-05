# Quickstart Guide: Optimization Results Desktop Explorer

**Date**: 2025-10-01  
**Purpose**: Validate implementation against user stories and acceptance criteria

## Prerequisites

- Python 3.9+ installed
- PySide6, pandas installed (`pip install -r requirements.txt`)
- Sample JSON optimization/backtest files in a directory
- At least 2 valid JSON files and 1 malformed file for testing

## Test Data Structure

Create test JSON files with this structure:
```json
{
  "metadata": {
    "chart": "EURUSD",
    "fold_id": 1
  },
  "results": [
    {
      "calmar_ratio": 1.25,
      "max_drawdown": 0.08,
      "profit_factor": 1.65,
      "sharpe_ratio": 1.15,
      "num_trades": 45,
      "param_lookback": 20,
      "param_threshold": 0.5
    }
  ]
}
```

## Acceptance Scenario Validation

### 1. Data Loading (FR-001, FR-002, FR-003)

**Test Steps**:
1. Launch application: `python ui_app.py`
2. Click "Choose Folder" and select directory with test JSON files
3. Click "Load JSONs"

**Expected Results**:
- ✅ All valid JSON files merged into single table
- ✅ `_source_file` column shows origin filename
- ✅ Malformed files skipped with log entries
- ✅ Mixed schemas handled gracefully
- ✅ Status bar shows: "Rows: N | Last op: X ms"

**Validation Commands**:
```python
# Check _source_file column exists
assert "_source_file" in loaded_df.columns

# Check malformed files logged
with open("opt_console_ui.log", "r") as f:
    log_content = f.read()
    assert "Failed to load" in log_content or "malformed" in log_content.lower()
```

### 2. Quality Control (FR-006, FR-007)

**Test Steps**:
1. Set min_trades = 20
2. Set max_mdd = 0.10 (10%)
3. Check "Drop degenerate" if desired
4. Click "Apply QC"

**Expected Results**:
- ✅ Rows not meeting criteria removed from display
- ✅ Status bar updated with new row count and timing
- ✅ Original data preserved (can revert by reloading)

**Validation Commands**:
```python
# Verify QC filtering
filtered_df = qc_filter(original_df, min_trades=20, max_mdd=0.10, nondegenerate=True)
assert len(filtered_df) <= len(original_df)
assert all(filtered_df["num_trades"] >= 20)
assert all(filtered_df["max_drawdown"] <= 0.10)
```

### 3. Filter with Percentage Parsing (FR-008, FR-009, FR-010)

**Test Steps**:
1. Enter filter: `max_drawdown < 8% and profit_factor >= 1.5`
2. Click "Apply Query/Sort/Limit"
3. Test alternative formats: `max_drawdown < 8 %` and `max_drawdown < 0.08`

**Expected Results**:
- ✅ All three percentage formats produce identical results
- ✅ Only rows meeting criteria displayed
- ✅ Invalid syntax shows friendly error dialog
- ✅ No state loss on filter errors

**Validation Commands**:
```python
# Test percentage parsing equivalence
formats = ["max_drawdown < 8%", "max_drawdown < 8 %", "max_drawdown < 0.08"]
results = [query_df(df, filter_expr=fmt) for fmt in formats]
assert all(len(r) == len(results[0]) for r in results)
```

### 4. Top-k per Group (FR-011)

**Test Steps**:
1. Set group_by = "chart,fold_id"
2. Set sort_by = "-calmar_ratio"
3. Set k = 3
4. Click "Top-k per group"

**Expected Results**:
- ✅ At most 3 results per chart+fold_id combination
- ✅ Results sorted by Calmar ratio (descending) within groups
- ✅ Missing column validation shows dialog if sort_by column absent

**Validation Commands**:
```python
# Verify Top-k results
result_df = topk_per_group(df, group_by="chart,fold_id", sort_by="-calmar_ratio", k=3)
group_counts = result_df.groupby(["chart", "fold_id"]).size()
assert all(count <= 3 for count in group_counts)
```

### 5. Pareto Analysis (FR-012, FR-016)

**Test Steps**:
1. Click "Pareto Frontier" button
2. If missing columns, verify validation dialog appears

**Expected Results**:
- ✅ Non-dominated solutions displayed (maximize Calmar/PF, minimize MDD)
- ✅ Missing column dialog shows required columns if data incomplete
- ✅ Operation timing displayed in status bar

**Validation Commands**:
```python
# Test Pareto validation
try:
    pareto_result = pareto_frontier(incomplete_df)
    assert False, "Should raise ValueError for missing columns"
except ValueError as e:
    assert "requires columns" in str(e).lower()
```

### 6. Stability Analysis (FR-013, FR-016)

**Test Steps**:
1. Click "Stability by Params" button
2. Verify param_* columns and metrics exist

**Expected Results**:
- ✅ Stability scores calculated per parameter combination
- ✅ Validation dialog if no param_* columns or required metrics
- ✅ Results grouped by parameter values

**Validation Commands**:
```python
# Test stability requirements
param_cols = [c for c in df.columns if c.startswith("param_")]
required_metrics = ["calmar_ratio", "profit_factor", "max_drawdown"]
available_metrics = [m for m in required_metrics if m in df.columns]
assert len(param_cols) >= 1 and len(available_metrics) >= 1
```

### 7. Profile Management (FR-021, FR-022, FR-023)

**Test Steps**:
1. Configure analysis settings (QC, filters, etc.)
2. Click "Save Profile" and enter name "TestProfile"
3. Change settings
4. Click "Load Profile" and select "TestProfile"

**Expected Results**:
- ✅ All settings restored to saved state
- ✅ profiles.json created with schema_version
- ✅ Profile dropdown shows available profiles

**Validation Commands**:
```python
# Verify profile structure
with open("profiles.json", "r") as f:
    profiles = json.load(f)
    assert "schema_version" in profiles
    assert "TestProfile" in profiles
    assert profiles["TestProfile"]["min_trades"] == expected_value
```

### 8. Export with Sidecar (FR-025, FR-026, FR-027, FR-028, FR-029)

**Test Steps**:
1. Apply some analysis to create filtered view
2. Click "Export Current View"
3. Choose output directory and filename

**Expected Results**:
- ✅ CSV file created with current data
- ✅ Parquet file created if pyarrow available
- ✅ Metadata sidecar JSON created with complete information
- ✅ Full filtered dataset exported (not just displayed 50k rows)

**Validation Commands**:
```python
# Verify export files
assert os.path.exists("export.csv")
assert os.path.exists("export.meta.json")

# Verify sidecar content
with open("export.meta.json", "r") as f:
    metadata = json.load(f)
    required_keys = ["app_version", "timestamp", "profile_name", "qc_params", 
                    "filter_expr", "visible_columns", "_source_files"]
    assert all(key in metadata for key in required_keys)
```

## Performance Validation

### Large Dataset Handling (FR-017, FR-018, FR-019)

**Test Steps**:
1. Create or load dataset with >50,000 rows
2. Observe table display and status bar

**Expected Results**:
- ✅ Table displays first 50,000 rows only
- ✅ Status bar shows: "Showing 50,000 of N rows | Last op: X ms"
- ✅ UI remains responsive during operations
- ✅ Export includes full dataset, not just displayed rows

### Operation Timing (FR-020)

**Test Steps**:
1. Perform various operations (QC, filter, analytics)
2. Observe status bar timing feedback

**Expected Results**:
- ✅ All operations complete in <1 second for typical datasets
- ✅ Status bar shows "Last op: X ms" after each operation
- ✅ UI doesn't freeze during processing

## Error Handling Validation

### Graceful Degradation (FR-030, FR-031)

**Test Steps**:
1. Try operations with missing required columns
2. Enter invalid filter expressions
3. Attempt operations on empty datasets

**Expected Results**:
- ✅ Friendly error dialogs explain issues clearly
- ✅ Current view state preserved on all errors
- ✅ No application crashes or data loss
- ✅ Helpful suggestions provided in error messages

### Unicode Path Support (FR-004)

**Test Steps**:
1. Create directory with Unicode characters in name
2. Load data from and export to Unicode paths

**Expected Results**:
- ✅ Unicode directory names handled correctly
- ✅ File operations succeed with international characters
- ✅ No encoding errors in logs or dialogs

## Logging Validation (FR-005)

**Test Steps**:
1. Perform various operations
2. Check `opt_console_ui.log` file

**Expected Results**:
- ✅ Log file created with rotating handler
- ✅ Load outcomes, errors, and timings recorded
- ✅ No sensitive data in logs
- ✅ Log rotation works (test with >1MB of logs)

## Constitutional Compliance Check

**Verify all constitutional principles**:
- ✅ Local-only operation (no network activity)
- ✅ Deterministic results (same input → same output)
- ✅ Separation of concerns (analytics engine testable independently)
- ✅ Performance targets met (50k-200k rows responsive)
- ✅ Reproducible exports (complete metadata sidecars)

## Success Criteria

All acceptance scenarios must pass without errors. The application should:
1. Handle the complete user workflow from data loading to export
2. Provide responsive performance with large datasets
3. Maintain constitutional compliance throughout
4. Offer graceful error handling and recovery
5. Support reproducible analysis through profiles and exports

**Final Validation**: Run the complete workflow end-to-end with real optimization data to ensure production readiness.
