
# Implementation Plan: Optimization Results Desktop Explorer

**Branch**: `001-build-a-desktop` | **Date**: 2025-10-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-build-a-desktop/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from file system structure or context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, `GEMINI.md` for Gemini CLI, `QWEN.md` for Qwen Code or `AGENTS.md` for opencode).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
Desktop application for quantitative analysts to explore large sets (50k-200k rows) of optimization/backtest JSON results and produce robust shortlists. Features include data loading with mixed schema handling, quality control filtering, multi-objective Pareto analysis, Top-k per group selection, parameter stability analysis, and reproducible exports with metadata sidecars. Built with Python 3.9+/PySide6 for local-only, deterministic operation with responsive UI through display truncation and comprehensive logging.

## Technical Context
**Language/Version**: Python 3.9+  
**Primary Dependencies**: PySide6 (GUI), pandas (data manipulation), pyarrow (optional Parquet export)  
**Storage**: Local JSON files (input), profiles.json, app_state.json, rotating log files  
**Testing**: pytest for unit tests, manual acceptance testing for UI workflows  
**Target Platform**: Cross-platform desktop (Windows, macOS, Linux)
**Project Type**: single - desktop application with analytics engine + GUI  
**Performance Goals**: 50k-200k rows responsive, <1s operations, UI truncation at 50k display rows  
**Constraints**: Local-only (no network), deterministic behavior, graceful degradation, Unicode support  
**Scale/Scope**: Single-user desktop app, ~10 main UI panels, comprehensive analytics suite

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitutional Compliance Analysis**:

✅ **I. Local-Only & Deterministic Execution**
- Python 3.9+ with PySide6/pandas ensures deterministic processing
- No network dependencies (local JSON files, no APIs)
- Reproducible results across sessions via profiles and export metadata

✅ **II. Robust UX & Safety (Never Lose Last View)**
- UI state preservation on errors through validation before operations
- Malformed JSON handling with logging, graceful schema degradation
- Friendly error dialogs with no state changes on validation failures

✅ **III. Separation of Concerns (UI vs Engine)**
- Analytics engine (pandas-based) independent of PySide6 UI
- Clear interface: engine functions callable without GUI dependencies
- UI handles presentation only, engine handles all data processing

✅ **IV. Performance & Responsiveness**
- 50k display truncation with full dataset export capability
- Operation timing in status bar, non-blocking UI operations
- Memory optimization through display limits and efficient pandas operations

✅ **V. Reproducibility & Extensibility**
- Export sidecar JSON with complete metadata (app_version, timestamp, settings)
- Profile system for repeatable workflows with schema versioning
- Analytics functions designed for extension without UI changes

**Technology Stack Compliance**: ✅ PASS
- Python 3.9+, PySide6, pandas, pyarrow (optional) - all approved
- No heavy GUI dependencies, no network libraries
- Rotating local logging with stdlib only

**Performance Requirements**: ✅ PASS
- Target 50k-200k rows with responsive UI
- Display truncation at 50k rows with status indicators
- Operation timing feedback in status bar

## Project Structure

### Documentation (this feature)
```
specs/[###-feature]/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
optimization_console_package/
├── optimization_console.py    # Analytics engine (data processing, algorithms)
├── ui_app.py                 # PySide6 GUI application
├── run_console.py           # CLI entry point (if needed)
├── requirements.txt         # Python dependencies
├── README.md               # User documentation
├── README_UI.md           # UI-specific documentation
├── run_ui.bat             # Windows launcher script
├── profiles.json          # User analysis profiles (generated)
├── app_state.json         # Application state persistence (generated)
├── opt_console_ui.log     # Rotating log file (generated)
└── tests/
    ├── unit/
    │   ├── test_analytics.py      # Analytics engine unit tests
    │   ├── test_data_loading.py   # JSON loading and validation tests
    │   └── test_export.py         # Export functionality tests
    ├── integration/
    │   ├── test_ui_workflows.py   # End-to-end UI workflow tests
    │   └── test_profile_system.py # Profile save/load integration tests
    └── acceptance/
        └── test_acceptance_criteria.py  # Constitutional acceptance tests
```

**Structure Decision**: Single desktop application structure selected. The analytics engine (`optimization_console.py`) provides all data processing capabilities as a standalone library, while the GUI (`ui_app.py`) handles presentation and user interaction. This maintains clear separation of concerns as required by the constitution, enabling the engine to be tested independently and potentially reused in other contexts.

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - No NEEDS CLARIFICATION items - all technical decisions provided by user
   - Research best practices for PySide6 desktop applications
   - Research pandas performance optimization for large datasets
   - Research cross-platform deployment strategies

2. **Generate and dispatch research agents**:
   ```
   Task: "Research PySide6 best practices for responsive desktop applications"
   Task: "Research pandas optimization techniques for 50k-200k row datasets"
   Task: "Research cross-platform Python desktop app deployment"
   Task: "Research UI design patterns for data analysis applications"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all technical decisions documented

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Entity name, fields, relationships
   - Validation rules from requirements
   - State transitions if applicable

2. **Generate API contracts** from functional requirements:
   - For each user action → endpoint
   - Use standard REST/GraphQL patterns
   - Output OpenAPI/GraphQL schema to `/contracts/`

3. **Generate contract tests** from contracts:
   - One test file per endpoint
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - Each story → integration test scenario
   - Quickstart test = story validation steps

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType cursor`
     **IMPORTANT**: Execute it exactly as specified above. Do not add or remove any arguments.
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base
- Generate tasks from Phase 1 design docs (contracts, data model, quickstart)
- Each contract → contract test task [P]
- Each entity → model creation task [P] 
- Each user story → integration test task
- Implementation tasks to make tests pass

**Ordering Strategy**:
- TDD order: Tests before implementation 
- Dependency order: Models before services before UI
- Mark [P] for parallel execution (independent files)

**Estimated Output**: 25-30 numbered, ordered tasks in tasks.md

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented (none required)

---
*Based on Constitution v1.1.0 - See `.specify/memory/constitution.md`*
