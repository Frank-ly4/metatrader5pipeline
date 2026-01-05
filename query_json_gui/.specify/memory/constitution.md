# Optimization Results Desktop UI (opt-console-ui) Constitution

## Core Principles

### I. Local-Only & Deterministic Execution
- All operations must execute locally without network dependencies
- Results must be deterministic and reproducible across sessions
- No external API calls or cloud services permitted
- Data processing must be consistent regardless of execution environment

### II. Robust UX & Safety (Never Lose Last View)
- Application must never lose user's current view state on errors
- Malformed data files shall be skipped with logging, not crash the app
- All operations must validate inputs before execution
- Friendly error dialogs must be shown for invalid operations with no state changes

### III. Separation of Concerns (UI vs Engine)
- Analytics engine must be independent of UI components
- Data processing logic must be testable without GUI dependencies
- UI components shall only handle presentation and user interaction
- Clear interfaces must exist between data layer, analytics engine, and UI

### IV. Performance & Responsiveness
- Application must remain responsive with 50,000+ rows loaded
- Operations must complete with timing feedback in status bar
- UI must not freeze during data processing operations
- Memory usage must be optimized for large dataset handling
- Target 50k–200k rows; if rendering would stall, truncate view to 50k with status notice "Showing 50,000 of N rows"

### V. Reproducibility & Extensibility
- All exports must include sufficient metadata for reproduction
- Column formatting and visibility settings must persist
- Profile system must enable repeatable analysis workflows
- Analytics functions must be extensible without UI changes
- Mandate export sidecar JSON with: app_version, UTC ISO timestamp, profile name, QC params, filter/sort/limit, group_by, objectives/weights, visible columns, _source_file list

## Additional Constraints & Technical Standards

### Technology Stack
- Python 3.9+ required
- PySide6 for GUI framework
- pandas for data manipulation
- pyarrow optional for Parquet export
- No additional heavy GUI dependencies permitted
- No network libraries allowed
- Local logging: rotating `opt_console_ui.log` (load results, query errors, validation failures, timings); no network

### Data Model
- Input files: `{ metadata?: {}, results: [ {...} ] }`
- Each `results[i]` merged with `metadata` creates one DataFrame row
- `_source_file` column added to track data origin
- All numeric columns validated before processing
- Required columns (per feature): Pareto → `calmar_ratio`, `max_drawdown`, `profit_factor`; Top-k → provided `sort_by` column; Stability → ≥1 `param_*` and ≥1 metric in {`calmar_ratio`, `profit_factor`, `max_drawdown`}
- Optional columns: all others; degrade gracefully with friendly dialog
- Units: store decimals; UI may render % for `max_drawdown`, `win_rate`
- NaN rule: ignore NaNs only for the metric being computed; keep row visible

### UI Standards
- Left panel: Data, QC, Query/Sort/Limit, Top-k, Advanced, Export & Profiles
- Right panel: sortable data table with column visibility controls
- Status bar format: `Rows: N | Last op: X ms`
- Header click sorting with multi-key support
- Percentage formatting for `max_drawdown` and `win_rate` (display % but store fraction)
- 4-decimal precision for other float columns
- Percent parsing rules: accept `10%`, `10 %`, or `0.10`; % form takes precedence when both present in a token

### Quality Control Rules
- `min_trades` default: 20
- `max_mdd` UI shows percentage, stores as fraction
- Drop degenerate results option available
- All QC parameters must be user-configurable

### Analytics Requirements
- Top-k per group: supports `chart`, `fold_id`, any `param_*` columns
- Pareto optimization: maximize `calmar_ratio`, minimize `max_drawdown`, maximize `profit_factor`
- Composite score: `Sharpe*1.0 + Sortino*0.5 + Calmar*1.0 + PF*0.5 - MDD*1.0`
- Stability analysis: group by `param_*`, compute robust metrics with `mean - λ*std`
- Spearman correlation matrix and partial dependence analysis

### Profiles & Persistence
- `profiles.json` fields: `data_dir`, `min_trades`, `max_mdd`, `nondegenerate`, `filter_expr`, `sort_by`, `limit`, `group_by`, `topk_sort_by`, `topk_k`, `topk_filter`, `pd_param`, `pd_metric`
- `app_state.json`: last directories, selected profile, column visibility, auto-apply flag
- Profile dropdown with Apply/Save/Manage operations
- Optional auto-apply last profile on startup
- Require `schema_version` in `profiles.json` and `app_state.json`; minor migrations fill defaults; breaking bumps major

### Acceptance Tests
- Load mixed folder (≥2 valid JSON, ≥1 malformed): valid rows visible, malformed logged, UI responsive
- QC with min_trades=20, max_mdd=10%, drop degenerate reduces rows appropriately
- Filter supports percentage: `max_drawdown < 8% and profit_factor >= 1.6`
- Sort by `-calmar_ratio` and multi-key `-calmar_ratio,profit_factor` works
- Top-k with `group_by=["chart","fold_id"]`, k=3 yields ≤3 per group
- Pareto returns non-dominated set for (Calmar↑, MDD↓, PF↑)
- Stability analysis appears when `param_*` columns exist
- Spearman matrix (param rows × metric columns) and partial dependence
- Profiles: Save/Apply/Manage with optional auto-apply
- One-click shortlist updates status bar with row count and timing
- Export writes CSV and Parquet (when pyarrow available) without crashes
- Column visibility persists for session with correct formatting
- Unicode paths work for load and export operations
- Percent parsing triplet (`8%`, `8 %`, `0.08`) behaves identically
- Export sidecar presence and correctness with expected metadata keys

## Development Workflow & Quality Gates

### Testing Requirements
- Unit tests mandatory for all analytics engine functions
- Smoke tests must verify mixed valid/malformed JSON loading
- All acceptance tests must pass before release
- Test coverage required for data processing and validation logic

### Code Review Standards
- All PRs must verify compliance with core principles
- Analytics engine changes require performance impact assessment
- UI changes must maintain separation of concerns
- Breaking changes must include migration documentation

### Versioning & Releases
- Semantic versioning: MAJOR.MINOR.BUILD format
- Breaking UI or engine changes require MAJOR version increment
- Release notes must document breaking changes and migration steps
- Version compatibility maintained within MAJOR releases

### Quality Gates
- CI must validate all acceptance tests pass
- Performance benchmarks must not regress for 50k+ row datasets
- Memory usage must remain within acceptable bounds
- All principles compliance verified before merge

## Governance

Constitution supersedes all other development practices and guidelines. Amendments require pull request with detailed migration plan and impact assessment. Breaking changes must be flagged in version numbers and documented with upgrade paths. CI gates must enforce principles compliance and acceptance test validation.

**Version**: 1.1.0 | **Ratified**: 2025-10-01 | **Last Amended**: 2025-10-01