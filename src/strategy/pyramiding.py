"""Pyramiding Option B: layered entries with accumulate=True semantics.

Given base entry/exit signals, emit up to 3 staggered entry layers at equal
size (30% each by default), resetting layers on exit.

This produces a boolean Series of entries compatible with vectorbt's
from_signals(..., accumulate=True).
"""

from __future__ import annotations

import pandas as pd


def layered_entries(
    base_entries: pd.Series,
    exits: pd.Series,
    max_layers: int = 3,
    
) -> pd.Series:
    """Convert base entries into layered entries up to max_layers.

    Each time a new base entry occurs while current_layers < max_layers, we
    allow an additional entry. Any exit resets current_layers to 0.
    """
    if max_layers is None or max_layers <= 1:
        return base_entries.astype(bool)

    entries = base_entries.astype(bool).copy()
    exits = exits.astype(bool).copy()
    open_layers = 0
    out_values: list[bool] = []
    for want_entry, is_exit in zip(entries.values, exits.values):
        if is_exit:
            open_layers = 0
        allow = bool(want_entry) and (open_layers < max_layers)
        if allow:
            open_layers += 1
        out_values.append(allow)
    return pd.Series(out_values, index=entries.index)



