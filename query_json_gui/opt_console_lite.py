#!/usr/bin/env python3
"""
Optimization Console Lite
==========================
Minimal, fast desktop app for viewing and querying optimizer JSON results.

Dependencies: PySide6, pandas, stdlib only
"""

import sys
import json
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import pandas as pd
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QTableView, QFileDialog,
    QCheckBox, QSpinBox, QTextEdit, QScrollArea, QGroupBox,
    QComboBox, QMessageBox, QStatusBar
)
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex
from PySide6.QtGui import QFont
import time


# ============================================================================
# Utility Functions
# ============================================================================

def _normalize_percent_tokens(expr: str) -> str:
    """Replace percentage tokens (8%, 8 %) with decimal fractions (0.08)."""
    # Match patterns like "8%", "8 %", "10.5%", etc.
    pattern = r'(\d+(?:\.\d+)?)\s*%'
    
    def replace_func(match):
        value = float(match.group(1))
        return str(value / 100.0)
    
    return re.sub(pattern, replace_func, expr)


def _apply_layered_filters(df: pd.DataFrame, filter_rows: List[Tuple[str, str, str]]) -> Tuple[str, pd.DataFrame]:
    """
    Build AND-joined clauses from layered filter rows.
    
    Args:
        df: Input DataFrame
        filter_rows: List of (metric, operator, value) tuples
        
    Returns:
        Tuple of (filter_expression_string, filtered_dataframe)
    """
    if not filter_rows:
        return "", df
    
    clauses = []
    for metric, op, value in filter_rows:
        # Normalize % in value
        value_normalized = _normalize_percent_tokens(value.strip())
        clauses.append(f"({metric} {op} {value_normalized})")
    
    expr = " and ".join(clauses)
    try:
        df_filtered = df.query(expr, engine="python")
        return expr, df_filtered
    except Exception as e:
        raise ValueError(f"Layered filter error: {e}")


def _apply_query_sort_limit(df: pd.DataFrame, filter_expr: str, sort_by: str, limit: int) -> pd.DataFrame:
    """
    Apply filter expression, sorting, and limit to DataFrame.
    
    Args:
        df: Input DataFrame
        filter_expr: pandas query expression (already normalized)
        sort_by: Comma-separated sort columns; "-col" means descending
        limit: Row limit (0 = no limit)
        
    Returns:
        Processed DataFrame
    """
    result = df.copy()
    
    # Apply filter
    if filter_expr and filter_expr.strip():
        normalized_expr = _normalize_percent_tokens(filter_expr.strip())
        result = result.query(normalized_expr, engine="python")
    
    # Apply sort
    if sort_by and sort_by.strip():
        sort_cols = []
        ascending = []
        for col in sort_by.split(','):
            col = col.strip()
            if col.startswith('-'):
                sort_cols.append(col[1:])
                ascending.append(False)
            else:
                sort_cols.append(col)
                ascending.append(True)
        result = result.sort_values(by=sort_cols, ascending=ascending)
    
    # Apply limit
    if limit > 0:
        result = result.head(limit)
    
    return result


def _build_sorted_df_for_topn(df: pd.DataFrame, metric: str, desc: bool, user_sort_by: str) -> pd.DataFrame:
    """
    Sort DataFrame by metric first (primary), then user sort keys (secondary).
    
    Args:
        df: Input DataFrame
        metric: Primary sort metric
        desc: True for descending (best first), False for ascending
        user_sort_by: User-specified sort string (comma-separated)
        
    Returns:
        Sorted DataFrame
    """
    sort_cols = [metric]
    ascending = [not desc]  # desc=True means best first (ascending=False)
    
    # Add user sort keys if provided
    if user_sort_by and user_sort_by.strip():
        for col in user_sort_by.split(','):
            col = col.strip()
            if col.startswith('-'):
                sort_cols.append(col[1:])
                ascending.append(False)
            else:
                sort_cols.append(col)
                ascending.append(True)
    
    return df.sort_values(by=sort_cols, ascending=ascending)


def detect_metric_columns(df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Auto-detect metric columns from DataFrame.
    
    Returns dict with keys: "higher" (higher is better), "lower" (lower is better), "other"
    """
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    
    # Exclude columns
    exclude_patterns = ['param_', 'id', '_id', 'chart', 'symbol', 'timestamp', 'date', 'time']
    filtered_cols = [
        col for col in numeric_cols 
        if not any(pattern in col.lower() for pattern in exclude_patterns)
    ]
    
    higher_is_better = []
    lower_is_better = []
    other = []
    
    higher_patterns = [
        'calmar', 'sharpe', 'sortino', 'profit_factor', 'pf', 'win_rate',
        'roi', 'cagr', 'return', 'expectancy', 'avg_trade', 'median_trade'
    ]
    lower_patterns = [
        'max_drawdown', 'mdd', 'drawdown', 'volatility', 'stdev', 'std',
        'downside_risk', 'var'
    ]
    
    for col in filtered_cols:
        col_lower = col.lower()
        if any(p in col_lower for p in higher_patterns):
            higher_is_better.append(col)
        elif any(p in col_lower for p in lower_patterns):
            lower_is_better.append(col)
        else:
            other.append(col)
    
    return {
        "higher": higher_is_better,
        "lower": lower_is_better,
        "other": other
    }


# ============================================================================
# Data Model
# ============================================================================

class DataFrameModel(QAbstractTableModel):
    """Simple pandas DataFrame model for QTableView."""
    
    def __init__(self, df: pd.DataFrame = None):
        super().__init__()
        self._df = df if df is not None else pd.DataFrame()
    
    def setDataFrame(self, df: pd.DataFrame):
        """Update the DataFrame and refresh the view."""
        self.beginResetModel()
        self._df = df
        self.endResetModel()
    
    def rowCount(self, parent=QModelIndex()):
        return len(self._df)
    
    def columnCount(self, parent=QModelIndex()):
        return len(self._df.columns)
    
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        
        if role == Qt.DisplayRole:
            value = self._df.iloc[index.row(), index.column()]
            
            # Format based on column name and type
            col_name = self._df.columns[index.column()]
            if pd.isna(value):
                return ""
            elif col_name in ['max_drawdown', 'win_rate'] and isinstance(value, (int, float)):
                return f"{value * 100:.2f}%"
            elif isinstance(value, float):
                return f"{value:.4f}"
            else:
                return str(value)
        
        return None
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._df.columns[section])
            else:
                return str(section + 1)
        return None
    
    def getDataFrame(self) -> pd.DataFrame:
        """Get the underlying DataFrame."""
        return self._df


# ============================================================================
# Main Window
# ============================================================================

class OptConsoleLiteWindow(QMainWindow):
    """Main window for Optimization Console Lite."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Optimization Console Lite")
        self.resize(1400, 800)
        
        # Data storage
        self.full_df = pd.DataFrame()  # Complete dataset
        self.display_df = pd.DataFrame()  # Current filtered/sorted view
        self.current_folder = ""
        
        # Layered filter state
        self.layered_filter_rows = []  # List of (metric, op, value) tuples
        self.filter_widgets = []  # List of widget tuples for each row
        
        # Setup UI
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the main UI layout."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        
        # Left panel (controls)
        left_panel = self._create_left_panel()
        layout.addWidget(left_panel, stretch=0)
        
        # Right panel (table + log)
        right_panel = self._create_right_panel()
        layout.addWidget(right_panel, stretch=1)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._update_status("Ready", 0)
    
    def _create_left_panel(self) -> QWidget:
        """Create scrollable left control panel."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(350)
        scroll.setMaximumWidth(450)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        
        # === Load Folder Section ===
        load_group = QGroupBox("Load Folder")
        load_layout = QVBoxLayout()
        
        self.recursive_check = QCheckBox("Recursive")
        self.recursive_check.setChecked(False)
        load_layout.addWidget(self.recursive_check)
        
        load_btn = QPushButton("Choose Folder && Load")
        load_btn.clicked.connect(self._load_folder)
        load_layout.addWidget(load_btn)
        
        load_group.setLayout(load_layout)
        layout.addWidget(load_group)
        
        # === Filter Expression Section ===
        filter_group = QGroupBox("Free-Text Filter")
        filter_layout = QVBoxLayout()
        
        self.filter_expr = QLineEdit()
        self.filter_expr.setPlaceholderText("e.g., profit_factor >= 1.5 and num_trades > 20")
        filter_layout.addWidget(QLabel("Filter Expression:"))
        filter_layout.addWidget(self.filter_expr)
        
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        
        # === Sort & Limit Section ===
        sort_group = QGroupBox("Sort & Limit")
        sort_layout = QVBoxLayout()
        
        self.sort_by = QLineEdit()
        self.sort_by.setPlaceholderText("e.g., -calmar_ratio,profit_factor")
        sort_layout.addWidget(QLabel("Sort By:"))
        sort_layout.addWidget(self.sort_by)
        
        limit_row = QHBoxLayout()
        limit_row.addWidget(QLabel("Limit:"))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(0, 1000000)
        self.limit_spin.setValue(0)
        self.limit_spin.setSpecialValueText("No Limit")
        limit_row.addWidget(self.limit_spin)
        sort_layout.addLayout(limit_row)
        
        sort_group.setLayout(sort_layout)
        layout.addWidget(sort_group)
        
        # === Layered Filters Section ===
        layered_group = QGroupBox("Layered Filters (AND)")
        self.layered_layout = QVBoxLayout()
        
        # Metric selection combo (populated after load)
        metric_row = QHBoxLayout()
        metric_row.addWidget(QLabel("Add Filter:"))
        self.metric_combo = QComboBox()
        metric_row.addWidget(self.metric_combo)
        add_filter_btn = QPushButton("+")
        add_filter_btn.clicked.connect(self._add_layered_filter_row)
        metric_row.addWidget(add_filter_btn)
        self.layered_layout.addLayout(metric_row)
        
        # Container for filter rows
        self.filter_rows_container = QVBoxLayout()
        self.layered_layout.addLayout(self.filter_rows_container)
        
        layered_group.setLayout(self.layered_layout)
        layout.addWidget(layered_group)
        
        # === Top-N Section ===
        topn_group = QGroupBox("Top-N")
        topn_layout = QVBoxLayout()
        
        topn_spin_row = QHBoxLayout()
        topn_spin_row.addWidget(QLabel("N:"))
        self.topn_spin = QSpinBox()
        self.topn_spin.setRange(0, 100000)
        self.topn_spin.setValue(0)
        self.topn_spin.setSpecialValueText("OFF")
        topn_spin_row.addWidget(self.topn_spin)
        topn_layout.addLayout(topn_spin_row)
        
        topn_layout.addWidget(QLabel("Metric:"))
        self.topn_metric_combo = QComboBox()
        topn_layout.addWidget(self.topn_metric_combo)
        
        topn_layout.addWidget(QLabel("Direction:"))
        self.topn_direction = QComboBox()
        self.topn_direction.addItems(["Desc (best first)", "Asc (lowest first)"])
        topn_layout.addWidget(self.topn_direction)
        
        apply_topn_btn = QPushButton("Apply Top-N")
        apply_topn_btn.clicked.connect(self._apply_topn)
        topn_layout.addWidget(apply_topn_btn)
        
        topn_group.setLayout(topn_layout)
        layout.addWidget(topn_group)
        
        # === Action Buttons ===
        btn_layout = QVBoxLayout()
        
        apply_btn = QPushButton("Apply (Filter → Sort → Limit)")
        apply_btn.clicked.connect(self._apply_filters)
        btn_layout.addWidget(apply_btn)
        
        reset_btn = QPushButton("Reset (Show ALL)")
        reset_btn.clicked.connect(self._reset_view)
        btn_layout.addWidget(reset_btn)
        
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        btn_layout.addWidget(export_btn)
        
        layout.addLayout(btn_layout)
        
        layout.addStretch()
        
        scroll.setWidget(container)
        return scroll
    
    def _create_right_panel(self) -> QWidget:
        """Create right panel with table and log."""
        container = QWidget()
        layout = QVBoxLayout(container)
        
        # Table
        self.table_view = QTableView()
        self.table_model = DataFrameModel()
        self.table_view.setModel(self.table_model)
        layout.addWidget(self.table_view, stretch=1)
        
        # Inline log
        log_label = QLabel("Load Log:")
        layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        self.log_text.setFont(QFont("Courier", 9))
        layout.addWidget(self.log_text)
        
        return container
    
    # ========================================================================
    # Core Operations
    # ========================================================================
    
    def _load_folder(self):
        """Load JSON files from chosen folder."""
        folder = QFileDialog.getExistingDirectory(self, "Choose Folder")
        if not folder:
            return
        
        self.current_folder = folder
        recursive = self.recursive_check.isChecked()
        
        start = time.time()
        self.log_text.clear()
        self._log(f"Loading from: {folder}")
        self._log(f"Recursive: {recursive}")
        
        # Find JSON files
        path = Path(folder)
        if recursive:
            json_files = list(path.rglob("*.json"))
        else:
            json_files = list(path.glob("*.json"))
        
        self._log(f"Found {len(json_files)} JSON file(s)")
        
        # Load each file
        all_rows = []
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Extract metadata and results
                metadata = data.get('metadata', {})
                results = data.get('results', [])
                
                if not results:
                    results = [data]  # Treat entire file as single result
                
                # Merge metadata into each result row
                for result in results:
                    if isinstance(result, dict):
                        row = {**metadata, **result}
                        row['_source_file'] = json_file.name
                        all_rows.append(row)
                
                self._log(f"✓ {json_file.name}: {len(results)} row(s)")
            
            except Exception as e:
                self._log(f"✗ {json_file.name}: {str(e)}")
        
        # Build DataFrame
        if all_rows:
            self.full_df = pd.DataFrame(all_rows)
            self.display_df = self.full_df.copy()
            
            # Update metric combos
            self._update_metric_combos()
            
            # Display all rows by default
            display_limit = min(len(self.display_df), 50000)
            self.table_model.setDataFrame(self.display_df.head(display_limit))
            
            elapsed = (time.time() - start) * 1000
            self._update_status(f"Loaded {len(self.full_df)} rows", elapsed)
            self._log(f"\nTotal: {len(self.full_df)} rows loaded in {elapsed:.0f} ms")
        else:
            self._log("\nNo valid data loaded!")
            QMessageBox.warning(self, "Load Failed", "No valid JSON data found.")
    
    def _update_metric_combos(self):
        """Update metric combo boxes after loading data."""
        metrics = detect_metric_columns(self.full_df)
        
        all_metrics = []
        if metrics["higher"]:
            all_metrics.extend([f"{m} (↑)" for m in metrics["higher"]])
        if metrics["lower"]:
            all_metrics.extend([f"{m} (↓)" for m in metrics["lower"]])
        if metrics["other"]:
            all_metrics.extend(metrics["other"])
        
        # Clean metrics (remove direction indicators for actual use)
        clean_metrics = [m.split(' (')[0] for m in all_metrics]
        
        self.metric_combo.clear()
        self.metric_combo.addItems(all_metrics)
        
        self.topn_metric_combo.clear()
        self.topn_metric_combo.addItems(all_metrics)
        
        # Store clean metric list
        self._clean_metrics = clean_metrics
    
    def _add_layered_filter_row(self):
        """Add a new layered filter row."""
        if self.metric_combo.count() == 0:
            QMessageBox.warning(self, "No Metrics", "Load data first to add filters.")
            return
        
        row_layout = QHBoxLayout()
        
        # Metric combo
        metric_combo = QComboBox()
        metric_combo.addItems([self.metric_combo.itemText(i) for i in range(self.metric_combo.count())])
        row_layout.addWidget(metric_combo)
        
        # Operator combo
        op_combo = QComboBox()
        op_combo.addItems([">", ">=", "<", "<=", "==", "!="])
        row_layout.addWidget(op_combo)
        
        # Value input
        value_input = QLineEdit()
        value_input.setPlaceholderText("e.g., 1.5 or 8%")
        row_layout.addWidget(value_input)
        
        # Remove button
        remove_btn = QPushButton("✕")
        remove_btn.clicked.connect(lambda: self._remove_layered_filter_row(row_layout))
        row_layout.addWidget(remove_btn)
        
        self.filter_rows_container.addLayout(row_layout)
        self.filter_widgets.append((row_layout, metric_combo, op_combo, value_input, remove_btn))
    
    def _remove_layered_filter_row(self, row_layout):
        """Remove a layered filter row."""
        # Remove from widgets list
        self.filter_widgets = [w for w in self.filter_widgets if w[0] != row_layout]
        
        # Remove widgets
        while row_layout.count():
            item = row_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.filter_rows_container.removeItem(row_layout)
    
    def _apply_filters(self):
        """Apply filters, sort, and limit."""
        if self.full_df.empty:
            QMessageBox.warning(self, "No Data", "Load data first.")
            return
        
        start = time.time()
        
        try:
            # Start with full dataset
            result = self.full_df.copy()
            
            # Apply layered filters
            layered_filter_data = []
            for _, metric_combo, op_combo, value_input, _ in self.filter_widgets:
                metric = self._clean_metrics[metric_combo.currentIndex()]
                op = op_combo.currentText()
                value = value_input.text()
                if metric and value:
                    layered_filter_data.append((metric, op, value))
            
            if layered_filter_data:
                _, result = _apply_layered_filters(result, layered_filter_data)
            
            # Apply free-text filter, sort, limit
            filter_expr = self.filter_expr.text()
            sort_by = self.sort_by.text()
            limit = self.limit_spin.value()
            
            result = _apply_query_sort_limit(result, filter_expr, sort_by, limit)
            
            # Update display
            self.display_df = result
            display_limit = min(len(self.display_df), 50000)
            self.table_model.setDataFrame(self.display_df.head(display_limit))
            
            elapsed = (time.time() - start) * 1000
            self._update_status(f"{len(self.display_df)} rows", elapsed, display_limit)
            
        except Exception as e:
            QMessageBox.critical(self, "Filter Error", f"Error applying filters:\n{str(e)}")
    
    def _apply_topn(self):
        """Apply Top-N filtering by selected metric."""
        if self.full_df.empty:
            QMessageBox.warning(self, "No Data", "Load data first.")
            return
        
        n = self.topn_spin.value()
        if n == 0:
            QMessageBox.information(self, "Top-N OFF", "Set N > 0 to apply Top-N filtering.")
            return
        
        start = time.time()
        
        try:
            # Start with full dataset or apply filters first
            result = self.full_df.copy()
            
            # Apply layered filters first
            layered_filter_data = []
            for _, metric_combo, op_combo, value_input, _ in self.filter_widgets:
                metric = self._clean_metrics[metric_combo.currentIndex()]
                op = op_combo.currentText()
                value = value_input.text()
                if metric and value:
                    layered_filter_data.append((metric, op, value))
            
            if layered_filter_data:
                _, result = _apply_layered_filters(result, layered_filter_data)
            
            # Apply free-text filter
            filter_expr = self.filter_expr.text()
            if filter_expr and filter_expr.strip():
                normalized = _normalize_percent_tokens(filter_expr.strip())
                result = result.query(normalized, engine="python")
            
            # Get metric and direction
            metric = self._clean_metrics[self.topn_metric_combo.currentIndex()]
            desc = self.topn_direction.currentIndex() == 0  # 0=Desc, 1=Asc
            
            # Sort and take top N
            user_sort = self.sort_by.text()
            result = _build_sorted_df_for_topn(result, metric, desc, user_sort)
            result = result.head(n)
            
            # Apply limit if specified
            limit = self.limit_spin.value()
            if limit > 0:
                result = result.head(limit)
            
            # Update display
            self.display_df = result
            display_limit = min(len(self.display_df), 50000)
            self.table_model.setDataFrame(self.display_df.head(display_limit))
            
            elapsed = (time.time() - start) * 1000
            self._update_status(f"Top-{n}: {len(self.display_df)} rows", elapsed, display_limit)
            
        except Exception as e:
            QMessageBox.critical(self, "Top-N Error", f"Error applying Top-N:\n{str(e)}")
    
    def _reset_view(self):
        """Reset to show all loaded data."""
        if self.full_df.empty:
            return
        
        self.display_df = self.full_df.copy()
        display_limit = min(len(self.display_df), 50000)
        self.table_model.setDataFrame(self.display_df.head(display_limit))
        
        self._update_status(f"{len(self.display_df)} rows (ALL)", 0, display_limit)
    
    def _export_csv(self):
        """Export current filtered view to CSV."""
        if self.display_df.empty:
            QMessageBox.warning(self, "No Data", "No data to export.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "", "CSV Files (*.csv)"
        )
        if not file_path:
            return
        
        try:
            # Export full filtered dataset (not just displayed rows)
            self.display_df.to_csv(file_path, index=False, encoding='utf-8')
            QMessageBox.information(
                self, "Export Success", 
                f"Exported {len(self.display_df)} rows to:\n{file_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Error exporting CSV:\n{str(e)}")
    
    # ========================================================================
    # UI Helpers
    # ========================================================================
    
    def _update_status(self, msg: str, elapsed_ms: float, display_limit: int = None):
        """Update status bar."""
        if display_limit and display_limit < len(self.display_df):
            status = f"Rows: {msg} | Last op: {elapsed_ms:.0f} ms | Showing {display_limit:,} of {len(self.display_df):,}"
        else:
            status = f"Rows: {msg} | Last op: {elapsed_ms:.0f} ms"
        self.status_bar.showMessage(status)
    
    def _log(self, message: str):
        """Append message to inline log."""
        self.log_text.append(message)


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    app = QApplication(sys.argv)
    window = OptConsoleLiteWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

