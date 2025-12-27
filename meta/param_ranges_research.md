## Parameter ranges: research basis and rationale (v4.2.5)

This note captures the sources and reasoning behind the optimizer ranges set in `config/strategy_params.py`.

### Summary of final ranges

- fast_min_len: 6–14
- fast_max_len: 16–28
- slow_min_len: 30–60
- slow_max_len: 70–150
- dma_atr_len: 10–30
- atr_len: 10–30
- upper_outer_mult: 1.8–3.0 step 0.1
- lower_outer_mult: 1.8–3.0 step 0.1
- upper_inner_mult: 0.8–1.6 step 0.1
- lower_inner_mult: 0.8–1.6 step 0.1
- momentum_len: 10–50
- momentum_threshold: 0.60–0.85 step 0.05

### Strategy context

The system uses McGinley Dynamic (DMA) bands with ATR-based inner/outer channels and a momentum regime filter based on the absolute percent change over a rolling lookback. The optimizer enforces validity constraints (fast_max_len < slow_min_len, etc.) and warms indicators for the longest lookback (see `src/optimizer/search.py`).

### Sources and conventions

- ATR period defaults: Wilder’s ATR canonical default is 14 bars; many references (textbooks, platforms) use 14 and nearby values. Allowing 10–30 balances responsiveness vs smoothness across intraday and swing contexts.
- Keltner/ATR channels: StockCharts and common practice employ ~2× ATR envelopes; practitioners vary between 1.5–3.0. We sample 1.8–3.0 for outer bands and 0.8–1.6 for inner pullback zones to maintain inner < outer and leave room for discovery without extreme whipsaw or over-wide bands.
- McGinley Dynamic: Frequently applied around ~14 length in literature and trading platforms; for adaptive min/max spans, we position fast windows in the short-term regime (6–28) and slow windows longer (30–150) to improve regime separation and avoid invalid combinations.
- Momentum regime: Percentile/quantile thresholds near the 60–80th percentile are common in time-series momentum/regime models. We set 0.60–0.85 and allow momentum lookback 10–50 to support symbols with different cycle lengths.

Note: The code computes momentum as |close/close[momentum_len] − 1| and gates trending if percent-rank > (threshold×100). This makes `momentum_threshold` a quantile in [0,1].

### Practical/novel considerations

- Separation between fast and slow ranges reduces optimizer time waste on invalid combos and enhances signal clarity.
- Inner bands < 1× ATR accommodate shallow pullbacks in strong trends; capping at 1.6 avoids frequent overlap with the outer envelopes.
- Extending `atr_len` and `dma_atr_len` up to 30 enables smoother volatility normalization in noisier series; longest-lookback handling already accounts for indicator warmup.

### Implementation pointers

- Ranges are specified as strings and normalized by `normalize_param_ranges`; floats are supported using `start-end:step` syntax.
- Domain constraints for `momentum_threshold` clamp to [0,1], so the specified range must lie within this interval.
- `scripts/save_opt_results.py` and `src/optimizer/search.py` use these ranges to compute warmup; no other changes are required when only ranges are updated.

### Future work

- Consider adaptive stepping (e.g., log-spaced) for length parameters when searching very wide intervals.
- Explore asymmetric inner/outer bands by regime (e.g., widen outer during high-volatility regimes identified by longer ATR).


