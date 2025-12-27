### Break the Bottleneck: Why We Were Slow, What We Fixed, and How

This document explains, in detail, how we identified the results-recording bottleneck, why specific optimizations were chosen, and exactly how they were implemented. The core optimizer, strategy logic, and metrics remain unchanged. The only differences are performance optimizations in the results recording/serialization layer and the optional Excel notebook update path.

### Context and Symptoms
- The optimizer completed in minutes, but recording results sometimes took up to ~30 minutes.
- CPU sat near 100% during recording; antivirus (McAfee) was also consuming significant CPU.
- The slowdown appeared after trials finished, implicating data processing and I/O, not simulation/evaluation.

### Diagnosis: Where Time Was Spent
We traced the slowdowns to common pandas and Excel patterns that become costly at scale:

- Repeated concatenations and copies in `scripts/save_opt_results.py` and `src/io/notebook.py` when building large DataFrames (e.g., trades across many trials/charts).
- Per-DataFrame datetime conversion with `pd.to_datetime` on every trades frame before concatenation.
- Large sorts on full result sets via `DataFrame.sort_values` multiple times.
- Reading existing Excel sheets (e.g., `AllResults`, `AllTrades`) only to append and rewrite them, which is expensive for large workbooks and triggers antivirus real-time scanning.
- Series.map/apply for per-row string construction (e.g., `trial_uid`), which is slower than vectorized approaches.
- Excel formatting/width adjustments and timezone stripping done repeatedly.

Together, these create high CPU pressure and many file operations (which in turn trigger antivirus scanning and I/O contention).

### Design Principles for the Fix
- Favor vectorized operations over row-wise `.map()`/`.apply()`.
- Accumulate records into lists and perform one `pd.concat(...)` at the end.
- Convert datetimes once in batch, not repeatedly per small frame.
- Sort only when it materially benefits the user and is feasible for the dataset size.
- Avoid reading/writing large Excel sheets unless absolutely required; prefer single-writer-pass appends.
- Reduce memory pressure by avoiding unnecessary `.copy()` and downcasting where safe.
- Minimize the number of file operations to be antivirus-friendly.

### What We Implemented (and Where)

- New CPU-/I/O-optimized scripts and helpers:
  - `scripts/save_opt_results_fast.py` (antivirus-friendly, minimal processing, optional CSV-only)
  - `scripts/save_opt_results_optimized.py` (CPU-optimized path; same outputs, smarter logic)
  - `scripts/save_opt_results_interactive.py` (interactive UX: chart/method/trials/k-fold/embargo/perf mode)
  - `src/io/fast_io.py` (reusable, high-performance helpers)
  - Batch launchers: `run_optimizer_fast.bat`, `run_optimizer_interactive.bat`, and updated `run_optimizer.bat` (PYTHONPATH and mode selection)

Below are each optimization, why it matters, and the implementation details.

---

### 1) Vectorized operations instead of slow .map()/.apply()

- Why: Series `.map()` and `.apply()` are per-element Python loops. For constructing `trial_uid` strings and similar operations across tens/hundreds of thousands of rows, vectorization is much faster and reduces Python overhead.

- How:
  - In `src/io/fast_io.py`, we introduced `vectorized_trial_uid_creation(trial_ids: pd.Series, run_id: str) -> pd.Series`, which converts IDs to a NumPy array, builds a boolean validity mask, and constructs the UID strings in a vectorized manner.
  - In `scripts/save_opt_results_optimized.py`, we implemented a similar local helper `create_trial_uids_vectorized(...)` (functionally equivalent) to avoid `.map()` when generating `trial_uid`.

- Where it’s used:
  - `scripts/save_opt_results_optimized.py`: adds `trial_uid` to results/trades using the vectorized helper.
  - `scripts/save_opt_results_interactive.py`: uses `vectorized_trial_uid_creation` from `fast_io.py` when writing JSON/Excel.

---

### 2) Single DataFrame concatenation instead of incremental

- Why: Repeated `pd.concat([...])` in a loop grows cost super-linearly because each concat creates a new DataFrame. The correct pattern is to accumulate frames in a list and perform one concat at the end.

- How:
  - We now gather all trades frames in a list (`trades_batch`) per run and perform a single `pd.concat(trades_batch, ignore_index=True, sort=False)` once, instead of incrementally concatenating.
  - A reusable helper `single_concat_operation(dfs)` in `src/io/fast_io.py` centralizes the pattern.

- Where it’s used:
  - `scripts/save_opt_results_optimized.py` and `scripts/save_opt_results_interactive.py`: build a list of trades DataFrames and concatenate once at the end.

---

### 3) Batch datetime processing instead of per-DataFrame

- Why: Calling `pd.to_datetime` for each small trades frame is slow. Doing this once, in batch, on a list of DataFrames reduces overhead, avoids redundant conversions, and lets us strip timezones consistently.

- How:
  - `src/io/fast_io.py` provides `batch_datetime_conversion(dfs, datetime_cols=[...])`, converting and tz-normalizing the target columns for all frames at once.
  - `scripts/save_opt_results_optimized.py` includes a local `process_datetime_columns_batch(...)` with the same goal.

- Where it’s used:
  - `scripts/save_opt_results_interactive.py`: calls `batch_datetime_conversion` before the single concat.
  - `scripts/save_opt_results_optimized.py`: processes `Entry Date`/`Exit Date` in batch.

---

### 4) Smart sorting that skips large datasets

- Why: Sorting millions of rows is O(n log n) and can dominate runtime. We only need sorting when it benefits the display or downstream processing.

- How:
  - `src/io/fast_io.py` adds `smart_dataframe_sort(df, sort_cols, max_rows=...)` to skip sorting beyond thresholds.
  - `scripts/save_opt_results_optimized.py` uses `efficient_dataframe_sort(...)` to sort only when dataset size is manageable. Stable sort (`kind='mergesort'`) is used when ordering by multiple keys.

- Where it’s used:
  - Both the optimized and interactive flows conditionally sort results and trades and fall back to unsorted writes for very large datasets.

---

### 5) Antivirus-friendly I/O with minimal file operations

- Why: Real-time antivirus scanning intercepts file opens/writes, especially with Excel. Reducing the number and size of file operations substantially lowers wall-clock time. Avoiding reads of large existing sheets eliminates unnecessary work.

- How:
  - `scripts/save_opt_results_fast.py` introduces a mode that:
    - Skips reading large existing Excel data (or skips Excel entirely via `--csv-only`).
    - Performs a single write pass per run (if Excel is enabled), minimizing file system churn.
  - `src/io/fast_io.py` provides `efficient_excel_write(filepath, sheets_data, max_file_size_mb=...)`: a single-writer-pass approach that avoids loading huge sheets and writes only the necessary tabs.
  - Batch files (`run_optimizer_fast.bat`, `run_optimizer_interactive.bat`, updated `run_optimizer.bat`) set `PYTHONPATH` so imports resolve cleanly without additional filesystem lookups.

- Where it’s used:
  - `scripts/save_opt_results_fast.py`: CSV-only or minimal-Excel path for maximum throughput.
  - `scripts/save_opt_results_interactive.py`: performance mode 1 (max speed) skips Excel entirely; modes 2–3 write smaller, targeted sheets.

---

### 6) Memory optimizations and reduced copying

- Why: Large intermediate DataFrames amplify CPU, memory, and GC overhead. Avoiding unnecessary `.copy()`, consolidating operations, and downcasting numeric types improves speed and robustness.

- How:
  - `src/io/fast_io.py` includes `optimize_dataframe_memory(df)` to downcast `int64/float64` where safe.
  - All flows minimize `.copy()` usage and avoid repeated frame rebuilds.
  - Results and trades are built once and reused; concatenation is done once; sorting is conditional.

- Where it’s used:
  - `scripts/save_opt_results_optimized.py` and `scripts/save_opt_results_interactive.py` apply downcasting and avoid repeated copies.

---

### Interfaces and How to Run

- `run_optimizer_fast.bat`
  - Presents a fast/optimized choice and sets `PYTHONPATH` to avoid import issues.
  - Fast mode supports: `--fast-mode` (minimal processing) and `--csv-only` (skip Excel entirely).

- `run_optimizer.bat`
  - Updated to offer: 1) FAST MODE, 2) OPTIMIZED, 3) ORIGINAL.
  - Preserves the legacy path while offering performance options.

- `run_optimizer_interactive.bat`
  - Launches `scripts/save_opt_results_interactive.py`.
  - Interactive selection: charts (single/multiple/all), method (random/grid/lhs/sobol), trials, k-fold, embargo, performance mode, and metric.

### Expected Impact
- CSV-only fast mode: reduces post-optimization recording from tens of minutes ➝ ~1–3 minutes (data-dependent).
- Optimized mode with Excel: typically 3–8 minutes instead of 30+ for large runs.
- Reduced antivirus interference by minimizing file ops and large reads.

### Strategy/Results Integrity
- The optimizer’s core sampling, evaluation functions, and entry/exit logic remain unchanged.
- Exit still uses closing above the inner upper band.
- K-fold and embargo behavior remain the same; we added interactive controls but did not alter the underlying logic.

### Trade-offs and Notes
- When datasets are very large, we may skip expensive sorts in workbook tabs for speed. This does not change results; it affects only presentation order.
- The standalone `save_opt_results_fast.py` can trim JSON payloads for size; use the interactive/optimized versions for full JSON.
- All Excel writing operates in a single pass; we avoid loading large `AllResults`/`AllTrades` unless explicitly small enough.

### Opportunities for Further Realism and Robustness
- Walk-forward/rolling OOS validation (in addition to time-based k-fold with embargo).
- Multiple-comparisons control (e.g., PBO/deflated Sharpe) across many trials/charts.
- More realistic costs and slippage models (spread, volatility- or time-of-day-based slippage).
- Auto-adjust Sobol trial counts to the nearest power-of-two to remove balance warnings.

### File Inventory (added/updated)
- Added: `scripts/save_opt_results_fast.py`
- Added: `scripts/save_opt_results_optimized.py`
- Added: `scripts/save_opt_results_interactive.py`
- Added: `src/io/fast_io.py`
- Added: `run_optimizer_fast.bat`, `run_optimizer_interactive.bat`
- Updated: `run_optimizer.bat` (mode selection + PYTHONPATH)

These are drop-in improvements around the existing optimizer. The evaluation/strategy logic is preserved unchanged; the speed-ups come from better data handling and leaner I/O.


