# Tasks: Optimization Results Desktop Explorer

**Input**: Design documents from `/specs/001-build-a-desktop/`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/

## Execution Flow (main)
```
1. Load plan.md from feature directory
   → Tech stack: Python 3.9+, PySide6, pandas, pyarrow (optional)
   → Structure: Single desktop application with analytics engine + GUI
2. Load design documents:
   → data-model.md: 5 entities (OptimizationResult, AnalysisProfile, ExportPackage, QualityControlRules, ShortlistCriteria)
   → contracts/: analytics_engine.py, ui_interface.py
   → quickstart.md: 8 acceptance scenarios with validation steps
3. Generate tasks by category:
   → Setup: Python project, dependencies, logging
   → Tests: Contract tests, integration tests (TDD approach)
   → Core: Analytics engine, UI components
   → Integration: Profile system, export functionality
   → Polish: Documentation, acceptance validation
4. Apply task rules:
   → Analytics engine functions = [P] (different functions, independent)
   → UI components = sequential (shared ui_app.py file)
   → Tests before implementation (TDD)
5. Number tasks sequentially (T001-T035)
6. Constitutional compliance validation throughout
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Phase 3.1: Setup & Infrastructure

- [ ] **T001** Create Python project structure with optimization_console.py, ui_app.py, requirements.txt, README_UI.md
- [ ] **T002** Initialize Python dependencies: PySide6>=6.5, pandas>=1.5, pyarrow>=15 (optional), pytest for testing
- [ ] **T003** [P] Configure rotating logging system in optimization_console.py: RotatingFileHandler for opt_console_ui.log (1MB × 5 files)

## Phase 3.2: Analytics Engine Contract Tests (TDD) ⚠️ MUST COMPLETE BEFORE 3.3
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**

- [ ] **T004** [P] Contract test load_json_results() in tests/unit/test_data_loading.py: mixed schemas, malformed files, Unicode paths
- [ ] **T005** [P] Contract test qc_filter() in tests/unit/test_quality_control.py: min_trades, max_mdd, degenerate filtering
- [ ] **T006** [P] Contract test query_df() in tests/unit/test_filtering.py: percentage parsing (8%, 8 %, 0.08), sort multi-key, limit
- [ ] **T007** [P] Contract test pareto_frontier() in tests/unit/test_pareto.py: multi-objective optimization, column validation
- [ ] **T008** [P] Contract test topk_per_group() in tests/unit/test_topk.py: grouping, stable ranking, pre-filtering
- [ ] **T009** [P] Contract test stability_by_params() in tests/unit/test_stability.py: param_* grouping, robust scoring
- [ ] **T010** [P] Contract test export_df() in tests/unit/test_export.py: CSV/Parquet export, sidecar metadata generation
- [ ] **T011** [P] Contract test validation helpers in tests/unit/test_validation.py: require_columns(), list_param_cols(), is_percent_col()

## Phase 3.3: Analytics Engine Implementation (ONLY after tests are failing)

- [ ] **T012** [P] Implement load_json_results() in optimization_console.py: JSON parsing, schema merging, _source_file addition, error handling
- [ ] **T013** [P] Implement qc_filter() in optimization_console.py: trades/drawdown thresholds, degenerate detection
- [ ] **T014** [P] Implement query_df() in optimization_console.py: percentage token parsing, pandas query integration, multi-key sorting
- [ ] **T015** [P] Implement validation helpers in optimization_console.py: column requirement checking, parameter detection, percentage column identification
- [ ] **T016** [P] Implement pareto_frontier() in optimization_console.py: dominance checking, multi-objective optimization with column validation
- [ ] **T017** [P] Implement topk_per_group() in optimization_console.py: pandas groupby, stable ranking, optional pre-filtering
- [ ] **T018** [P] Implement stability_by_params() in optimization_console.py: parameter grouping, robust statistics (mean - λ*std), stability scoring
- [ ] **T019** [P] Implement composite_score() in optimization_console.py: weighted metric combination, configurable weights
- [ ] **T020** [P] Implement param_spearman() in optimization_console.py: parameter-metric correlation matrix
- [ ] **T021** [P] Implement partial_dependence() in optimization_console.py: quantile binning, parameter effect analysis
- [ ] **T022** [P] Implement export_df() in optimization_console.py: CSV/Parquet export, UTF-8 encoding, metadata sidecar generation

## Phase 3.4: UI Component Tests (TDD)

- [ ] **T023** [P] Integration test data loading workflow in tests/integration/test_ui_data_loading.py: folder selection, JSON loading, table update
- [ ] **T024** [P] Integration test QC workflow in tests/integration/test_ui_quality_control.py: filter application, table refresh, timing display
- [ ] **T025** [P] Integration test analytics workflows in tests/integration/test_ui_analytics.py: Pareto/Top-k/Stability with validation dialogs
- [ ] **T026** [P] Integration test profile system in tests/integration/test_ui_profiles.py: save/load profiles, schema versioning
- [ ] **T027** [P] Integration test export workflow in tests/integration/test_ui_export.py: export dialog, sidecar generation, directory persistence

## Phase 3.5: UI Implementation (Sequential - shared ui_app.py file)

- [ ] **T028** Implement MainWindow layout in ui_app.py: left control panel (Data, QC, Query/Sort/Limit, Top-k, Advanced, Export & Profiles), right table view
- [ ] **T029** Implement DataFrameModel in ui_app.py: QAbstractTableModel for large datasets, percentage formatting, 4-decimal precision, column visibility
- [ ] **T030** Implement data loading UI in ui_app.py: folder selection dialog, JSON loading with progress, status bar updates, Unicode path support
- [ ] **T031** Implement analytics UI controls in ui_app.py: QC filters, query/sort/limit inputs, Top-k configuration, advanced analytics buttons
- [ ] **T032** Implement validation dialogs in ui_app.py: missing column detection, friendly error messages, operation abortion without state loss
- [ ] **T033** Implement large data safeguards in ui_app.py: 50k row display truncation, status bar truncation notice, full dataset export preservation

## Phase 3.6: Profile & Persistence System

- [ ] **T034** Implement profile system in ui_app.py: profiles.json with schema versioning, save/load/manage operations, migration handling
- [ ] **T035** Implement app state persistence in ui_app.py: app_state.json with schema versioning, directory persistence, column visibility, auto-apply settings

## Phase 3.7: Integration & Polish

- [ ] **T036** [P] Update README_UI.md: required vs optional columns per feature, percent parsing examples, truncation behavior, logging details, export sidecar format
- [ ] **T037** [P] Create acceptance test suite in tests/acceptance/test_constitutional_compliance.py: all constitutional acceptance criteria validation
- [ ] **T038** Performance optimization: pandas operations, UI responsiveness, memory usage for 50k-200k rows
- [ ] **T039** Error handling integration: comprehensive logging, graceful degradation, user-friendly error recovery
- [ ] **T040** Manual testing validation: run quickstart.md scenarios, verify all acceptance criteria pass

## Dependencies

**Critical Path**:
- Setup (T001-T003) → Contract Tests (T004-T011) → Analytics Implementation (T012-T022) → UI Tests (T023-T027) → UI Implementation (T028-T035) → Integration (T036-T040)

**Blocking Relationships**:
- T004-T011 must FAIL before T012-T022 (TDD requirement)
- T012-T022 must pass before T028-T035 (UI depends on analytics engine)
- T023-T027 must FAIL before T028-T035 (UI TDD)
- T034-T035 depend on T028-T033 (profile system needs base UI)

**Parallel Opportunities**:
- T004-T011: All analytics contract tests (different test files)
- T012-T022: All analytics functions (different functions in same file, but independent)
- T023-T027: All UI integration tests (different test files)
- T036-T037: Documentation and acceptance tests (different files)

## Parallel Execution Examples

### Analytics Contract Tests (Phase 3.2)
```bash
# Launch T004-T011 together:
pytest tests/unit/test_data_loading.py::test_load_json_results_contract -v
pytest tests/unit/test_quality_control.py::test_qc_filter_contract -v  
pytest tests/unit/test_filtering.py::test_query_df_contract -v
pytest tests/unit/test_pareto.py::test_pareto_frontier_contract -v
pytest tests/unit/test_topk.py::test_topk_per_group_contract -v
pytest tests/unit/test_stability.py::test_stability_by_params_contract -v
pytest tests/unit/test_export.py::test_export_df_contract -v
pytest tests/unit/test_validation.py::test_validation_helpers_contract -v
```

### Analytics Implementation (Phase 3.3)
```bash
# Implement T012-T022 in parallel (different functions):
# Each task implements specific function in optimization_console.py
# Functions are independent and can be developed simultaneously
```

### Documentation & Testing (Phase 3.7)
```bash
# Launch T036-T037 together:
# Update README_UI.md (T036)
# Create acceptance tests (T037)
```

## Constitutional Compliance Checkpoints

**Throughout Implementation**:
- ✅ **Local-Only**: No network dependencies (T002 requirements validation)
- ✅ **Separation of Concerns**: Analytics engine independent of UI (T012-T022 vs T028-T035)
- ✅ **Performance**: 50k-200k row targets with truncation (T033, T038)
- ✅ **Reproducibility**: Export sidecars with complete metadata (T022, T027)
- ✅ **Robustness**: Validation dialogs, graceful degradation (T032, T039)

**Acceptance Criteria Mapping**:
- FR-001 to FR-005: T004, T012 (Data loading)
- FR-006 to FR-010: T005, T013 (Quality control)
- FR-011 to FR-016: T007-T009, T016-T018 (Analytics)
- FR-017 to FR-020: T033, T038 (Performance)
- FR-021 to FR-024: T034-T035 (Profiles)
- FR-025 to FR-029: T010, T022, T027 (Export)
- FR-030 to FR-034: T032, T039 (UX & Reliability)

## Validation Checklist
*GATE: Checked before task completion*

- [x] All contracts have corresponding tests (T004-T011 → T012-T022)
- [x] All entities have implementation tasks (5 entities covered in analytics + UI)
- [x] All tests come before implementation (TDD enforced)
- [x] Parallel tasks truly independent (different files or functions)
- [x] Each task specifies exact file path
- [x] No task modifies same file as another [P] task (ui_app.py tasks sequential)
- [x] Constitutional compliance validated throughout
- [x] All 34 functional requirements mapped to tasks

## Notes
- [P] tasks = different files or independent functions, no dependencies
- Verify tests fail before implementing (TDD critical for quality)
- Commit after each task completion
- Focus on constitutional compliance: local-only, deterministic, responsive, reproducible
- Target: 50k-200k rows with <1s operations and graceful degradation
