# Query Results JSON Viewer - Simple Mode

A standalone PySide6 desktop application for interactively filtering and sorting JSON optimization results.

## Features

- **Load Multiple JSON Files**: Select a folder and load all `.json` files at once
- **Auto-Detected Filters**: Automatically creates filters for all numeric and categorical fields with smart percent/ratio handling
- **Interactive Filtering**: Toggle filters on/off, set ranges, exact values, or "Between" (Min-Max) ranges
- **Header Sorting**: Click column headers to sort, drag columns to reorder
- **Top N Limiting**: Limit results to top N rows after filtering and sorting
- **Export Results**: Save filtered and sorted data as CSV
- **Clean Interface**: Single-page design with all controls visible

## Requirements

Install dependencies:

```bash
pip install PySide6 pandas
```

Or use the existing `requirements.txt` if available in your project.

## Quick Start

1. **Launch the application:**

   **Windows:** Double-click `run_simple.bat`
   
   **Or use command line:**
   ```bash
   python opt_console_simple.py
   ```

2. **Load JSON files:**
   - Click **"Load Folder"** button
   - Select a folder containing `.json` files
   - The app loads all JSON files (non-recursive, single folder only)
   - All results are displayed immediately

3. **Apply filters:**
   - Check the checkbox next to any field to enable filtering
   - **Numeric fields**: Choose operator (≤, =, ≥, ≠, ↔) and enter value(s)
     - **↔ Between**: Shows Min and Max input fields for range filtering
   - **Categorical fields**: Choose operator (=, !=) and enter text value
   - Multiple filters combine with AND logic
   - **Filter legend** at the top shows all available operators

4. **Sort and limit:**
   - **Click column headers** to sort (ascending/descending)
   - **Drag column headers** to reorder columns
   - Set "Top N" to limit results (0 = show all)
   - Top N applies after filtering and current sort order

5. **Apply changes:**
   - Click **"Apply Filters"** to update the table
   - Click **"Reset"** to clear all filters and show full data

6. **Export:**
   - Click **"Export CSV"** to save the current filtered/sorted data
   - Choose a location and filename
   - Data is saved as UTF-8 CSV

## JSON Format

The app expects JSON files with this structure:

```json
{
  "metadata": { ... },
  "results": [
    {
      "field1": value1,
      "field2": value2,
      "max_drawdown": 0.15,
      "win_rate": 0.58,
      ...
    },
    ...
  ]
}
```

- **"results"**: Array of result objects (required)
- **"metadata"**: Ignored by the app
- Each result object becomes a row in the table
- A `_source_file` column is automatically added with the filename

## Numeric Field Handling

The app intelligently handles **percentages** and **ratios** based on field names:

### Percentage Fields
Only specific fields are treated as percentages:
- **Field names**: `win_rate`, `max_drawdown`, or fields ending with `_pct` or `_percent`
- **Input formats**: `60`, `60%`, or `0.60` (all interpreted as 60%)
- **Display format**: `60.00%`
- **Examples**: `win_rate`, `max_drawdown`, `success_pct`

### Ratio Fields  
All other numeric fields (including ratio fields) display as raw numbers:
- **Field names**: `sharpe_ratio`, `profit_factor`, `calmar_ratio`, etc.
- **Input format**: Raw numbers (e.g., `4` means 4.0, not 400%)
- **Display format**: `4.0000` (4 decimal places, no % suffix)
- **Examples**: `sharpe_ratio`, `profit_factor`, `calmar_ratio`, `sortino_ratio`

## Filter Examples

### Numeric Filters

1. **Less than or equal to:**
   - Field: `profit_factor`
   - Operator: `≤`
   - Value: `2.5`

2. **Between range:**
   - Field: `max_drawdown`
   - Operator: `↔`
   - Min: `5%` (or `0.05`)
   - Max: `15%` (or `0.15`)

3. **Greater than or equal to:**
   - Field: `win_rate`
   - Operator: `≥`
   - Value: `60%` (or `60` or `0.60`)

4. **Not equal to:**
   - Field: `sharpe_ratio`
   - Operator: `≠`
   - Value: `0`

### Percentage Input

The app accepts percentages in two formats:
- **Decimal**: `0.15` (15%)
- **Percent notation**: `15%`

Both are converted to decimal internally (0.15).

### Categorical Filters

1. **Equals:**
   - Field: `strategy`
   - Operator: `=`
   - Value: `MeanReversion`

2. **Not equals:**
   - Field: `_source_file`
   - Operator: `!=`
   - Value: `test.json`

## Display Features

- **Percentage columns**: Only `win_rate`, `max_drawdown`, and `*_pct`/`*_percent` fields display as percentages (e.g., `15.00%`)
- **Numeric precision**: Float values displayed with 4 decimal places
- **Column sizing**: Columns auto-resize to fit content
- **Performance limit**: Display up to 50,000 rows for optimal performance

## Status Bar

Shows real-time information:
- **Rows**: Current number of visible rows
- **Loaded from X files**: Number of successfully loaded JSON files  
- **Filters**: Number of active filters (when filtering is applied)
- **Last op**: Time taken for last operation in milliseconds
- **Showing X of Y**: Appears when Top N limiting or 50,000 row cap is active

## Log Area

Located at the bottom-left, the log shows:
- Files successfully loaded with row counts
- Files skipped due to errors (JSON decode issues, missing fields)
- Filter application results
- Export operations

## Error Handling

- **Malformed JSON**: Skipped with error message in log
- **Missing "results" field**: Skipped with warning
- **Invalid filter values**: Filter ignored silently
- **No files found**: Warning dialog displayed

## Keyboard Shortcuts

- Standard OS shortcuts apply (Ctrl+C for copy in table, etc.)
- No custom shortcuts implemented

## Tips

1. **Start broad, refine gradually**: Load data first, then add filters one at a time
2. **Use Top N for quick testing**: Limit to 100-1000 rows while experimenting with filters  
3. **Use header sorting**: Click column headers to sort, no need for separate controls
4. **Between ranges**: Use ↔ operator for min-max ranges, both fields are optional
5. **Check the log**: If results look wrong, check the log for load errors
6. **Reset often**: Use Reset button to quickly clear all filters and start fresh
7. **Export filtered data**: Export saves current filtered+sorted+Top N result

## Limitations

- **Single folder only**: Does not search subfolders recursively
- **Performance cap**: Maximum 50,000 rows displayed
- **No profiles**: Cannot save/load filter configurations
- **No metadata handling**: Metadata in JSON files is ignored
- **Simple filters only**: No support for complex expressions or OR logic

## Troubleshooting

**No data appears after loading:**
- Check that JSON files contain a "results" array
- Review the log area for parsing errors
- Verify JSON format is valid

**Filters don't work:**
- Ensure the checkbox is checked
- Verify value format (for percentages: use 60, 60%, or 0.60)
- For Between (↔): check that min ≤ max
- Click "Apply Filters" button after setting filters

**Percentage values look wrong:**
- Check if your data uses decimals (0.15) or percentages (15)
- The app auto-detects, but you can manually enter either format

**Export fails:**
- Check file permissions in the target folder
- Ensure filename doesn't contain invalid characters
- Verify you have disk space available

## Comparison with Other Modes

This is the **simple** version focused on ease of use:

- **opt_console_simple.py**: This app - lightweight, one-page filtering
- **opt_console_lite.py**: CLI-based filtering with JSON config
- **ui_app.py**: Full-featured desktop app with analytics, charting, profiles

Choose this version if you need:
- Quick interactive filtering
- No configuration files
- Visual interface without complexity
- Standalone tool with minimal dependencies

## License

Same as parent project.

## Support

For issues or questions, refer to the main project README or documentation.

