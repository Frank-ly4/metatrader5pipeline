from __future__ import annotations

from typing import Tuple, List

import pandas as pd

import optimization_console as oc


def format_value_for_display(column_name: str, value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        if isinstance(value, (int,)):
            return str(value)
        if isinstance(value, float):
            if oc.is_percent_col(column_name):
                return f"{value * 100:.2f}%"
            return f"{value:.4f}"
        return str(value)
    except Exception:
        return str(value)


def truncate_for_view(df: pd.DataFrame, cap: int = 50_000) -> Tuple[pd.DataFrame, str]:
    if df is None or df.empty:
        return pd.DataFrame(), ""
    if len(df) > cap:
        suffix = f"| Showing 50,000 of {len(df):,}"
        return df.head(cap).copy(), suffix
    return df.copy(), ""


def available_group_columns(df: pd.DataFrame) -> List[str]:
    cols: List[str] = []
    if df is None or df.empty:
        return cols
    if "chart" in df.columns:
        cols.append("chart")
    if "fold_id" in df.columns:
        cols.append("fold_id")
    cols.extend([c for c in df.columns if c.startswith("param_")])
    return cols


def shorten_expression(expr: str, max_len: int = 80) -> str:
    if not expr:
        return "(none)"
    expr = expr.strip()
    if len(expr) <= max_len:
        return expr
    return expr[: max_len - 1] + "…"


