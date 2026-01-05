#!/usr/bin/env python3
"""
Standalone PySide6 Query Results JSON Viewer
A simple, intuitive interface for filtering and sorting optimization results.
"""

import sys
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTableView, QStatusBar, QSplitter,
    QScrollArea, QLabel, QCheckBox, QComboBox, QLineEdit, QSpinBox,
    QTextEdit, QGroupBox, QMessageBox, QDialog, QDialogButtonBox,
    QRadioButton, QPlainTextEdit, QAbstractItemView
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QFont, QAction

import pandas as pd
import numpy as np

from scripts.build_ranges_from_selection import (
    build_ranges as build_ranges_from_selection,
    format_ranges_text,
)


def is_percent_candidate(col: str) -> bool:
    """Name-based heuristic: only these are percent candidates."""
    c = (col or "").lower()
    if c in {"win_rate", "max_drawdown"}:
        return True
    return c.endswith("_pct") or c.endswith("_percent")


def detect_percent_storage_mode(s: pd.Series) -> str:
    """Classify how a percent-like column is stored: 'fraction'|'percent'|'raw'."""
    s_num = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if s_num.empty:
        return "raw"
    q = s_num.quantile([0.05, 0.50, 0.95]).values
    q05, q50, q95 = q[0], q[1], q[2]
    # Fraction heuristic: values mostly in [0, 1.2]
    if q95 <= 1.2 and q05 >= 0:
        return "fraction"
    # Percent heuristic: values within [0, 100], median at least 1
    if 0 <= q05 and q95 <= 100 and q50 >= 1:
        return "percent"
    return "raw"


def parse_user_number(text: str, col: str, percent_mode_map: Dict[str, str]) -> Optional[float]:
    """Parse user input according to percent storage mode; no DataFrame mutation."""
    s = (text or "").strip()
    if not s:
        return None
    mode = percent_mode_map.get(col, "raw")
    is_percent_col = is_percent_candidate(col)
    typed_percent = False
    if s.endswith('%'):
        typed_percent = True
        s = s[:-1].strip()
    val = float(s)
    if not is_percent_col or mode == "raw":
        return val
    if mode == "fraction":
        # Stored 0..1 → convert user 60/60%/0.60 to 0.60
        if typed_percent or val > 1:
            return val / 100.0
        return val
    if mode == "percent":
        # Stored 0..100 → convert user 0.60 to 60
        if typed_percent or val >= 1:
            return val
        return val * 100.0
    return val


class PandasModel(QAbstractTableModel):
    """Table model for displaying pandas DataFrame."""
    
    def __init__(self, data: pd.DataFrame = None):
        super().__init__()
        self._data = data if data is not None else pd.DataFrame()
        self._percent_mode_map: Dict[str, str] = {}
    
    def set_percent_mode_map(self, mode_map: Dict[str, str]):
        """Provide column -> storage mode mapping for percent candidates."""
        self._percent_mode_map = mode_map or {}
    
    def update_data(self, data: pd.DataFrame):
        """Update the model with new data."""
        self.beginResetModel()
        self._data = data if data is not None else pd.DataFrame()
        self.endResetModel()
    
    def rowCount(self, parent=QModelIndex()):
        return len(self._data)
    
    def columnCount(self, parent=QModelIndex()):
        return len(self._data.columns)
    
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        
        if role == Qt.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]
            col_name = self._data.columns[index.column()]
            
            # Handle None/NaN
            if pd.isna(value):
                return ""
            
            # Percent/ration formatting based on detected storage mode
            mode = self._percent_mode_map.get(col_name, "raw")
            if mode in ("fraction", "percent") and isinstance(value, (int, float)):
                if pd.isna(value):
                    return ""
                if mode == "fraction":
                    return f"{value * 100:.2f}%"
                if mode == "percent":
                    return f"{value:.2f}%"
            
            # Format floats
            if isinstance(value, float):
                return f"{value:.4f}"
            
            return str(value)
        
        return None
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._data.columns[section])
            else:
                return str(section + 1)
        return None
    
    def sort(self, column: int, order):
        """Sort table by given column number."""
        if self._data.empty or column >= len(self._data.columns):
            return
        
        self.layoutAboutToBeChanged.emit()
        
        col_name = self._data.columns[column]
        ascending = (order == Qt.AscendingOrder)
        
        # Sort the dataframe
        self._data = self._data.sort_values(by=col_name, ascending=ascending)
        self._data.reset_index(drop=True, inplace=True)
        
        self.layoutChanged.emit()


class FilterWidget(QWidget):
    """Widget representing a single filter (checkbox, field name, operator, value inputs)."""
    
    def __init__(self, field_name: str, field_type: str, parent=None):
        super().__init__(parent)
        self.field_name = field_name
        self.field_type = field_type  # 'numeric' or 'categorical'
        
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 2, 5, 2)
        
        # Checkbox to enable/disable filter
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(False)
        layout.addWidget(self.checkbox)
        
        # Field name label
        label = QLabel(field_name)
        label.setMinimumWidth(150)
        layout.addWidget(label)
        
        if field_type == 'numeric':
            # Operator dropdown: ≤, =, ≥, ≠, ↔
            self.operator = QComboBox()
            self.operator.addItems(['≤', '=', '≥', '≠', '↔'])
            self.operator.currentTextChanged.connect(self._on_operator_changed)
            layout.addWidget(self.operator)
            
            # Value inputs
            self.value1 = QLineEdit()
            self.value1.setPlaceholderText("value")
            self.value1.setMaximumWidth(100)
            layout.addWidget(self.value1)
            
            self.value2 = QLineEdit()
            self.value2.setPlaceholderText("max")
            self.value2.setMaximumWidth(100)
            self.value2.setVisible(False)
            layout.addWidget(self.value2)
        else:
            # Categorical filter: = or !=
            self.operator = QComboBox()
            self.operator.addItems(['=', '!='])
            layout.addWidget(self.operator)
            
            self.value1 = QLineEdit()
            self.value1.setPlaceholderText("value")
            self.value1.setMaximumWidth(200)
            layout.addWidget(self.value1)
            
            self.value2 = None
        
        layout.addStretch()
        self.setLayout(layout)
    
    def _on_operator_changed(self, text):
        """Show/hide second value input for '↔' operator and update placeholders."""
        if self.value2:
            is_between = text == '↔'
            self.value2.setVisible(is_between)
            
            if is_between:
                self.value1.setPlaceholderText("min")
                self.value2.setPlaceholderText("max")
            else:
                self.value1.setPlaceholderText("value")
    
    def is_active(self) -> bool:
        """Check if this filter is enabled."""
        return self.checkbox.isChecked()
    
    def get_filter_spec(self) -> Optional[Dict[str, Any]]:
        """Get filter specification if active."""
        if not self.is_active():
            return None
        
        operator = self.operator.currentText()
        value1_text = self.value1.text().strip()
        
        if not value1_text:
            return None
        
        spec = {
            'field': self.field_name,
            'type': self.field_type,
            'operator': operator,
        }
        
        if self.field_type == 'numeric':
            # Note: actual parsing occurs in _on_apply_filters using percent mode map
            spec['value1_text'] = value1_text
            if operator == '↔':
                value2_text = self.value2.text().strip() if self.value2 else ""
                if not value2_text:
                    return None
                spec['value2_text'] = value2_text
        else:
            spec['value1'] = value1_text
        
        return spec


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Query Results JSON Viewer")
        self.setGeometry(100, 100, 1400, 800)
        
        # Data storage
        self.raw_data: pd.DataFrame = pd.DataFrame()
        self.filtered_data: pd.DataFrame = pd.DataFrame()
        self.loaded_folder: Optional[str] = None
        self.filter_widgets: List[FilterWidget] = []
        # Percent storage modes per column
        self.percent_mode_map: Dict[str, str] = {}
        # Drop nulls toggle (default ON)
        self.drop_nulls: bool = True
        # Column visibility state (name -> visible)
        self.column_visibility: Dict[str, bool] = {}
        # Temporary override to show hidden columns
        self.show_hidden_override: bool = False
        
        # Setup UI
        self._setup_ui()
        
        # Show welcome message
        self.log_area.append("Welcome! Click 'Load Folder' to begin.")
    
    def _setup_ui(self):
        """Initialize the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        
        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel: controls
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)
        
        # Right panel: table
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)
        
        # Set initial splitter sizes (30% left, 70% right)
        splitter.setSizes([400, 1000])
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        # Menu bar (Settings)
        self._build_menu()
    
    def _create_left_panel(self) -> QWidget:
        """Create the left control panel with resizable Filters and bottom area."""
        panel = QWidget()
        root_layout = QVBoxLayout(panel)
        
        # Top controls row
        top_controls = QHBoxLayout()
        self.load_button = QPushButton("Load Folder")
        self.load_button.clicked.connect(self._on_load_folder)
        top_controls.addWidget(self.load_button)
        self.load_files_button = QPushButton("Load Files")
        self.load_files_button.clicked.connect(self._on_load_files)
        top_controls.addWidget(self.load_files_button)
        # Drop nulls toggle
        self.drop_nulls_cb = QCheckBox("Drop null rows")
        self.drop_nulls_cb.setChecked(True)
        self.drop_nulls_cb.stateChanged.connect(lambda _: setattr(self, 'drop_nulls', self.drop_nulls_cb.isChecked()))
        top_controls.addWidget(self.drop_nulls_cb)
        # Toggle show hidden columns
        self.btn_toggle_hidden = QPushButton("Show Hidden Columns")
        self.btn_toggle_hidden.setCheckable(True)
        self.btn_toggle_hidden.setChecked(False)
        self.btn_toggle_hidden.clicked.connect(self._on_toggle_show_hidden)
        top_controls.addWidget(self.btn_toggle_hidden)
        top_controls.addStretch()
        
        # Put controls in a standalone widget to keep layout tidy
        controls_container = QWidget()
        controls_container.setLayout(top_controls)
        root_layout.addWidget(controls_container)
        
        # Vertical splitter for Filters vs bottom area (limit/actions/log)
        v_splitter = QSplitter(Qt.Vertical)
        
        # Top part: Filters section (scrollable)
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        filters_group = QGroupBox("Filters (AND combined)")
        filters_layout = QVBoxLayout()
        
        legend_frame = QGroupBox("Symbols:")
        legend_layout = QVBoxLayout()
        legend_text = QLabel(
            "≤ Less than or equal\n"
            "= Equal to\n"
            "≥ Greater than or equal\n"
            "≠ Not equal to\n"
            "↔ Between (Min–Max)"
        )
        legend_text.setStyleSheet("color: #666; font-size: 11px; margin: 2px;")
        legend_layout.addWidget(legend_text)
        legend_frame.setLayout(legend_layout)
        filters_layout.addWidget(legend_frame)
        
        self.filters_scroll = QScrollArea()
        self.filters_scroll.setWidgetResizable(True)
        self.filters_container = QWidget()
        self.filters_container_layout = QVBoxLayout(self.filters_container)
        self.filters_container_layout.addStretch()
        self.filters_scroll.setWidget(self.filters_container)
        
        filters_layout.addWidget(self.filters_scroll)
        filters_group.setLayout(filters_layout)
        top_layout.addWidget(filters_group)
        v_splitter.addWidget(top_widget)
        
        # Bottom part: limit/actions/export/log
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        
        limit_group = QGroupBox("Row Limiting")
        limit_layout = QVBoxLayout()
        limit_row = QHBoxLayout()
        limit_row.addWidget(QLabel("Top N:"))
        self.top_n = QSpinBox()
        self.top_n.setMinimum(0)
        self.top_n.setMaximum(50000)
        self.top_n.setValue(0)
        self.top_n.setSpecialValueText("All")
        limit_row.addWidget(self.top_n)
        limit_layout.addLayout(limit_row)
        info_label = QLabel("💡 Click column headers to sort, drag to reorder")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 11px; margin: 5px;")
        limit_layout.addWidget(info_label)
        limit_group.setLayout(limit_layout)
        bottom_layout.addWidget(limit_group)
        
        button_layout = QHBoxLayout()
        self.apply_button = QPushButton("Apply Filters")
        self.apply_button.clicked.connect(self._on_apply_filters)
        button_layout.addWidget(self.apply_button)
        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self._on_reset)
        button_layout.addWidget(self.reset_button)
        bottom_layout.addLayout(button_layout)
        
        # Row Actions Section
        row_actions_group = QGroupBox("Row Actions")
        row_actions_layout = QVBoxLayout()
        row_actions_info = QLabel("<small>Select a row in the table first:</small>")
        row_actions_layout.addWidget(row_actions_info)
        
        self.btn_set_baseline = QPushButton("Set as Optimizer Baseline")
        self.btn_set_baseline.clicked.connect(self._on_set_baseline)
        row_actions_layout.addWidget(self.btn_set_baseline)

        self.btn_set_test_ranges = QPushButton("Set as Parameter Test Values")
        self.btn_set_test_ranges.clicked.connect(self._on_set_test_ranges)
        row_actions_layout.addWidget(self.btn_set_test_ranges)
        
        self.btn_run_analysis = QPushButton("Run Analysis…")
        self.btn_run_analysis.clicked.connect(self._on_run_analysis)
        row_actions_layout.addWidget(self.btn_run_analysis)
        
        self.btn_backtest = QPushButton("Backtest this parameter set…")
        self.btn_backtest.clicked.connect(self._on_backtest_demand)
        row_actions_layout.addWidget(self.btn_backtest)
        
        self.btn_export_preset = QPushButton("Export preset…")
        self.btn_export_preset.clicked.connect(self._on_export_preset)
        row_actions_layout.addWidget(self.btn_export_preset)
        
        row_actions_group.setLayout(row_actions_layout)
        bottom_layout.addWidget(row_actions_group)
        
        self.export_button = QPushButton("Export CSV")
        self.export_button.clicked.connect(self._on_export_csv)
        bottom_layout.addWidget(self.export_button)
        
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout()
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        # Smaller default log height; resizable via splitter
        self.log_area.setMaximumHeight(100)
        font = QFont("Consolas", 8)
        self.log_area.setFont(font)
        log_layout.addWidget(self.log_area)
        log_group.setLayout(log_layout)
        bottom_layout.addWidget(log_group)
        
        v_splitter.addWidget(bottom_widget)
        v_splitter.setSizes([600, 200])

        scroll_host = QWidget()
        scroll_host_layout = QVBoxLayout(scroll_host)
        scroll_host_layout.setContentsMargins(0, 0, 0, 0)
        scroll_host_layout.setSpacing(0)
        scroll_host_layout.addWidget(v_splitter)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.NoFrame)
        left_scroll.setWidget(scroll_host)
        
        root_layout.addWidget(left_scroll)
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """Create the right table panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Table view
        self.table_view = QTableView()
        self.table_model = PandasModel()
        self.table_view.setModel(self.table_model)
        
        # Enable interactive sorting and column reordering
        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        header = self.table_view.horizontalHeader()
        header.setSectionsMovable(True)
        header.setSortIndicatorShown(True)
        
        layout.addWidget(self.table_view)
        
        return panel
    
    def _on_load_folder(self):
        """Load all JSON files from selected folder."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder with JSON Files",
            self.loaded_folder or ""
        )
        
        if not folder:
            return
        
        self.loaded_folder = folder
        self.log_area.clear()
        self.log_area.append(f"Loading JSON files from: {folder}\n")
        
        # Find all JSON files
        json_files = list(Path(folder).glob("*.json"))
        
        if not json_files:
            self.log_area.append("No JSON files found in folder.")
            QMessageBox.warning(self, "No Files", "No JSON files found in the selected folder.")
            return
        
        # Load and parse each file
        all_results = []
        loaded_count = 0
        skipped_count = 0
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Extract results array
                if isinstance(data, dict) and 'results' in data:
                    results = data['results']
                elif isinstance(data, list):
                    results = data
                else:
                    self.log_area.append(f"⚠ Skipped {json_file.name}: no 'results' field")
                    skipped_count += 1
                    continue
                
                # Add source file to each result and strip param_ prefix
                for result in results:
                    if isinstance(result, dict):
                        result['_source_file'] = json_file.name
                        # Strip param_ prefix from parameter columns
                        keys_to_rename = [k for k in result.keys() if k.startswith('param_')]
                        for old_key in keys_to_rename:
                            new_key = old_key[6:]  # Remove 'param_' prefix
                            result[new_key] = result.pop(old_key)
                        all_results.append(result)
                
                loaded_count += 1
                self.log_area.append(f"✓ Loaded {json_file.name}: {len(results)} results")
                
            except json.JSONDecodeError as e:
                self.log_area.append(f"✗ Skipped {json_file.name}: JSON decode error - {e}")
                skipped_count += 1
            except Exception as e:
                self.log_area.append(f"✗ Skipped {json_file.name}: {e}")
                skipped_count += 1
        
        # Convert to DataFrame
        if not all_results:
            self.log_area.append("\nNo valid results found.")
            QMessageBox.warning(self, "No Data", "No valid results found in JSON files.")
            return
        
        self.raw_data = pd.DataFrame(all_results)
        # Clean nulls/inf based on toggle
        self.raw_data = self._clean_df(self.raw_data, self.drop_nulls)
        # Detect percent storage mode map
        self.percent_mode_map = {}
        for col in self.raw_data.columns:
            if is_percent_candidate(col):
                self.percent_mode_map[col] = detect_percent_storage_mode(self.raw_data[col])
        # Reorder columns: UID then _source_file first
        cols = list(self.raw_data.columns)
        def _find_col(name):
            target = name.lower()
            for c in cols:
                if str(c).lower() == target:
                    return c
            return None
        uid_col = _find_col("uid")
        src_col = _find_col("_source_file")
        new_order = []
        if uid_col is not None:
            new_order.append(uid_col)
        if src_col is not None and src_col not in new_order:
            new_order.append(src_col)
        if new_order:
            remaining = [c for c in cols if c not in new_order]
            self.raw_data = self.raw_data.reindex(columns=new_order + remaining)
        # Initialize column visibility (default visible); prefer UID over trial_id if both exist
        self.column_visibility = {str(c): True for c in self.raw_data.columns}
        cols_lower = {str(c).lower() for c in self.raw_data.columns}
        if "uid" in cols_lower and "trial_id" in cols_lower:
            # Hide trial_id when uid is present
            for c in self.raw_data.columns:
                if str(c).lower() == "trial_id":
                    self.column_visibility[str(c)] = False
                    break
        
        # Limit to 50,000 rows for performance
        if len(self.raw_data) > 50000:
            self.log_area.append(f"\n⚠ Limiting to first 50,000 rows (total: {len(self.raw_data)})")
            self.raw_data = self.raw_data.head(50000)
        
        self.filtered_data = self.raw_data.copy()
        
        # Update UI
        self._create_filters()
        # Prefill defaults and apply once on load
        try:
            self._prefill_default_filters()
            self._on_apply_filters()
        except Exception as e:
            self.log_area.append(f"⚠ Failed to apply default filters: {e}")
            self._update_table()
        
        self.log_area.append(f"\n✓ Total rows loaded: {len(self.raw_data)}")
        self.log_area.append(f"✓ Files loaded: {loaded_count} | Skipped: {skipped_count}")
        
        truncation_msg = ""
        if len(self.raw_data) > 50000:
            truncation_msg = f" | Showing 50,000 of {len(self.raw_data)}"
        
        self.status_bar.showMessage(
            f"Rows: {len(self.filtered_data)} | Loaded from {loaded_count} files{truncation_msg}"
        )

    def _on_load_files(self):
        """Load selected JSON files via file dialog (multi-select)."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select JSON Files",
            self.loaded_folder or "",
            "JSON Files (*.json)"
        )
        if not files:
            return
        # Remember last directory
        try:
            self.loaded_folder = os.path.dirname(files[0]) or self.loaded_folder
        except Exception:
            pass
        self.log_area.clear()
        self.log_area.append(f"Loading selected files (n={len(files)})\n")
        all_results = []
        loaded_count = 0
        skipped_count = 0
        for fpath in files:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict) and 'results' in data:
                    results = data['results']
                elif isinstance(data, list):
                    results = data
                else:
                    self.log_area.append(f"⚠ Skipped {os.path.basename(fpath)}: no 'results' field")
                    skipped_count += 1
                    continue
                for result in results:
                    if isinstance(result, dict):
                        result['_source_file'] = os.path.basename(fpath)
                        all_results.append(result)
                loaded_count += 1
                self.log_area.append(f"✓ Loaded {os.path.basename(fpath)}: {len(results)} results")
            except json.JSONDecodeError as e:
                self.log_area.append(f"✗ Skipped {os.path.basename(fpath)}: JSON decode error - {e}")
                skipped_count += 1
            except Exception as e:
                self.log_area.append(f"✗ Skipped {os.path.basename(fpath)}: {e}")
                skipped_count += 1
        if not all_results:
            self.log_area.append("\nNo valid results found.")
            QMessageBox.warning(self, "No Data", "No valid results found in selected files.")
            return
        self.raw_data = pd.DataFrame(all_results)
        self.raw_data = self._clean_df(self.raw_data, self.drop_nulls)
        self.percent_mode_map = {}
        for col in self.raw_data.columns:
            if is_percent_candidate(col):
                self.percent_mode_map[col] = detect_percent_storage_mode(self.raw_data[col])
        # Reorder columns: UID then _source_file
        cols = list(self.raw_data.columns)
        def _find_col(name):
            target = name.lower()
            for c in cols:
                if str(c).lower() == target:
                    return c
            return None
        uid_col = _find_col("uid")
        src_col = _find_col("_source_file")
        new_order = []
        if uid_col is not None:
            new_order.append(uid_col)
        if src_col is not None and src_col not in new_order:
            new_order.append(src_col)
        if new_order:
            remaining = [c for c in cols if c not in new_order]
            self.raw_data = self.raw_data.reindex(columns=new_order + remaining)
        # Initialize/adjust column visibility as in folder load
        self.column_visibility = {str(c): True for c in self.raw_data.columns}
        cols_lower = {str(c).lower() for c in self.raw_data.columns}
        if "uid" in cols_lower and "trial_id" in cols_lower:
            for c in self.raw_data.columns:
                if str(c).lower() == "trial_id":
                    self.column_visibility[str(c)] = False
                    break
        # Truncate for UI performance
        if len(self.raw_data) > 50000:
            self.log_area.append(f"\n⚠ Limiting to first 50,000 rows (total: {len(self.raw_data)})")
            self.raw_data = self.raw_data.head(50000)
        self.filtered_data = self.raw_data.copy()
        self._create_filters()
        # Prefill defaults and apply once on load
        try:
            self._prefill_default_filters()
            self._on_apply_filters()
        except Exception as e:
            self.log_area.append(f"⚠ Failed to apply default filters: {e}")
            self._update_table()
        self.log_area.append(f"\n✓ Total rows loaded: {len(self.raw_data)}")
        self.log_area.append(f"✓ Files loaded: {loaded_count} | Skipped: {skipped_count}")
        truncation_msg = ""
        if len(self.raw_data) > 50000:
            truncation_msg = f" | Showing 50,000 of {len(self.raw_data)}"
        self.status_bar.showMessage(
            f"Rows: {len(self.filtered_data)} | Loaded selected files{truncation_msg}"
        )
    
    def _create_filters(self):
        """Auto-detect fields and create filter widgets."""
        # Clear existing filters
        for widget in self.filter_widgets:
            widget.deleteLater()
        self.filter_widgets.clear()
        
        # Remove stretch
        layout = self.filters_container_layout
        while layout.count() > 0:
            layout.takeAt(0)
        
        # Detect field types
        for col in self.raw_data.columns:
            if col == '_source_file':
                # Treat source file as categorical
                field_type = 'categorical'
            elif pd.api.types.is_numeric_dtype(self.raw_data[col]):
                field_type = 'numeric'
            else:
                field_type = 'categorical'
            
            widget = FilterWidget(col, field_type)
            self.filter_widgets.append(widget)
            layout.addWidget(widget)
        
        layout.addStretch()
    
    def _on_apply_filters(self):
        """Apply all active filters, sort, and limit results."""
        start_time = time.time()
        
        # Start with raw data (cleaned per current toggle)
        df = self._clean_df(self.raw_data.copy(), self.drop_nulls)
        
        # Collect active filters
        filter_specs = []
        for widget in self.filter_widgets:
            spec = widget.get_filter_spec()
            if spec:
                filter_specs.append(spec)
        
        # Apply filters (AND combination)
        for spec in filter_specs:
            field = spec['field']
            operator = spec['operator']
            
            if spec['type'] == 'numeric':
                # Parse values according to detected percent storage mode
                try:
                    value1 = parse_user_number(spec['value1_text'], field, self.percent_mode_map)
                except Exception:
                    continue
                
                if operator == '≤':
                    df = df[df[field] <= value1]
                elif operator == '=':
                    df = df[df[field] == value1]
                elif operator == '≥':
                    df = df[df[field] >= value1]
                elif operator == '≠':
                    df = df[df[field] != value1]
                elif operator == '↔':
                    try:
                        value2 = parse_user_number(spec.get('value2_text', ''), field, self.percent_mode_map)
                    except Exception:
                        continue
                    if value1 is None or value2 is None:
                        continue
                    if value1 > value2:
                        continue
                    df = df[(df[field] >= value1) & (df[field] <= value2)]
            else:
                # Categorical
                value1 = spec['value1']
                if operator == '=':
                    df = df[df[field].astype(str) == value1]
                elif operator == '!=':
                    df = df[df[field].astype(str) != value1]
        
        # Track total after filtering but before Top N
        total_after_filtering = len(df)
        
        # Apply top N limit (sorting is now handled by table headers)
        top_n = self.top_n.value()
        if top_n > 0:
            df = df.head(top_n)
        
        self.filtered_data = df
        self._update_table()
        
        elapsed_time = time.time() - start_time
        
        active_count = len(filter_specs)
        # Show truncation info if Top N applied and data was truncated
        truncation_info = ""
        if top_n > 0 and len(self.filtered_data) < total_after_filtering:
            truncation_info = f" | Showing {len(self.filtered_data)} of {total_after_filtering}"
        
        self.status_bar.showMessage(
            f"Rows: {len(self.filtered_data)} | "
            f"Filters: {active_count} | "
            f"Last op: {elapsed_time * 1000:.0f}ms{truncation_info}"
        )
        
        self.log_area.append(
            f"\nApplied {active_count} filter(s) → {len(self.filtered_data)} rows "
            f"({elapsed_time:.3f}s)"
        )

    def _prefill_default_filters(self):
        """Prefill default filters and enable them.
        Defaults:
          - calmar_ratio between 0.01 and 0.10 (fractions)
          - total_trades ≥ 100
          - max_drawdown between 1.5% and 4.2%
        """
        # Helper to find widget by case-insensitive column name
        def find_widget(col_name: str) -> Optional[FilterWidget]:
            for w in self.filter_widgets:
                if str(w.field_name).lower() == col_name.lower():
                    return w
            return None

        # calmar_ratio between 0.01 and 0.10
        w = find_widget('calmar_ratio')
        if w and w.field_type == 'numeric':
            w.checkbox.setChecked(True)
            w.operator.setCurrentText('↔')
            # Values are fractions in data
            w.value1.setText('0.01')
            w.value2.setText('0.10')

        # total_trades ≥ 100
        w = find_widget('total_trades')
        if w and w.field_type == 'numeric':
            w.checkbox.setChecked(True)
            w.operator.setCurrentText('≥')
            w.value1.setText('100')

        # max_drawdown between 1.5% and 4.2%
        # Data may be stored as percent or fraction; parse_user_number handles it.
        w = find_widget('max_drawdown')
        if w and w.field_type == 'numeric':
            w.checkbox.setChecked(True)
            w.operator.setCurrentText('↔')
            w.value1.setText('1.5%')
            w.value2.setText('4.2%')
    
    def _on_reset(self):
        """Reset all filters and show full data."""
        # Uncheck all filters
        for widget in self.filter_widgets:
            widget.checkbox.setChecked(False)
            widget.value1.clear()
            if widget.value2:
                widget.value2.clear()
        
        # Reset Top N and clear any table sorting
        self.top_n.setValue(0)
        self.table_view.sortByColumn(-1, Qt.AscendingOrder)  # Clear sorting
        
        # Reset data
        self.filtered_data = self.raw_data.copy()
        self._update_table()
        
        self.status_bar.showMessage(f"Rows: {len(self.filtered_data)} | Reset to full data")
        self.log_area.append("\nReset: showing all rows")
    
    def _on_export_preset(self):
        """Export selected row's parameters as a preset JSON file."""
        selected_indexes = self.table_view.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(self, "No Selection", "Please select a row first.")
            return
        
        row_index = selected_indexes[0].row()
        
        if self.filtered_data is None or self.filtered_data.empty or row_index >= len(self.filtered_data):
            QMessageBox.warning(self, "Invalid Selection", "No valid row selected.")
            return
        
        row_data = self.filtered_data.iloc[row_index].to_dict()
        
        # Extract parameters and metadata
        params = {}
        meta_fields = {}
        
        skip_cols = {'_source_file', 'fold_id', 'bars_total', 'bars_train', 'bars_embargo', 
                   'bars_val', 'val_start', 'val_end', 'total_return', 'sharpe_ratio', 
                   'sortino_ratio', 'calmar_ratio', 'max_drawdown', 'win_rate', 
                   'total_trades', 'profit_factor', 'expectancy', 'start_capital', 
                   'end_capital', 'avg_hold_hours', 'ulcer_index', 'omega_0', 'omega_fees',
                   'chart', 'trial_id', 'method', 'trial_uid', 'uid', 'score', 'is_pareto',
                   'stability_score', 'group_rank'}
        
        for col, val in row_data.items():
            if col in {'chart', 'fold_id', '_source_file', 'total_return', 
                      'sharpe_ratio', 'sortino_ratio', 'calmar_ratio', 'max_drawdown',
                      'win_rate', 'total_trades', 'profit_factor', 'trial_uid', 'uid'}:
                if not pd.isna(val):
                    meta_fields[col] = val
            elif col not in skip_cols:
                if not pd.isna(val):
                    params[col] = val
        
        if not params:
            QMessageBox.warning(self, "No Parameters", "No parameter columns found in selected row.")
            return
        
        # Build preset JSON
        preset = {
            'meta': {
                'exported_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'trial_uid': meta_fields.get('trial_uid', meta_fields.get('uid', 'unknown')),
                'source_file': meta_fields.get('_source_file', 'unknown'),
                'chart': meta_fields.get('chart', 'N/A'),
                'fold_id': meta_fields.get('fold_id', 'N/A'),
            },
            'performance': {
                'total_return': meta_fields.get('total_return', 0),
                'sharpe_ratio': meta_fields.get('sharpe_ratio', 0),
                'sortino_ratio': meta_fields.get('sortino_ratio', 0),
                'calmar_ratio': meta_fields.get('calmar_ratio', 0),
                'max_drawdown': meta_fields.get('max_drawdown', 0),
                'win_rate': meta_fields.get('win_rate', 0),
                'total_trades': meta_fields.get('total_trades', 0),
                'profit_factor': meta_fields.get('profit_factor', 0),
            },
            'parameters': params,
        }
        
        # Generate default filename
        trial_uid = preset['meta']['trial_uid']
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        default_name = f"preset_{trial_uid}_{timestamp}.json"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Preset", default_name,
            "JSON Files (*.json);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(preset, f, indent=2)
            
            self.log_area.append(f"\n✓ Exported preset to: {file_path}")
            QMessageBox.information(
                self, "Export Successful",
                f"Preset exported successfully:\n{file_path}\n\n"
                f"Parameters: {len(params)}\n"
                f"Trial UID: {trial_uid}"
            )
        except Exception as e:
            self.log_area.append(f"\n✗ Export preset failed: {e}")
            QMessageBox.critical(self, "Export Failed", f"Failed to export preset:\n{e}")
    
    def _on_export_csv(self):
        """Export current filtered/sorted data to CSV."""
        if self.filtered_data.empty:
            QMessageBox.warning(self, "No Data", "No data to export.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export CSV",
            "filtered_results.csv",
            "CSV Files (*.csv)"
        )
        
        if not file_path:
            return
        
        try:
            self.filtered_data.to_csv(file_path, index=False, encoding='utf-8')
            self.log_area.append(f"\n✓ Exported {len(self.filtered_data)} rows to: {file_path}")
            QMessageBox.information(
                self,
                "Export Successful",
                f"Exported {len(self.filtered_data)} rows to:\n{file_path}"
            )
        except Exception as e:
            self.log_area.append(f"\n✗ Export failed: {e}")
            QMessageBox.critical(self, "Export Failed", f"Failed to export CSV:\n{e}")
    
    def _update_table(self):
        """Update the table view with current filtered data."""
        self.table_model.set_percent_mode_map(self.percent_mode_map)
        self.table_model.update_data(self.filtered_data)
        self.table_view.resizeColumnsToContents()
        self._apply_column_visibility()

    def _apply_column_visibility(self):
        """Apply column visibility settings to the table view."""
        if self.filtered_data is None or self.filtered_data.empty:
            return
        show_all = self.show_hidden_override
        # Map: column name -> index
        name_to_index = {str(name): idx for idx, name in enumerate(self.filtered_data.columns)}
        for name, idx in name_to_index.items():
            visible = self.column_visibility.get(name, True)
            self.table_view.setColumnHidden(idx, False if show_all else (not visible))

    def _resolve_strategy_params_path(self) -> Optional[str]:
        """Resolve path to config/strategy_params_v2.py based on loaded folder."""
        if not self.loaded_folder:
            QMessageBox.critical(self, "Error", "No data folder loaded. Cannot determine project path.")
            return None
        search_root = Path(self.loaded_folder).resolve()
        for candidate_root in (search_root, *search_root.parents):
            candidate = candidate_root / "config" / "strategy_params_v2.py"
            if candidate.exists():
                return str(candidate)
        QMessageBox.critical(
            self,
            "File Not Found",
            "Could not locate config/strategy_params_v2.py starting from:\n"
            f"{search_root}\n\n"
            "Verify the folder structure or load data from a project run folder."
        )
        return None

    @staticmethod
    def _to_python_scalar(value: Any) -> Any:
        """Convert numpy/pandas scalar types to native Python equivalents."""
        if isinstance(value, np.generic):
            try:
                return value.item()
            except Exception:
                return value
        return value

    def _collect_selected_rows(self) -> List[Dict[str, Any]]:
        """Return DataFrame rows (as dicts) for the current table selection."""
        if self.filtered_data is None or self.filtered_data.empty:
            return []
        selection_model = self.table_view.selectionModel()
        if selection_model is None:
            return []
        rows: List[Dict[str, Any]] = []
        for model_index in selection_model.selectedRows():
            row_idx = model_index.row()
            if row_idx < 0 or row_idx >= len(self.filtered_data):
                continue
            row_series = self.filtered_data.iloc[row_idx]
            row_dict: Dict[str, Any] = {}
            for col, val in row_series.items():
                coerced = self._to_python_scalar(val)
                if isinstance(coerced, float) and pd.isna(coerced):
                    coerced = None
                row_dict[col] = coerced
            rows.append(row_dict)
        return rows

    def _build_menu(self):
        """Build the Settings menu with column visibility."""
        menubar = self.menuBar()
        settings_menu = menubar.addMenu("Settings")
        act_columns = QAction("Column Visibility…", self)
        act_columns.triggered.connect(self._open_column_visibility_dialog)
        settings_menu.addAction(act_columns)

    def _open_column_visibility_dialog(self):
        """Open a simple dialog to choose visible columns."""
        if self.filtered_data is None or self.filtered_data.empty:
            QMessageBox.information(self, "No Data", "Load data to configure columns.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Column Visibility")
        v = QVBoxLayout(dlg)
        # Build checkbox list
        checkboxes = []
        for col in self.filtered_data.columns:
            name = str(col)
            cb = QCheckBox(name)
            cb.setChecked(self.column_visibility.get(name, True))
            v.addWidget(cb)
            checkboxes.append((name, cb))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        v.addWidget(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        if dlg.exec() == QDialog.Accepted:
            # Update visibility map
            for name, cb in checkboxes:
                self.column_visibility[name] = cb.isChecked()
            # Turning off override when user edits settings
            if self.show_hidden_override:
                self.show_hidden_override = False
                self.btn_toggle_hidden.setChecked(False)
                self.btn_toggle_hidden.setText("Show Hidden Columns")
            self._apply_column_visibility()

    def _on_toggle_show_hidden(self):
        """Toggle showing all columns regardless of visibility settings."""
        self.show_hidden_override = self.btn_toggle_hidden.isChecked()
        self.btn_toggle_hidden.setText("Hide Hidden Columns" if self.show_hidden_override else "Show Hidden Columns")
        self._apply_column_visibility()

    def _clean_df(self, df: pd.DataFrame, drop_nulls: bool = True) -> pd.DataFrame:
        """Replace inf with NaN and (optionally) drop null rows across numeric columns."""
        if df.empty:
            return df
        df = df.replace([np.inf, -np.inf], np.nan)
        if not drop_nulls:
            return df
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if numeric_cols:
            df = df.dropna(how="all", subset=numeric_cols)
        else:
            df = df.dropna(how="all")
        return df

    def _on_set_baseline(self):
        """Set selected row's parameters as optimizer baseline."""
        selected_indexes = self.table_view.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(self, "No Selection", "Please select a row first.")
            return
        
        row_index = selected_indexes[0].row()
        
        if self.filtered_data is None or self.filtered_data.empty or row_index >= len(self.filtered_data):
            QMessageBox.warning(self, "Invalid Selection", "No valid row selected.")
            return
        
        row_data = self.filtered_data.iloc[row_index].to_dict()
        
        # Extract all parameter columns (no longer have param_ prefix)
        params = {}
        meta_fields = {}
        
        skip_cols = {'_source_file', 'fold_id', 'bars_total', 'bars_train', 'bars_embargo', 
                   'bars_val', 'val_start', 'val_end', 'total_return', 'sharpe_ratio', 
                   'sortino_ratio', 'calmar_ratio', 'max_drawdown', 'win_rate', 
                   'total_trades', 'profit_factor', 'expectancy', 'start_capital', 
                   'end_capital', 'avg_hold_hours', 'ulcer_index', 'omega_0', 'omega_fees',
                   'chart', 'trial_id', 'method', 'trial_uid', 'score', 'is_pareto',
                   'stability_score', 'group_rank', 'uid'}
        
        for col, val in row_data.items():
            if col in skip_cols:
                # Store key metadata
                if col in {'chart', 'fold_id', '_source_file', 'total_return', 
                          'sharpe_ratio', 'calmar_ratio', 'max_drawdown'}:
                    meta_fields[col] = val
                continue
            
            # Assume everything else is a parameter
            if not pd.isna(val):
                params[col] = val
        
        if not params:
            QMessageBox.warning(self, "No Parameters", "No parameter columns found in selected row.")
            return
        
        # Confirm with user
        msg = f"Set {len(params)} parameters as optimizer baseline?\n\n"
        msg += f"Chart: {meta_fields.get('chart', 'N/A')}\n"
        msg += f"Fold: {meta_fields.get('fold_id', 'N/A')}\n"
        msg += f"Calmar: {meta_fields.get('calmar_ratio', 'N/A')}\n"
        msg += f"\nThis will overwrite DEFAULT_PARAMS in strategy_params_v2.py\n"
        msg += f"(TEST_RANGES will remain unchanged)"
        
        reply = QMessageBox.question(
            self, "Confirm Set Baseline", msg,
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        target_path = self._resolve_strategy_params_path()
        if not target_path:
            return
        
        try:
            import shutil
            import re
            
            # Create timestamped backup
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            backup_path = f"{target_path}.backup_{timestamp}"
            shutil.copy2(target_path, backup_path)
            
            # Read existing file
            with open(target_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Generate new DEFAULT_PARAMS dict
            param_lines = ["DEFAULT_PARAMS: Dict[str, Union[float, int, bool]] = {"]
            param_lines.append(f"    # Generated from query interface on {time.strftime('%Y-%m-%d %H:%M:%S')}")
            param_lines.append(f"    # Source: {meta_fields.get('_source_file', 'unknown')}")
            param_lines.append(f"    # Chart: {meta_fields.get('chart', 'N/A')}, Fold: {meta_fields.get('fold_id', 'N/A')}")
            calmar_val = meta_fields.get('calmar_ratio', 0)
            sharpe_val = meta_fields.get('sharpe_ratio', 0)
            mdd_val = meta_fields.get('max_drawdown', 0)
            param_lines.append(f"    # Performance: Calmar={calmar_val:.4f}, Sharpe={sharpe_val:.4f}, MDD={mdd_val:.2f}%")
            
            for key, val in sorted(params.items()):
                if isinstance(val, bool):
                    param_lines.append(f"    \"{key}\": {val},")
                elif isinstance(val, (int, float)):
                    param_lines.append(f"    \"{key}\": {val},")
                elif isinstance(val, str):
                    param_lines.append(f"    \"{key}\": \"{val}\",")
                else:
                    param_lines.append(f"    \"{key}\": {repr(val)},")
            
            param_lines.append("}")
            new_baseline_block = "\n".join(param_lines)
            
            # Replace DEFAULT_PARAMS block using regex
            pattern = r'DEFAULT_PARAMS:\s*Dict\[.*?\]\s*=\s*\{[^}]*\}'
            
            if not re.search(pattern, content, re.DOTALL):
                QMessageBox.critical(self, "Parse Error", "Could not find DEFAULT_PARAMS block in file.")
                return
            
            new_content = re.sub(pattern, new_baseline_block, content, count=1, flags=re.DOTALL)
            
            # Write updated file
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            QMessageBox.information(
                self, "Success",
                f"Baseline parameters updated!\n\n"
                f"File: {os.path.basename(target_path)}\n"
                f"Backup: {os.path.basename(backup_path)}\n"
                f"Parameters set: {len(params)}"
            )
            
        except Exception as exc:
            QMessageBox.critical(self, "Set Baseline Failed", str(exc))

    def _on_set_test_ranges(self):
        """Set selected rows as TEST_RANGES in strategy_params_v2.py."""
        selected_rows = self._collect_selected_rows()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Select one or more rows first.")
            return

        try:
            ranges = build_ranges_from_selection(selected_rows)
        except Exception as exc:
            QMessageBox.critical(self, "Range Builder Error", f"Failed to build ranges:\n{exc}")
            return

        for key, values in list(ranges.items()):
            ranges[key] = [self._to_python_scalar(v) for v in values]

        if not ranges:
            QMessageBox.warning(self, "No Parameters", "No parameter-like columns were found in the selected rows.")
            return

        preview_lines: List[str] = []
        for idx, key in enumerate(sorted(ranges.keys())):
            vals = ranges[key]
            preview = ", ".join(str(v) for v in vals[:5])
            if len(vals) > 5:
                preview += ", …"
            preview_lines.append(f"{key}: {len(vals)} value(s) [{preview}]")
            if idx >= 7:
                break
        preview_text = "\n".join(preview_lines)
        msg = (
            f"Update TEST_RANGES with {len(ranges)} parameter(s) built from "
            f"{len(selected_rows)} selected row(s)?\n\n"
            "This will overwrite the existing TEST_RANGES block and create a timestamped backup.\n\n"
            f"Preview:\n{preview_text}"
        )

        reply = QMessageBox.question(
            self,
            "Confirm TEST_RANGES Update",
            msg,
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        target_path = self._resolve_strategy_params_path()
        if not target_path:
            return

        try:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            header_comment = (
                f"    # Generated via Query GUI on {time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"from {len(selected_rows)} selected row(s)"
            )
            block_text = format_ranges_text(ranges)
            block_lines = block_text.splitlines()
            if len(block_lines) > 1:
                block_lines.insert(1, header_comment)
                block_text = "\n".join(block_lines)

            with open(target_path, 'r', encoding='utf-8') as f:
                content = f.read()

            pattern = r"TEST_RANGES:\s*Dict\[.*?\]\s*=\s*\{[\s\S]*?\}"
            if not re.search(pattern, content, re.DOTALL):
                QMessageBox.critical(self, "Parse Error", "Could not locate TEST_RANGES block in strategy_params_v2.py.")
                return

            backup_path = f"{target_path}.backup_{timestamp}"
            shutil.copy2(target_path, backup_path)
            new_content = re.sub(pattern, block_text, content, count=1, flags=re.DOTALL)

            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            self.log_area.append(
                f"\n✓ Updated TEST_RANGES with {len(ranges)} parameter(s) "
                f"from {len(selected_rows)} row(s). Backup: {os.path.basename(backup_path)}"
            )
            QMessageBox.information(
                self,
                "TEST_RANGES Updated",
                f"Successfully updated TEST_RANGES ({len(ranges)} parameters).\n"
                f"Backup created: {os.path.basename(backup_path)}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Update Failed", f"Failed to update TEST_RANGES:\n{exc}")

    def _on_run_analysis(self):
        """Run performance analysis for selected row."""
        selected_indexes = self.table_view.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(self, "No Selection", "Please select a row first.")
            return
        
        row_index = selected_indexes[0].row()
        
        if self.filtered_data is None or self.filtered_data.empty or row_index >= len(self.filtered_data):
            QMessageBox.warning(self, "Invalid Selection", "No valid row selected.")
            return
        
        row_data = self.filtered_data.iloc[row_index].to_dict()
        
        # Show scope selection dialog
        dialog = AnalysisScopeDialog(row_data, self)
        if dialog.exec() != QDialog.Accepted:
            return
        
        scope = dialog.get_scope()
        format_type = dialog.get_format()
        
        # Find matching rows based on scope
        if scope == "fold_only":
            matching_rows = [row_data]
        elif scope == "all_folds":
            matching_rows = self._find_matching_params(row_data, same_chart=True)
        elif scope == "all_charts":
            matching_rows = self._find_matching_params(row_data, same_chart=False)
        else:
            matching_rows = [row_data]
        
        if not matching_rows:
            QMessageBox.warning(self, "No Data", "No matching rows found.")
            return
        
        # Generate report
        report_text = self._generate_performance_report(matching_rows, scope, format_type, row_data)
        
        # Show report dialog
        report_dialog = AnalysisReportDialog(report_text, row_data, self)
        report_dialog.exec()
    
    def _find_matching_params(self, row_data: dict, same_chart: bool) -> list:
        """Find rows with matching parameter values."""
        if self.filtered_data is None or self.filtered_data.empty:
            return []
        
        # Extract parameter columns from row_data
        skip_cols = {'_source_file', 'fold_id', 'bars_total', 'bars_train', 'bars_embargo', 
                   'bars_val', 'val_start', 'val_end', 'total_return', 'sharpe_ratio', 
                   'sortino_ratio', 'calmar_ratio', 'max_drawdown', 'win_rate', 
                   'total_trades', 'profit_factor', 'expectancy', 'start_capital', 
                   'end_capital', 'avg_hold_hours', 'ulcer_index', 'omega_0', 'omega_fees',
                   'chart', 'trial_id', 'method', 'trial_uid', 'score', 'is_pareto',
                   'stability_score', 'group_rank', 'uid'}
        
        param_cols = [col for col in row_data.keys() if col not in skip_cols and col in self.filtered_data.columns]
        
        if not param_cols:
            return [row_data]
        
        # Build filter condition with proper index alignment
        mask = pd.Series([True] * len(self.filtered_data), index=self.filtered_data.index)
        
        for col in param_cols:
            val = row_data.get(col)
            if pd.isna(val):
                mask &= self.filtered_data[col].isna()
            else:
                # Handle floating point comparison with tolerance
                if isinstance(val, float):
                    mask &= (self.filtered_data[col] - val).abs() < 1e-9
                else:
                    mask &= self.filtered_data[col] == val
        
        if same_chart and 'chart' in self.filtered_data.columns:
            chart_val = row_data.get('chart')
            if chart_val:
                mask &= self.filtered_data['chart'] == chart_val
        
        matching_df = self.filtered_data[mask]
        return matching_df.to_dict('records')
    
    def _on_backtest_demand(self):
        """Run on-demand backtest for selected row."""
        selected_indexes = self.table_view.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(self, "No Selection", "Please select a row first.")
            return
        
        row_index = selected_indexes[0].row()
        
        if self.filtered_data is None or self.filtered_data.empty or row_index >= len(self.filtered_data):
            QMessageBox.warning(self, "Invalid Selection", "No valid row selected.")
            return
        
        row_data = self.filtered_data.iloc[row_index].to_dict()
        
        # Show backtest config dialog
        dialog = BacktestConfigDialog(row_data, self)
        if dialog.exec() != QDialog.Accepted:
            return
        
        config = dialog.get_config()
        
        # Get trial UID
        trial_uid = row_data.get('trial_uid', row_data.get('uid', None))
        if not trial_uid:
            QMessageBox.critical(self, "Error", "No trial UID found in selected row.")
            return
        
        # Determine path to backtest CLI script
        if not self.loaded_folder:
            QMessageBox.critical(self, "Error", "No data folder loaded. Cannot determine project path.")
            return
        
        # From outputs/runs, go up two levels to project root, then into scripts/
        script_path = os.path.join(
            self.loaded_folder, "..", "..", "scripts", "run_regime_analysis.py"
        )
        script_path = os.path.normpath(os.path.abspath(script_path))
        
        if not os.path.exists(script_path):
            QMessageBox.critical(self, "Script Not Found", f"Could not locate:\n{script_path}")
            return
        
        # Build command
        import subprocess
        import sys as sys_module
        
        python_exe = sys_module.executable
        cmd = [
            python_exe,
            script_path,
            "--uid", str(trial_uid),
            "--capital", str(config['capital']),
            "--fees", str(config['fees']),
            "--max-positions", str(config['max_positions']),
        ]
        
        # Show progress message
        self.log_area.append(f"\n🔬 Running regime analysis for {trial_uid}...")
        self.log_area.append(f"   Chart: {row_data.get('chart', 'N/A')}")
        self.log_area.append(f"   Capital: ${config['capital']:,.2f}")
        self.log_area.append(f"   Fees: {config['fees']*100:.2f}%")
        self.log_area.append(f"   Max Positions: {config['max_positions']}")
        QApplication.processEvents()  # Update UI
        
        try:
            # Run backtest CLI
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else "Unknown error"
                self.log_area.append(f"✗ Regime analysis failed: {error_msg}")
                # Also log stdout in case error was printed there
                if result.stdout:
                    self.log_area.append(f"   Output: {result.stdout[:200]}...")
                QMessageBox.critical(self, "Analysis Failed", f"Error:\n{error_msg}\n\nOutput: {result.stdout[:500] if result.stdout else 'No output'}")
                return
            
            # Parse JSON output
            analysis_data = json.loads(result.stdout)
            
            if not analysis_data.get('success', False):
                error_msg = analysis_data.get('error', 'Unknown error')
                self.log_area.append(f"✗ Regime analysis failed: {error_msg}")
                QMessageBox.critical(self, "Analysis Failed", f"Error:\n{error_msg}")
                return
            
            # Get report text from analysis output
            report_text = analysis_data.get('report_text', 'No report generated')
            
            # Show report dialog
            report_dialog = AnalysisReportDialog(report_text, row_data, self)
            report_dialog.setWindowTitle("Regime Performance Analysis")
            report_dialog.exec()
            
            self.log_area.append("✓ Regime analysis completed successfully")
            
            # Log regime breakdown summary
            if analysis_data.get('chart_analysis_available'):
                regime_breakdown = analysis_data.get('regime_breakdown', {})
                self.log_area.append(f"   Regimes analyzed: {len(regime_breakdown)}")
            else:
                self.log_area.append("   ⚠ Chart analysis not available - trades not tagged by regime")
            
        except subprocess.TimeoutExpired:
            self.log_area.append("✗ Regime analysis timed out (>5 minutes)")
            QMessageBox.critical(self, "Timeout", "Analysis took too long and was cancelled.")
        except json.JSONDecodeError as e:
            self.log_area.append(f"✗ Failed to parse analysis output: {e}")
            QMessageBox.critical(self, "Parse Error", f"Failed to parse analysis output:\n{e}")
        except Exception as e:
            self.log_area.append(f"✗ Regime analysis error: {e}")
            QMessageBox.critical(self, "Error", f"Analysis error:\n{e}")
    
    def _generate_performance_report(self, rows: list, scope: str, format_type: str, selected_row: dict) -> str:
        """Generate performance analysis report."""
        lines = []
        
        if format_type == "structured":
            lines.append("="*70)
            lines.append("PERFORMANCE ANALYSIS REPORT")
            lines.append("="*70)
            lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"Scope: {scope.replace('_', ' ').title()}")
            lines.append(f"Rows analyzed: {len(rows)}")
            lines.append("")
        else:
            lines.append(f"Performance Analysis Report - {time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"Scope: {scope}, Rows: {len(rows)}")
            lines.append("")
        
        # Executive Summary
        if len(rows) > 1:
            metrics = ['total_return', 'sharpe_ratio', 'calmar_ratio', 'max_drawdown', 'total_trades']
            
            if format_type == "structured":
                lines.append("-" * 70)
                lines.append("EXECUTIVE SUMMARY")
                lines.append("-" * 70)
            else:
                lines.append("Summary:")
            
            for metric in metrics:
                vals = [r.get(metric) for r in rows if not pd.isna(r.get(metric))]
                if vals:
                    mean_val = np.mean(vals)
                    std_val = np.std(vals)
                    min_val = np.min(vals)
                    max_val = np.max(vals)
                    lines.append(f"  {metric}: mean={mean_val:.4f}, std={std_val:.4f}, min={min_val:.4f}, max={max_val:.4f}")
            
            lines.append("")
        
        # Fold/Chart Breakdown
        if format_type == "structured":
            lines.append("-" * 70)
            lines.append("DETAILED BREAKDOWN")
            lines.append("-" * 70)
        else:
            lines.append("Details:")
        
        for i, row in enumerate(rows, 1):
            chart = row.get('chart', 'N/A')
            fold = row.get('fold_id', 'N/A')
            
            lines.append(f"\n[{i}] Chart: {chart}, Fold: {fold}")
            lines.append(f"    Total Return: {row.get('total_return', 0):.2f}%")
            lines.append(f"    Sharpe: {row.get('sharpe_ratio', 0):.4f}")
            lines.append(f"    Calmar: {row.get('calmar_ratio', 0):.4f}")
            lines.append(f"    Max Drawdown: {row.get('max_drawdown', 0):.2f}%")
            lines.append(f"    Total Trades: {int(row.get('total_trades', 0))}")
            lines.append(f"    Win Rate: {row.get('win_rate', 0):.2f}%")
            
            if 'val_start' in row and 'val_end' in row:
                lines.append(f"    Val Period: {row.get('val_start')} to {row.get('val_end')}")
            
            if 'bars_train' in row:
                lines.append(f"    Bars: train={int(row.get('bars_train', 0))}, embargo={int(row.get('bars_embargo', 0))}, val={int(row.get('bars_val', 0))}")
        
        lines.append("")
        
        # Chart Analysis Integration
        chart_name = selected_row.get('chart', '')
        if chart_name and self.loaded_folder:
            if format_type == "structured":
                lines.append("-" * 70)
                lines.append("CHART ENVIRONMENT ANALYSIS")
                lines.append("-" * 70)
            else:
                lines.append("\nChart Environment:")
            
            # Try to load chart analysis
            analysis_found = False
            analyses_dir = os.path.join(self.loaded_folder, "..", "analyses")
            analyses_dir = os.path.normpath(os.path.abspath(analyses_dir))
            
            if os.path.exists(analyses_dir):
                # Look for analysis file with fixed name (no timestamp)
                base_name = os.path.splitext(chart_name)[0]
                analysis_file = os.path.join(analyses_dir, f"{base_name}.json")
                
                # Note: internal debug logs go to self.log_area, not the report
                
                if os.path.exists(analysis_file):
                    try:
                        with open(analysis_file, 'r', encoding='utf-8') as f:
                            analysis_data = json.load(f)
                        
                        summary = analysis_data.get('summary', {})
                        lines.append(f"Chart: {chart_name}")
                        lines.append(f"  Total Bars: {summary.get('bars', 'N/A')}")
                        lines.append(f"  Timeframe: {summary.get('timeframe', 'N/A')}")
                        lines.append(f"  Date Range: {summary.get('start', 'N/A')} to {summary.get('end', 'N/A')}")
                        
                        trend_dist = summary.get('trend_distribution', {})
                        if trend_dist:
                            lines.append(f"  Trend Distribution:")
                            for trend, data in trend_dist.items():
                                lines.append(f"    {trend}: {data.get('pct', 0):.1f}%")
                        
                        vol_dist = summary.get('vol_distribution', {})
                        if vol_dist:
                            lines.append(f"  Volatility Distribution:")
                            for vol, data in vol_dist.items():
                                lines.append(f"    {vol}: {data.get('pct', 0):.1f}%")
                        
                        analysis_found = True
                    except Exception as e:
                        # Quiet in report; log to console area for diagnostics
                        try:
                            self.log_area.append(
                                f"Chart analysis load failed for {os.path.basename(analysis_file)}: {type(e).__name__}: {e}"
                            )
                        except Exception:
                            pass
            
            if not analysis_found:
                lines.append(f"Chart: {chart_name}")
                lines.append("Status: Not available")
                lines.append("")
                lines.append("To generate chart analysis:")
                
                if self.loaded_folder:
                    project_dir = os.path.normpath(os.path.abspath(os.path.join(self.loaded_folder, "..", "..")))
                    lines.append(f"1. Open command prompt in: {project_dir}")
                else:
                    lines.append("1. Open command prompt in project folder")
                
                lines.append("2. Run: run_chart_analyzer.bat")
                lines.append(f"3. When prompted, select chart: {chart_name}")
                lines.append("4. Enable option: --save-analysis")
                lines.append("5. After completion, re-run this performance analysis")
                lines.append("")
                lines.append("Alternatively, run directly:")
                lines.append(f"python scripts\\chart_analyzer.py --chart {chart_name} --save-analysis")
        
        lines.append("")
        if format_type == "structured":
            lines.append("="*70)
            lines.append("END OF REPORT")
            lines.append("="*70)
        
        return "\n".join(lines)


class AnalysisScopeDialog(QDialog):
    """Dialog for selecting analysis scope and format."""
    
    def __init__(self, row_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Run Performance Analysis")
        self.resize(450, 280)
        
        layout = QVBoxLayout(self)
        
        # Scope selection
        scope_group = QGroupBox("Analyze scope:")
        scope_layout = QVBoxLayout(scope_group)
        
        self.radio_fold_only = QRadioButton("This fold only")
        self.radio_all_folds = QRadioButton("All folds for this parameter set (same chart)")
        self.radio_all_charts = QRadioButton("This parameter set across all charts")
        
        self.radio_fold_only.setChecked(True)
        
        scope_layout.addWidget(self.radio_fold_only)
        scope_layout.addWidget(self.radio_all_folds)
        scope_layout.addWidget(self.radio_all_charts)
        
        layout.addWidget(scope_group)
        
        # Format selection
        format_group = QGroupBox("Report format:")
        format_layout = QVBoxLayout(format_group)
        
        self.radio_plain = QRadioButton("Simple")
        self.radio_structured = QRadioButton("Detailed")
        
        self.radio_plain.setChecked(True)
        
        format_layout.addWidget(self.radio_plain)
        format_layout.addWidget(self.radio_structured)
        
        layout.addWidget(format_group)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Ok
        )
        button_box.button(QDialogButtonBox.Ok).setText("Generate Analysis")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        layout.addWidget(button_box)
    
    def get_scope(self) -> str:
        if self.radio_fold_only.isChecked():
            return "fold_only"
        elif self.radio_all_folds.isChecked():
            return "all_folds"
        else:
            return "all_charts"
    
    def get_format(self) -> str:
        return "plain" if self.radio_plain.isChecked() else "structured"


class AnalysisReportDialog(QDialog):
    """Dialog for displaying and saving analysis report."""
    
    def __init__(self, report_text: str, row_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Performance Analysis Report")
        self.resize(800, 600)
        
        self.report_text = report_text
        self.row_data = row_data
        
        layout = QVBoxLayout(self)
        
        # Text display
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText(report_text)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Courier New", 9))
        
        layout.addWidget(self.text_edit)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        btn_save = QPushButton("Save Report...")
        btn_close = QPushButton("Close")
        
        btn_save.clicked.connect(self._save_report)
        btn_close.clicked.connect(self.accept)
        
        button_layout.addWidget(btn_save)
        button_layout.addStretch()
        button_layout.addWidget(btn_close)
        
        layout.addLayout(button_layout)
    
    def _save_report(self):
        """Save report to file."""
        try:
            # Generate default filename
            trial_uid = self.row_data.get('trial_uid', self.row_data.get('uid', 'unknown'))
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            default_name = f"run_analysis_{trial_uid}_{timestamp}.txt"
            
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Analysis Report", default_name,
                "Text Files (*.txt);;All Files (*)"
            )
            
            if not file_path:
                return
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.report_text)
            
            QMessageBox.information(
                self, "Success", f"Report saved to:\n{file_path}"
            )
            
        except Exception as exc:
            QMessageBox.critical(
                self, "Save Failed", str(exc)
            )


class BacktestConfigDialog(QDialog):
    """Dialog for configuring backtest parameters."""
    
    def __init__(self, row_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Backtest Configuration")
        self.resize(500, 450)
        
        self.row_data = row_data
        
        layout = QVBoxLayout(self)
        
        # Info section
        info_group = QGroupBox("Selected Row")
        info_layout = QVBoxLayout()
        
        trial_uid = row_data.get('trial_uid', row_data.get('uid', 'N/A'))
        chart = row_data.get('chart', 'N/A')
        fold = row_data.get('fold_id', 'N/A')
        
        info_layout.addWidget(QLabel(f"Trial UID: {trial_uid}"))
        info_layout.addWidget(QLabel(f"Chart: {chart}"))
        info_layout.addWidget(QLabel(f"Fold: {fold}"))
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Scope selection
        scope_group = QGroupBox("Backtest Scope")
        scope_layout = QVBoxLayout()
        
        # Note: Scope removed - always analyzes the selected fold/chart
        info_note = QLabel("<i>Note: Analysis will run on the selected trial's chart and fold.</i>")
        info_note.setWordWrap(True)
        scope_layout.addWidget(info_note)
        
        scope_group.setLayout(scope_layout)
        layout.addWidget(scope_group)
        
        # Runtime parameters
        params_group = QGroupBox("Backtest Parameters")
        params_layout = QVBoxLayout()
        
        # Capital
        capital_row = QHBoxLayout()
        capital_row.addWidget(QLabel("Starting Capital:"))
        self.capital_input = QLineEdit("10000")
        self.capital_input.setPlaceholderText("e.g., 10000")
        capital_row.addWidget(self.capital_input)
        params_layout.addLayout(capital_row)
        
        # Fees
        fees_row = QHBoxLayout()
        fees_row.addWidget(QLabel("Fees (%):"))
        self.fees_input = QLineEdit("0.1")
        self.fees_input.setPlaceholderText("e.g., 0.1 for 0.1%")
        fees_row.addWidget(self.fees_input)
        params_layout.addLayout(fees_row)
        
        # Max positions
        positions_row = QHBoxLayout()
        positions_row.addWidget(QLabel("Max Concurrent Positions:"))
        self.positions_input = QLineEdit("3")
        self.positions_input.setPlaceholderText("e.g., 3")
        positions_row.addWidget(self.positions_input)
        params_layout.addLayout(positions_row)
        
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Ok
        )
        button_box.button(QDialogButtonBox.Ok).setText("Run Backtest")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        layout.addWidget(button_box)
    
    def get_config(self) -> Dict[str, Any]:
        """Get backtest configuration."""
        try:
            capital = float(self.capital_input.text())
        except ValueError:
            capital = 10000.0
        
        try:
            fees_pct = float(self.fees_input.text())
            fees = fees_pct / 100.0  # Convert percentage to decimal
        except ValueError:
            fees = 0.001
        
        try:
            max_positions = int(self.positions_input.text())
        except ValueError:
            max_positions = 3
        
        return {
            'capital': capital,
            'fees': fees,
            'max_positions': max_positions,
        }


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

