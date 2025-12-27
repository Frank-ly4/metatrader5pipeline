Opt 4 – Clean, Modular McGinley DMA Bands Strategy Suite (2h UTC)

Overview
- Purpose: Provide a clean, modular, and reproducible implementation of the McGinley DMA Bands strategy with a simple engine, focused optimizer, and reporting.
- Data cadence/timezone: 2h UTC.
- Positioning: Long-only (for now), fees preserved, position size = 30% of portfolio, max concurrent orders = 1.
- Data source: Uses local opt_4 data folders under `opt_4/data/`:
  - `charts_raw/` (drop raw charts here)
  - `charts_cl/` (cleaned/renamed)
  - `active_charts/` (in-use charts)
  - `used_charts/` (moved here after pipeline use)

Structure
- config/
  - data.py: Paths, data frequency
  - strategy.py: Parameter ranges and logic toggles (all optional toggles OFF by default)
  - portfolio.py: Backtest configuration (fees, size, size_type, max_orders)
- src/
  - indicators/mcg_dma.py: Numba McGinley DMA + vbt wrapper
  - strategy/bands.py: Strategy signal generation (entries/exits)
  - engine/backtest.py: Portfolio construction and stats
  - optimizer/search.py: Grid/random search with constraints and seeding
  - validation/report.py: Stats summary + human-readable commentary
  - io/data_loader.py: Load charts from ../data/active_charts, normalize columns, set frequency
  - io/writer.py: Save outputs to ./outputs
- scripts/
  - run_backtest.py: Run a single backtest with a fixed parameter set
  - run_optimize.py: Run random/grid search with focused ranges
  - run_validate.py: Re-run best params and save a readable report
- outputs/: Results, logs

Optional toggles (all OFF by default)
- use_trending_pullback_fastdma: Trend entry pullback checks fast DMA instead of slow DMA
- use_trending_pullback_lowerinner: Trend entry pullback checks lower inner band
- use_ranging_reclaim: Range entry requires Close > lower_inner after piercing lower_outer
- use_protective_lowerinner_exit: Exit if Close < lower_inner while in position
- (Placeholders for later) use_atr_stop, use_time_stop – planned as future enhancements

Run Examples
1) Single backtest (edit params in scripts/run_backtest.py):
   python scripts/run_backtest.py

2) Random search (seeded):
   python scripts/run_optimize.py --method random --trials 200 --metric total_return

3) Grid search (bounded):
   python scripts/run_optimize.py --method grid --trials 200 --metric total_return

Notes
- The optimizer validates and skips invalid DMA overlaps before running.
- Random search is seeded for deterministic sampling (np.random.seed(42)).
- Sortino, Sharpe, Calmar, Max Drawdown, Win Rate, Profit Factor, Expectancy and more are reported.


