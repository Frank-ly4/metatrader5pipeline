## Changelog

### 2026-01-03

- **Margin-aware backtest sizing (`src/engine/backtest.py`)**  
  Switched from percent-based position sizing to margin-capped sizing using `mt5_broker_spec.json` (FOREX.com MT5 specs).  
  This aligns Python backtests with live MT5 margin behavior (40% max used, 30% free buffer) and uses symbol contract size and leverage to compute lot-based `amount` for vectorbt.

- **MT5 margin guardrails in generated EAs (`src/codegen/mql5_generator.py`)**  
  Added constants and logic to enforce 40% max margin usage and 30% free-margin buffer in MQL5 via `OrderCalcMargin`.  
  Implemented dynamic DMA bands (fast/slow EMAs scaled by volatility), hierarchical exits (time stop, ADX stagnation, chandelier, trend invalidation, range profit), and state tracking so generated EAs behave like the Python v2 strategy.

- **Refined strategy parameter search space for exotics (`config/strategy_params_v2.py`)**  
  Replaced broad `list(range(...))` grids with targeted `stepped(...)` ranges tuned to USDSEK / USDTHB behavior.  
  Focused `base_slow_len` into 50–65, outer band multipliers into 2.25–2.75 with fine steps, tightened cooldown/holding-period ranges, and reduced `max_equity_heat_pct` / `max_consec_losses` to favor resilience over raw return.

- **Per-trial regime attribution using parquet (`src/optimizer/search.py`, `scripts/run_optimizer_cli.py`)**  
  - Updated `run_optimizer_cli` to pass the current `chart_name` into `toggles` for each trial.  
  - Added `_compute_regime_stats` in `search.evaluate_collect` that:
    - Loads the matching parquet from `data/active_charts/`,
    - Merges trade entry times with indicator snapshots via `merge_asof`, and
    - Aggregates performance by volatility (ATR) and trend-strength (ADX) buckets.  
  - Each trial row now includes a `regime_stats` field (when data is available), enabling downstream tools (`run_query_results.bat`) to filter/sort not only by Sharpe/Calmar, but also by where the strategy actually performs (e.g., high-vol trend vs low-vol range).

- **Regime analysis script scaffold (`scripts/attribute_regime.py`)**  
  Created a best-effort Python script that documents and scaffolds the parquet + trades join logic for deeper offline analysis.  
  It is wired to load a run JSON and the corresponding parquet chart, and demonstrates how to attribute trade returns by ATR/ADX regimes; the runtime attribution path in `search.py` uses the same conceptual approach.


