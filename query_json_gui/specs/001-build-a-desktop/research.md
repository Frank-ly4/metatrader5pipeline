# Research: Optimization Results Desktop Explorer

**Date**: 2025-10-01  
**Feature**: Desktop application for exploring optimization/backtest JSON results

## Technical Decisions & Research Findings

### PySide6 Desktop Application Architecture

**Decision**: Use Model-View architecture with QAbstractTableModel for large dataset display  
**Rationale**: 
- QAbstractTableModel provides efficient handling of large datasets through lazy loading
- Separates data logic from UI presentation as required by constitution
- Built-in sorting, filtering, and selection capabilities
- Memory efficient for 50k+ row display with virtual scrolling

**Alternatives Considered**:
- Direct QTableWidget population: Rejected due to memory overhead for large datasets
- Custom QML interface: Rejected due to complexity and constitutional requirement for simple tech stack
- Tkinter: Rejected due to poor cross-platform appearance and limited table performance

**Implementation Pattern**:
```python
class DataFrameModel(QAbstractTableModel):
    # Efficient pandas DataFrame wrapper
    # Handles display formatting (% for drawdown, 4-decimal floats)
    # Supports column visibility and sorting
```

### Pandas Performance Optimization

**Decision**: Use pandas query() with engine="python" for filter expressions, implement display truncation at UI layer  
**Rationale**:
- pandas query() provides safe expression evaluation with percentage token parsing
- Display truncation (50k rows) maintains UI responsiveness while preserving full dataset for exports
- Vectorized operations ensure sub-second performance for analytics functions
- Memory mapping for large JSON files when needed

**Alternatives Considered**:
- SQLite backend: Rejected due to complexity and JSON schema flexibility requirements
- Dask for out-of-core processing: Rejected as overkill for 200k row target
- Custom query parser: Rejected due to security concerns and pandas query() adequacy

**Performance Strategies**:
- Lazy loading for UI display (QAbstractTableModel virtual methods)
- Efficient column type inference during JSON loading
- Vectorized analytics operations (Pareto, Top-k, Stability)
- Memory-conscious export streaming for large result sets

### Cross-Platform Deployment

**Decision**: Python wheel distribution with platform-specific launchers  
**Rationale**:
- Maintains constitutional requirement for simple deployment
- Python virtual environment isolation prevents dependency conflicts
- Platform launchers (run_ui.bat for Windows) provide user-friendly startup
- No complex packaging (PyInstaller) needed for target user base

**Alternatives Considered**:
- PyInstaller executable: Rejected due to large bundle size and startup time
- Docker containers: Rejected as inappropriate for desktop GUI applications
- Platform-specific packages (MSI, DMG): Rejected due to maintenance overhead

**Deployment Strategy**:
- requirements.txt with pinned versions for reproducibility
- Platform-specific launcher scripts
- Clear installation documentation in README.md
- Virtual environment setup automation

### UI Design Patterns for Data Analysis

**Decision**: Left control panel / right table layout with status bar feedback  
**Rationale**:
- Familiar pattern for data analysis tools (matches user expectations)
- Logical workflow progression from data loading to analysis to export
- Status bar provides operation timing as required by constitution
- Responsive design accommodates different screen sizes

**Alternatives Considered**:
- Tabbed interface: Rejected due to workflow disruption and context switching
- Wizard-style interface: Rejected as too restrictive for exploratory analysis
- Multi-window design: Rejected due to complexity and window management issues

**UI Component Architecture**:
```
MainWindow
├── ControlPanel (left)
│   ├── DataSection (load, QC)
│   ├── QuerySection (filter, sort, limit)
│   ├── AnalyticsSection (Pareto, Top-k, Stability)
│   └── ProfileSection (save, load, export)
└── DataView (right)
    ├── TableView (with DataFrameModel)
    └── StatusBar (rows, timing, truncation notice)
```

### Analytics Algorithm Implementation

**Decision**: Pure pandas/numpy implementations with constitutional validation patterns  
**Rationale**:
- Leverages pandas' optimized operations for performance
- Maintains deterministic behavior across platforms
- Enables comprehensive unit testing without GUI dependencies
- Supports constitutional requirement for column validation

**Key Algorithms**:
- **Pareto Frontier**: Vectorized dominance checking with numpy boolean indexing
- **Top-k per Group**: pandas groupby with nlargest/nsmallest for stable ranking
- **Stability Analysis**: Grouped statistics with robust scoring (mean - λ*std)
- **Parameter Correlation**: Spearman rank correlation with categorical encoding

**Validation Strategy**:
```python
def require_columns(df: pd.DataFrame, cols: List[str]) -> Optional[List[str]]:
    """Return missing columns or None if all present"""
    
def validate_pareto_requirements(df: pd.DataFrame) -> None:
    """Raise ValueError with friendly message if requirements not met"""
```

### Logging and Error Handling

**Decision**: Python stdlib logging with RotatingFileHandler, comprehensive error boundaries  
**Rationale**:
- Constitutional requirement for local-only logging
- Rotating logs prevent disk space issues
- Error boundaries ensure "never lose last view" principle
- Structured logging enables troubleshooting and performance monitoring

**Logging Strategy**:
- Application events: data loading, operation timing, validation failures
- Error recovery: malformed JSON handling, missing column graceful degradation
- Performance monitoring: operation duration, memory usage patterns
- User actions: profile saves/loads, export operations

## Research Conclusions

All technical decisions align with constitutional requirements:
- ✅ Local-only operation (no network dependencies)
- ✅ Deterministic behavior (pandas/numpy consistency)
- ✅ Separation of concerns (analytics engine independent of UI)
- ✅ Performance targets (50k-200k rows with responsive UI)
- ✅ Reproducibility (export metadata, profile system)

The chosen architecture provides a solid foundation for implementing all functional requirements while maintaining constitutional compliance and user experience standards.
