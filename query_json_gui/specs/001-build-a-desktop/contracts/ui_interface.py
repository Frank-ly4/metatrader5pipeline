"""
UI Interface Contract
====================

This file defines the interface contract for the UI component.
Defines the expected behavior and interactions for the PySide6 GUI application.
"""

from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod


class UIComponentContract(ABC):
    """Contract interface for UI components and interactions."""
    
    # Application Lifecycle
    @abstractmethod
    def initialize_application(self) -> None:
        """
        Initialize the main application window and components.
        
        Requirements:
            - Load application state from app_state.json
            - Set up logging with rotating file handler
            - Initialize UI components with constitutional layout
        """
        pass
    
    @abstractmethod
    def shutdown_application(self) -> None:
        """
        Clean shutdown of application with state persistence.
        
        Requirements:
            - Save current application state to app_state.json
            - Ensure no data loss on exit
        """
        pass
    
    # Data Management
    @abstractmethod
    def load_data_from_directory(self, directory_path: str) -> bool:
        """
        Load JSON files from specified directory.
        
        Args:
            directory_path: Path to directory containing JSON files
            
        Returns:
            True if data loaded successfully, False otherwise
            
        Requirements:
            - FR-001: Load multiple JSON files from folder
            - FR-004: Support Unicode file paths
            - FR-005: Log loading outcomes and errors
            - Display loading progress and results to user
        """
        pass
    
    @abstractmethod
    def apply_quality_control(self, min_trades: int, max_mdd: float, 
                             nondegenerate: bool) -> bool:
        """
        Apply quality control filters to loaded data.
        
        Args:
            min_trades: Minimum number of trades threshold
            max_mdd: Maximum drawdown threshold (as fraction)
            nondegenerate: Whether to drop degenerate results
            
        Returns:
            True if QC applied successfully, False otherwise
            
        Requirements:
            - FR-006: Quality control filters
            - FR-007: Drop degenerate results option
            - Update table display with filtered results
            - Show operation timing in status bar
        """
        pass
    
    @abstractmethod
    def apply_filter_sort_limit(self, filter_expr: str, sort_by: str, 
                               limit: int) -> bool:
        """
        Apply filter, sort, and limit operations to current data.
        
        Args:
            filter_expr: pandas query expression with % parsing
            sort_by: Sort specification string
            limit: Row limit (0 = unlimited)
            
        Returns:
            True if operations applied successfully, False otherwise
            
        Requirements:
            - FR-008: Percentage expression parsing
            - FR-009: Complex filter expressions
            - FR-010: Validate syntax with helpful errors
            - FR-034: Multi-column sorting support
        """
        pass
    
    # Analytics Operations
    @abstractmethod
    def run_pareto_analysis(self) -> bool:
        """
        Execute Pareto frontier analysis on current data.
        
        Returns:
            True if analysis completed successfully, False otherwise
            
        Requirements:
            - FR-012: Pareto frontier analysis
            - FR-016: Validate required columns before execution
            - Show validation dialog if columns missing
            - Update table with Pareto-optimal results
        """
        pass
    
    @abstractmethod
    def run_topk_analysis(self, group_by: str, sort_by: str, k: int,
                         filter_expr: Optional[str] = None) -> bool:
        """
        Execute Top-k per group analysis.
        
        Args:
            group_by: Comma-separated grouping columns
            sort_by: Sort specification for ranking
            k: Number of results per group
            filter_expr: Optional pre-filter expression
            
        Returns:
            True if analysis completed successfully, False otherwise
            
        Requirements:
            - FR-011: Top-k per group functionality
            - FR-016: Validate required columns
            - Show validation dialog if columns missing
        """
        pass
    
    @abstractmethod
    def run_stability_analysis(self) -> bool:
        """
        Execute parameter stability analysis.
        
        Returns:
            True if analysis completed successfully, False otherwise
            
        Requirements:
            - FR-013: Parameter stability metrics
            - FR-016: Validate param_* columns and metrics exist
            - Show validation dialog if requirements not met
        """
        pass
    
    @abstractmethod
    def run_correlation_analysis(self) -> bool:
        """
        Execute parameter-metric correlation analysis.
        
        Returns:
            True if analysis completed successfully, False otherwise
            
        Requirements:
            - FR-014: Spearman correlation analysis
            - Display correlation matrix in table format
        """
        pass
    
    @abstractmethod
    def run_partial_dependence(self, param: str, metric: str) -> bool:
        """
        Execute partial dependence analysis.
        
        Args:
            param: Parameter column name
            metric: Metric column name
            
        Returns:
            True if analysis completed successfully, False otherwise
            
        Requirements:
            - FR-015: Partial dependence analysis
            - Validate specified columns exist
        """
        pass
    
    # Display Management
    @abstractmethod
    def update_table_display(self, operation_time_ms: Optional[float] = None) -> None:
        """
        Update table display with current data state.
        
        Args:
            operation_time_ms: Operation timing for status bar
            
        Requirements:
            - FR-017: Handle 50k-200k rows responsively
            - FR-018: Truncate display at 50k rows
            - FR-019: Show truncation status indicator
            - FR-020: Display operation timing
        """
        pass
    
    @abstractmethod
    def show_validation_dialog(self, operation_name: str, 
                              missing_columns: List[str]) -> None:
        """
        Display validation error dialog for missing columns.
        
        Args:
            operation_name: Name of operation that failed validation
            missing_columns: List of missing required columns
            
        Requirements:
            - FR-031: Friendly validation dialogs
            - FR-030: Never lose current view state
            - Clear explanation of requirements
        """
        pass
    
    # Profile Management
    @abstractmethod
    def save_profile(self, profile_name: str) -> bool:
        """
        Save current analysis settings as named profile.
        
        Args:
            profile_name: User-assigned profile name
            
        Returns:
            True if profile saved successfully, False otherwise
            
        Requirements:
            - FR-021: Save analysis settings as profiles
            - FR-023: Schema versioning for backward compatibility
        """
        pass
    
    @abstractmethod
    def load_profile(self, profile_name: str) -> bool:
        """
        Load and apply saved analysis profile.
        
        Args:
            profile_name: Name of profile to load
            
        Returns:
            True if profile loaded successfully, False otherwise
            
        Requirements:
            - FR-022: Load saved profiles to restore state
            - FR-024: Persist application state between sessions
        """
        pass
    
    @abstractmethod
    def list_available_profiles(self) -> List[str]:
        """
        Get list of available profile names.
        
        Returns:
            List of saved profile names
            
        Requirements:
            - Support profile selection UI
        """
        pass
    
    # Export Operations
    @abstractmethod
    def export_current_view(self, output_directory: str, filename: str) -> bool:
        """
        Export current table view with metadata sidecar.
        
        Args:
            output_directory: Directory for export files
            filename: Base filename (without extension)
            
        Returns:
            True if export completed successfully, False otherwise
            
        Requirements:
            - FR-025: Export to CSV format
            - FR-026: Export to Parquet when available
            - FR-027: Generate metadata sidecar
            - FR-028: Include complete reproducibility info
            - FR-029: Export full dataset even if display truncated
        """
        pass
    
    # Error Handling
    @abstractmethod
    def handle_operation_error(self, operation_name: str, error_message: str) -> None:
        """
        Handle operation errors with user-friendly feedback.
        
        Args:
            operation_name: Name of failed operation
            error_message: Error description
            
        Requirements:
            - FR-030: Never lose current view state on errors
            - FR-031: Show friendly validation dialogs
            - Log errors for troubleshooting
        """
        pass


class UILayoutContract:
    """Contract for UI layout and component organization."""
    
    # Layout Requirements (Constitutional)
    LEFT_PANEL_SECTIONS = [
        "Data",                    # Load JSONs, choose directory
        "QC",                     # Quality control filters  
        "Query/Sort/Limit",       # Filter expressions, sorting, limits
        "Top-k",                  # Top-k per group analysis
        "Advanced",               # Pareto, Stability, Correlations
        "Export & Profiles"       # Export and profile management
    ]
    
    RIGHT_PANEL_COMPONENTS = [
        "DataTable",              # Main results table with sorting
        "StatusBar"               # Row count, operation timing, truncation notice
    ]
    
    # Status Bar Format (Constitutional)
    STATUS_BAR_FORMAT = "Rows: {count:,} | Last op: {time_ms:.0f} ms"
    STATUS_BAR_TRUNCATED = "Showing 50,000 of {total:,} rows | Last op: {time_ms:.0f} ms"
    
    # Column Formatting Requirements
    PERCENTAGE_COLUMNS = ["max_drawdown", "win_rate"]  # Display as %, store as fraction
    DECIMAL_PRECISION = 4  # For non-percentage float columns
    
    # Performance Thresholds
    DISPLAY_TRUNCATION_THRESHOLD = 50_000  # Rows
    TARGET_OPERATION_TIME_MS = 1_000      # Target response time


class UIValidationContract:
    """Contract for UI validation and error handling."""
    
    # Required Columns by Analysis Type (Constitutional)
    PARETO_REQUIRED_COLUMNS = ["calmar_ratio", "max_drawdown", "profit_factor"]
    STABILITY_REQUIRED_PARAM_COLUMNS = 1  # Minimum param_* columns
    STABILITY_REQUIRED_METRICS = ["calmar_ratio", "profit_factor", "max_drawdown"]  # At least one
    
    # Validation Dialog Templates
    MISSING_COLUMNS_DIALOG = """
    {operation_name} requires the following columns:
    
    {column_list}
    
    Operation cancelled. Please ensure your data contains these columns.
    """
    
    INVALID_FILTER_DIALOG = """
    Filter expression is invalid:
    
    {error_message}
    
    Please check your syntax. Examples:
    • max_drawdown < 8%
    • profit_factor >= 1.5 and num_trades > 20
    """
    
    # Percent Parsing Examples (Constitutional)
    PERCENT_PARSING_EXAMPLES = [
        "8%",      # Standard percentage
        "8 %",     # Spaced percentage  
        "0.08"     # Decimal equivalent
    ]
