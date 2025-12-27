### Optimization Pipeline: Architecture, Methods, and End-to-End Flow

This document explains our full optimization pipeline in depth: what it does, how it works, the methods and tools used, why we chose them, and how the data flows from raw charts to final artifacts (Excel/CSV/JSON). The core strategy and optimizer logic are unchanged by recent performance improvements; only the surrounding data handling and I/O were optimized.

### High-Level Goals
- Explore parameter configurations across one or more charts.
- Evaluate each configuration using the current strategy logic with realistic execution assumptions.
- Aggregate and persist results (metrics, parameters, trade logs) to durable artifacts.
- Support time-based k-fold validation with embargo to reduce leakage.
- Provide fast, antivirus-friendly result recording with optional Excel workbook integration.

### Core Components and Where They Live
- Orchestration (scripts):
  - `scripts/run_optimize.py` (simple baseline run)
  - `scripts/save_opt_results.py` (original recorder)
  - `scripts/save_opt_results_optimized.py` (CPU-optimized recorder)
  - `scripts/save_opt_results_fast.py` (antivirus-friendly, minimal processing)
  - `scripts/save_opt_results_interactive.py` (interactive UX: chart/method/trials/k-fold/embargo/performance)
- Optimizer and evaluation:
  - `src/optimizer/search.py`
    - Sampling: `random_search`, `grid_search`, `lhs_search`, `sobol_search`, `sample_param_sets`
    - Evaluation: `evaluate_collect` (single split), `evaluate_collect_kfold` (time-based k-fold + embargo)
    - Utilities: `normalize_param_ranges` (range parsing/coercion)
- Strategy logic (entries/exits, indicators):
  - `src/strategy/` (e.g., `bands.py` for current signals)
  - Current exit condition uses close above inner upper band (`upper_inner`).
- Configuration:
  - `config/strategy_params.py` (parameter ranges)
  - `config/user_inputs.py` (`TOGGLES`, backtest fees/position sizing/data frequency)
- Data and I/O:
  - `src/io/data_loader.py` (chart discovery and loading)
  - `src/io/notebook.py`, `src/io/excel_io.py` (Excel workbook integration)
  - `src/io/json_io.py` (per-run JSON artifacts)
  - `src/io/fast_io.py` (vectorized UID creation, batch datetime conversion, optimized Excel write, memory downcasting)
- Meta/logging:
  - `src/meta/logger.py` (append to discoveries/issues)

### Data Sources and Discovery
- Charts are discovered from `data/active_charts/` via `list_active_chart_paths()`.
- Each CSV is loaded by `load_chart_from_path` and normalized into a `DataFrame` with expected columns (e.g., `Open/High/Low/Close` and timestamps).

### Parameter Ranges and Normalization
- `config/strategy_params.py` defines `PARAM_RANGES` which may contain numeric ranges, lists, or string/range-like encodings.
- `normalize_param_ranges` coerces these into sampled value spaces that the sampler understands consistently across methods.

### Sampling Methods (Why and How)
- Random (`random_search`):
  - Fast, simple baseline with seeded reproducibility.
  - Good for coarse exploration when the space is large and constraints are mild.
- Grid (`grid_search`):
  - Systematic coverage across discrete grids. Potentially expensive as dimensionality grows.
  - We allow `max_combinations` to cap runtime.
- Latin Hypercube Sampling (LHS) (`lhs_search`):
  - Stratified sampling ensures better coverage than naive random for a fixed number of trials.
  - Useful when ranges are continuous and we want uniform marginal coverage per dimension.
- Sobol (`sobol_search`):
  - Quasi-random low-discrepancy sequence; excellent uniformity properties at scale.
  - Note: best balance properties when trial count is a power of two (we warn when not). This improves coverage consistency.

Sampling returns a list of parameter dictionaries. For each chart and each param set, we run the evaluation.

### Evaluation and Metrics
- `evaluate_collect(price, params, TOGGLES)`:
  - Executes the strategy with the given parameters on the provided chart.
  - Produces a result row (metrics + params) and an optional trades `DataFrame`.
- `evaluate_collect_kfold(price, params, TOGGLES, k_folds, embargo_frac)`:
  - Splits the time series into time-ordered folds.
  - Applies an embargo window between train/validation segments to avoid leakage via overlapping information.
  - Returns per-fold rows (for metrics) and consolidated trades.

Common metrics include `total_return`, `sharpe_ratio`, `sortino_ratio`, `calmar_robust`, `max_drawdown`, `profit_factor`, `expectancy`, `win_rate`, `avg_hold_hours`, and counts such as `total_trades`.

### Strategy Logic (Separation of Concerns)
- Strategy signal generation and risk logic live in `src/strategy/`.
- Current exit condition (as implemented in `bands.py`):
  - Base exit when `Close > upper_inner` (inner upper band), with optional protective exits via toggles (e.g., reclaiming `lower_inner`).
- Entries are a combination of trending pullbacks and ranging conditions (based on DMA bands, ATR-derived bands, and momentum regime inference).
- This separation ensures the optimizer/backtester operates independently of the chart analyzer logic and GUI concerns.

### Cross-Validation and Embargo (Why and How)
- Time-based k-fold validation simulates multiple contiguous validation windows to test parameter robustness across market regimes.
- `embargo_frac` introduces a buffer between train and validation segments to avoid information bleed when indicators or lookbacks create overlap.
- We also compute a lookback bound to validate that the fold sizes are feasible (enough bars for indicators and embargo).

### Aggregation and Post-Processing Flow
1) For each chart and trial (or fold), collect a result row and (optionally) trades.
2) Flatten the parameters into `param_*` columns for tabular outputs.
3) Append chart name, `trial_id`, and method metadata to each row.
4) Aggregate rows in a Python list.
5) Aggregate trades DataFrames in a list; perform a single concatenation at the end.
6) Compute derived fields (e.g., `duration_hours`, `trade_index`) vectorially.
7) Rank results by the selected metric (descending), subject to size-aware sorting.

### Outputs and Artifacts
- Excel workbook (`outputs/notebooks/optimizer_central.xlsx`):
  - Tabs include: `Runs`, per-run `run_<id>_summary`, optionally `AllResults`/`AllTrades`, and per-run `run_<id>_trades` when not too large.
  - Writing is performed in a single pass to reduce file operations and antivirus triggers.
- JSON artifact (`outputs/runs/<name>.json`):
  - Contains a metadata block (run settings, chart list, paths, best summary) and an array of all result rows.
  - Intended as a machine-friendly record of the full run.
- CSV exports (`outputs/csv/`):
  - Consolidated run-level CSV (all results), plus optional per-chart CSVs where useful.

### Performance Modes and Tools
- Batch entry points:
  - `run_optimizer.bat` (mode selector: 1) FAST, 2) OPTIMIZED, 3) ORIGINAL)
  - `run_optimizer_fast.bat` (fast/minimal or optimized)
  - `run_optimizer_interactive.bat` (interactive UX with chart/method/trials/k-fold/embargo/metric)
- Modes:
  - Maximum speed (CSV-only): Skips Excel entirely; minimal post-processing; reduces antivirus overhead.
  - Optimized: Vectorized operations, single concatenation, smart sorting, minimal Excel I/O.
  - Original: Preserves legacy behavior for comparison/backward-compatibility.

### Why These Design Choices
- Reproducibility: All samplers accept a seed; `trial_id` and `run_id` are used to build `trial_uid`.
- Realism: Time-based k-fold and embargo reduce leakage. Strategy evaluation uses next-bar style logic rather than same-bar fills.
- Maintainability: IO helpers (`fast_io.py`) encapsulate vectorized UID creation, batch datetime handling, and memory downcasting.
- Scalability: Single `concat`, vectorization, and skipping large sorts keep runtime linear with data volume.
- Antivirus resilience: Fewer, larger writes and avoiding large reads on existing workbooks reduce McAfee/AV overhead.

### Error Handling and Resilience
- Excel writing supports retries and atomic fallback (see `src/io/excel_io.py`).
- Notebook corruption detection: attempts to read sheet names and backs up/replaces corrupted files.
- Graceful degradation: when datasets are large, we skip expensive sorts or large sheet merges to complete writes reliably.

### Logging, Discoverability, and Reproducibility
- `append_discovery` records run metadata, artifacts, and best summaries under `outputs/` meta logs.
- `run_id` is time-based, ensuring uniqueness per run. `trial_uid = f"{run_id}:{trial_id}"` allows cross-file traceability.
- JSON artifacts allow programmatic ingestion of runs.

### Configuration and Toggles
- `config/user_inputs.py` (`BACKTEST_CONFIG`, `TOGGLES`) sets fees, starting capital, position sizing, and optional behaviors (e.g., moving processed charts after runs).
- `config/strategy_params.py` sets parameter ranges (inner/outer multipliers, smoothing lengths, momentum length). Ranges may be string-encoded and are normalized by the optimizer.

### Known Limitations and Next Steps
- Sorting and full workbook maintenance are intentionally reduced for very large runs to prioritize latency; if a fully sorted global ledger is required for every run, expect longer post-processing.
- Sobol sequences cover space best with power-of-two trial counts; we can auto-adjust or warn (we currently warn).
- Future enhancements (optional): walk-forward OOS evaluation, multiple-comparisons control (PBO/deflated Sharpe), more realistic slippage/spread models, and nearest power-of-two rounding for Sobol.

### End-to-End Flow (Condensed)
1) Discover charts (`data/active_charts/*`).
2) Normalize parameter ranges.
3) Sample parameter sets via chosen method (random/grid/LHS/Sobol).
4) Evaluate each configuration on each chart (and per-fold when k-fold enabled).
5) Accumulate result rows and trades in lists.
6) Batch process datetimes; single `concat` to build trades table.
7) Vectorized UID creation; optional size-aware sorting.
8) Persist artifacts (CSV/JSON, optionally Excel) with antivirus-friendly I/O.
9) Append discovery metadata and summarize to console.

This pipeline balances correctness, robustness, and throughput. Strategy logic is cleanly separated from the optimizer and the results recorder, enabling independent evolution of sampling methods, validation schemes, and strategy rules while keeping the recording path fast and reliable.


