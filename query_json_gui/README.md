# Optimization Results Console (JSON)

This mini-console lets you **load many optimizer result JSONs**, apply **filters**, **rank**, **Pareto-select**, assess **stability across charts/folds**, compute **param↔metric correlations**, **partial dependence**, and extract **top‑k per group** shortlists—then **export** everything.

Tested with Python 3.9+. Core dependency: `pandas` (and optionally `pyarrow` for Parquet).

## Quick Start

```bash
# 1) Put your JSON files in a folder, e.g., /path/to/results
# 2) Run the CLI to generate exports:
python run_console.py --data_dir /path/to/results --out_dir ./console_exports
```

Key optional flags:
- `--min_trades 20` (QC)  
- `--max_mdd 0.10` (QC; 10% as 0.10)  
- `--score_weights '{"sharpe_ratio":1,"calmar_ratio":1,"max_drawdown":-1}'`  
- `--topk_group_by chart` (or `chart,fold_id`)  
- `--topk_sort_by -calmar_ratio` (use `-col` for descending)  
- `--topk_k 5`  
- `--topk_filter 'profit_factor >= 1.6 and calmar_ratio > 0 and max_drawdown < 10% and total_trades >= 20'`  
- `--pd_param param_adx_threshold --pd_metric calmar_ratio`

Exports land in `--out_dir` as CSV (and Parquet if `pyarrow` is installed).

## What’s Inside

### 1) QC Filters
`qc_filter`: enforce a **minimum trade count**, **max drawdown**, and remove degenerate rows (no-trade runs where key metrics are all zero). This protects your shortlists.

### 2) Multi‑Objective Composite Score
`composite_score`: weighted sum over available metrics (default emphasizes risk‑adjusted returns). Tune weights per your mandate.

### 3) Robustness / Stability by Parameter Set
`stability_by_params`: group by full `param_*` signature and compute `mean`, `std`, quartiles, and a **robust** score `mean − λ·std` (negated for lower‑better metrics like drawdown). Outputs a **stability_score** combining robust Calmar, PF, and inverse of robust MDD.

### 4) Param Correlations & Partial Dependence
- `param_spearman`: Spearman rank correlations (param ↔ metric).  
- `partial_dependence`: bin a parameter into quantiles and report count/mean/median/std of a chosen metric—quick sensitivity read.

### 5) Pareto Frontier
`pareto_frontier`: Non‑dominated set across any list of objectives, e.g., maximize Calmar & PF, minimize MDD. Keeps only configs no other row strictly dominates across all objectives.

### 6) Risk Diagnostics
Adds derived summaries like a quick **gain‑to‑pain proxy** (`total_return / max_drawdown`) and exposes any `param_max_consec_losses` as `loss_streak_cap`.

### 7) Generalization Checks
If your JSONs tag rows with a `subset`/`split` (e.g., train vs OOS), the console aggregates means/medians per subset.

### 8) Top‑K per Group (Deep Explanation)
**Problem:** Global top‑k often overrepresents one market or period.  
**Solution:** take the **top‑k within each group**, where group = chart, fold, (chart,fold), or a parameter bin.

**Why:** You get **coverage** and guard against regime bias; great for promoting candidates to OOS testing or EA generation.

**API:**  
```python
topk_per_group(df,
               group_by="chart",          # or ["chart","fold_id"], or a param bin column
               sort_by="-calmar_ratio",   # use "-" for descending
               k=5,
               filter_expr="profit_factor >= 1.6 and calmar_ratio > 0 and max_drawdown < 10% and total_trades >= 20")
```

**Examples:**
- *Top‑5 per chart by Calmar with quality guards* (above).  
- *Top‑3 per (chart,fold) by PF with MDD<8% & ≥25 trades*.  
- *Top‑10 per param bin* for `param_adx_threshold` to explore sweet‑spots.  
- *Top‑n per month/quarter* (if you add date grouping columns).

### 9) Exports
`export_df`: write CSV + Parquet (if `pyarrow` installed) for any table (Pareto set, stability table, top‑k list, etc.).

## Programmatic Use (Python)

```python
from optimization_console import *

paths = glob.glob("/path/to/results/*.json")
df = load_json_results(paths)
df = add_risk_derivatives(df)
base = qc_filter(df, min_trades=30, max_mdd=0.12)

scored = composite_score(base).sort_values("score", ascending=False)
pf = pareto_frontier(base, [("calmar_ratio","max"),("max_drawdown","min"),("profit_factor","max")])

stab = stability_by_params(base, metrics=["calmar_ratio","profit_factor","max_drawdown"], lambda_std=0.5)
corr = param_spearman(base, metric_cols=["calmar_ratio","profit_factor","max_drawdown","sharpe_ratio"])
pd_table = partial_dependence(base, param="param_adx_threshold", metric="calmar_ratio")

topk = topk_per_group(base, group_by="chart", sort_by="-calmar_ratio", k=5,
                      filter_expr="profit_factor >= 1.6 and calmar_ratio > 0 and max_drawdown < 10% and total_trades >= 20")

export_df(topk, "./exports", "topk_per_chart")
```

## Requirements
- `pandas`
- Optional: `pyarrow` (for Parquet)

```bash
pip install pandas pyarrow
```

## Tips
- You can pass percent thresholds in filter expressions (e.g., `max_drawdown < 10%`).
- If you need different metrics, just add columns to your JSONs; the console auto‑adapts.
- Combine **Pareto** + **Top‑k per group** for robust shortlists: first Pareto on (Calmar↑, MDD↓, PF↑), then take top‑k per chart.

---

Happy hunting. If you want me to wire EA generation (Pine/MQL5) into this flow, say the word and we’ll add a code‑export stage that includes seeds/params for reproducibility.
