# Optimization Console Lite

**A minimal, fast desktop app for viewing and querying optimizer JSON results.**

## Overview

Optimization Console Lite is a streamlined version of the full Optimization Console, designed for quick exploration and filtering of large optimizer/backtest JSON result sets. It provides essential features for loading, filtering, sorting, and exporting data with minimal dependencies.

## Features

- **Fast JSON Loading**: Load single or multiple JSON files (recursive folder scanning optional)
- **Flexible Filtering**: Free-text filter expressions with percentage token support
- **Layered Filters**: Add multiple AND-combined filter conditions via UI
- **Multi-Key Sorting**: Sort by multiple columns with ascending/descending control
- **Top-N Analysis**: Select top N rows by any metric
- **CSV Export**: Export filtered results with full dataset (no display truncation)
- **Auto-Metric Detection**: Automatically categorizes metrics (higher-is-better, lower-is-better)
- **Responsive UI**: Handles large datasets (50k+ rows) with display truncation
- **Inline Logging**: Shows load outcomes and skipped malformed files

## Dependencies

- **Python 3.9+**
- **PySide6** (Qt for Python)
- **pandas** (data manipulation)
- **Standard library only** (no additional packages)

## Installation

```bash
# Install dependencies
pip install PySide6 pandas

# Or use requirements.txt from the main project
pip install -r requirements.txt
```

## Running the Application

```bash
python opt_console_lite.py
```

## Workflow

### 1. Load Data

1. Click **"Choose Folder & Load"**
2. Select a folder containing JSON files
3. Optionally check **"Recursive"** to scan subfolders
4. All JSON files are loaded and merged into a single table
5. Each row includes a `_source_file` column for traceability

**JSON Format Expected:**
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
      "num_trades": 45,
      "param_lookback": 20
    }
  ]
}
```

**Note**: Files with malformed JSON are skipped and logged in the inline log area.

### 2. Filter Data

#### Free-Text Filter
Enter pandas query expressions with percentage support:

```python
# Examples
max_drawdown < 8%
max_drawdown < 8 %
max_drawdown < 0.08

profit_factor >= 1.6 and num_trades > 30
calmar_ratio >= 0.5 and max_drawdown < 10%
```

All three percentage formats (`8%`, `8 %`, `0.08`) are equivalent.

#### Layered Filters
1. Click **"+"** to add a filter row
2. Select metric, operator, and value
3. Multiple rows are combined with AND logic
4. Click **"✕"** to remove a filter row

**Example**: Add two filters:
- `calmar_ratio >= 0.5`
- `profit_factor >= 1.6`

These combine as: `(calmar_ratio >= 0.5) and (profit_factor >= 1.6)`

### 3. Sort & Limit

#### Sorting
Enter comma-separated column names in **"Sort By"**:

```
# Examples
-calmar_ratio                    # Descending by calmar_ratio
calmar_ratio                     # Ascending by calmar_ratio
-calmar_ratio,profit_factor      # Multi-key: primary desc, secondary asc
-calmar_ratio,-profit_factor     # Both descending
```

Prefix with `-` for descending order.

#### Limiting
Set **"Limit"** to cap the number of rows (0 = no limit).

### 4. Top-N Analysis

Select top N rows by a chosen metric:

1. Set **N** (number of rows to keep)
2. Choose **Metric** from dropdown (auto-populated after load)
3. Select **Direction**:
   - **Desc (best first)**: Higher values first (for metrics like `calmar_ratio`)
   - **Asc (lowest first)**: Lower values first (for metrics like `max_drawdown`)
4. Click **"Apply Top-N"**

**Top-N Pipeline**:
1. Apply layered filters (if any)
2. Apply free-text filter (if any)
3. Sort by chosen metric (primary) + user sort keys (secondary)
4. Keep top N rows
5. Apply limit (if specified)

**Example**: 
- **N = 10**
- **Metric = calmar_ratio**
- **Direction = Desc (best first)**
- **User Sort = profit_factor**

Result: Top 10 rows by `calmar_ratio` (descending), ties broken by `profit_factor`.

### 5. Apply & Export

- **Apply (Filter → Sort → Limit)**: Apply all filters, sorting, and limits
- **Reset (Show ALL)**: Clear all filters and show the full loaded dataset
- **Export CSV**: Export the current filtered/sorted result to CSV (UTF-8)

**Important**: Export always uses the full filtered result, not just the displayed rows (which may be truncated at 50,000 for UI performance).

## UI Sections

### Left Panel (Controls)

1. **Load Folder**: Choose directory, recursive option, load button
2. **Free-Text Filter**: pandas query expression with % support
3. **Sort & Limit**: Multi-key sorting and row limit
4. **Layered Filters (AND)**: Add/remove filter rows dynamically
5. **Top-N**: Select top N rows by metric
6. **Action Buttons**: Apply, Reset, Export CSV

### Right Panel (Data View)

1. **Table**: Displays current data (truncated at 50,000 rows if needed)
2. **Load Log**: Shows load messages, skipped files, and errors

### Status Bar

Shows:
- **Row count**: Current filtered dataset size
- **Last operation time**: In milliseconds
- **Truncation notice**: If displaying fewer than total filtered rows

Example: `Rows: 1,234 | Last op: 15 ms | Showing 50,000 of 75,000`

## Auto-Metric Detection

After loading data, the app auto-detects metrics and categorizes them:

### Higher-is-Better (↑)
- Patterns: `calmar`, `sharpe`, `sortino`, `profit_factor`, `pf`, `win_rate`, `roi`, `cagr`, `return`, `expectancy`, `avg_trade`, `median_trade`

### Lower-is-Better (↓)
- Patterns: `max_drawdown`, `mdd`, `drawdown`, `volatility`, `stdev`, `std`, `downside_risk`, `var`

### Other
- All other numeric columns (excluding `param_*`, `id`, `_id`, `chart`, `symbol`, `timestamp`, `date`, `time`)

Metrics are shown in the dropdowns with directional indicators (↑↓) for clarity.

## Performance Notes

- **Display Truncation**: The table view shows up to 50,000 rows for UI responsiveness
- **Full Export**: Export always includes the complete filtered dataset
- **Large Datasets**: Tested with 50k-200k rows; operations complete in <1 second
- **Status Indicator**: When truncated, status bar shows: `Showing X of Y rows`

## Filter Expression Examples

### Basic Filters
```python
max_drawdown < 0.08
profit_factor >= 1.5
num_trades > 20
```

### Percentage Formats (All Equivalent)
```python
max_drawdown < 8%
max_drawdown < 8 %
max_drawdown < 0.08
```

### Combined Filters
```python
max_drawdown < 8% and profit_factor >= 1.6
calmar_ratio >= 0.5 and num_trades >= 30
profit_factor > 1.5 and win_rate > 0.6 and max_drawdown < 10%
```

### Advanced Filters
```python
(calmar_ratio > 1.0 or sharpe_ratio > 1.5) and max_drawdown < 0.1
param_lookback >= 10 and param_threshold <= 0.5
```

## Sort Expression Examples

```
# Single column
-calmar_ratio              # Descending
calmar_ratio               # Ascending

# Multiple columns
-calmar_ratio,profit_factor              # Primary desc, secondary asc
-calmar_ratio,-profit_factor             # Both descending
-calmar_ratio,profit_factor,-num_trades  # Three-key sort
```

## Error Handling

### Malformed JSON
- Files with invalid JSON are **skipped** (not crashed)
- Logged in the inline log area with error details

### Missing Columns
- If a filter/sort references a non-existent column, an error dialog appears
- No data loss; current view is preserved

### Invalid Filter Syntax
- pandas query syntax errors are caught and displayed
- Suggestions provided in error dialog

### Empty Results
- If filters produce zero rows, the table is cleared
- Status bar shows "0 rows"
- Reset button restores the full dataset

## Keyboard Shortcuts

- **Enter in fields**: Does NOT auto-apply (use explicit Apply buttons)
- **Ctrl+Q**: Quit application (standard)

## Comparison: Lite vs Full

| Feature | Lite | Full App |
|---------|------|----------|
| JSON Loading | ✓ | ✓ |
| Filter & Sort | ✓ | ✓ |
| Top-N | ✓ | ✓ |
| Layered Filters | ✓ | ✗ |
| Quality Control | ✗ | ✓ |
| Pareto Analysis | ✗ | ✓ |
| Stability Analysis | ✗ | ✓ |
| Parameter Correlation | ✗ | ✓ |
| Profile Management | ✗ | ✓ |
| Parquet Export | ✗ | ✓ |
| Metadata Sidecars | ✗ | ✓ |

## Troubleshooting

### No metrics in dropdown
- **Cause**: Data not loaded yet
- **Solution**: Load data first using "Choose Folder & Load"

### Filter syntax error
- **Cause**: Invalid pandas query syntax
- **Solution**: Check examples above; ensure column names match exactly (case-sensitive)

### Slow loading
- **Cause**: Very large number of files or very large JSON files
- **Solution**: Use non-recursive mode; filter files before loading

### Export fails
- **Cause**: File permissions or invalid path
- **Solution**: Choose a writable directory; avoid special characters in filename

## Advanced Tips

### Combining Filters
1. Use **Layered Filters** for simple numeric conditions
2. Use **Free-Text Filter** for complex logic (AND/OR combinations)
3. Both are applied together (layered filters AND free-text filter)

### Efficient Top-N Workflow
1. Apply layered/free-text filters first to reduce dataset
2. Use Top-N to select best candidates
3. Export for further analysis

### Exploring Large Datasets
1. Load data (shows ALL rows by default)
2. Use Reset button to return to full dataset anytime
3. Iteratively refine filters
4. Export final shortlist

## License

Part of the Optimization Console project. See main README.md for licensing details.

## Support

For issues or questions, refer to the main project documentation or open an issue on the project repository.

