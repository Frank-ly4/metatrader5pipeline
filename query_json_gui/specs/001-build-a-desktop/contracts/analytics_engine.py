"""
Analytics Engine Contract
=========================

This file defines the interface contract for the analytics engine component.
All functions must be implemented to satisfy the constitutional requirements
for separation of concerns and testability.
"""

from typing import List, Optional, Tuple, Dict, Any, Sequence
import pandas as pd


class AnalyticsEngineContract:
    """Contract interface for the analytics engine component."""
    
    # Data Loading & Validation
    def load_json_results(self, paths: List[str]) -> pd.DataFrame:
        """
        Load and merge multiple JSON files into unified DataFrame.
        
        Args:
            paths: List of JSON file paths to load
            
        Returns:
            DataFrame with merged results and _source_file column
            
        Requirements:
            - FR-001: Load multiple JSON files and merge into unified table
            - FR-002: Add source file tracking (_source_file column)
            - FR-003: Handle mixed JSON schemas gracefully
            - FR-004: Support Unicode file paths
            - FR-005: Log loading outcomes and errors
        """
        raise NotImplementedError
    
    def require_columns(self, df: pd.DataFrame, cols: List[str]) -> Optional[List[str]]:
        """
        Validate required columns exist in DataFrame.
        
        Args:
            df: DataFrame to validate
            cols: List of required column names
            
        Returns:
            List of missing columns or None if all present
            
        Requirements:
            - FR-016: Validate required columns before analysis
        """
        raise NotImplementedError
    
    def list_param_cols(self, df: pd.DataFrame) -> List[str]:
        """
        List all parameter columns (param_* prefix) in DataFrame.
        
        Args:
            df: DataFrame to scan for parameter columns
            
        Returns:
            List of parameter column names
            
        Requirements:
            - Support for stability analysis grouping
        """
        raise NotImplementedError
    
    def is_percent_col(self, name: str) -> bool:
        """
        Check if column should be displayed as percentage.
        
        Args:
            name: Column name to check
            
        Returns:
            True if column represents percentage data
            
        Requirements:
            - UI formatting for max_drawdown, win_rate
        """
        raise NotImplementedError
    
    # Quality Control & Filtering
    def qc_filter(self, df: pd.DataFrame, min_trades: int = 20, 
                  max_mdd: float = 1.0, nondegenerate: bool = False) -> pd.DataFrame:
        """
        Apply quality control filters to remove unreliable results.
        
        Args:
            df: Input DataFrame
            min_trades: Minimum number of trades required
            max_mdd: Maximum drawdown threshold (as fraction)
            nondegenerate: Whether to drop zero-trade/zero-metric results
            
        Returns:
            Filtered DataFrame meeting quality criteria
            
        Requirements:
            - FR-006: Quality control filters for min trades and max drawdown
            - FR-007: Support dropping degenerate results
        """
        raise NotImplementedError
    
    def query_df(self, df: pd.DataFrame, filter_expr: Optional[str] = None,
                 sort_by: Optional[str] = None, limit: int = 0) -> pd.DataFrame:
        """
        Apply filter, sort, and limit operations to DataFrame.
        
        Args:
            df: Input DataFrame
            filter_expr: pandas query expression with % parsing support
            sort_by: Sort specification (e.g., "-calmar_ratio,profit_factor")
            limit: Maximum rows to return (0 = unlimited)
            
        Returns:
            Processed DataFrame
            
        Requirements:
            - FR-008: Parse percentage expressions (8%, 8 %, 0.08)
            - FR-009: Support complex filter expressions
            - FR-010: Validate filter syntax with helpful errors
            - FR-034: Multi-column sorting with ascending/descending
        """
        raise NotImplementedError
    
    # Analytics Functions
    def pareto_frontier(self, df: pd.DataFrame, 
                       objectives: Sequence[Tuple[str, str]] = None) -> pd.DataFrame:
        """
        Find Pareto-optimal solutions for multi-objective optimization.
        
        Args:
            df: Input DataFrame
            objectives: List of (column, direction) pairs
                       Default: [("calmar_ratio", "max"), ("max_drawdown", "min"), 
                                ("profit_factor", "max")]
            
        Returns:
            DataFrame containing non-dominated solutions
            
        Requirements:
            - FR-012: Pareto frontier analysis for multi-objective optimization
            - Required columns: calmar_ratio, max_drawdown, profit_factor
        """
        raise NotImplementedError
    
    def topk_per_group(self, df: pd.DataFrame, group_by: str, sort_by: str,
                       k: int, filter_expr: Optional[str] = None) -> pd.DataFrame:
        """
        Select top-k results per group for fair shortlisting.
        
        Args:
            df: Input DataFrame
            group_by: Comma-separated grouping columns
            sort_by: Sort specification for ranking within groups
            k: Number of results per group
            filter_expr: Optional pre-filter expression
            
        Returns:
            DataFrame with ≤k results per group
            
        Requirements:
            - FR-011: Top-k per group for fair shortlisting
            - Support chart, fold_id, param_* grouping
        """
        raise NotImplementedError
    
    def stability_by_params(self, df: pd.DataFrame, 
                           metrics: Sequence[str] = None,
                           lambda_std: float = 0.5) -> pd.DataFrame:
        """
        Calculate parameter stability metrics across market conditions.
        
        Args:
            df: Input DataFrame
            metrics: Metrics to analyze (default: calmar_ratio, profit_factor, max_drawdown)
            lambda_std: Robustness penalty factor
            
        Returns:
            DataFrame with stability scores per parameter combination
            
        Requirements:
            - FR-013: Stability metrics for parameter sets
            - Required: ≥1 param_* column and ≥1 specified metric
        """
        raise NotImplementedError
    
    def composite_score(self, df: pd.DataFrame, 
                       weights: Optional[Dict[str, float]] = None) -> pd.DataFrame:
        """
        Calculate composite performance score with configurable weights.
        
        Args:
            df: Input DataFrame
            weights: Metric weights (default: Sharpe*1.0 + Sortino*0.5 + 
                    Calmar*1.0 + PF*0.5 - MDD*1.0)
            
        Returns:
            DataFrame sorted by composite_score (descending)
            
        Requirements:
            - Weighted combination of performance metrics
            - Graceful degradation for missing metrics
        """
        raise NotImplementedError
    
    def param_spearman(self, df: pd.DataFrame, 
                      metric_cols: Optional[Sequence[str]] = None) -> pd.DataFrame:
        """
        Calculate Spearman correlations between parameters and metrics.
        
        Args:
            df: Input DataFrame
            metric_cols: Metrics to correlate (auto-detected if None)
            
        Returns:
            Correlation matrix as DataFrame
            
        Requirements:
            - FR-014: Parameter-metric correlations via Spearman analysis
        """
        raise NotImplementedError
    
    def partial_dependence(self, df: pd.DataFrame, param: str, metric: str,
                          bins: int = 8) -> pd.DataFrame:
        """
        Calculate partial dependence of metric on parameter.
        
        Args:
            df: Input DataFrame
            param: Parameter column name
            metric: Metric column name
            bins: Number of quantile bins
            
        Returns:
            DataFrame with binned parameter effects
            
        Requirements:
            - FR-015: Partial dependence analysis for parameter effects
        """
        raise NotImplementedError
    
    # Export Functions
    def export_df(self, df: pd.DataFrame, out_dir: str, name: str,
                  meta: Optional[Dict[str, Any]] = None) -> Tuple[str, Optional[str], str]:
        """
        Export DataFrame with metadata sidecar for reproducibility.
        
        Args:
            df: DataFrame to export
            out_dir: Output directory path
            name: Base filename (without extension)
            meta: Additional metadata to include in sidecar
            
        Returns:
            Tuple of (csv_path, parquet_path, sidecar_path)
            
        Requirements:
            - FR-025: Export to CSV format
            - FR-026: Export to Parquet when available
            - FR-027: Generate metadata sidecar JSON
            - FR-028: Include complete reproducibility information
            - FR-029: Export full dataset even when display truncated
        """
        raise NotImplementedError


# Contract Test Interface
class AnalyticsEngineTests:
    """Contract tests that must pass for any analytics engine implementation."""
    
    def test_load_json_results_basic(self):
        """Test basic JSON loading functionality."""
        raise NotImplementedError
    
    def test_load_json_results_mixed_schemas(self):
        """Test handling of mixed JSON schemas."""
        raise NotImplementedError
    
    def test_load_json_results_malformed(self):
        """Test graceful handling of malformed JSON files."""
        raise NotImplementedError
    
    def test_qc_filter_min_trades(self):
        """Test minimum trades filtering."""
        raise NotImplementedError
    
    def test_qc_filter_max_drawdown(self):
        """Test maximum drawdown filtering."""
        raise NotImplementedError
    
    def test_query_df_percent_parsing(self):
        """Test percentage parsing in filter expressions."""
        raise NotImplementedError
    
    def test_pareto_frontier_basic(self):
        """Test basic Pareto frontier calculation."""
        raise NotImplementedError
    
    def test_pareto_frontier_missing_columns(self):
        """Test Pareto analysis with missing required columns."""
        raise NotImplementedError
    
    def test_topk_per_group_basic(self):
        """Test basic Top-k per group functionality."""
        raise NotImplementedError
    
    def test_stability_analysis_basic(self):
        """Test parameter stability analysis."""
        raise NotImplementedError
    
    def test_stability_analysis_missing_params(self):
        """Test stability analysis with missing param columns."""
        raise NotImplementedError
    
    def test_export_with_sidecar(self):
        """Test export with metadata sidecar generation."""
        raise NotImplementedError
    
    def test_unicode_path_handling(self):
        """Test Unicode file path support."""
        raise NotImplementedError
