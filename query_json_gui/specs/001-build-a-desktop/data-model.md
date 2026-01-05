# Data Model: Optimization Results Desktop Explorer

**Date**: 2025-10-01  
**Feature**: Desktop application for exploring optimization/backtest JSON results

## Core Entities

### OptimizationResult
**Purpose**: Individual backtest/optimization outcome with performance metrics and parameters

**Attributes**:
- `_source_file` (string): Origin JSON filename for traceability
- `calmar_ratio` (float): Risk-adjusted return metric (required for Pareto analysis)
- `max_drawdown` (float): Maximum peak-to-trough decline (stored as fraction, displayed as %)
- `profit_factor` (float): Gross profit / gross loss ratio (required for Pareto analysis)
- `sharpe_ratio` (float, optional): Risk-adjusted return measure
- `sortino_ratio` (float, optional): Downside deviation-adjusted return
- `num_trades` (int): Total number of trades executed
- `win_rate` (float): Percentage of winning trades (stored as fraction, displayed as %)
- `param_*` (various): Strategy parameters with param_ prefix for stability analysis
- `chart` (string, optional): Market/instrument identifier for grouping
- `fold_id` (string/int, optional): Cross-validation fold identifier
- Additional metrics as available in source JSON

**Validation Rules**:
- `num_trades` ≥ 0
- `max_drawdown` ∈ [0, 1] (fraction)
- `win_rate` ∈ [0, 1] (fraction) if present
- `profit_factor` > 0 if present
- Required columns validated per analysis type (see AnalysisRequirements)

**State Transitions**: Immutable once loaded (read-only analysis)

### AnalysisProfile
**Purpose**: Named collection of user preferences for repeatable analysis workflows

**Attributes**:
- `schema_version` (string): Version for backward compatibility (e.g., "1.1.0")
- `name` (string): User-assigned profile identifier
- `data_dir` (string): Last used data directory path
- `min_trades` (int): Quality control minimum trade threshold (default: 20)
- `max_mdd` (float): Quality control maximum drawdown threshold (fraction)
- `nondegenerate` (boolean): Whether to drop zero-trade results
- `filter_expr` (string): pandas query expression with % parsing support
- `sort_by` (string): Sort specification (e.g., "-calmar_ratio,profit_factor")
- `limit` (int): Row limit for display (0 = unlimited)
- `group_by` (string): Comma-separated grouping columns for Top-k analysis
- `topk_sort_by` (string): Sort specification for Top-k within groups
- `topk_k` (int): Number of results per group in Top-k analysis
- `topk_filter` (string): Optional pre-filter for Top-k analysis
- `pd_param` (string): Parameter column for partial dependence analysis
- `pd_metric` (string): Metric column for partial dependence analysis

**Validation Rules**:
- `name` must be non-empty and unique within profiles
- `min_trades` ≥ 0
- `max_mdd` ∈ [0, 1]
- `limit` ≥ 0
- `topk_k` ≥ 1
- `filter_expr` must be valid pandas query syntax
- Schema version must match supported versions

**State Transitions**:
```
Created → Saved → [Modified] → Saved
                ↓
              Loaded → Applied to UI
```

### ExportPackage
**Purpose**: Complete result set with metadata for reproducibility

**Attributes**:
- `data_files`: 
  - `{name}.csv` (string path): CSV export for universal compatibility
  - `{name}.parquet` (string path, optional): Parquet export if pyarrow available
- `metadata_file`: `{name}.meta.json` (string path): Sidecar metadata
- `metadata_content`:
  - `app_version` (string): Application version (e.g., "1.1.0")
  - `timestamp` (string): UTC ISO timestamp of export
  - `profile_name` (string): Active profile name or "None"
  - `qc_params` (object): Quality control settings applied
  - `filter_expr` (string): Filter expression used
  - `sort_by` (string): Sort specification applied
  - `limit` (int|null): Row limit applied
  - `group_by` (string): Grouping specification
  - `objectives_weights` (string): Analysis objectives description
  - `visible_columns` (array): Column names in export
  - `_source_files` (array): Unique source JSON filenames
  - `rows_exported` (int): Total rows in export
  - `data_source_dir` (string): Original data directory path

**Validation Rules**:
- At least one data file must be successfully created
- Metadata must include all required fields
- `rows_exported` must match actual export row count
- `_source_files` must be unique and non-empty
- Timestamp must be valid UTC ISO format

**State Transitions**: Created → Written → Immutable

### QualityControlRules
**Purpose**: Configurable thresholds for filtering unreliable results

**Attributes**:
- `min_trades` (int): Minimum number of trades required (default: 20)
- `max_mdd` (float): Maximum acceptable drawdown as fraction (e.g., 0.10 for 10%)
- `drop_degenerate` (boolean): Whether to remove zero-trade/zero-metric results

**Validation Rules**:
- `min_trades` ≥ 0
- `max_mdd` ∈ [0, 1]
- Applied before any analysis operations

**Relationships**: Used by OptimizationResult filtering

### ShortlistCriteria
**Purpose**: Multi-objective constraints for identifying robust strategy candidates

**Attributes**:
- `pareto_objectives`: Array of (column, direction) pairs
  - Default: [("calmar_ratio", "max"), ("max_drawdown", "min"), ("profit_factor", "max")]
- `topk_config`:
  - `group_columns` (array): Grouping columns (e.g., ["chart", "fold_id"])
  - `sort_column` (string): Ranking metric within groups
  - `k` (int): Number of results per group
  - `pre_filter` (string, optional): Quality filter before grouping
- `stability_config`:
  - `param_columns` (array): Parameter columns for grouping (auto-detected param_*)
  - `metrics` (array): Metrics to analyze for stability
  - `lambda_std` (float): Robustness penalty factor (default: 0.5)

**Validation Rules**:
- Pareto objectives must reference existing columns
- Top-k sort column must exist in dataset
- Stability requires ≥1 param_* column and ≥1 specified metric
- All referenced columns validated before analysis execution

## Analysis Requirements Matrix

| Analysis Type | Required Columns | Optional Columns | Validation |
|---------------|------------------|------------------|------------|
| **Pareto Frontier** | `calmar_ratio`, `max_drawdown`, `profit_factor` | All others | Pre-execution column check |
| **Top-k per Group** | Columns in `sort_by` parameter | Grouping columns, filter columns | Dynamic validation |
| **Stability Analysis** | ≥1 `param_*`, ≥1 of {`calmar_ratio`, `profit_factor`, `max_drawdown`} | Additional metrics | Pre-execution check |
| **Composite Score** | None (graceful degradation) | `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`, `profit_factor`, `max_drawdown` | Best-effort calculation |
| **Spearman Correlation** | ≥1 `param_*` | Metric columns | Parameter detection |
| **Partial Dependence** | Specified param and metric columns | None | Column existence check |

## Data Flow Architecture

```
JSON Files → OptimizationResult[] → QualityControlRules → Filtered Results
                                                              ↓
AnalysisProfile → ShortlistCriteria → Analytics Engine → Processed Results
                                                              ↓
ExportPackage ← UI Display ← Performance Optimized View (50k limit)
```

## Persistence Schema

### profiles.json Structure
```json
{
  "schema_version": "1.1.0",
  "profile_name_1": { /* AnalysisProfile attributes */ },
  "profile_name_2": { /* AnalysisProfile attributes */ }
}
```

### app_state.json Structure
```json
{
  "schema_version": "1.1.0",
  "data_dir": "/path/to/last/data/directory",
  "export_dir": "/path/to/last/export/directory", 
  "current_profile_name": "profile_name_1",
  "column_visibility": ["col1", "col2", "col3"],
  "auto_apply_profile": true
}
```

## Constitutional Compliance

- **Separation of Concerns**: Analytics engine operates on pure data entities, UI handles presentation
- **Reproducibility**: ExportPackage captures complete analysis state
- **Performance**: OptimizationResult supports efficient pandas operations
- **Robustness**: Validation rules prevent invalid states and operations
- **Extensibility**: Entity structure supports additional metrics and parameters without breaking changes
