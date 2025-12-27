# Optimization Pipeline: Latency Reduction Action Plan

## Introduction

This document outlines a modularized action plan to further decrease latency between running the optimizer and saving results. The goal is to implement these improvements incrementally, ensuring code integrity, minimal disruption, and long-lasting, efficient solutions.

## Guiding Principles

*   **Code Integrity**: Every change will be thoroughly tested to ensure the correctness of the optimization and metric calculations.
*   **Minimal Disruption**: Edits will be localized and designed to integrate smoothly with the existing codebase.
*   **Efficient Code**: Solutions will prioritize vectorized operations, single-pass processing, and intelligent resource management.
*   **Complete & Long-Lasting**: No temporary or "band-aid" patches; all implementations will aim for robustness and maintainability.

---

## Action Plan: Further Latency Reductions

### Phase 1: Core Performance Enhancements

These items focus on fundamental architectural improvements for speed.

### 1. Implement Parallel Processing for Chart Evaluation

**Objective**: Utilize multiple CPU cores to process different charts concurrently, significantly reducing overall run time for multi-chart optimizations.

*   **Action Items**:
    *   **1.1 Encapsulate Single Chart Processing**: Create a dedicated function to handle the entire optimization pipeline for a single chart. This function will take a chart path, parameters, and toggles, and return the processed results and trades for that specific chart.
    *   **1.2 Integrate Parallel Executor**: Modify `scripts/run_optimizer_cli.py` to use a parallel processing library (e.g., `multiprocessing.Pool` or `joblib`) to distribute the single-chart processing function across available CPU cores.
    *   **1.3 Aggregate Parallel Results**: Implement robust logic to collect and combine the results and trades DataFrames returned from each parallel process into the final aggregate results.

*   **Requisite Items**:
    *   Familiarity with Python's `multiprocessing` module or `joblib` for parallel task distribution.
    *   Ensuring that each chart's processing is entirely independent and does not rely on shared mutable state.

*   **Prerequisite Items**:
    *   The existing single-threaded evaluation logic must be stable and correct (confirmed).

*   **Flow of Tasks**:
    1.  Create a new module, e.g., `src/optimizer/parallel_runner.py`, and define a function `process_single_chart(chart_path, params_list, toggles, run_id_prefix)`. This function will encapsulate the chart loading, parameter sampling, and the loop calling `evaluate_collect` or `evaluate_collect_kfold` for a single chart.
    2.  In `scripts/run_optimizer_cli.py`, import the new `process_single_chart` function.
    3.  Replace the existing `for chart_idx, chart_path in enumerate(selected_charts):` loop with a call to a parallel executor (e.g., `Pool.map` or `joblib.Parallel(n_jobs=-1)(...)`) that applies `process_single_chart` to each `selected_chart`.
    4.  Refactor the collection of `all_rows` and `trades_batch` in `scripts/run_optimizer_cli.py` to correctly aggregate the outputs from the parallel processes.
    5.  Thoroughly test the parallel execution to ensure no race conditions, deadlocks, or data corruption occur.

### 2. Implement JIT Compilation (Numba) for Hotspots

**Objective**: Accelerate computationally intensive Python loops within the strategy and metric calculations by compiling them to optimized machine code.

*   **Action Items**:
    *   **2.1 Profile Codebase**: Identify the specific functions or loops within `src/strategy/bands.py` (signal computation) and `src/metrics/metrics.py` (individual metric calculations) that consume the most CPU time.
    *   **2.2 Apply Numba Decorators**: Apply the `@numba.jit` decorator to the identified hotspot functions, prioritizing `nopython=True` mode for maximum performance.
    *   **2.3 Verify Numba Integration**: Ensure that the Numba-compiled functions produce identical results to their original Python counterparts.

*   **Requisite Items**:
    *   Understanding of Numba's capabilities, supported data types, and limitations (e.g., pure Python vs. NumPy/Pandas integration).
    *   The `numba` library must be installed in the environment.

*   **Prerequisite Items**:
    *   A clear understanding of the mathematical operations within the target functions.

*   **Flow of Tasks**:
    1.  Install Numba: `pip install numba`.
    2.  Run a profiler (e.g., `cProfile` or `line_profiler`) on a sample optimization run to pinpoint exact CPU bottlenecks within `compute_signals` and the individual metric functions.
    3.  In `src/strategy/bands.py`, add `import numba` and apply `@numba.jit(nopython=True)` to relevant functions (e.g., any custom loop-based indicator calculations). If `nopython=True` causes errors, try without it or with `forceobj=True` as a fallback.
    4.  In `src/metrics/metrics.py`, apply `@numba.jit(nopython=True)` to simple, array-based metric calculations where loops or NumPy operations can benefit directly.
    5.  Execute a comprehensive set of tests and compare results against non-Numba runs to ensure numerical equivalence and confirm performance gains.

### Phase 2: Advanced Data Handling & Storage

These items focus on optimizing how results are stored and retrieved, particularly for very large datasets.

### 3. Implement Optimized Trade Logging & Aggregation

**Objective**: Provide flexible control over trade logging to reduce I/O overhead for large runs, allowing aggregation or omission of granular trade data.

*   **Action Items**:
    *   **3.1 Introduce Trade Logging Granularity Option**: Add a new parameter (e.g., `trade_log_mode`) to `scripts/run_optimizer_cli.py` to control trade output: `full` (current behavior), `aggregated` (e.g., daily PnL summary), or `none`.
    *   **3.2 Conditional Trade Data Collection**: Modify `evaluate_collect` and `evaluate_collect_kfold` (in `src/optimizer/search.py`) to conditionally return `trades_df` based on the selected `trade_log_mode`.
    *   **3.3 Implement Trade Aggregation Logic**: Create a new function (e.g., in `src/io/fast_io.py`) that can aggregate raw trade data into a summarized format (e.g., daily total PnL, number of trades, win rate per day).
    *   **3.4 Update Output Saving**: Adjust the output generation logic in `scripts/run_optimizer_cli.py` and the Excel/JSON writing functions to handle either full, aggregated, or no trade data based on `trade_log_mode`.

*   **Requisite Items**:
    *   Clear definition of aggregation strategies (e.g., what constitutes an "aggregated" trade log).
    *   Robust handling of edge cases where no trades occur or data is sparse.

*   **Prerequisite Items**:
    *   Understanding of Pandas `groupby()` and `resample()` functions for time-series aggregation.

*   **Flow of Tasks**:
    1.  Add a `--trade-log-mode` argument to `scripts/run_optimizer_cli.py` (with choices like `full`, `aggregated`, `none`).
    2.  Pass this `trade_log_mode` down to `evaluate_collect` and `evaluate_collect_kfold`.
    3.  In `src/optimizer/search.py`, modify `evaluate_collect` and `evaluate_collect_kfold` to return `trades_df` only if `trade_log_mode == 'full'`.
    4.  Create a new function, e.g., `src/io/trade_aggregator.py::aggregate_trades(trades_df, interval='1D')`, that transforms the detailed trades into a summary.
    5.  In `scripts/run_optimizer_cli.py`, if `trade_log_mode == 'aggregated'`, call `aggregate_trades` before passing the data to the output functions.
    6.  Update Excel and JSON output functions to correctly label and store aggregated trade data.

### 4. Integrate Database for Persistent Results Storage

**Objective**: Provide a more scalable and queryable storage solution for optimization results, especially for very extensive or frequent runs, improving long-term data management and retrieval performance.

*   **Action Items**:
    *   **4.1 Database Schema Design**: Define a robust and query-efficient schema for storing run metadata, optimization results, and (optionally) trade data in a relational database (e.g., SQLite for simplicity, or PostgreSQL if future scaling requires).
    *   **4.2 Implement Database Writer Module**: Create a new Python module with functions to connect to the database, create tables (if they don't exist), and efficiently insert run metadata, results, and trades.
    *   **4.3 Integrate into CLI**: Add an option to `scripts/run_optimizer_cli.py` to enable database storage.
    *   **4.4 (Optional) Database Reader/Query Tool**: Develop a basic utility to query and retrieve results directly from the database, demonstrating its value.

*   **Requisite Items**:
    *   Proficiency in SQL and database design principles.
    *   Familiarity with a Python database connector library (e.g., `sqlite3`, `SQLAlchemy`).

*   **Prerequisite Items**:
    *   Stable and complete results DataFrames from the `evaluate_collect` functions.

*   **Flow of Tasks**:
    1.  Create a new module, e.g., `src/io/db_handler.py`.
    2.  In `db_handler.py`, define functions: `init_db(db_path)`, `save_run_metadata(conn, run_metadata)`, `save_results_df(conn, run_id, results_df)`, and `save_trades_df(conn, run_id, trades_df)`.
    3.  In `scripts/run_optimizer_cli.py`, add a `--save-to-db` argument.
    4.  If `--save-to-db` is enabled, call `init_db` at the start of `main` to get a database connection.
    5.  After `results_df` and `trades_df_all` are finalized, call the `save_results_df` and `save_trades_df` functions to persist data.
    6.  (Optional but recommended for utility) Create a separate script, e.g., `scripts/query_optimizer_db.py`, that allows users to run SQL queries against the saved data.

### Phase 3: Minor Optimizations & User Control

These items focus on smaller, targeted improvements and enhanced user configurability.

### 5. Enhanced Pre-computation of Static Indicators

**Objective**: Further reduce redundant calculations by ensuring that any indicators whose values do not change with parameter variations are computed only once per chart.

*   **Action Items**:
    *   **5.1 Analyze `compute_signals`**: Review `src/strategy/bands.py::compute_signals` and identify any indicator calculations that are independent of the `params` dictionary (e.g., a simple moving average, ATR if `atr_len` is not a parameter).
    *   **5.2 Refactor for Pre-computation**: Create a new function (e.g., `_precompute_static_indicators(price)`) that calculates these static indicators.
    *   **5.3 Integrate Pre-computation**: Modify `evaluate_collect` (in `src/optimizer/search.py`) to call `_precompute_static_indicators` once per chart and pass the results to `compute_signals`.

*   **Requisite Items**:
    *   Detailed understanding of the dependencies of each indicator within the strategy.

*   **Prerequisite Items**:
    *   A clean separation of responsibilities within `compute_signals`.

*   **Flow of Tasks**:
    1.  In `src/strategy/bands.py`, identify indicators that are constant across different `params`.
    2.  Create `_precompute_static_indicators(price: pd.DataFrame) -> dict` in `src/strategy/bands.py` (or a new `src/strategy/indicator_utils.py`) that returns a dictionary of these pre-computed series.
    3.  Modify `compute_signals` to accept an optional `precomputed_indicators: dict` argument. If provided, it uses these; otherwise, it computes them internally.
    4.  In `src/optimizer/search.py`, within the main chart loop, call `_precompute_static_indicators` once for each `price` DataFrame and pass the result to `compute_signals` in `evaluate_collect`.

### 6. Granular User Control Over Output Types

**Objective**: Give users more fine-grained control over which output artifacts are generated (JSON, CSV, Excel), allowing them to skip unneeded I/O entirely.

*   **Action Items**:
    *   **6.1 Separate Output Flags**: Replace or augment the `performance_mode` with distinct boolean flags (e.g., `--output-json`, `--output-csv`, `--output-excel`).
    *   **6.2 Update CLI Prompts**: Modify the `scripts/run_optimizer_cli.py` to prompt the user for each output type independently.
    *   **6.3 Conditional Output Generation**: Adjust the output saving logic in `main()` to only call the relevant `write_run_json`, Excel append, and CSV export functions based on these flags.

*   **Requisite Items**:
    *   Clear and intuitive command-line interface design.

*   **Prerequisite Items**:
    *   All output writing functions are modular and can be called independently.

*   **Flow of Tasks**:
    1.  In `scripts/run_optimizer_cli.py`, modify `get_optimization_parameters` to include new boolean questions: "Output JSON?", "Output CSV?", "Output Excel?".
    2.  In the `main` function, update the `if params['performance_mode'] > 1:` checks for Excel and the `if params['performance_mode'] > 1:` check for CSV to instead check the new explicit `output_excel`, `output_csv` flags respectively. JSON already has a dedicated section, ensure it also checks `output_json`.
    3.  Ensure the summary section correctly reports which files *will* be generated based on these choices.

---

This plan prioritizes the most impactful changes first, building a more robust and efficient pipeline step by step. Each phase can be implemented and tested independently to minimize risk.
