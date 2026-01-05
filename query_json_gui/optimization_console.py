"""Optimization Console Analytics Engine

Self-contained analytics helpers for loading, transforming, querying and exporting
optimization/backtest JSON results. Designed to be resilient to missing columns
and heterogeneous JSON schemas. Only depends on pandas/numpy.

Public API:
- load_json_results(paths)
- add_risk_derivatives(df)
- qc_filter(df, min_trades, max_mdd, nondegenerate)
- query_df(df, filter_expr, sort_by, limit)
- composite_score(df, weights)
- pareto_frontier(df, objectives)
- stability_by_params(df, metrics, lambda_std)
- param_spearman(df, metric_cols)
- partial_dependence(df, param, metric, bins)
- topk_per_group(df, group_by, sort_by, k, filter_expr)
- export_df(df, out_dir, name)

Notes
-----
- "max_drawdown" is treated as a fraction (0.08 == 8%). If your data is in %,
  convert before use or rely on query_df percent normalization for filtering.
- Parameters are detected by prefix "param_" when grouping for stability.
"""

from __future__ import annotations

import json
import os
import re
import warnings
from typing import Iterable, List, Optional, Sequence, Tuple
from collections import OrderedDict

import numpy as np
import pandas as pd
import logging


APP_VERSION = "1.1.0"
logger = logging.getLogger("opt_console_ui")

PCT_TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
PCT_TOKEN_SPACED_RE = re.compile(r"(\d+(?:\.\d+)?)\s+%")


def _safe_numeric(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(series, errors="coerce")


def _first_present_column(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _guess_numeric_col(df: pd.DataFrame, name_variants: Sequence[str], default: Optional[str] = None) -> Optional[str]:
    exact = _first_present_column(df, name_variants)
    if exact:
        return exact
    lowered = {c.lower(): c for c in df.columns}
    for v in name_variants:
        vlow = v.lower()
        if vlow in lowered:
            return lowered[vlow]
        for key, original in lowered.items():
            if vlow in key:
                return original
    return default


def _flatten_record(obj: dict) -> dict:
    if not isinstance(obj, dict):
        return {"value": obj}
    out = {}
    for key in ["params", "parameters", "metrics", "results", "meta", "metadata"]:
        if key in obj and isinstance(obj[key], dict):
            for k2, v2 in obj[key].items():
                out_key = f"{key}_{k2}" if key in ("meta", "metadata") else k2
                out[out_key] = v2
    for k, v in obj.items():
        if not isinstance(v, dict):
            out[k] = v
    return out


def load_json_results(paths: Iterable[str]) -> pd.DataFrame:
    records: List[dict] = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except Exception as exc:
            warnings.warn(f"Failed to load {p}: {exc}")
            try:
                logger.warning(f"Failed to load {p}: {exc}")
            except Exception:
                pass
            continue

        def _push(obj: dict):
            flat = _flatten_record(obj)
            flat["_source_file"] = os.path.basename(p)
            for k, v in list(flat.items()):
                if isinstance(v, (list, dict)):
                    try:
                        flat[k] = json.dumps(v)
                    except Exception:
                        flat[k] = str(v)
            records.append(flat)

        if isinstance(data, list):
            for row in data:
                _push(row)
        elif isinstance(data, dict):
            if isinstance(data.get("results"), list):
                for row in data["results"]:
                    _push(row)
            elif isinstance(data.get("records"), list):
                for row in data["records"]:
                    _push(row)
            else:
                _push(data)
        else:
            _push({"value": data})

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame.from_records(records)
    
    # Strip 'param_' prefix from parameter columns for cleaner display
    rename_map = {}
    for col in df.columns:
        if col.startswith('param_'):
            new_name = col[6:]  # Remove 'param_' prefix
            rename_map[col] = new_name
    
    if rename_map:
        df = df.rename(columns=rename_map)
    
    return df


def add_risk_derivatives(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    df = df.copy()
    total_return_col = _guess_numeric_col(df, ["total_return", "net_profit_pct", "net_return", "return", "roi"])
    mdd_col = _guess_numeric_col(df, ["max_drawdown", "mdd", "max_dd", "drawdown"])
    trades_col = _guess_numeric_col(df, ["num_trades", "trades", "n_trades"])
    expectancy_col = _guess_numeric_col(df, ["expectancy", "exp_per_trade", "expected_value"])
    if total_return_col and mdd_col:
        total_return = _safe_numeric(df[total_return_col])
        mdd = _safe_numeric(df[mdd_col]).abs()
        with np.errstate(divide="ignore", invalid="ignore"):
            df["gtp_proxy"] = np.where(mdd > 0, total_return / mdd, np.nan)
    else:
        df["gtp_proxy"] = np.nan
    if expectancy_col:
        df["exp_per_trade"] = _safe_numeric(df[expectancy_col])
    elif total_return_col and trades_col:
        total_return = _safe_numeric(df[total_return_col])
        trades = _safe_numeric(df[trades_col])
        with np.errstate(divide="ignore", invalid="ignore"):
            df["exp_per_trade"] = np.where(trades > 0, total_return / trades, np.nan)
    else:
        df["exp_per_trade"] = np.nan
    if "param_max_consec_losses" in df.columns:
        df["loss_streak_cap"] = _safe_numeric(df["param_max_consec_losses"])  # type: ignore[index]
    elif "max_consec_losses" in df.columns:
        df["loss_streak_cap"] = _safe_numeric(df["max_consec_losses"])  # type: ignore[index]
    else:
        df["loss_streak_cap"] = np.nan
    return df


def qc_filter(df: pd.DataFrame, min_trades: int = 0, max_mdd: float = 1.0, nondegenerate: bool = False) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    df = df.copy()
    trades_col = _guess_numeric_col(df, ["num_trades", "trades", "n_trades"], default=None)
    if trades_col is None:
        df["num_trades"] = 0
        trades_col = "num_trades"
    mdd_col = _guess_numeric_col(df, ["max_drawdown", "mdd", "max_dd", "drawdown"], default=None)
    if mdd_col is None:
        df["max_drawdown"] = np.nan
        mdd_col = "max_drawdown"
    mask = pd.Series(True, index=df.index)
    mask &= _safe_numeric(df[trades_col]) >= float(min_trades)
    mdd_vals = _safe_numeric(df[mdd_col])
    mask &= mdd_vals.isna() | (mdd_vals <= float(max_mdd))
    if nondegenerate:
        core_candidates = [
            _guess_numeric_col(df, ["total_return", "net_return", "net_profit_pct", "roi"]),
            _guess_numeric_col(df, ["profit_factor", "pf"]),
            _guess_numeric_col(df, ["sharpe_ratio", "sharpe"]),
            _guess_numeric_col(df, ["calmar_ratio", "calmar"]),
            _guess_numeric_col(df, ["sortino_ratio", "sortino"]),
        ]
        core_cols = [c for c in core_candidates if c]
        if core_cols:
            zero_core = (_safe_numeric(df[trades_col]) == 0)
            zero_core &= _safe_numeric(df[core_cols]).fillna(0).abs().sum(axis=1) == 0
            mask &= ~zero_core
    return df.loc[mask].reset_index(drop=True)


def _normalize_percent_tokens(expr: str) -> str:
    """Normalize percent tokens in expressions.
    
    Handles: 10%, 10 %, 0.10 with % form taking precedence.
    """
    if not expr:
        return expr
    
    # First handle spaced percentages (10 %) - these take precedence
    expr = PCT_TOKEN_SPACED_RE.sub(lambda m: str(float(m.group(1)) / 100.0), expr)
    
    # Then handle regular percentages (10%)
    expr = PCT_TOKEN_RE.sub(lambda m: str(float(m.group(1)) / 100.0), expr)
    
    return expr


def normalize_percent_expr(expr: str) -> str:
    """Public helper to normalize percent tokens in filter expressions.

    Accepts inputs like "8%", "8 %", or "0.08". Percentage forms are
    converted to decimal fractions, with spaced percent taking precedence
    when both appear within a token.
    """
    return _normalize_percent_tokens(expr)


def _parse_sort_by(sort_by: Optional[str]) -> Tuple[List[str], List[bool]]:
    cols: List[str] = []
    asc: List[bool] = []
    if not sort_by:
        return cols, asc
    for token in [t.strip() for t in str(sort_by).split(',') if t.strip()]:
        if token.startswith('-'):
            cols.append(token[1:])
            asc.append(False)
        else:
            cols.append(token)
            asc.append(True)
    return cols, asc


def query_df(
    df: pd.DataFrame,
    filter_expr: Optional[str] = None,
    sort_by: Optional[str] = None,
    limit: int = 0,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    out = df.copy()
    if filter_expr and str(filter_expr).strip():
        expr = _normalize_percent_tokens(str(filter_expr))
        try:
            out = out.query(expr, engine="python")
        except Exception as exc:
            warnings.warn(f"query_df failed, returning unfiltered DF. Error: {exc}")
    if sort_by:
        cols, asc = _parse_sort_by(sort_by)
        present = [c for c in cols if c in out.columns]
        if present:
            asc2 = [asc[cols.index(c)] for c in present]
            out = out.sort_values(by=present, ascending=asc2, kind="mergesort")
    if isinstance(limit, (int, np.integer)) and int(limit) > 0:
        out = out.head(int(limit))
    out = out.reset_index(drop=True)
    return out


def composite_score(
    df: pd.DataFrame,
    weights: Optional[dict] = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    if weights is None:
        weights = {"Sharpe": 1.0, "Sortino": 0.5, "Calmar": 1.0, "PF": 0.5, "MDD": -1.0}
    df = df.copy()
    col_map = {
        "Sharpe": _guess_numeric_col(df, ["sharpe_ratio", "sharpe"]),
        "Sortino": _guess_numeric_col(df, ["sortino_ratio", "sortino"]),
        "Calmar": _guess_numeric_col(df, ["calmar_ratio", "calmar"]),
        "PF": _guess_numeric_col(df, ["profit_factor", "pf"]),
        "MDD": _guess_numeric_col(df, ["max_drawdown", "mdd", "max_dd", "drawdown"]),
    }
    score = pd.Series(0.0, index=df.index)
    for logical, w in weights.items():
        col = col_map.get(logical)
        if not col:
            continue
        s = _safe_numeric(df[col]).fillna(0.0)
        score = score + (float(w) * s)
    df["composite_score"] = score
    df = df.sort_values(by=["composite_score"], ascending=[False]).reset_index(drop=True)
    return df


def pareto_frontier(
    df: pd.DataFrame,
    objectives: Sequence[Tuple[str, str]] = (("calmar_ratio", "max"), ("max_drawdown", "min"), ("profit_factor", "max")),
) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    
    # Validate required columns for default Pareto objectives
    if objectives == (("calmar_ratio", "max"), ("max_drawdown", "min"), ("profit_factor", "max")):
        required = ["calmar_ratio", "max_drawdown", "profit_factor"]
        missing = require_columns(df, required)
        if missing:
            raise ValueError(f"Pareto analysis requires columns: {missing}")
    
    cols: List[str] = []
    dirs: List[int] = []
    for col, direction in objectives:
        actual_col = _guess_numeric_col(df, [col]) or col
        if actual_col not in df.columns:
            continue
        cols.append(actual_col)
        dirs.append(1 if str(direction).lower().startswith("max") else -1)
    if not cols:
        return df.head(0)
    M = np.column_stack([_safe_numeric(df[c]).to_numpy() for c in cols])
    dir_arr = np.array(dirs, dtype=float)
    M_dir = M * dir_arr
    n = M_dir.shape[0]
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        better_equal = (M_dir >= M_dir[i]).all(axis=1)
        strictly_better = (M_dir > M_dir[i]).any(axis=1)
        dominated_by_j = better_equal & strictly_better
        dominated_by_j[i] = False
        if dominated_by_j.any():
            keep[i] = False
    res = df.loc[keep].copy().reset_index(drop=True)
    return res


def _param_columns(df: pd.DataFrame) -> List[str]:
    params = [c for c in df.columns if c.startswith("param_")]
    if params:
        return params
    params = [c for c in df.columns if "param" in c.lower()]
    return params


def list_param_cols(df: pd.DataFrame) -> List[str]:
    """Return list of parameter columns (param_* prefix)."""
    return [c for c in df.columns if c.startswith("param_")]


def is_percent_col(name: str) -> bool:
    """Return True if column name represents a percentage field."""
    return name in ("max_drawdown", "win_rate")


def require_columns(df: pd.DataFrame, cols: List[str]) -> Optional[List[str]]:
    """Check if required columns exist in DataFrame.
    
    Returns:
        None if all columns present, otherwise list of missing columns.
    """
    if df is None or df.empty:
        return cols if cols else None
    
    missing = [col for col in cols if col not in df.columns]
    return missing if missing else None


def stability_by_params(
    df: pd.DataFrame,
    metrics: Sequence[str] = ("calmar_ratio", "profit_factor", "max_drawdown"),
    lambda_std: float = 0.5,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    
    # Validate required columns for stability analysis
    params = _param_columns(df)
    if not params:
        raise ValueError("Stability analysis requires at least one param_* column")
    
    # Check for at least one required metric
    required_metrics = ["calmar_ratio", "profit_factor", "max_drawdown"]
    available_metrics = [m for m in required_metrics if m in df.columns]
    if not available_metrics:
        raise ValueError(f"Stability analysis requires at least one metric from: {required_metrics}")
    
    metric_cols = []
    for m in metrics:
        col = _guess_numeric_col(df, [m]) or m
        if col in df.columns:
            metric_cols.append(col)
    if not metric_cols:
        return pd.DataFrame()
    group = df.groupby(params, dropna=False)
    rows = []
    for keys, g in group:
        row = {}
        if not isinstance(keys, tuple):
            keys = (keys,)
        for kname, kval in zip(params, keys):
            row[kname] = kval
        robust_vals = []
        for col in metric_cols:
            s = _safe_numeric(g[col])
            mean, std = float(s.mean()), float(s.std(ddof=0))
            try:
                q25 = float(s.quantile(0.25))
                q50 = float(s.quantile(0.50))
                q75 = float(s.quantile(0.75))
            except Exception:
                q25 = q50 = q75 = np.nan
            if "drawdown" in col.lower():
                robust = -(mean + lambda_std * std)
            else:
                robust = mean - lambda_std * std
            row[f"robust_{col}"] = robust
            row[f"mean_{col}"] = mean
            row[f"std_{col}"] = std
            row[f"q25_{col}"] = q25
            row[f"q50_{col}"] = q50
            row[f"q75_{col}"] = q75
            robust_vals.append(robust)
        row["n"] = int(len(g))
        row["stability_score"] = float(np.nanmean(robust_vals)) if robust_vals else np.nan
        rows.append(row)
    out = pd.DataFrame(rows)
    if "stability_score" in out.columns:
        out = out.sort_values("stability_score", ascending=False)
    return out.reset_index(drop=True)


def param_spearman(
    df: pd.DataFrame,
    metric_cols: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    params = _param_columns(df)
    if not params:
        return pd.DataFrame()
    if metric_cols is None:
        metric_cols = [
            _guess_numeric_col(df, ["calmar_ratio", "calmar"]),
            _guess_numeric_col(df, ["profit_factor", "pf"]),
            _guess_numeric_col(df, ["max_drawdown", "mdd", "drawdown"]),
            _guess_numeric_col(df, ["sharpe_ratio", "sharpe"]),
            _guess_numeric_col(df, ["sortino_ratio", "sortino"]),
            _guess_numeric_col(df, ["gtp_proxy"]),
        ]
        metric_cols = [c for c in metric_cols if c]
    if not metric_cols:
        return pd.DataFrame()
    enc_params = {}
    for p in params:
        s = df[p]
        if pd.api.types.is_numeric_dtype(s):
            enc_params[p] = _safe_numeric(s)
        else:
            codes, _ = pd.factorize(s, na_sentinel=-1)
            enc_params[p] = pd.Series(codes, index=df.index, dtype=float)
    X = pd.DataFrame(enc_params)
    Y = pd.DataFrame({m: _safe_numeric(df[m]) for m in metric_cols})
    combined = pd.concat([X, Y], axis=1)
    corr = combined.corr(method="spearman")
    res = corr.loc[X.columns, Y.columns]
    return res


def partial_dependence(
    df: pd.DataFrame,
    param: str,
    metric: str,
    bins: int = 8,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["param_bin", "param_bin_mid", "metric_mean", "count"])
    if param not in df.columns or metric not in df.columns:
        p_actual = _guess_numeric_col(df, [param]) or param
        m_actual = _guess_numeric_col(df, [metric]) or metric
    else:
        p_actual, m_actual = param, metric
    if p_actual not in df.columns or m_actual not in df.columns:
        return pd.DataFrame(columns=["param_bin", "param_bin_mid", "metric_mean", "count"])
    p = _safe_numeric(df[p_actual])
    y = _safe_numeric(df[m_actual])
    try:
        bins_s = pd.qcut(p, q=max(1, int(bins)), duplicates="drop")
    except Exception:
        try:
            bins_s = pd.cut(p, bins=max(1, int(bins)))
        except Exception:
            return pd.DataFrame(columns=["param_bin", "param_bin_mid", "metric_mean", "count"])
    grouped = pd.DataFrame({"param_bin": bins_s, "metric": y}).dropna()
    agg = grouped.groupby("param_bin").agg(metric_mean=("metric", "mean"), count=("metric", "size")).reset_index()
    mids: List[float] = []
    for interval in agg["param_bin"]:
        if hasattr(interval, "mid"):
            mids.append(float(interval.mid))
        else:
            try:
                left = float(interval.left)
                right = float(interval.right)
                mids.append((left + right) / 2.0)
            except Exception:
                mids.append(np.nan)
    agg["param_bin_mid"] = mids
    agg = agg.sort_values("param_bin_mid").reset_index(drop=True)
    return agg[["param_bin", "param_bin_mid", "metric_mean", "count"]]


def topk_per_group(
    df: pd.DataFrame,
    group_by: Sequence[str] | str,
    sort_by: str,
    k: int,
    filter_expr: Optional[str] = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    
    # Validate required sort_by column exists
    cols, asc = _parse_sort_by(sort_by)
    if cols:
        missing = require_columns(df, cols)
        if missing:
            raise ValueError(f"Top-k analysis requires sort_by columns: {missing}")
    
    work = df.copy()
    if filter_expr and str(filter_expr).strip():
        work = query_df(work, filter_expr=filter_expr)
    if isinstance(group_by, str):
        group_cols = [c.strip() for c in group_by.split(',') if c.strip()]
    else:
        group_cols = list(group_by)
    if not group_cols:
        return pd.DataFrame()
    if not cols:
        return (
            work.groupby(group_cols, dropna=False)
            .head(k)
            .reset_index(drop=True)
        )
    present = [c for c in cols if c in work.columns]
    if present:
        asc2 = [asc[cols.index(c)] for c in present]
        work = work.sort_values(by=present, ascending=asc2, kind="mergesort")
    res = work.groupby(group_cols, dropna=False).head(k).reset_index(drop=True)
    return res


def export_df(df: pd.DataFrame, out_dir: str, name: str, meta: Optional[dict] = None) -> Tuple[str, Optional[str], str]:
    """Export DataFrame with sidecar metadata.
    
    Returns:
        Tuple of (csv_path, parquet_path, sidecar_path)
    """
    if df is None or df.empty:
        raise ValueError("Nothing to export: DataFrame is empty.")
    if not name:
        name = "export"
    
    # Ensure Unicode path handling
    os.makedirs(out_dir, exist_ok=True)
    
    # Export CSV with UTF-8 encoding
    csv_path = os.path.join(out_dir, f"{name}.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8")
    
    # Export Parquet if available
    parquet_path: Optional[str] = None
    try:
        import pyarrow  # noqa: F401
        parquet_path = os.path.join(out_dir, f"{name}.parquet")
        df.to_parquet(parquet_path, index=False, engine="pyarrow")
    except Exception:
        parquet_path = None
    
    # Create sidecar metadata
    from datetime import datetime
    
    # Build EXACT keys in required order
    meta = meta or {}
    sidecar_meta = OrderedDict()
    sidecar_meta["app_version"] = APP_VERSION
    sidecar_meta["timestamp_utc"] = datetime.utcnow().isoformat() + "Z"
    sidecar_meta["profile_name"] = meta.get("profile_name", "None")
    sidecar_meta["qc_params"] = meta.get("qc_params", {})
    sidecar_meta["filter_expr"] = meta.get("filter_expr", None)
    sidecar_meta["sort_by"] = meta.get("sort_by", None)
    sidecar_meta["limit"] = meta.get("limit", None)
    sidecar_meta["group_by"] = meta.get("group_by", None)
    sidecar_meta["objectives_weights"] = meta.get("objectives_weights", None)
    sidecar_meta["visible_columns"] = meta.get("visible_columns", list(df.columns))
    sidecar_meta["_source_files"] = (
        sorted(df["_source_file"].unique().tolist()) if "_source_file" in df.columns else []
    )
    sidecar_meta["row_count"] = int(len(df))
    
    # Write sidecar JSON with UTF-8 encoding
    sidecar_path = os.path.join(out_dir, f"{name}.meta.json")
    with open(sidecar_path, "w", encoding="utf-8", errors="replace") as f:
        json.dump(sidecar_meta, f, indent=2, ensure_ascii=False)
    
    return csv_path, parquet_path, sidecar_path


__all__ = [
    "load_json_results",
    "add_risk_derivatives",
    "qc_filter",
    "query_df",
    "composite_score",
    "pareto_frontier",
    "stability_by_params",
    "param_spearman",
    "partial_dependence",
    "topk_per_group",
    "export_df",
    "list_param_cols",
    "is_percent_col",
    "require_columns",
]


