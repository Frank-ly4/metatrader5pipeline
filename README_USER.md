Optimizer v4.2 – User Guide

What’s new
- Single central Excel workbook at `outputs/notebooks/optimizer_central.xlsx`
- One JSON per run under `outputs/runs/`
- User-editable configs in `config/`
- Layered pyramiding (up to 3 layers of 30%, accumulate=True)
- Meta logs appended to `meta/discoveries.md`

Quick start
1) Standardize raw charts:
   `python scripts\standardize.py --from data\charts_raw --to data\charts_cl --also-copy-active`
2) Run single backtest (sanity):
   `python scripts\run_backtest_simple.py`
3) Run optimizer (example):
   `python scripts\save_opt_results.py --method random --trials 20 --metric total_return --seed 42`
4) Query results:
   `python scripts\query_results.py --metric total_return --top 20`

Edit configuration
- `config/user_inputs.py`:
  - BACKTEST_CONFIG: `fees`, `position_size`, `starting_capital`, `data_freq`
  - TOGGLES: `move_processed_charts`, `progress_step`
- `config/strategy_params.py`:
  - `BASELINE_PARAMS`: used by `scripts/run_backtest.py`
  - `PARAM_RANGES`: used by `scripts/save_opt_results.py`

Outputs
- JSON: `outputs/runs/<run>.json`
- Excel: `outputs/notebooks/optimizer_central.xlsx` (append-only)
- Meta: `meta/discoveries.md`

PineScript generator
- Double-click `run_pinescript_generator.bat` or run:
  - `cd 4.2\4.2.2; $env:PYTHONPATH=(Get-Location).Path; python scripts\generate_pine.py --mode prompt`
- Follow the prompts:
  - Choose JSON or Excel
  - Select run or paste `trial_uid` (format: `RUNID:TRIALID`)
  - Output saved to `outputs/pine/{trial_uid}.pine`

Meta layer (non-blocking)
- Discoveries: auto-appended to `meta/discoveries.md` on runs/generation
- Issues: auto-appended to `meta/issues.md` on errors
- Optional validator (on demand): `run_meta_validator.bat`

Workbook structure
- Sheets: `Runs`, `AllResults`, `AllTrades`, `run_<id>_summary`, `run_<id>_trades`, and per-chart sheets
- Column order: IDs (`run_id`,`trial_id`,`chart`,`method`) → `param_*` → metrics
- Sorting: `AllResults` by (run_id, chart, trial_id); `AllTrades` by (run_id, chart, trial_id, trade_index)

Notes
- All datetimes are written tz-naive for Excel compatibility
- No per-run CSV/XLSX files are created; the central workbook is the source of truth
- If enabled, processed charts are moved to `data/used_charts/`


