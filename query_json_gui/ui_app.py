import glob
import json
import logging
import os
import re
import shutil
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional, List, Dict

import numpy as np
import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

import optimization_console as oc
from ui_helpers import available_group_columns, shorten_expression

APP_VERSION = "1.1.0"
SCHEMA_VERSION_PROFILES = "1.0"
SCHEMA_VERSION_APP_STATE = "1.0"

# Setup logging
def setup_logging():
    """Setup rotating log file for the application."""
    log_file = "opt_console_ui.log"
    
    # Create logger
    logger = logging.getLogger("opt_console_ui")
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create rotating file handler (1MB max, 5 files)
    handler = RotatingFileHandler(
        log_file, 
        maxBytes=1024*1024,  # 1MB
        backupCount=5,
        encoding='utf-8'
    )
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(handler)
    
    return logger

# Initialize logger
logger = setup_logging()


class DataFrameModel(QtCore.QAbstractTableModel):
    def __init__(self, df: Optional[pd.DataFrame] = None):
        super().__init__()
        self._df = df if df is not None else pd.DataFrame()
        self._sort_order: Dict[int, QtCore.Qt.SortOrder] = {}

    def update(self, df: Optional[pd.DataFrame]):
        self.beginResetModel()
        self._df = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else (0 if self._df is None else len(self._df))

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else (0 if self._df is None else self._df.shape[1])

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid() or self._df is None:
            return None
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            val = self._df.iat[index.row(), index.column()]
            if pd.isna(val):
                return ""
            if isinstance(val, float):
                try:
                    col_name = str(self._df.columns[index.column()])
                    if oc.is_percent_col(col_name):
                        return f"{val * 100:.2f}%"
                except Exception:
                    pass
                return f"{val:.4f}"
            return str(val)
        return None

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole or self._df is None:
            return None
        if orientation == QtCore.Qt.Horizontal:
            try:
                return str(self._df.columns[section])
            except Exception:
                return str(section)
        else:
            return str(section)

    def sort(self, column: int, order: QtCore.Qt.SortOrder = QtCore.Qt.AscendingOrder) -> None:
        if self._df is None or self._df.empty:
            return
        self.layoutAboutToBeChanged.emit()
        col_name = str(self._df.columns[column])
        ascending = order == QtCore.Qt.AscendingOrder
        try:
            self._df = self._df.sort_values(by=[col_name], ascending=[ascending], kind="mergesort").reset_index(drop=True)
        except Exception:
            pass
        self.layoutChanged.emit()


class SortBuilderDialog(QtWidgets.QDialog):
    """Dialog to build multi-key sort specification."""

    def __init__(self, df: pd.DataFrame, parent: Optional[QtWidgets.QWidget] = None, initial_sort: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Build Sort")
        self.df = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
        self.sort_items: List[tuple] = []
        
        v = QtWidgets.QVBoxLayout(self)
        
        # List widget for sort keys
        self.list_widget = QtWidgets.QListWidget()
        v.addWidget(self.list_widget)
        
        # Add sort key controls
        h_add = QtWidgets.QHBoxLayout()
        self.cb_field = QtWidgets.QComboBox()
        for col in self.df.columns if not self.df.empty else []:
            self.cb_field.addItem(str(col))
        h_add.addWidget(QtWidgets.QLabel("Field:"))
        h_add.addWidget(self.cb_field)
        self.cb_direction = QtWidgets.QComboBox()
        self.cb_direction.addItems(["Asc", "Desc"])
        h_add.addWidget(QtWidgets.QLabel("Direction:"))
        h_add.addWidget(self.cb_direction)
        btn_add = QtWidgets.QPushButton("+ Add")
        btn_add.clicked.connect(self._add_sort_key)
        h_add.addWidget(btn_add)
        v.addLayout(h_add)
        
        # Reorder buttons
        h_reorder = QtWidgets.QHBoxLayout()
        btn_up = QtWidgets.QPushButton("↑ Up")
        btn_up.clicked.connect(self._move_up)
        btn_down = QtWidgets.QPushButton("↓ Down")
        btn_down.clicked.connect(self._move_down)
        btn_remove = QtWidgets.QPushButton("− Remove")
        btn_remove.clicked.connect(self._remove_key)
        h_reorder.addWidget(btn_up)
        h_reorder.addWidget(btn_down)
        h_reorder.addWidget(btn_remove)
        h_reorder.addStretch(1)
        v.addLayout(h_reorder)
        
        # Buttons
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)
        
        # Parse initial if provided
        if initial_sort:
            self._parse_initial_sort(initial_sort)
    
    def _parse_initial_sort(self, sort_str: str):
        for token in [t.strip() for t in sort_str.split(',') if t.strip()]:
            if token.startswith('-'):
                self.sort_items.append((token[1:], "Desc"))
            else:
                self.sort_items.append((token, "Asc"))
        self._refresh_list()
    
    def _add_sort_key(self):
        field = self.cb_field.currentText().strip()
        direction = self.cb_direction.currentText()
        if field:
            self.sort_items.append((field, direction))
            self._refresh_list()
    
    def _remove_key(self):
        idx = self.list_widget.currentRow()
        if 0 <= idx < len(self.sort_items):
            self.sort_items.pop(idx)
            self._refresh_list()
    
    def _move_up(self):
        idx = self.list_widget.currentRow()
        if idx > 0:
            self.sort_items[idx], self.sort_items[idx - 1] = self.sort_items[idx - 1], self.sort_items[idx]
            self._refresh_list()
            self.list_widget.setCurrentRow(idx - 1)
    
    def _move_down(self):
        idx = self.list_widget.currentRow()
        if 0 <= idx < len(self.sort_items) - 1:
            self.sort_items[idx], self.sort_items[idx + 1] = self.sort_items[idx + 1], self.sort_items[idx]
            self._refresh_list()
            self.list_widget.setCurrentRow(idx + 1)
    
    def _refresh_list(self):
        self.list_widget.clear()
        for field, direction in self.sort_items:
            symbol = "↓" if direction == "Desc" else "↑"
            self.list_widget.addItem(f"{symbol} {field}")
    
    def get_sort_string(self) -> str:
        parts = []
        for field, direction in self.sort_items:
            if direction == "Desc":
                parts.append(f"-{field}")
            else:
                parts.append(field)
        return ",".join(parts)


class FilterBuilderDialog(QtWidgets.QDialog):
    """Dialog to build a filter expression with preview.

    Non-destructive: does not mutate parent view. Apply only writes to input field.
    """

    PREVIEW_DEBOUNCE_MS = 300

    def __init__(self, df: pd.DataFrame, parent: Optional[QtWidgets.QWidget] = None, initial_expr: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Build Filter")
        self.df = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
        self.result_expr: str = initial_expr or ""
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._run_preview)

        v = QtWidgets.QVBoxLayout(self)

        # Rows container
        self.rows_container = QtWidgets.QWidget(self)
        self.rows_layout = QtWidgets.QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.rows_container)

        btns_row = QtWidgets.QHBoxLayout()
        self.btn_add_row = QtWidgets.QPushButton("+ Add Row")
        self.btn_add_row.clicked.connect(self._add_row)
        btns_row.addWidget(self.btn_add_row)
        btns_row.addStretch(1)
        v.addLayout(btns_row)

        # Advanced area
        self.chk_advanced = QtWidgets.QCheckBox("Advanced")
        self.chk_advanced.toggled.connect(self._toggle_advanced)
        v.addWidget(self.chk_advanced)

        self.txt_advanced = QtWidgets.QPlainTextEdit()
        self.txt_advanced.setReadOnly(False)  # allow lightweight manual edits
        self.txt_advanced.setPlaceholderText("Raw expression preview…")
        self.txt_advanced.hide()
        self.txt_advanced.textChanged.connect(self._on_advanced_changed)
        v.addWidget(self.txt_advanced)

        # Preview
        self.lbl_preview = QtWidgets.QLabel("Matches: –")
        v.addWidget(self.lbl_preview)

        # Buttons
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_apply)
        buttons.rejected.connect(self._on_cancel)
        v.addWidget(buttons)

        # Initialize with one row
        self._add_row()
        if initial_expr:
            self.txt_advanced.setPlainText(initial_expr)
            self.chk_advanced.setChecked(True)
            self._schedule_preview()

    def _field_list(self) -> List[str]:
        if self.df is None or self.df.empty:
            return []
        cols = list(self.df.columns)
        key_metrics = [
            "calmar_ratio",
            "profit_factor",
            "max_drawdown",
            "sharpe_ratio",
            "total_trades",
            "win_rate",
        ]
        # prefer num_trades if total_trades not present
        if "total_trades" not in cols and "num_trades" in cols:
            key_metrics = [
                "calmar_ratio",
                "profit_factor",
                "max_drawdown",
                "sharpe_ratio",
                "num_trades",
                "win_rate",
            ]
        params = [c for c in cols if c.startswith("param_")]
        ordered = [c for c in key_metrics if c in cols]
        for c in cols:
            if c not in ordered and not c.startswith("param_"):
                ordered.append(c)
        ordered.extend([c for c in params if c not in ordered])
        return ordered

    def _add_row(self):
        roww = QtWidgets.QWidget(self.rows_container)
        h = QtWidgets.QHBoxLayout(roww)
        h.setContentsMargins(0, 0, 0, 0)

        cb_field = QtWidgets.QComboBox(roww)
        for f in self._field_list():
            cb_field.addItem(f)
        h.addWidget(cb_field)

        cb_op = QtWidgets.QComboBox(roww)
        ops = ["=", "!=", ">", ">=", "<", "<=", "between", "in"]
        for op in ops:
            cb_op.addItem(op)
        h.addWidget(cb_op)

        val_edit = QtWidgets.QLineEdit(roww)
        val_edit.setPlaceholderText("value or 8% / 0.08")
        h.addWidget(val_edit)

        val_edit2 = QtWidgets.QLineEdit(roww)
        val_edit2.setPlaceholderText("max for between")
        val_edit2.hide()
        h.addWidget(val_edit2)

        btn_remove = QtWidgets.QToolButton(roww)
        btn_remove.setText("–")
        h.addWidget(btn_remove)

        def on_op_changed(index: int):
            op = cb_op.currentText()
            if op == "between":
                val_edit2.show()
                val_edit.setPlaceholderText("min (e.g., 8% or 0.08)")
            else:
                val_edit2.hide()
                if op == "in":
                    val_edit.setPlaceholderText("comma,separated,list")
                else:
                    val_edit.setPlaceholderText("value or 8% / 0.08")
            self._update_advanced()
            self._schedule_preview()

        cb_op.currentIndexChanged.connect(on_op_changed)

        def on_changed(*args):
            self._update_advanced()
            self._schedule_preview()

        cb_field.currentIndexChanged.connect(on_changed)
        val_edit.textChanged.connect(on_changed)
        val_edit2.textChanged.connect(on_changed)

        def on_remove():
            roww.setParent(None)
            roww.deleteLater()
            self._update_advanced()
            self._schedule_preview()

        btn_remove.clicked.connect(on_remove)

        self.rows_layout.addWidget(roww)
        self._update_advanced()

    def _toggle_advanced(self, checked: bool):
        self.txt_advanced.setVisible(checked)
        self._update_advanced()

    def _compose_expression(self) -> str:
        parts: List[str] = []
        for i in range(self.rows_layout.count()):
            roww = self.rows_layout.itemAt(i).widget()
            if roww is None:
                continue
            cb_field = roww.layout().itemAt(0).widget()
            cb_op = roww.layout().itemAt(1).widget()
            val_edit = roww.layout().itemAt(2).widget()
            val_edit2 = roww.layout().itemAt(3).widget()
            field = cb_field.currentText().strip() if isinstance(cb_field, QtWidgets.QComboBox) else ""
            op = cb_op.currentText().strip() if isinstance(cb_op, QtWidgets.QComboBox) else ""
            v1 = val_edit.text().strip() if isinstance(val_edit, QtWidgets.QLineEdit) else ""
            v2 = val_edit2.text().strip() if isinstance(val_edit2, QtWidgets.QLineEdit) else ""
            if not field or not op:
                continue
            if op == "between":
                if v1 and v2:
                    parts.append(f"({field} >= {v1}) and ({field} <= {v2})")
            elif op == "in":
                values = [t.strip() for t in v1.split(',') if t.strip()]
                norm_vals = []
                for tok in values:
                    # Keep numeric/percent tokens as-is; quote others
                    if re.match(r"^-?\d+(?:\.\d+)?\s*%?$", tok):
                        norm_vals.append(oc.normalize_percent_expr(tok))
                    else:
                        norm_vals.append(f"'{tok}'")
                if norm_vals:
                    parts.append(f"{field} in [{', '.join(norm_vals)}]")
            else:
                if v1:
                    parts.append(f"{field} {op} {v1}")
        return " and ".join(parts)

    def _update_advanced(self):
        expr = self._compose_expression()
        if not self.chk_advanced.isChecked():
            # Keep preview text up to date behind the scenes
            self.result_expr = expr
        else:
            # Show advanced text
            # If user edits advanced directly, we preserve their changes
            cur = self.txt_advanced.toPlainText().strip()
            if not cur or cur == self.result_expr:
                self.txt_advanced.blockSignals(True)
                self.txt_advanced.setPlainText(expr)
                self.txt_advanced.blockSignals(False)
            self.result_expr = self.txt_advanced.toPlainText().strip()

    def _on_advanced_changed(self):
        if self.chk_advanced.isChecked():
            self.result_expr = self.txt_advanced.toPlainText().strip()
            self._schedule_preview()

    def _schedule_preview(self):
        self._timer.start(self.PREVIEW_DEBOUNCE_MS)

    def _run_preview(self):
        expr = self.result_expr or self._compose_expression()
        if not expr:
            self.lbl_preview.setText("Matches: 0")
            return
        try:
            # Non-destructive: evaluate against provided df
            res = oc.query_df(self.df, filter_expr=expr, sort_by=None, limit=0)
            self.lbl_preview.setText(f"Matches: {len(res)}")
        except Exception as exc:
            # Friendly inline error
            self.lbl_preview.setText(f"Error: {exc}")

    def _on_apply(self):
        self.result_expr = (self.txt_advanced.toPlainText().strip() if self.chk_advanced.isChecked() else self._compose_expression()).strip()
        logger.info("FilterBuilder: apply")
        self.accept()

    def _on_cancel(self):
        logger.info("FilterBuilder: cancel")
        self.reject()

    def get_expression(self) -> str:
        return self.result_expr or ""


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Optimization Console UI v1.1.0")
        self.resize(1200, 700)

        self.current_df: pd.DataFrame = pd.DataFrame()
        self.loaded_df: pd.DataFrame = pd.DataFrame()
        self.full_df: pd.DataFrame = pd.DataFrame()  # For large data safeguards
        self._column_actions: Dict[str, QtWidgets.QAction] = {}
        self._restore_last_filter: bool = False
        self.data_dir: Optional[str] = None
        self.export_dir: Optional[str] = None
        self.current_profile_name: Optional[str] = None
        self._pending_column_visibility = None
        self._debounce_timer = QtCore.QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self.apply_qsl)
        
        # Load app state
        self._load_app_state()

        self._init_ui()

    def _init_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        layout = QtWidgets.QHBoxLayout(central)

        # Left controls (scrollable)
        controls_widget = QtWidgets.QWidget()
        controls = QtWidgets.QVBoxLayout(controls_widget)
        controls_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls_widget)
        layout.addWidget(scroll, 0)

        # Data Section
        box_data = QtWidgets.QGroupBox("Data")
        v_data = QtWidgets.QVBoxLayout(box_data)
        self.lbl_data_dir = QtWidgets.QLabel("No folder selected")
        btn_choose = QtWidgets.QPushButton("Choose Folder…")
        btn_load = QtWidgets.QPushButton("Load JSONs")
        btn_choose.clicked.connect(self.choose_folder)
        btn_load.clicked.connect(self.load_jsons)
        v_data.addWidget(self.lbl_data_dir)
        v_data.addWidget(btn_choose)
        v_data.addWidget(btn_load)
        controls.addWidget(box_data)

        # QC Section
        box_qc = QtWidgets.QGroupBox("QC")
        form_qc = QtWidgets.QFormLayout(box_qc)
        self.spin_min_trades = QtWidgets.QSpinBox()
        self.spin_min_trades.setRange(0, 1_000_000)
        self.dsb_max_mdd = QtWidgets.QDoubleSpinBox()
        self.dsb_max_mdd.setRange(0.0, 1.0)
        self.dsb_max_mdd.setSingleStep(0.01)
        self.chk_nondeg = QtWidgets.QCheckBox("Drop degenerate")
        btn_qc = QtWidgets.QPushButton("Apply QC")
        btn_qc.clicked.connect(self.apply_qc)
        form_qc.addRow("min_trades", self.spin_min_trades)
        form_qc.addRow("max_mdd", self.dsb_max_mdd)
        form_qc.addRow(self.chk_nondeg)
        form_qc.addRow(btn_qc)
        controls.addWidget(box_qc)

        # Query/Sort/Limit Section
        box_qsl = QtWidgets.QGroupBox("Query / Sort / Limit")
        form_qsl = QtWidgets.QFormLayout(box_qsl)
        # Filter row with Build Filter button
        self.le_filter = QtWidgets.QLineEdit()
        self.le_filter.setPlaceholderText("e.g. max_drawdown < 8% and profit_factor >= 1.5")
        self.le_filter.setToolTip("Accepts 8%, 8 %, or 0.08")
        self.le_filter.returnPressed.connect(self._debounced_apply_qsl)
        # Ensure editable/selectable
        self.le_filter.setEnabled(True)
        self.le_filter.setReadOnly(False)
        self.le_filter.setFocusPolicy(QtCore.Qt.StrongFocus)
        btn_build_filter = QtWidgets.QPushButton("Build Filter…")
        btn_build_filter.clicked.connect(self.open_filter_builder)
        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(self.le_filter)
        filter_row.addWidget(btn_build_filter)
        filter_row_w = QtWidgets.QWidget()
        filter_row_w.setLayout(filter_row)
        
        # Preset & History chips
        chips_layout = QtWidgets.QHBoxLayout()
        chips_layout.setContentsMargins(0, 4, 0, 4)
        # Presets
        btn_preset_quality = QtWidgets.QPushButton("Quality")
        btn_preset_quality.setToolTip("profit_factor >= 1.6 and calmar_ratio > 0 and max_drawdown < 10% and total_trades >= 20")
        btn_preset_quality.clicked.connect(lambda: self._load_preset("profit_factor >= 1.6 and calmar_ratio > 0 and max_drawdown < 10% and total_trades >= 20"))
        btn_preset_risk = QtWidgets.QPushButton("Risk-tight")
        btn_preset_risk.setToolTip("max_drawdown < 8% and profit_factor >= 1.5")
        btn_preset_risk.clicked.connect(lambda: self._load_preset("max_drawdown < 8% and profit_factor >= 1.5"))
        btn_preset_return = QtWidgets.QPushButton("Return-tilt")
        btn_preset_return.setToolTip("calmar_ratio >= 0.5 and total_trades >= 30")
        btn_preset_return.clicked.connect(lambda: self._load_preset("calmar_ratio >= 0.5 and total_trades >= 30"))
        chips_layout.addWidget(QtWidgets.QLabel("Presets:"))
        chips_layout.addWidget(btn_preset_quality)
        chips_layout.addWidget(btn_preset_risk)
        chips_layout.addWidget(btn_preset_return)
        chips_layout.addSpacing(10)
        chips_layout.addWidget(QtWidgets.QLabel("History:"))
        self.history_chips_layout = QtWidgets.QHBoxLayout()
        chips_layout.addLayout(self.history_chips_layout)
        chips_layout.addStretch(1)
        chips_w = QtWidgets.QWidget()
        chips_w.setLayout(chips_layout)
        form_qsl.addRow(chips_w)
        lbl_hint = QtWidgets.QLabel("Click a chip to load its filter; Apply to run.")
        lbl_hint.setStyleSheet("color: gray; font-size: 9pt;")
        form_qsl.addRow(lbl_hint)
        
        self.le_sort = QtWidgets.QLineEdit()
        self.le_sort.setPlaceholderText("e.g. -calmar_ratio,profit_factor")
        self.le_sort.setToolTip("Affects the main table (Query/Sort/Limit).")
        self.le_sort.returnPressed.connect(self._debounced_apply_qsl)
        # Ensure editable/selectable
        self.le_sort.setEnabled(True)
        self.le_sort.setReadOnly(False)
        self.le_sort.setFocusPolicy(QtCore.Qt.StrongFocus)
        btn_build_sort = QtWidgets.QPushButton("Build Sort…")
        btn_build_sort.clicked.connect(self.open_sort_builder)
        sort_row = QtWidgets.QHBoxLayout()
        sort_row.addWidget(self.le_sort)
        sort_row.addWidget(btn_build_sort)
        sort_row_w = QtWidgets.QWidget()
        sort_row_w.setLayout(sort_row)
        
        self.spin_limit = QtWidgets.QSpinBox()
        self.spin_limit.setRange(0, 2_000_000)
        btn_qsl = QtWidgets.QPushButton("Apply Query/Sort/Limit")
        btn_qsl.clicked.connect(self.apply_qsl)
        form_qsl.addRow("filter_expr", filter_row_w)
        form_qsl.addRow("Sort (Main View)", sort_row_w)
        form_qsl.addRow("limit", self.spin_limit)
        form_qsl.addRow(btn_qsl)
        # Reset to QC Base button
        btn_reset_qc = QtWidgets.QPushButton("Reset to QC Base")
        btn_reset_qc.setToolTip("Show the full QC base (no filter, no limit)")
        btn_reset_qc.clicked.connect(self.reset_to_qc_base)
        form_qsl.addRow(btn_reset_qc)
        controls.addWidget(box_qsl)
        
        # Refresh history chips
        self._refresh_history_chips()

        # Top-k per group Section
        box_topk = QtWidgets.QGroupBox("Top-k per group")
        form_topk = QtWidgets.QFormLayout(box_topk)
        self.le_group_by = QtWidgets.QLineEdit()
        self.le_group_by.setPlaceholderText("e.g. chart or chart,fold_id")
        self.le_topk_sort = QtWidgets.QLineEdit()
        self.le_topk_sort.setPlaceholderText("e.g. -calmar_ratio")
        self.spin_k = QtWidgets.QSpinBox()
        self.spin_k.setRange(1, 1_000_000)
        self.le_topk_filter = QtWidgets.QLineEdit()
        self.le_topk_filter.setPlaceholderText("optional: quality filter")
        btn_group_select = QtWidgets.QPushButton("Select Groups…")
        btn_group_select.clicked.connect(self.open_group_by_selector)
        btn_topk = QtWidgets.QPushButton("Top-k per group")
        btn_topk.clicked.connect(self.apply_topk)
        gb_layout = QtWidgets.QHBoxLayout()
        gb_layout.addWidget(self.le_group_by)
        gb_layout.addWidget(btn_group_select)
        gbw = QtWidgets.QWidget()
        gbw.setLayout(gb_layout)
        form_topk.addRow("group_by", gbw)
        self.le_topk_sort.setToolTip("Used only when running Top-k per group; does not change main table sort.")
        form_topk.addRow("Top-k Sort (Per-Group)", self.le_topk_sort)
        form_topk.addRow("k", self.spin_k)
        form_topk.addRow("filter_expr", self.le_topk_filter)
        form_topk.addRow(btn_topk)
        controls.addWidget(box_topk)

        # Advanced Section
        box_adv = QtWidgets.QGroupBox("Advanced")
        form_adv = QtWidgets.QFormLayout(box_adv)
        btn_pareto = QtWidgets.QPushButton("Pareto Frontier")
        btn_score = QtWidgets.QPushButton("Composite Score")
        btn_stability = QtWidgets.QPushButton("Stability by Params")
        btn_corr = QtWidgets.QPushButton("Param↔Metric Spearman")
        self.le_pd_param = QtWidgets.QLineEdit()
        self.le_pd_param.setPlaceholderText("e.g. param_lookback")
        self.le_pd_metric = QtWidgets.QLineEdit()
        self.le_pd_metric.setPlaceholderText("e.g. calmar_ratio")
        btn_pd = QtWidgets.QPushButton("Partial Dependence")
        btn_pareto.clicked.connect(self.apply_pareto)
        btn_score.clicked.connect(self.apply_score)
        btn_stability.clicked.connect(self.apply_stability)
        btn_corr.clicked.connect(self.apply_corr)
        btn_pd.clicked.connect(self.apply_pd)
        form_adv.addRow(btn_pareto)
        form_adv.addRow(btn_score)
        form_adv.addRow(btn_stability)
        form_adv.addRow(btn_corr)
        form_adv.addRow("pd_param", self.le_pd_param)
        form_adv.addRow("pd_metric", self.le_pd_metric)
        form_adv.addRow(btn_pd)
        controls.addWidget(box_adv)

        # Export & Profiles Section
        box_exp = QtWidgets.QGroupBox("Export & Profiles")
        v_exp = QtWidgets.QVBoxLayout(box_exp)
        btn_export = QtWidgets.QPushButton("Export Current View")
        btn_save_profile = QtWidgets.QPushButton("Save Profile…")
        btn_load_profile = QtWidgets.QPushButton("Load Profile…")
        btn_export.clicked.connect(self.export_view)
        btn_save_profile.clicked.connect(self.save_profile)
        btn_load_profile.clicked.connect(self.load_profile)
        v_exp.addWidget(btn_export)
        v_exp.addWidget(btn_save_profile)
        v_exp.addWidget(btn_load_profile)
        controls.addWidget(box_exp)

        controls.addStretch(1)

        # Right table
        self.table = QtWidgets.QTableView()
        self.table.setSortingEnabled(False)
        self.model = DataFrameModel(pd.DataFrame())
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        
        # Enable context menu on table
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        
        # Column visibility menu
        self.columns_menu_btn = QtWidgets.QToolButton()
        self.columns_menu_btn.setText("Columns ▾")
        self.columns_menu_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.columns_menu = QtWidgets.QMenu(self)
        self.columns_menu_btn.setMenu(self.columns_menu)
        toolbar = QtWidgets.QToolBar()
        toolbar.addWidget(self.columns_menu_btn)
        self.addToolBar(QtCore.Qt.TopToolBarArea, toolbar)
        
        # Summary bar above table
        self.summary_label = QtWidgets.QLabel("QC: — | Filter: (none) | Sort: (none) | Limit: all")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("background-color: #f0f0f0; padding: 4px; font-size: 9pt;")
        self.summary_label.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        self.summary_label.linkActivated.connect(self._on_summary_clicked)
        
        right_panel = QtWidgets.QVBoxLayout()
        right_panel.addWidget(self.summary_label)
        right_panel.addWidget(self.table, 1)
        right_w = QtWidgets.QWidget()
        right_w.setLayout(right_panel)
        layout.addWidget(right_w, 1)
        
        self._refresh_columns_menu()
        self._update_summary_bar()
        
        # Apply pending last filter only if user opted in
        if getattr(self, '_restore_last_filter', False) and hasattr(self, '_pending_last_filter') and self._pending_last_filter:
            self.le_filter.setText(self._pending_last_filter)
            self._pending_last_filter = None

    # Utilities
    def _info(self, title: str, msg: str):
        QtWidgets.QMessageBox.information(self, title, msg)

    def _warn(self, title: str, msg: str):
        QtWidgets.QMessageBox.warning(self, title, msg)

    def _error(self, title: str, msg: str):
        QtWidgets.QMessageBox.critical(self, title, msg)

    def _update_table(self, df: Optional[pd.DataFrame], operation_time_ms: Optional[float] = None):
        """Update table with large data safeguards."""
        if df is None or df.empty:
            self.current_df = pd.DataFrame()
            self.full_df = pd.DataFrame()
            self.model.update(self.current_df)
            self.statusBar().showMessage("No data")
            return
        
        # Store full dataframe for exports
        self.full_df = df.copy()
        
        # Implement 50k row truncation for display
        if len(df) > 50_000:
            display_df = df.head(50_000)
            self.current_df = display_df.copy()
            self.model.update(self.current_df)
            self._refresh_columns_menu()
            
            status_msg = f"Showing 50,000 of {len(df):,} rows"
            if operation_time_ms is not None:
                status_msg += f" | Last op: {operation_time_ms:.0f} ms"
            self.statusBar().showMessage(status_msg)
            logger.info(f"Large dataset truncated for display: {len(df):,} rows -> 50,000 rows")
        else:
            self.current_df = df.copy()
            self.model.update(self.current_df)
            self._refresh_columns_menu()
            
            status_msg = f"Rows: {len(df):,}"
            if operation_time_ms is not None:
                status_msg += f" | Last op: {operation_time_ms:.0f} ms"
            self.statusBar().showMessage(status_msg)

        # Rebuild Columns ▾ with robust QAction handling
        try:
            self._rebuild_columns_menu()
        except Exception as exc:
            logger.warning(f"Columns menu rebuild failed: {exc}")

    def _rebuild_columns_menu(self):
        self.columns_menu.clear()
        if self.current_df is None or self.current_df.empty:
            self._column_actions.clear()
            return
        new_actions: Dict[str, QtWidgets.QAction] = {}
        for i, col in enumerate(self.current_df.columns):
            name = str(col)
            try:
                act = self._column_actions.get(name)
                if act is None:
                    act = QtWidgets.QAction(name, self.columns_menu)
                    act.setCheckable(True)
                # Determine visibility
                is_visible = not self.table.isColumnHidden(i)
                act.setChecked(is_visible)
                # Disconnect prior connections to avoid duplicate triggers
                try:
                    act.toggled.disconnect()
                except Exception:
                    pass
                def make_toggler(col_index: int, col_name: str):
                    def _toggle(checked: bool):
                        # Guard for missing/shifted columns
                        try:
                            if col_index < 0 or col_index >= len(self.current_df.columns):
                                logger.info(f"Columns: skip toggle for missing column index {col_index} ({col_name})")
                                return
                            self.table.setColumnHidden(col_index, not checked)
                        except Exception as exc2:
                            logger.warning(f"Columns: error toggling '{col_name}': {exc2}")
                    return _toggle
                act.toggled.connect(make_toggler(i, name))
                self.columns_menu.addAction(act)
                new_actions[name] = act
            except Exception as exc:
                logger.info(f"Columns: skip action for '{name}': {exc}")
        self._column_actions = new_actions

    # Actions
    def _validate_missing_columns(self, missing_cols: List[str], operation_name: str) -> bool:
        """Show validation dialog for missing columns and return False to abort."""
        if missing_cols:
            msg = f"{operation_name} requires the following columns:\n\n"
            msg += "\n".join(f"• {col}" for col in missing_cols)
            msg += "\n\nOperation cancelled. Please ensure your data contains these columns."
            self._error(f"{operation_name} - Missing Columns", msg)
            logger.warning(f"{operation_name} failed - missing columns: {missing_cols}")
            return False
        return True

    def _debounced_apply_qsl(self):
        """Trigger apply after debounce delay (for Enter key press)."""
        self._debounce_timer.start(250)
    
    def _load_preset(self, preset_expr: str):
        """Load a preset filter into filter_expr field."""
        self.le_filter.setText(preset_expr)
        logger.info(f"Preset filter loaded: {preset_expr[:50]}...")
    
    def _load_history(self, history_expr: str):
        """Load a history filter into filter_expr field."""
        self.le_filter.setText(history_expr)
        logger.info(f"History filter loaded: {history_expr[:50]}...")
    
    def _refresh_history_chips(self):
        """Refresh history chips from app_state.json."""
        # Clear existing history chips
        while self.history_chips_layout.count():
            item = self.history_chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Load history from state
        try:
            if os.path.exists(self.app_state_path):
                with open(self.app_state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    hist = state.get("filter_history", [])
                    for expr in hist[:5]:
                        btn = QtWidgets.QPushButton(shorten_expression(expr, 40))
                        btn.setToolTip(expr)
                        btn.clicked.connect(lambda checked, e=expr: self._load_history(e))
                        self.history_chips_layout.addWidget(btn)
        except Exception as exc:
            logger.warning(f"Refresh history chips failed: {exc}")
    
    def _update_summary_bar(self):
        """Update the summary bar with current QC/filter/sort/limit."""
        qc_text = f"min_trades={self.spin_min_trades.value()} max_mdd={self.dsb_max_mdd.value():.2f} nondegenerate={'on' if self.chk_nondeg.isChecked() else 'off'}"
        filter_text = shorten_expression(self.le_filter.text().strip(), 60)
        sort_text = shorten_expression(self.le_sort.text().strip(), 40) if self.le_sort.text().strip() else "(none)"
        limit_val = self.spin_limit.value()
        limit_text = str(limit_val) if limit_val > 0 else "all"
        
        summary = f'QC: {qc_text} | <a href="filter">Filter</a>: {filter_text} | <a href="sort">Sort</a>: {sort_text} | Limit: {limit_text}'
        self.summary_label.setText(summary)
    
    def _on_summary_clicked(self, link: str):
        """Handle clicks on summary bar links."""
        if link == "filter":
            self.open_filter_builder()
        elif link == "sort":
            self.open_sort_builder()
    
    def open_filter_builder(self):
        base_df = self.current_df if self.current_df is not None else pd.DataFrame()
        dlg = FilterBuilderDialog(base_df, self, initial_expr=self.le_filter.text().strip())
        logger.info("FilterBuilder: open")
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            expr = dlg.get_expression()
            self.le_filter.setText(expr)
            self._update_summary_bar()
            logger.info("FilterBuilder: applied expression")
        else:
            logger.info("FilterBuilder: cancelled")
    
    def open_sort_builder(self):
        base_df = self.current_df if self.current_df is not None else pd.DataFrame()
        dlg = SortBuilderDialog(base_df, self, initial_sort=self.le_sort.text().strip())
        logger.info("SortBuilder: open")
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            sort_str = dlg.get_sort_string()
            # Validate fields exist
            cols = [c.strip().lstrip('-') for c in sort_str.split(',') if c.strip()]
            missing = [c for c in cols if c not in base_df.columns]
            if missing:
                self._error("Sort Builder - Invalid Columns", 
                           f"The following columns do not exist:\n\n" + "\n".join(f"• {c}" for c in missing))
                logger.warning(f"SortBuilder: invalid columns {missing}")
            else:
                self.le_sort.setText(sort_str)
                self._update_summary_bar()
                logger.info(f"SortBuilder: applied {sort_str}")
        else:
            logger.info("SortBuilder: cancelled")

    def choose_folder(self):
        dirpath = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose Data Folder", self.data_dir or os.getcwd()
        )
        if dirpath:
            self.data_dir = dirpath
            self.lbl_data_dir.setText(dirpath)
            self._save_app_state()

    def load_jsons(self):
        # Load and merge all JSON files from the selected directory
        if not self.data_dir:
            self._warn("Load JSONs", "Please choose a folder first.")
            return
        
        start_time = time.time()
        try:
            paths = [os.path.join(self.data_dir, f) for f in os.listdir(self.data_dir) if f.lower().endswith('.json')]
            if not paths:
                self._warn("Load JSONs", "No JSON files found in the selected folder.")
                logger.warning(f"No JSON files found in directory: {self.data_dir}")
                return
            
            logger.info(f"Loading {len(paths)} JSON files from: {self.data_dir}")
            
            # Merge JSONs and add derived metrics like gtp_proxy and exp_per_trade
            df = oc.load_json_results(paths)
            df = oc.add_risk_derivatives(df)
            self.loaded_df = df
            # Default to 'show all' on first load: clear filter/sort, limit=0 and apply QC
            self.le_filter.setText("")
            self.le_sort.setText("")
            self.spin_limit.setValue(0)
            self.apply_qc()

            operation_time = (time.time() - start_time) * 1000
            logger.info(f"Successfully loaded {len(df)} rows from {len(paths)} files in {operation_time:.0f}ms (QC base shown)")
        except Exception as exc:
            logger.error(f"Load JSONs failed: {exc}")
            self._error("Load JSONs Failed", str(exc))

    def apply_qc(self):
        # Apply quality control filters to loaded data
        if self.loaded_df is None or self.loaded_df.empty:
            self._warn("QC", "No data loaded.")
            return
        
        start_time = time.time()
        try:
            # Filter by min trades, max drawdown, and optionally drop degenerate rows
            df = oc.qc_filter(
                self.loaded_df,
                min_trades=int(self.spin_min_trades.value()),
                max_mdd=float(self.dsb_max_mdd.value()),  # Fraction (0.10 = 10%)
                nondegenerate=bool(self.chk_nondeg.isChecked()),
            )
            operation_time = (time.time() - start_time) * 1000
            # Show QC base as current view with no additional filtering
            self._update_table(df, operation_time)
            
            logger.info(f"QC filter applied: {len(self.loaded_df)} -> {len(df)} rows in {operation_time:.0f}ms")
        except Exception as exc:
            logger.error(f"QC failed: {exc}")
            self._error("QC Failed", str(exc))

    def apply_qsl(self):
        # Apply query, sort and limit to QC base (or full) data
        base_df = self.full_df if self.full_df is not None and not self.full_df.empty else self.loaded_df
        if base_df is None or base_df.empty:
            self._warn("Query/Sort/Limit", "No data to query. Load & optionally QC first.")
            return
        
        start_time = time.time()
        try:
            df = oc.query_df(
                base_df,
                filter_expr=self.le_filter.text().strip(),
                sort_by=self.le_sort.text().strip(),
                limit=int(self.spin_limit.value()),
            )
            operation_time = (time.time() - start_time) * 1000
            self._update_table(df, operation_time)
            logger.info(f"Query/Sort/Limit applied: {len(base_df)} -> {len(df)} rows in {operation_time:.0f}ms")
            # Persist last applied filter for prefill
            self._persist_filter_history(self.le_filter.text().strip(), applied=True)
            self._refresh_history_chips()
            self._update_summary_bar()
        except Exception as exc:
            logger.error(f"Query/Sort/Limit failed: {exc}")
            self._error("Query/Sort/Limit Failed", str(exc))

    def reset_to_qc_base(self):
        # Restore full QC base view (no filter, no limit)
        self.le_filter.setText("")
        self.le_sort.setText("")
        self.spin_limit.setValue(0)
        base = self.full_df if isinstance(self.full_df, pd.DataFrame) and not self.full_df.empty else self.loaded_df
        if base is None or base.empty:
            self._warn("Reset to QC Base", "No QC base available. Load data first.")
            return
        self._update_table(base)
        self._update_summary_bar()
        logger.info("Reset to QC base")

    def _persist_filter_history(self, expr: str, applied: bool = False):
        if not expr:
            return
        try:
            # Load current state
            state = {}
            if os.path.exists(self.app_state_path):
                with open(self.app_state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    if not isinstance(state, dict):
                        state = {}
            hist: List[str] = list(state.get("filter_history", []))
            if expr in hist:
                hist.remove(expr)
            hist.insert(0, expr)
            hist = hist[:5]
            state["filter_history"] = hist
            if applied:
                state["last_applied_filter"] = expr
            # keep schema version
            state.setdefault("schema_version", SCHEMA_VERSION_APP_STATE)
            # preserve other keys
            with open(self.app_state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as exc:
            logger.warning(f"Persist filter history failed: {exc}")

    def apply_topk(self):
        # Get top-k rows per group (e.g., top 5 strategies per chart)
        if self.full_df is None or self.full_df.empty:
            self._warn("Top-k", "No data to process. Load & optionally QC first.")
            return
        
        start_time = time.time()
        try:
            group_by_text = self.le_group_by.text().strip()
            if not group_by_text:
                # Default: try chart if present
                options = available_group_columns(self.full_df)
                if "chart" in options:
                    group_by_text = "chart"
                    self.le_group_by.setText(group_by_text)
                else:
                    self._warn("Top-k", "Please provide group_by (e.g., chart or chart,fold_id).")
                    return
            
            # Validate sort_by column exists
            sort_by_text = self.le_topk_sort.text().strip()
            if sort_by_text:
                from optimization_console import _parse_sort_by, require_columns
                cols, _ = _parse_sort_by(sort_by_text)
                missing = require_columns(self.full_df, cols)
                if not self._validate_missing_columns(missing or [], "Top-k Analysis"):
                    return
            
            # Select top k rows for each group, with optional pre-filtering
            df = oc.topk_per_group(
                self.full_df,
                group_by=group_by_text,            # Single column or comma-separated list
                sort_by=sort_by_text,              # Column(s) to sort by within groups
                k=int(self.spin_k.value()),        # Number of rows to keep per group
                filter_expr=self.le_topk_filter.text().strip() or None,  # Optional quality filter
            )
            operation_time = (time.time() - start_time) * 1000
            self._update_table(df, operation_time)
            
            logger.info(f"Top-k applied: {len(self.full_df)} -> {len(df)} rows in {operation_time:.0f}ms")
        except ValueError as exc:
            # Handle validation errors gracefully
            if "requires" in str(exc).lower():
                logger.warning(f"Top-k validation failed: {exc}")
                self._error("Top-k Analysis - Validation Failed", str(exc))
            else:
                logger.error(f"Top-k failed: {exc}")
                self._error("Top-k Failed", str(exc))
        except Exception as exc:
            logger.error(f"Top-k failed: {exc}")
            self._error("Top-k Failed", str(exc))

    def open_group_by_selector(self):
        base_df = self.full_df if self.full_df is not None and not self.full_df.empty else self.loaded_df
        cols = available_group_columns(base_df)
        if not cols:
            self._warn("Select Groups", "No groupable columns (chart/fold_id/param_*) found.")
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Select Group Columns")
        v = QtWidgets.QVBoxLayout(dlg)
        listw = QtWidgets.QListWidget()
        listw.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        listw.setUniformItemSizes(True)
        # Populate
        current = [c.strip() for c in self.le_group_by.text().split(',') if c.strip()]
        for c in cols:
            item = QtWidgets.QListWidgetItem(c)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if c in current else QtCore.Qt.Unchecked)
            listw.addItem(item)
        v.addWidget(listw)
        # Buttons
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        v.addWidget(btns)
        def on_ok():
            selected = []
            for i in range(listw.count()):
                it = listw.item(i)
                if it.checkState() == QtCore.Qt.Checked:
                    selected.append(it.text())
            if selected:
                self.le_group_by.setText(','.join(selected))
            dlg.accept()
        def on_cancel():
            dlg.reject()
        btns.accepted.connect(on_ok)
        btns.rejected.connect(on_cancel)
        dlg.exec()

    def apply_pareto(self):
        # Find Pareto-optimal (non-dominated) solutions across multiple objectives
        if self.full_df is None or self.full_df.empty:
            self._warn("Pareto", "No data to process.")
            return
        
        start_time = time.time()
        try:
            # Validate required columns for Pareto analysis
            required_cols = ["calmar_ratio", "max_drawdown", "profit_factor"]
            missing = oc.require_columns(self.full_df, required_cols)
            if not self._validate_missing_columns(missing or [], "Pareto Analysis"):
                return
            
            # Default objectives: max calmar, min drawdown, max profit_factor
            df = oc.pareto_frontier(self.full_df)
            operation_time = (time.time() - start_time) * 1000
            self._update_table(df, operation_time)
            
            logger.info(f"Pareto analysis: {len(self.full_df)} -> {len(df)} rows in {operation_time:.0f}ms")
        except ValueError as exc:
            if "requires" in str(exc).lower():
                logger.warning(f"Pareto validation failed: {exc}")
                self._error("Pareto Analysis - Validation Failed", str(exc))
            else:
                logger.error(f"Pareto failed: {exc}")
                self._error("Pareto Failed", str(exc))
        except Exception as exc:
            logger.error(f"Pareto failed: {exc}")
            self._error("Pareto Failed", str(exc))

    def apply_score(self):
        if self.full_df is None or self.full_df.empty:
            self._warn("Composite Score", "No data to process.")
            return
        
        start_time = time.time()
        try:
            df = oc.composite_score(self.full_df)
            operation_time = (time.time() - start_time) * 1000
            self._update_table(df, operation_time)
            
            logger.info(f"Composite score applied in {operation_time:.0f}ms")
        except Exception as exc:
            logger.error(f"Composite score failed: {exc}")
            self._error("Composite Score Failed", str(exc))

    def apply_stability(self):
        if self.full_df is None or self.full_df.empty:
            self._warn("Stability", "No data to process.")
            return
        
        start_time = time.time()
        try:
            # Validate required columns for stability analysis
            param_cols = oc.list_param_cols(self.full_df)
            if not param_cols:
                self._error("Stability Analysis - Missing Columns", 
                           "Stability analysis requires at least one param_* column.")
                logger.warning("Stability analysis failed - no param_* columns found")
                return
            
            required_metrics = ["calmar_ratio", "profit_factor", "max_drawdown"]
            available_metrics = [m for m in required_metrics if m in self.full_df.columns]
            if not available_metrics:
                self._error("Stability Analysis - Missing Columns",
                           f"Stability analysis requires at least one metric from:\n\n" +
                           "\n".join(f"• {m}" for m in required_metrics))
                logger.warning(f"Stability analysis failed - no required metrics found: {required_metrics}")
                return
            
            df = oc.stability_by_params(self.full_df)
            operation_time = (time.time() - start_time) * 1000
            self._update_table(df, operation_time)
            
            logger.info(f"Stability analysis: {len(param_cols)} params, {len(available_metrics)} metrics in {operation_time:.0f}ms")
        except ValueError as exc:
            if "requires" in str(exc).lower():
                logger.warning(f"Stability validation failed: {exc}")
                self._error("Stability Analysis - Validation Failed", str(exc))
            else:
                logger.error(f"Stability failed: {exc}")
                self._error("Stability Failed", str(exc))
        except Exception as exc:
            logger.error(f"Stability failed: {exc}")
            self._error("Stability Failed", str(exc))

    def apply_corr(self):
        if self.current_df is None or self.current_df.empty:
            self._warn("Correlations", "No data to process.")
            return
        try:
            df = oc.param_spearman(self.current_df)
            # Show as a long table for the UI
            if isinstance(df, pd.DataFrame) and not df.empty:
                df = df.reset_index().melt(id_vars=df.index.name or 'index', var_name='metric', value_name='spearman')
            self._update_table(df)
        except Exception as exc:
            self._error("Correlations Failed", str(exc))

    def apply_pd(self):
        if self.current_df is None or self.current_df.empty:
            self._warn("Partial Dependence", "No data to process.")
            return
        try:
            param = self.le_pd_param.text().strip()
            metric = self.le_pd_metric.text().strip()
            if not param or not metric:
                self._warn("Partial Dependence", "Please provide pd_param and pd_metric.")
                return
            df = oc.partial_dependence(self.current_df, param=param, metric=metric, bins=8)
            self._update_table(df)
        except Exception as exc:
            self._error("Partial Dependence Failed", str(exc))

    def export_view(self):
        if self.full_df is None or self.full_df.empty:
            self._warn("Export", "No data to export.")
            return
        
        # Use export_dir if available, otherwise fall back to data_dir
        default_dir = self.export_dir or self.data_dir or os.getcwd()
        out_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose Export Folder", default_dir
        )
        if not out_dir:
            return
        
        try:
            # Create export metadata
            export_meta = {
                "profile_name": self.current_profile_name or "None",
                "qc_params": {
                    "min_trades": int(self.spin_min_trades.value()),
                    "max_mdd": float(self.dsb_max_mdd.value()),
                    "nondegenerate": bool(self.chk_nondeg.isChecked())
                },
                "filter_expr": self.le_filter.text().strip(),
                "sort_by": self.le_sort.text().strip(),
                "limit": int(self.spin_limit.value()) if self.spin_limit.value() > 0 else None,
                "group_by": self.le_group_by.text().strip(),
                "objectives_weights": "Default Pareto: calmar_ratio(max), max_drawdown(min), profit_factor(max)",
                "visible_columns": list(self.full_df.columns),
            }
            
            # Export with sidecar - use full_df to export complete filtered data
            csv_path, parquet_path, sidecar_path = oc.export_df(
                self.full_df, out_dir, name="view", meta=export_meta
            )
            
            # Remember export directory
            self.export_dir = out_dir
            self._save_app_state()
            
            msg = f"Exported CSV to:\n{csv_path}\n\nSidecar metadata to:\n{sidecar_path}"
            if parquet_path:
                msg += f"\n\nExported Parquet to:\n{parquet_path}"
            self._info("Export Complete", msg)
            
            logger.info(f"Export completed: {len(self.full_df)} rows to {out_dir}")
        except Exception as exc:
            logger.error(f"Export failed: {exc}")
            self._error("Export Failed", str(exc))

    # Schema versioning and app state
    @property
    def app_state_path(self) -> str:
        here = os.path.abspath(os.path.dirname(__file__))
        return os.path.join(here, "app_state.json")
    
    def _load_app_state(self):
        """Load application state with schema versioning."""
        try:
            if os.path.exists(self.app_state_path):
                with open(self.app_state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                
                # Check schema version and migrate if needed
                schema_version = state.get("schema_version", "0.0")
                if schema_version != SCHEMA_VERSION_APP_STATE:
                    logger.info(f"Migrating app state from {schema_version} to {SCHEMA_VERSION_APP_STATE}")
                    state.setdefault("export_dir", None)
                    state.setdefault("current_profile_name", None)
                    state.setdefault("column_visibility", None)
                    state["schema_version"] = SCHEMA_VERSION_APP_STATE
                    self._save_app_state_dict(state)
                
                # Apply state
                self.data_dir = state.get("data_dir")
                self.export_dir = state.get("export_dir")
                self.current_profile_name = state.get("current_profile_name")
                self._pending_column_visibility = state.get("column_visibility") or None
                self._pending_last_filter = state.get("last_applied_filter") or None
                
                logger.info("App state loaded successfully")
        except Exception as exc:
            logger.warning(f"Failed to load app state: {exc}")
    
    def _save_app_state(self):
        """Save current application state."""
        # Build column visibility map
        visibility = {}
        try:
            if self.current_df is not None and not self.current_df.empty:
                for i, col in enumerate(self.current_df.columns):
                    visibility[str(col)] = not self.table.isColumnHidden(i)
        except Exception:
            pass
        
        # Preserve filter_history and last_applied_filter if already in state
        existing_hist = []
        existing_last = None
        try:
            if os.path.exists(self.app_state_path):
                with open(self.app_state_path, "r", encoding="utf-8") as f:
                    old_state = json.load(f)
                    existing_hist = old_state.get("filter_history", [])
                    existing_last = old_state.get("last_applied_filter")
        except Exception:
            pass
        
        state = {
            "schema_version": SCHEMA_VERSION_APP_STATE,
            "data_dir": self.data_dir,
            "export_dir": self.export_dir,
            "current_profile_name": self.current_profile_name,
            "column_visibility": visibility or None,
            "filter_history": existing_hist or [],
            "last_applied_filter": existing_last,
        }
        self._save_app_state_dict(state)
    
    def _save_app_state_dict(self, state: dict):
        """Save app state dictionary to file."""
        try:
            with open(self.app_state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as exc:
            logger.error(f"Failed to save app state: {exc}")

    def _refresh_columns_menu(self):
        try:
            self._rebuild_columns_menu()
        except Exception as exc:
            logger.warning(f"Columns menu refresh failed: {exc}")
        # Clear pending visibility after initial application
        self._pending_column_visibility = None

    # Profiles
    @property
    def profiles_path(self) -> str:
        here = os.path.abspath(os.path.dirname(__file__))
        return os.path.join(here, "profiles.json")

    def collect_profile(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION_PROFILES,
            "data_dir": self.data_dir or "",
            "min_trades": int(self.spin_min_trades.value()),
            "max_mdd": float(self.dsb_max_mdd.value()),
            "nondegenerate": bool(self.chk_nondeg.isChecked()),
            "filter_expr": self.le_filter.text(),
            "sort_by": self.le_sort.text(),
            "limit": int(self.spin_limit.value()),
            "group_by": self.le_group_by.text(),
            "topk_sort_by": self.le_topk_sort.text(),
            "topk_k": int(self.spin_k.value()),
            "topk_filter": self.le_topk_filter.text(),
            "pd_param": self.le_pd_param.text(),
            "pd_metric": self.le_pd_metric.text(),
        }

    def apply_profile(self, profile: dict):
        self.data_dir = profile.get("data_dir") or self.data_dir
        self.lbl_data_dir.setText(self.data_dir or "No folder selected")
        self.spin_min_trades.setValue(int(profile.get("min_trades", self.spin_min_trades.value())))
        self.dsb_max_mdd.setValue(float(profile.get("max_mdd", self.dsb_max_mdd.value())))
        self.chk_nondeg.setChecked(bool(profile.get("nondegenerate", self.chk_nondeg.isChecked())))
        self.le_filter.setText(str(profile.get("filter_expr", self.le_filter.text())))
        self.le_sort.setText(str(profile.get("sort_by", self.le_sort.text())))
        self.spin_limit.setValue(int(profile.get("limit", self.spin_limit.value())))
        self.le_group_by.setText(str(profile.get("group_by", self.le_group_by.text())))
        self.le_topk_sort.setText(str(profile.get("topk_sort_by", self.le_topk_sort.text())))
        self.spin_k.setValue(int(profile.get("topk_k", self.spin_k.value())))
        self.le_topk_filter.setText(str(profile.get("topk_filter", self.le_topk_filter.text())))
        self.le_pd_param.setText(str(profile.get("pd_param", self.le_pd_param.text())))
        self.le_pd_metric.setText(str(profile.get("pd_metric", self.le_pd_metric.text())))

    def save_profile(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "Save Profile", "Profile name:")
        if not ok or not name.strip():
            return
        profile = self.collect_profile()
        try:
            profiles = {"schema_version": SCHEMA_VERSION_PROFILES}
            if os.path.exists(self.profiles_path):
                with open(self.profiles_path, "r", encoding="utf-8") as f:
                    profiles = json.load(f)
                    if not isinstance(profiles, dict):
                        profiles = {"schema_version": SCHEMA_VERSION_PROFILES}
                    
                    # Migrate profiles if needed
                    if profiles.get("schema_version", "0.0") != SCHEMA_VERSION_PROFILES:
                        logger.info(f"Migrating profiles to schema version {SCHEMA_VERSION_PROFILES}")
                        profiles["schema_version"] = SCHEMA_VERSION_PROFILES
            
            profiles[name.strip()] = profile
            self.current_profile_name = name.strip()
            
            with open(self.profiles_path, "w", encoding="utf-8") as f:
                json.dump(profiles, f, indent=2)
            
            self._save_app_state()
            self._info("Profile Saved", f"Saved profile '{name}'.")
            logger.info(f"Profile '{name}' saved successfully")
        except Exception as exc:
            logger.error(f"Save profile failed: {exc}")
            self._error("Save Profile Failed", str(exc))

    def load_profile(self):
        try:
            profiles = {}
            if os.path.exists(self.profiles_path):
                with open(self.profiles_path, "r", encoding="utf-8") as f:
                    profiles = json.load(f)
                    if not isinstance(profiles, dict):
                        profiles = {}
                    
                    # Migrate profiles if needed
                    if profiles.get("schema_version", "0.0") != SCHEMA_VERSION_PROFILES:
                        logger.info(f"Migrating profiles to schema version {SCHEMA_VERSION_PROFILES}")
                        profiles["schema_version"] = SCHEMA_VERSION_PROFILES
                        # Save migrated profiles
                        with open(self.profiles_path, "w", encoding="utf-8") as f2:
                            json.dump(profiles, f2, indent=2)
            
            # Filter out schema_version from profile names
            profile_names = [k for k in profiles.keys() if k != "schema_version"]
            if not profile_names:
                self._warn("Load Profile", "No profiles found.")
                return
            
            names = sorted(profile_names)
            item, ok = QtWidgets.QInputDialog.getItem(self, "Load Profile", "Choose profile:", names, 0, False)
            if not ok or not item:
                return
            
            self.apply_profile(profiles.get(item, {}))
            self.current_profile_name = item
            self._save_app_state()
            
            logger.info(f"Profile '{item}' loaded successfully")
        except Exception as exc:
            logger.error(f"Load profile failed: {exc}")
            self._error("Load Profile Failed", str(exc))

    def _show_table_context_menu(self, pos: QtCore.QPoint):
        """Show context menu on table right-click."""
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        
        menu = QtWidgets.QMenu(self)
        
        action_baseline = menu.addAction("Set as Optimizer Baseline")
        action_analysis = menu.addAction("Run Analysis...")
        action_regime = menu.addAction("Regime Analysis (Backtest)…")
        
        action = menu.exec_(self.table.viewport().mapToGlobal(pos))
        
        if action == action_baseline:
            self._set_as_baseline(index.row())
        elif action == action_analysis:
            self._run_analysis(index.row())
        elif action == action_regime:
            self._run_regime_analysis_backtest(index.row())
    
    def _set_as_baseline(self, row_index: int):
        """Set selected row's parameters as optimizer baseline."""
        try:
            if self.current_df.empty or row_index >= len(self.current_df):
                self._warn("Invalid Selection", "No valid row selected.")
                return
            
            row_data = self.current_df.iloc[row_index].to_dict()
            
            # Extract all parameter columns (no longer have param_ prefix after Change 1)
            params = {}
            meta_fields = {}
            
            for col, val in row_data.items():
                # Skip known non-parameter columns
                skip_cols = {'_source_file', 'fold_id', 'bars_total', 'bars_train', 'bars_embargo', 
                           'bars_val', 'val_start', 'val_end', 'total_return', 'sharpe_ratio', 
                           'sortino_ratio', 'calmar_ratio', 'max_drawdown', 'win_rate', 
                           'total_trades', 'profit_factor', 'expectancy', 'start_capital', 
                           'end_capital', 'avg_hold_hours', 'ulcer_index', 'omega_0', 'omega_fees',
                           'chart', 'trial_id', 'method', 'trial_uid', 'score', 'is_pareto',
                           'stability_score', 'group_rank'}
                
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
                self._warn("No Parameters", "No parameter columns found in selected row.")
                return
            
            # Confirm with user
            msg = f"Set {len(params)} parameters as optimizer baseline?\n\n"
            msg += f"Chart: {meta_fields.get('chart', 'N/A')}\n"
            msg += f"Fold: {meta_fields.get('fold_id', 'N/A')}\n"
            msg += f"Calmar: {meta_fields.get('calmar_ratio', 'N/A')}\n"
            msg += f"\nThis will overwrite BASELINE_PARAMS in strategy_params_v2.py"
            
            reply = QtWidgets.QMessageBox.question(
                self, "Confirm Set Baseline", msg,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            
            if reply != QtWidgets.QMessageBox.Yes:
                return
            
            # Path to strategy_params_v2.py
            target_path = os.path.join(
                self.data_dir if self.data_dir else "",
                "..", "config", "strategy_params_v2.py"
            )
            target_path = os.path.normpath(os.path.abspath(target_path))
            
            if not os.path.exists(target_path):
                self._error("File Not Found", f"Could not locate:\n{target_path}")
                return
            
            # Create timestamped backup
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            backup_path = f"{target_path}.backup_{timestamp}"
            
            import shutil
            shutil.copy2(target_path, backup_path)
            logger.info(f"Created backup: {backup_path}")
            
            # Read existing file
            with open(target_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Generate new BASELINE_PARAMS dict
            param_lines = ["BASELINE_PARAMS: Dict[str, Union[float, int, bool]] = {"]
            param_lines.append(f"    # Generated from query interface on {time.strftime('%Y-%m-%d %H:%M:%S')}")
            param_lines.append(f"    # Source: {meta_fields.get('_source_file', 'unknown')}")
            param_lines.append(f"    # Chart: {meta_fields.get('chart', 'N/A')}, Fold: {meta_fields.get('fold_id', 'N/A')}")
            param_lines.append(f"    # Performance: Calmar={meta_fields.get('calmar_ratio', 'N/A'):.4f}, Sharpe={meta_fields.get('sharpe_ratio', 'N/A'):.4f}, MDD={meta_fields.get('max_drawdown', 'N/A'):.2f}%")
            
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
            
            # Replace BASELINE_PARAMS block using regex
            import re
            pattern = r'BASELINE_PARAMS:\s*Dict\[.*?\]\s*=\s*\{[^}]*\}'
            
            if not re.search(pattern, content, re.DOTALL):
                self._error("Parse Error", "Could not find BASELINE_PARAMS block in file.")
                return
            
            new_content = re.sub(pattern, new_baseline_block, content, count=1, flags=re.DOTALL)
            
            # Write updated file
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            logger.info(f"Updated BASELINE_PARAMS in {target_path}")
            
            self._info("Success", 
                      f"Baseline parameters updated!\n\n"
                      f"File: {os.path.basename(target_path)}\n"
                      f"Backup: {os.path.basename(backup_path)}\n"
                      f"Parameters set: {len(params)}")
            
        except Exception as exc:
            logger.error(f"Set baseline failed: {exc}")
            self._error("Set Baseline Failed", str(exc))
    
    def _run_analysis(self, row_index: int):
        """Run performance analysis for selected row."""
        try:
            if self.current_df.empty or row_index >= len(self.current_df):
                self._warn("Invalid Selection", "No valid row selected.")
                return
            
            row_data = self.current_df.iloc[row_index].to_dict()
            
            # Show scope selection dialog
            dialog = AnalysisScopeDialog(row_data, self)
            if dialog.exec_() != QtWidgets.QDialog.Accepted:
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
                self._warn("No Data", "No matching rows found.")
                return
            
            # Generate report
            report_text = self._generate_performance_report(matching_rows, scope, format_type, row_data)
            
            # Show report dialog
            report_dialog = AnalysisReportDialog(report_text, row_data, self)
            report_dialog.exec_()
            
        except Exception as exc:
            logger.error(f"Run analysis failed: {exc}")
            self._error("Analysis Failed", str(exc))
    
    def _find_matching_params(self, row_data: dict, same_chart: bool) -> list:
        """Find rows with matching parameter values."""
        if self.current_df.empty:
            return []
        
        # Extract parameter columns from row_data
        skip_cols = {'_source_file', 'fold_id', 'bars_total', 'bars_train', 'bars_embargo', 
                   'bars_val', 'val_start', 'val_end', 'total_return', 'sharpe_ratio', 
                   'sortino_ratio', 'calmar_ratio', 'max_drawdown', 'win_rate', 
                   'total_trades', 'profit_factor', 'expectancy', 'start_capital', 
                   'end_capital', 'avg_hold_hours', 'ulcer_index', 'omega_0', 'omega_fees',
                   'chart', 'trial_id', 'method', 'trial_uid', 'score', 'is_pareto',
                   'stability_score', 'group_rank'}
        
        param_cols = [col for col in row_data.keys() if col not in skip_cols and col in self.current_df.columns]
        
        if not param_cols:
            return [row_data]
        
        # Build filter condition
        mask = pd.Series([True] * len(self.current_df))
        
        for col in param_cols:
            val = row_data.get(col)
            if pd.isna(val):
                mask &= self.current_df[col].isna()
            else:
                # Handle floating point comparison with tolerance
                if isinstance(val, float):
                    mask &= (self.current_df[col] - val).abs() < 1e-9
                else:
                    mask &= self.current_df[col] == val
        
        if same_chart and 'chart' in self.current_df.columns:
            chart_val = row_data.get('chart')
            if chart_val:
                mask &= self.current_df['chart'] == chart_val
        
        matching_df = self.current_df[mask]
        return matching_df.to_dict('records')
    
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
            lines.append(f"    Total Return: {row.get('total_return', 'N/A'):.2f}%")
            lines.append(f"    Sharpe: {row.get('sharpe_ratio', 'N/A'):.4f}")
            lines.append(f"    Calmar: {row.get('calmar_ratio', 'N/A'):.4f}")
            lines.append(f"    Max Drawdown: {row.get('max_drawdown', 'N/A'):.2f}%")
            lines.append(f"    Total Trades: {row.get('total_trades', 'N/A')}")
            lines.append(f"    Win Rate: {row.get('win_rate', 'N/A'):.2f}%")
            
            if 'val_start' in row and 'val_end' in row:
                lines.append(f"    Val Period: {row.get('val_start')} to {row.get('val_end')}")
            
            if 'bars_train' in row:
                lines.append(f"    Bars: train={row.get('bars_train')}, embargo={row.get('bars_embargo')}, val={row.get('bars_val')}")
        
        lines.append("")
        
        # Chart Analysis Integration
        chart_name = selected_row.get('chart', '')
        if chart_name:
            if format_type == "structured":
                lines.append("-" * 70)
                lines.append("CHART ENVIRONMENT ANALYSIS")
                lines.append("-" * 70)
            else:
                lines.append("\nChart Environment:")
            
            # Try to load chart analysis
            analysis_found = False
            if self.data_dir:
                analyses_dir = os.path.join(self.data_dir, "..", "outputs", "analyses")
                analyses_dir = os.path.normpath(os.path.abspath(analyses_dir))
                
                if os.path.exists(analyses_dir):
                    # Prefer exact match <base>.json, fallback to index.json
                    base_name = os.path.splitext(chart_name)[0]
                    exact_path = os.path.join(analyses_dir, f"{base_name}.json")
                    analysis_data = None
                    if os.path.exists(exact_path):
                        try:
                            with open(exact_path, 'r', encoding='utf-8') as f:
                                analysis_data = json.load(f)
                        except Exception as e:
                            logger.warning(f"Failed to read analysis {exact_path}: {e}")
                    else:
                        # fallback: use index.json to locate latest
                        index_path = os.path.join(analyses_dir, 'index.json')
                        try:
                            with open(index_path, 'r', encoding='utf-8') as f:
                                idx = json.load(f) or {}
                            matches = []
                            for k, entries in idx.items():
                                if os.path.basename(k) == chart_name and entries:
                                    latest = sorted(entries, key=lambda e: e.get('generated_at',''), reverse=True)[0]
                                    matches.append(latest.get('path'))
                            if matches:
                                with open(matches[0], 'r', encoding='utf-8') as f:
                                    analysis_data = json.load(f)
                        except Exception as e:
                            logger.warning(f"Failed to resolve analysis from index.json: {e}")

                    if analysis_data:
                        try:
                            summary = analysis_data.get('summary', {})
                            lines.append(f"Chart: {chart_name}")
                            lines.append(f"  Total Bars: {summary.get('bars', 'N/A')}")
                            lines.append(f"  Timeframe: {summary.get('timeframe', 'N/A')}")
                            lines.append(f"  Date Range: {summary.get('start', 'N/A')} to {summary.get('end', 'N/A')}")
                            
                            trend_dist = summary.get('trend_distribution', {})
                            if trend_dist:
                                lines.append(f"  Trend Distribution (by bars):")
                                for trend, data in trend_dist.items():
                                    lines.append(f"    {trend}: {data.get('pct', 0):.1f}%")
                            vol_dist = summary.get('vol_distribution', {})
                            if vol_dist:
                                lines.append(f"  Volatility Distribution (by bars):")
                                for vol, data in vol_dist.items():
                                    lines.append(f"    {vol}: {data.get('pct', 0):.1f}%")

                            # If regime_avg_ret_per_bar is present, show it (bps)
                            reg_perf = summary.get('regime_avg_ret_per_bar', {})
                            if isinstance(reg_perf, dict) and reg_perf:
                                lines.append("  Avg return per bar by regime (bps):")
                                for label, v in reg_perf.items():
                                    try:
                                        lines.append(f"    {label:<22}: {(float(v) * 100):.3f}")
                                    except Exception:
                                        pass

                            analysis_found = True
                        except Exception as e:
                            logger.warning(f"Failed to load chart analysis: {e}")
            
            if not analysis_found:
                lines.append(f"Chart: {chart_name}")
                lines.append("Status: Not available")
                lines.append("")
                lines.append("To generate chart analysis:")
                
                if self.data_dir:
                    project_dir = os.path.normpath(os.path.abspath(os.path.join(self.data_dir, "..")))
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

    def _run_regime_analysis_backtest(self, row_index: int):
        try:
            if self.current_df.empty or row_index >= len(self.current_df):
                self._warn("Invalid Selection", "No valid row selected.")
                return
            row = self.current_df.iloc[row_index].to_dict()
            trial_uid = str(row.get('trial_uid') or row.get('uid') or "").strip()
            if not trial_uid:
                self._warn("Missing UID", "Selected row has no trial_uid/uid.")
                return

            # Prompt for config
            capital, ok = QtWidgets.QInputDialog.getDouble(self, "Capital", "Starting capital:", 10000.0, 1.0, 1e12, 2)
            if not ok: return
            fees, ok = QtWidgets.QInputDialog.getDouble(self, "Fees", "Fees (decimal, e.g., 0.001 = 0.1%):", 0.001, 0.0, 1.0, 6)
            if not ok: return
            maxpos, ok = QtWidgets.QInputDialog.getInt(self, "Max Positions", "Max concurrent positions:", 3, 1, 100)
            if not ok: return

            if not self.data_dir:
                self._warn("Run Analyzer", "Choose a data folder first (JSON results).")
                return
            project_dir = os.path.normpath(os.path.abspath(os.path.join(self.data_dir, "..")))
            script_path = os.path.join(project_dir, "scripts", "run_regime_analysis.py")
            if not os.path.exists(script_path):
                self._error("Not Found", f"Could not locate analyzer:\n{script_path}")
                return

            import subprocess
            cmd = [
                sys.executable, script_path,
                "--uid", trial_uid,
                "--capital", str(capital),
                "--fees", str(fees),
                "--max-positions", str(maxpos),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                self._error("Analyzer Failed", proc.stdout or proc.stderr or "Unknown error")
                return
            data = json.loads(proc.stdout)
            if not data.get("success", False):
                self._error("Analyzer Error", data.get("error", "Unknown error"))
                return

            # Render concise detailed report
            lines = []
            meta = data.get("meta", {})
            overall = data.get("overall_performance", {})
            lines.append(f"Trial UID: {meta.get('trial_uid')}")
            lines.append(f"Chart: {meta.get('chart')} | Fold: {meta.get('fold_id')}")
            lines.append(f"Capital: ${meta.get('capital'):,.2f} | Fees: {meta.get('fees')} | Max Pos: {meta.get('max_positions')}")
            lines.append("")
            lines.append("OVERALL:")
            lines.append(f"  Return: {overall.get('total_return', 0):.2f}%  | Sharpe: {overall.get('sharpe_ratio', 0):.4f}")
            lines.append(f"  Sortino: {overall.get('sortino_ratio', 0):.4f} | Calmar: {overall.get('calmar_ratio', 0):.4f}")
            lines.append(f"  Max DD: {overall.get('max_drawdown', 0):.2f}% | Trades: {overall.get('total_trades', 0)}")
            lines.append(f"  Win%: {overall.get('win_rate', 0):.2f}% | PF: {overall.get('profit_factor', 0):.2f}")
            lines.append("")
            rb = data.get("regime_breakdown", {})
            if rb:
                lines.append("BY REGIME:")
                for regime, m in sorted(rb.items(), key=lambda kv: kv[1].get('trade_count', 0), reverse=True):
                    lines.append(f"- {regime}:")
                    lines.append(f"    Trades: {m.get('trade_count',0)} | Win%: {m.get('win_rate',0):.2f}%")
                    lines.append(f"    Total PnL: ${m.get('total_pnl',0):.2f} | Avg PnL: ${m.get('avg_pnl',0):.2f}")
                    lines.append(f"    Return: {m.get('total_return_pct',0):.2f}% | Max DD: {m.get('max_drawdown_pct',0):.2f}%")
                    tr = m.get('trades', [])
                    show = min(20, len(tr))
                    if show:
                        lines.append(f"    Trades (first {show}):")
                        for t in tr[:show]:
                            lines.append(f"      {t.get('entry_time')} | {t.get('direction','?'):<5} PnL=${t.get('pnl',0):.2f} ({t.get('pnl_pct',0):.2f}%)")
            else:
                lines.append("No regime breakdown available (no analysis file or no trades).")

            # Show report
            report_dialog = AnalysisReportDialog("\n".join(lines), row, self)
            report_dialog.exec_()
        except Exception as exc:
            logger.error(f"Regime analysis failed: {exc}")
            self._error("Regime Analysis Failed", str(exc))


class AnalysisScopeDialog(QtWidgets.QDialog):
    """Dialog for selecting analysis scope and format."""
    
    def __init__(self, row_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Run Performance Analysis")
        self.resize(450, 280)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Scope selection
        scope_group = QtWidgets.QGroupBox("Analyze scope:")
        scope_layout = QtWidgets.QVBoxLayout(scope_group)
        
        self.radio_fold_only = QtWidgets.QRadioButton("This fold only")
        self.radio_all_folds = QtWidgets.QRadioButton("All folds for this parameter set (same chart)")
        self.radio_all_charts = QtWidgets.QRadioButton("This parameter set across all charts")
        
        self.radio_fold_only.setChecked(True)
        
        scope_layout.addWidget(self.radio_fold_only)
        scope_layout.addWidget(self.radio_all_folds)
        scope_layout.addWidget(self.radio_all_charts)
        
        layout.addWidget(scope_group)
        
        # Format selection
        format_group = QtWidgets.QGroupBox("Report format:")
        format_layout = QtWidgets.QVBoxLayout(format_group)
        
        self.radio_plain = QtWidgets.QRadioButton("Plain text")
        self.radio_structured = QtWidgets.QRadioButton("Structured (sections/tables)")
        
        self.radio_structured.setChecked(True)
        
        format_layout.addWidget(self.radio_plain)
        format_layout.addWidget(self.radio_structured)
        
        layout.addWidget(format_group)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok
        )
        button_box.button(QtWidgets.QDialogButtonBox.Ok).setText("Generate Analysis")
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


class AnalysisReportDialog(QtWidgets.QDialog):
    """Dialog for displaying and saving analysis report."""
    
    def __init__(self, report_text: str, row_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Performance Analysis Report")
        self.resize(800, 600)
        
        self.report_text = report_text
        self.row_data = row_data
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Text display
        self.text_edit = QtWidgets.QPlainTextEdit()
        self.text_edit.setPlainText(report_text)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QtGui.QFont("Courier New", 9))
        
        layout.addWidget(self.text_edit)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        btn_save = QtWidgets.QPushButton("Save Report...")
        btn_close = QtWidgets.QPushButton("Close")
        
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
            trial_uid = self.row_data.get('trial_uid', 'unknown')
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            default_name = f"run_analysis_{trial_uid}_{timestamp}.txt"
            
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save Analysis Report", default_name,
                "Text Files (*.txt);;All Files (*)"
            )
            
            if not file_path:
                return
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.report_text)
            
            QtWidgets.QMessageBox.information(
                self, "Success", f"Report saved to:\n{file_path}"
            )
            
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, "Save Failed", str(exc)
            )


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


