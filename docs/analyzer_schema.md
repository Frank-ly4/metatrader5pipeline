### Analyzer Feature Parquet Schema

This document describes the columns and metadata written by `analyzer/feature_writer.py`.

Columns (per row / per bar):
- `timestamp`: Bar timestamp (datetime64[ns]) from the source chart index.
- `symbol`: Asset symbol (string), inferred from filename unless provided.
- `timeframe`: Bar interval label inferred from index spacing (e.g., `2h`, `15m`).
- `provider`: Feature provider used (e.g., `mcg`, `pa_only`).
- `feature_version`: Version tag for reproducibility (e.g., `v1`).
- `trend_label`: Provider-specific trend label per bar.
- `regime_label`: Optional regime label (present for providers that compute it).
- Pattern flags (0/1), when enabled: `candle_engulf_bull`, `candle_engulf_bear`, `candle_pin_bull`, `candle_pin_bear`, `candle_doji`, `inside_bar`, `outside_bar`, `nr7`, and optionally `swing_hh`, `swing_hl`, `swing_lh`, `swing_ll`.

Metadata columns (constant per file, repeated per row for portability):
- `bars_hash`: SHA256 over (Timestamp, Open, High, Low, Close) in ascending order.
- `bar_count`: Number of bars in the source price DataFrame.
- `first_ts`: ISO8601 of the first timestamp.
- `last_ts`: ISO8601 of the last timestamp.
- `tz`: Timezone string (`UTC`, `naive`, etc.).

File naming pattern:
`<symbol>_<timeframe>_<provider>_<feature_version>.parquet`

Notes:
- Columns may include additional provider-specific features as needed; all additions must be documented here.
- PNG export logic and regime plots are unchanged and separate from feature storage.


