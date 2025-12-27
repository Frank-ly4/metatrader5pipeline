### 2025-08-31 – Update strategy parameter ranges (v4.2.5)

### 2025-08-31 – Deprecate config/strategy.py (v4.2.5)

### 2025-08-31 – Chart Analyzer & Splicing (v4.2.5)

- Added `scripts/chart_analyzer.py` (CLI) and engine `src/strategy/regime.py`.
- Regime detection improved: momentum lens, robust volatility (median HL/Close), McGinley/HMA slope, hysteresis.
- Splicing modes: equal parts (`--equal-parts N`), by regime (`--by-regime`), and custom ranges (`--custom`).
- Output slices saved under `data/charts_cl` (originals preserved in `data/active_charts`).
- Integrated menu in `scripts/run_interface_pro.py` (option 4) and added `run_chart_analyzer.bat`.

- Marked `config/strategy.py` as deprecated and empty; canonical ranges live in `config/strategy_params.py`.
- Optimizer and interface do not import `config/strategy.py`; removing content avoids drift/confusion.

- Updated `config/strategy_params.py` `PARAM_RANGES` to research-backed intervals:
  - fast_min_len 6–14; fast_max_len 16–28
  - slow_min_len 30–60; slow_max_len 70–150
  - dma_atr_len 10–30; atr_len 10–30
  - outer mult 1.8–3.0; inner mult 0.8–1.6 (step 0.1)
  - momentum_len 10–50; momentum_threshold 0.60–0.85 (step 0.05)
- Rationale captured in `meta/param_ranges_research.md` (ATR=14 baseline, Keltner ≈2×ATR, McGinley ~14; regime thresholds around 60–80th percentile).
- No code changes required elsewhere; Pine/MQL5 generators already accept these fields as inputs.

Run discoveries will be appended here automatically by `scripts/save_opt_results.py`.

Advanced Query & Filter (v4.2.5)
-
-Added `scripts/query_advanced.py` (CLI) and integrated into `run_interface_pro.py` (Main Menu > 6. Advanced Filtering & Search > 1. Query results by performance and portfolio conditions).
-Allows filtering backtest results from `optimizer_central.xlsx` (or CSV) by:
  - Minimum total return (`--min-return`)
  - Specific chart(s) (`--charts`)
  - Exact fees (`--fees`)
  - Exact position size percentage (`--size-pct`)
  - Exact starting capital (`--init-capital`)
-Outputs top-N matching strategies with relevant metrics and parameters; optional CSV export.
-Batch launcher: `run_query_advanced.bat` for quick command-line execution.
-Rationale: Enables targeted analysis of past optimization runs to find strategies that meet specific profit/portfolio criteria.

### 2025-08-31 – Interactive Backtest Filter & MQL5 Exporter (v4.2.5)

- Refactored the advanced query feature into a primary, interactive workflow inside `run_interface_pro.py`.
- New main menu option "1. Interactive Backtest Filter & Analysis" guides the user through a stateful analysis session.
- Workflow:
  1.  Select a recent optimization run.
  2.  View top trials and apply interactive filters for performance metrics (e.g., total_return >= 10%, calmar_robust between 2-5) and charts.
  3.  From the filtered list of strategies, users can:
      - View detailed performance breakdowns.
      - Generate MQL5 Expert Advisor (`.mq5`) files for one or more selected trials.
      - Reset filters or select a different run.
- Deprecated and removed the standalone `scripts/query_advanced.py` and `run_query_advanced.bat` as this new workflow provides a more powerful and integrated user experience.

---

## Summary of Changes from opt_4/4.2.4 to opt_4/4.2.5

- **Advanced Results Query:**
  - Enabled filtering of backtest results by specific profit targets (e.g., +10%), exact fees, position sizing, initial capital, and selected charts.
  - Implemented as a CLI script (`scripts/query_advanced.py`), integrated into the `run_interface_pro.py` menu, and available via `run_query_advanced.bat`.
- **Interactive Backtest Filter & MQL5 Exporter:**
  - Refactored the advanced query feature into a primary, interactive workflow inside `run_interface_pro.py`.
  - The new workflow allows users to select runs, apply multiple performance filters, view detailed results, and generate MQL5 Expert Advisor files directly from the filtered list.
  - Deprecated and removed the standalone `scripts/query_advanced.py` and its `.bat` launcher in favor of this more integrated and powerful tool.

- **Chart Analyzer & Splicing:**
  - Introduced a robust regime-aware chart analysis and splicing tool (`scripts/chart_analyzer.py`).
  - Comprehensive logging of all new features and changes in `meta/discoveries.md`.
---
## Cumulative highlights across opt_4 (ultimate summary)
- 4.1: Robust imports, controlled pyramiding, multi‑chart optimization, progress reporting, enriched artifacts, central Excel appender, chart mover.
- 4.2.x: Central notebook focus and schema consistency; enhanced validation and metadata; performance and UX improvements.
- 4.2.5: Regime‑aware chart analyzer and splicer; LHS/Sobol sampling; hotspots narrowing; research‑grounded parameter ranges; consolidation to `strategy_params.py`; an interactive backtest filter with MQL5 generation; batch and interface integrations.

## run_id: 20250810_110530
- timestamp: 2025-08-10 11:05:30
- charts: ['chart_cl_1.csv', 'chart_cl_2.csv', 'chart_cl_3.csv', 'chart_cl_4.csv', 'chart_cl_5.csv', 'chart_cl_6.csv']
- trials: 2
- best: total_return=27.14405115272949, sharpe_ratio=1.7559857748132426, max_drawdown=6.320847327912693
- notes: run completed
- outputs:
  - json: outputs\runs\trial_random_2_total_return_42_20250810_110530.json
  - excel: 


## [4.2.3] 2025-08-10T11:06:55.481137 — pine_generator
- Run: 20250810_110530
- Trials: 1
- trial_uid: 20250810_110530:8
- Artifacts: outputs\pine\20250810_110530_8.pine


## [4.2.3] 2025-08-10T12:48:10.082283 — optimizer
- Run: 20250810_194751
- Trials: 200
- trial_uid: 
- Artifacts: outputs\runs\trial_random_200_total_return_42_20250810_194751.json


## [4.2.3] 2025-08-10T12:55:12.292272 — pine_generator
- Run: 20250810_194751
- Trials: 1
- trial_uid: 20250810_194751:464
- Artifacts: outputs\pine\20250810_194751_464.pine


## [4.2.3] 2025-08-16T08:41:31.859696 — optimizer
- Run: 20250816_154130
- Trials: 200
- trial_uid: 
- Artifacts: outputs\runs\trial_random_200_total_return_42_20250816_154130.json


## [4.2.3] 2025-08-16T09:13:17.167280 — optimizer
- Run: 20250816_161114
- Trials: 100
- trial_uid: 
- Artifacts: outputs\runs\trial_random_100_total_return_42_20250816_161114.json


## [4.2.3] 2025-08-16T14:46:48.359034 — optimizer
- Run: 20250816_214451
- Trials: 50
- trial_uid: 
- Artifacts: outputs\runs\trial_random_50_total_return_42_20250816_214451.json


## [4.2.3] 2025-08-16T15:17:19.755978 — optimizer
- Run: 20250816_221531
- Trials: 50
- trial_uid: 
- Artifacts: outputs\runs\trial_random_50_total_return_42_20250816_221531.json


## [4.2.3] 2025-08-23T05:20:03.568595 — optimizer
- Run: 20250823_122000
- Trials: 10
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_10_total_return_42_20250823_122000.json


## [4.2.3] 2025-08-23T05:24:05.314540 — optimizer
- Run: 20250823_122333
- Trials: 100
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_100_total_return_42_20250823_122333.json


## [4.2.3] 2025-08-23T05:53:45.027587 — optimizer
- Run: 20250823_125318
- Trials: 100
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_100_total_return_42_20250823_125318.json


## [4.2.3] 2025-08-23T05:57:19.744842 — optimizer
- Run: 20250823_125618
- Trials: 200
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_200_total_return_42_20250823_125618.json


## [4.2.3] 2025-08-23T06:04:54.815860 — optimizer
- Run: 20250823_130210
- Trials: 500
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_500_total_return_42_20250823_130210.json


## [4.2.3] 2025-08-23T09:21:51.394654 — optimizer
- Run: 20250823_162013
- Trials: 75
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_75_total_return_42_20250823_162013.json


## [4.2.3] 2025-08-23T10:57:51.313612 — optimizer
- Run: 20250823_175658
- Trials: 20
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_20_total_return_42_20250823_175658.json


## [4.2.3] 2025-08-24T05:34:00.539252 — optimizer
- Run: 20250824_123348
- Trials: 10
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_10_total_return_42_20250824_123348.json


## [4.2.3] 2025-08-24T05:49:27.280718 — optimizer
- Run: 20250824_124904
- Trials: 20
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_20_total_return_42_20250824_124904.json


## [4.2.3] 2025-08-24T05:52:26.974008 — optimizer
- Run: 20250824_125220
- Trials: 5
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_5_total_return_42_20250824_125220.json


## [4.2.3] 2025-08-24T05:53:28.341582 — optimizer
- Run: 20250824_125322
- Trials: 5
- trial_uid: 
- Artifacts: outputs\runs\trial_random_5_total_return_42_20250824_125322.json


## [4.2.3] 2025-08-24T06:02:07.538358 — optimizer
- Run: 20250824_130000
- Trials: 100
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_100_total_return_42_20250824_130000.json


## [4.2.3] 2025-08-24T06:23:40.793248 — optimizer
- Run: 20250824_131811
- Trials: 100
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_100_total_return_42_20250824_131811.json


## [4.2.3] 2025-08-24T07:01:37.672007 — optimizer
- Run: 20250824_135356
- Trials: 50
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_50_total_return_42_20250824_135356.json


## [4.2.3] 2025-08-30T07:36:11.725932 — optimizer
- Run: 20250830_143604
- Trials: 10
- trial_uid: 
- Artifacts: 


## [4.2.3] 2025-08-30T07:50:52.689802 — optimizer
- Run: 20250830_145026
- Trials: 50
- trial_uid: 
- Artifacts: 


## [4.2.3] 2025-08-30T08:02:02.766058 — optimizer
- Run: 20250830_150157
- Trials: 10
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_10_total_return_42_20250830_150157.json


## [4.2.3] 2025-08-30T08:08:14.923437 — optimizer
- Run: 20250830_150755
- Trials: 100
- trial_uid: 
- Artifacts: outputs\runs\trial_random_100_total_return_42_20250830_150755.json


## [4.2.3] 2025-08-30T08:17:16.771882 — optimizer
- Run: 20250830_151652
- Trials: 5
- trial_uid: 
- Artifacts: outputs\runs\trial_random_5_total_return_42_20250830_151652.json


## [4.2.3] 2025-08-30T08:43:52.953631 — optimizer
- Run: 20250830_154322
- Trials: 50
- trial_uid: 
- Artifacts: outputs\runs\trial_random_50_total_return_42_20250830_154322.json


## [4.2.3] 2025-08-30T08:54:20.055636 — optimizer
- Run: 20250830_155351
- Trials: 5
- trial_uid: 
- Artifacts: outputs\runs\trial_random_5_total_return_42_20250830_155351.json


## [4.2.3] 2025-08-30T09:11:03.094804 — optimizer
- Run: 20250830_161028
- Trials: 10
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_10_total_return_42_20250830_161028.json


## [4.2.3] 2025-08-30T09:20:31.491617 — optimizer
- Run: 20250830_161937
- Trials: 150
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_150_total_return_42_20250830_161937.json


## [4.2.3] 2025-08-31T06:42:06.900665 — optimizer
- Run: 20250831_134123
- Trials: 20
- trial_uid: 
- Artifacts: outputs\runs\trial_random_20_total_return_42_20250831_134123.json


## [4.2.3] 2025-08-31T07:06:53.030131 — optimizer
- Run: 20250831_140542
- Trials: 200
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_200_total_return_42_20250831_140542.json


## [4.2.5] 2025-08-31T07:15:04.914202 — code_generator
- Run: 20250831_140542
- Trials: 1
- trial_uid: 20250831_140542:2164
- Artifacts: outputs\pine\20250831_140542_2164.pine, outputs\mql5\20250831_140542_2164.mq5


## [4.2.3] 2025-08-31T09:15:06.009484 — optimizer
- Run: 20250831_161129
- Trials: 1000
- trial_uid: 
- Artifacts: outputs\runs\trial_grid_1000_total_return_42_20250831_161129.json


## [4.2.3] 2025-08-31T09:59:33.063859 — optimizer
- Run: 20250831_165524
- Trials: 50
- trial_uid: 
- Artifacts: outputs\runs\trial_sobol_50_total_return_42_20250831_165524.json


## [4.2.3] 2025-08-31T10:13:29.454170 — optimizer
- Run: 20250831_170943
- Trials: 50
- trial_uid: 
- Artifacts: outputs\runs\trial_lhs_50_total_return_42_20250831_170943.json


## [4.2.3] 2025-08-31T10:19:38.521007 — optimizer
- Run: 20250831_171553
- Trials: 50
- trial_uid: 
- Artifacts: outputs\runs\trial_sobol_50_total_return_42_20250831_171553.json


## [4.2.3] 2025-09-01T16:37:13.896533 — optimizer
- Run: 20250901_233201
- Trials: 20
- trial_uid: 
- Artifacts: outputs\runs\trial_sobol_20_total_return_42_20250901_233201.json


## [4.2.3] 2025-09-01T16:51:50.403287 — optimizer
- Run: 20250901_234702
- Trials: 25
- trial_uid: 
- Artifacts: outputs\runs\trial_sobol_25_total_return_42_20250901_234702.json


## [4.2.3] 2025-09-02T14:11:13.761648 — optimizer
- Run: 20250902_210613
- Trials: 100
- trial_uid: 
- Artifacts: outputs\runs\trial_sobol_100_total_return_42_20250902_210613.json


## [4.2.3] 2025-09-07T10:39:58.621325 — optimizer
- Run: 20250907_172851
- Trials: 50
- trial_uid: 
- Artifacts: outputs\runs\trial_lhs_50_total_return_42_20250907_172851.json


## [4.2.3] 2025-09-08T06:20:27.744382 — optimizer
- Run: 20250908_131125
- Trials: 15
- trial_uid: 
- Artifacts: outputs\runs\trial_sobol_15_total_return_42_20250908_131125.json


## [4.2.5] 2025-09-14T10:53:42.040135 — mql5_generator
- Run: 20250914_174333
- Trials: 1
- trial_uid: 20250914_174333:1060
- Artifacts: outputs\mql5\20250914_174333_1060.mq5


## [4.2.5] 2025-09-19T11:12:12.291405 — mql5_generator
- Run: 20250919_150404
- Trials: 1
- trial_uid: 20250919_150404:850
- Artifacts: outputs\mql5\20250919_150404_850.mq5


## [4.2.5] 2025-09-21T08:03:59.241107 — mql5_generator
- Run: 20250921_142405
- Trials: 1
- trial_uid: 20250921_142405:338
- Artifacts: outputs\mql5\20250921_142405_338.mq5


## [4.2.5] 2025-09-21T08:12:53.578439 — mql5_generator
- Run: 20250921_142405
- Trials: 1
- trial_uid: 20250921_142405:338
- Artifacts: outputs\mql5\20250921_142405_338.mq5


## [4.2.5] 2025-09-21T08:13:17.189072 — mql5_generator
- Run: 20250921_142405
- Trials: 1
- trial_uid: 20250921_142405:338
- Artifacts: outputs\mql5\20250921_142405_338.mq5


## [4.2.5] 2025-09-21T08:32:34.263875 — mql5_generator
- Run: 20250921_142405
- Trials: 1
- trial_uid: 20250921_142405:338
- Artifacts: outputs\mql5\20250921_142405_338.mq5


## [4.2.5] 2025-09-21T11:57:11.503410 — mql5_generator
- Run: 20250921_141203
- Trials: 1
- trial_uid: 20250921_141203:826
- Artifacts: outputs\mql5\20250921_141203_826.mq5
