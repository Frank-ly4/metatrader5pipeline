# opt-console-ui Smoketests

This suite verifies critical behaviors headlessly (no GUI required).

## Run

```
python -m tests.run_smoketests
```

## What it checks

1) Export sidecar keys EXACT: `app_version, timestamp_utc, profile_name, qc_params, filter_expr, sort_by, limit, group_by, objectives_weights, visible_columns, _source_files, row_count`.
2) Logging rotation: `opt_console_ui.log` exists, rotates at 1MB × 5, entries for good load, malformed skip, and fake error.
3) Percent parsing parity: `8%`, `8 %`, `0.08` produce identical filtered rows.
4) Sorting & formatting helpers: sort toggles asc/desc; percent columns show `xx.xx%`; other floats 4 decimals.
5) Unicode paths: load fixtures and export into Unicode directory; sidecar readable as UTF-8.
6) Large dataset truncation: helper limits view to 50,000 rows and returns suffix `| Showing 50,000 of N`; export uses full DataFrame.

Artifacts are written into a temporary Unicode workspace directory.
