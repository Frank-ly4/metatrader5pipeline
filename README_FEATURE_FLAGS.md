### Feature flags (bands_v2)

Toggle via the `toggles` dict passed to `compute_signals(price, params, toggles)`.
Defaults shown below; turning a flag off restores legacy v2 behavior for that facet.

```
feature_state_machine: true            # Regime→Setup→Trigger execution
feature_hierarchical_exits: true       # Initial stop, partial@1R→BE, DMA/Chandelier trail
feature_volatility_filter: true        # ATR% floor/cap filter
feature_session_filter: false          # Session (broker time) filter
feature_htf_confirm: false             # Reserved
feature_cooldowns: true                # Cooldown after entry/exit
feature_equity_heat_guard: true        # Cap equity heat via max_equity_heat_pct
feature_pyramiding_addon_distance: true# Require ATR distance between add-ons
feature_no_bfill_dynamic_len: true     # Remove bfill from dynamic EMA lengths
feature_exit_before_entry: true        # Evaluate exits before entries within bar
feature_block_reentry_same_bar: true   # Prevent same-bar re-entry after exit
```

Key params introduced:

- slope_len, adx_floor, cooldown_bars, atr_pct_floor/atr_pct_cap
- session_start/session_end
- init_atr_mult, dma_buffer_mult, partial_pct, be_buffer, trail_dma_buffer
- dead_bars, adx_dead_threshold, max_equity_heat_pct, max_consec_losses
- friday_cutoff_bars, min_addon_distance_ATR, block_reentry_same_bar

Back-compat: set all flags to false to match legacy v2 outputs (within rounding).


