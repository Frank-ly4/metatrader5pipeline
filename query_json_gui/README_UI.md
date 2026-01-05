## Optimization Console UI (PySide6) v1.1.0

Cross-platform desktop UI to analyze many JSON backtest/optimization results with robust validation, logging, and large-data handling.

### Features

- **Data Loading**: Load and merge multiple `*.json` result files (adds `_source_file`) with Unicode path support
- **QC Filters**: `min_trades`, `max_mdd` (fraction like `0.10`), and drop degenerate with column validation
- **Query/Sort/Limit**: Enhanced `%` parsing (`8%`, `8 %`, `0.08`) in expressions and `-col` for descending
- **Top‑k per Group**: Single or multi-column group keys (`chart,fold_id`) with required column validation
- **Advanced Analytics**: Pareto frontier, Composite score, Stability by params, Param↔Metric Spearman, Partial dependence
- **Smart Export**: CSV + Parquet with metadata sidecar JSON for reproducibility
- **Profiles**: Save/Load named profiles with schema versioning to `profiles.json`
- **Large Data Handling**: 50k+ row truncation for display with full export capability
- **Logging**: Rotating log file (`opt_console_ui.log`) for operations and errors

### Filter Builder (New)

- Launch via the **Build Filter…** button next to the filter input
- Build filters using rows: `(Field | Operator | Value)`
  - Operators: `=`, `!=`, `>`, `>=`, `<`, `<=`, `between`, `in`
  - Fields list prioritizes metrics: `calmar_ratio`, `profit_factor`, `max_drawdown`, `sharpe_ratio`, `total_trades`, `win_rate`, then any `param_*`
  - Value supports percent tokens: `8%`, `8 %`, or `0.08`; `between` provides min/max; `in` accepts comma-separated values
- Advanced toggle shows raw expression preview/edit area
- Live preview: debounced count of matching rows against the current view; errors are caught and shown
- Apply writes the composed expression to the filter input (does not auto-run)

### Preset & History Chips (New)

**Preset Filters** (static):
- **Quality**: `profit_factor >= 1.6 and calmar_ratio > 0 and max_drawdown < 10% and total_trades >= 20`
- **Risk-tight**: `max_drawdown < 8% and profit_factor >= 1.5`
- **Return-tilt**: `calmar_ratio >= 0.5 and total_trades >= 30`

**History Chips**: Show the last 5 unique filters from previous sessions (most recent first)
- Persisted in `app_state.json` as `filter_history`
- Clicking a chip loads the filter into the input field (does not auto-apply)
- Hint: "Click a chip to load its filter; Apply to run"

### Sort Builder (New)

- Launch via **Build Sort…** next to the sort input
- Add multiple sort keys (Field + Direction asc/desc), reorder via Up/Down
- Validates columns exist; Apply writes a string like `col,-col` into the sort input
- If unknown columns are detected, shows a friendly dialog and does not apply

### Safe Apply & Enter Key (New)

- Press Enter in the filter or sort input to trigger **Apply Query/Sort/Limit** after ~250ms debounce
- If a filter parse error occurs, a dialog is shown, the error is logged, and the table is not changed (non-destructive)

### Summary Bar (New)

- Compact summary above the table: `QC: min_trades=… max_mdd=… nondegenerate=… | Filter: <short> | Sort: <sort_by or (none)> | Limit: <N or all>`
- Click "Filter" to open the Filter Builder; click "Sort" to open the Sort Builder
- Updates automatically when QC/filter/sort/limit settings change

### Presets & History (New)

- Preset chips under the filter input:
  - Quality → `profit_factor >= 1.6 and calmar_ratio > 0 and max_drawdown < 10% and total_trades >= 20`
  - Risk-tight → `max_drawdown < 8% and profit_factor >= 1.5`
  - Return-tilt → `calmar_ratio >= 0.5 and total_trades >= 30`
- History chips show the last 5 unique filters (most recent first); click to populate the filter input
- Persistence: history is stored in `app_state.json` as `filter_history`; the last applied expression is stored as `last_applied_filter` and prefilled on startup

### Sort Builder (New)

- Launch via **Build Sort…** next to the sort input
- Add multiple sort keys (Field + Direction asc/desc), reorder via Up/Down
- Validates columns exist; Apply writes a string like `col,-col` into the sort input

### Safe Apply & Debounce (New)

- Press Enter in filter/sort inputs to auto-apply after ~250ms debounce
- If a filter parse error occurs, a dialog is shown, the error is logged, and the table is not changed

### Summary Bar (New)

- Compact summary above the table: `QC: min_trades=… max_mdd=… nondegenerate=… | Filter: <short> | Sort: <sort_by or (none)> | Limit: <N or all>`
- Click “Filter” to open the Filter Builder; click “Sort” to open the Sort Builder

### Group-by Selection

- Use the `Select Groups…` button to open a multi-select dialog of available grouping columns.
- Available options include `chart`, `fold_id`, and any `param_*` columns present in the data.
- Dialog and manual text field (`group_by`) stay in sync; applying dialog writes a comma list.
- Default: if `group_by` is empty, `chart` is used when available; otherwise a warning is shown.

### Column Visibility

- Use the `Columns ▾` menu to toggle per-column visibility on the current view.
- Visibility persists for the session and is saved to `app_state.json` under `column_visibility`.
- On startup, visibility is restored if present.

### Sort Fields Clarification

- **Sort (Main View)**: Affects the main Query/Sort/Limit results.
- **Top-k Sort (Per-Group)**: Used only when running Top-k per group; does not change the main table sort.

### UI on Small Screens

- The entire left control panel is scrollable so the Advanced section remains reachable on smaller displays.

### Validation Before Analytics

- Pareto requires: `calmar_ratio`, `max_drawdown`, `profit_factor`
- Top-k requires: the chosen `sort_by` column(s) exist in the dataset
- Stability requires: at least one `param_*` and at least one metric from `{calmar_ratio, profit_factor, max_drawdown}`
- When validation fails, a friendly dialog is shown and the current view does not change.

### Export with Sidecar Metadata

Choose an output directory via "Export Current View". The app writes:
- **`view.csv`** - Standard CSV format for universal compatibility  
- **`view.parquet`** - Efficient columnar format if `pyarrow` is available (preserves data types)
- **`view.meta.json`** - Sidecar metadata for reproducibility

**Sidecar Contents:**
```json
{
  "app_version": "1.1.0",
  "timestamp_utc": "2025-10-01T12:34:56Z",
  "profile_name": "MyAnalysis",
  "qc_params": {"min_trades": 20, "max_mdd": 0.1, "nondegenerate": true},
  "filter_expr": "profit_factor >= 1.5",
  "sort_by": "-calmar_ratio",
  "limit": null,
  "group_by": "chart",
  "objectives_weights": "Default Pareto: calmar_ratio(max), max_drawdown(min), profit_factor(max)",
  "visible_columns": ["calmar_ratio", "max_drawdown", "profit_factor", "_source_file"],
  "_source_files": ["backtest_001.json", "backtest_002.json"],
  "row_count": 1250
}
```

### Large Data & Performance

- **Default After Load**: After loading a folder, the main table shows the full QC base (no filter, no limit). On-screen display is truncated to 50,000 rows if necessary.
- **Reset to QC Base**: Use the "Reset to QC Base" button to restore the full QC base view anytime (clears filter, sort, and limit).
- **Truncation Behavior**: For datasets >50,000 rows, the table displays only the first 50,000 for responsiveness
- **Status Indicator**: Shows "Showing 50,000 of N rows" when truncated
- **Full Export**: Exports always include the complete filtered dataset, not just the displayed rows
- **Operation Timing**: Status bar shows operation timing (e.g., "Last op: 245 ms")

### Logging

- **Log File**: `opt_console_ui.log` in the application directory
- **Rotating Logs**: 1MB max size, keeps 5 backup files
- **Logged Events**: Load results, query errors, validation failures, operation timings
- **Privacy**: No network activity; all logging is local only

### Notes & Resilience

- **Column Validation**: Operations validate required columns and show friendly error dialogs for missing data
- **Mixed Schemas**: Tolerates missing columns and mixed schemas across JSON files; operations work with available data
- **Percent Parsing**: Accepts `8%`, `8 %`, or `0.08` equivalently with % form taking precedence
- **Unicode Support**: Full Unicode path support for international file/folder names
- **Error Recovery**: Informative dialogs shown for invalid operations; app never crashes on bad data
- **Auto-Derivatives**: Automatically adds risk derivatives like `gtp_proxy` (gain-to-pain) and `exp_per_trade` when loading data


