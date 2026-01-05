# Quick Start: Optimization Console Lite

**Fast JSON explorer for optimizer results**

## 🚀 Launch

```bash
python opt_console_lite.py
# OR
run_lite.bat    # Windows
```

## 📖 5-Minute Workflow

### 1. Load Data
1. Click **"Choose Folder & Load"**
2. Select folder with JSON files
3. Check **"Recursive"** for subfolders (optional)

### 2. Add Filters
**Option A: Free-Text**
```python
max_drawdown < 8% and profit_factor >= 1.5
```

**Option B: Layered Filters**
- Click **"+"** to add row
- Select: `calmar_ratio` `>=` `1.0`
- Add another: `max_drawdown` `<` `10%`

### 3. Sort Results
```
-calmar_ratio,profit_factor
```
*(Descending by calmar, then ascending by PF)*

### 4. Top-N (Optional)
- Set **N = 10**
- Choose **Metric = calmar_ratio**
- Pick **Direction = Desc (best first)**
- Click **"Apply Top-N"**

### 5. Export
- Click **"Export CSV"**
- Choose save location
- Full filtered dataset saved (not just visible rows)

## 🎯 Key Features

✅ Recursive folder scanning  
✅ Percentage parsing (`8%` = `8 %` = `0.08`)  
✅ Multi-key sorting (`-col1,col2,-col3`)  
✅ Layered AND filters (add/remove dynamically)  
✅ Top-N by any metric  
✅ Display truncation at 50k rows (full export)  
✅ Inline log for malformed files  
✅ No crashes, no data loss  

## 📊 Filter Examples

```python
# Single condition
calmar_ratio >= 0.5

# Multiple conditions
profit_factor >= 1.5 and num_trades > 20

# Percentage formats (all equivalent)
max_drawdown < 8%
max_drawdown < 8 %
max_drawdown < 0.08

# Complex logic
(calmar_ratio > 1.0 or sharpe_ratio > 1.5) and max_drawdown < 10%
```

## 🔧 Status Bar Guide

```
Rows: 1,234 | Last op: 15 ms
```
✅ Normal view (all filtered rows shown)

```
Rows: 75,000 | Last op: 22 ms | Showing 50,000 of 75,000
```
⚠️ Truncated view (export still saves all 75k rows)

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| No metrics in dropdown | Load data first |
| Filter syntax error | Check examples; column names are case-sensitive |
| Slow loading | Use non-recursive; reduce file count |
| Export fails | Check write permissions; avoid special chars |

## 🆚 Lite vs Full

**Use Lite for:**
- Quick data exploration
- Simple filtering/sorting
- Top-N selection
- Fast CSV exports

**Use Full for:**
- Pareto analysis
- Stability metrics
- Parameter correlations
- Profile management
- Parquet exports
- Metadata sidecars

## 📚 More Info

- **Full Documentation**: `README_LITE.md`
- **Implementation Details**: `IMPLEMENTATION_SUMMARY_LITE.md`
- **Run Tests**: `python tests/run_smoketests_lite.py`
- **Test Data**: `test_data_lite/` folder

## ⚡ Pro Tips

1. **Reset Button**: Returns to full loaded dataset instantly
2. **Layered + Free-Text**: Both filters combine with AND logic
3. **Top-N Pipeline**: Applies filters first, then selects top N
4. **Export Full**: Always exports complete filtered result, not just displayed rows
5. **Left Panel Scrolls**: All controls accessible on small screens

---

**Dependencies**: Python 3.9+ | PySide6 | pandas  
**Install**: `pip install PySide6 pandas`

✨ **Enjoy fast JSON exploration!** ✨

