from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple
import json

import numpy as np
import pandas as pd
import optuna

from config.strategy_params_v2 import TEST_RANGES
from config.user_inputs import TOGGLES
from config import backtest_user_inputs as B
from config.data import ACTIVE_CHARTS_DIR

from src.io.data_loader import load_chart_from_path, list_active_chart_paths
from src.strategy.bands_v2 import compute_signals
from src.engine.backtest import run_backtest


def _make_json_serializable(obj):
    """Convert pandas/numpy objects to JSON-serializable types."""
    # Handle pandas/numpy types first before checking for NaN
    if isinstance(obj, pd.Series):
        return _make_json_serializable(obj.to_dict())
    elif isinstance(obj, (pd.Timestamp, pd.DatetimeIndex)):
        return str(obj)
    elif isinstance(obj, pd.Timedelta):
        return str(obj)
    elif isinstance(obj, (np.integer, np.int64, np.int32, np.int8, np.int16)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
        return float(obj)
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_json_serializable(item) for item in obj]
    else:
        # Check for scalar NaN last
        try:
            if pd.isna(obj):
                return None
        except (ValueError, TypeError):
            pass
        return obj


class Objective:
    """Optuna objective bridging v4.2.5 engine and Bayesian search.

    Parameters
    ----------
    charts: list of chart names or absolute paths
    metric: objective metric to maximize ('calmar'|'sharpe'|'composite')
    min_trades: minimum total trades across charts to accept a trial
    max_mdd: optional maximum allowed max drawdown (in percent units, e.g., 8.0)
    seed: optional seed to pass into any stochastic components (unused here)
    """

    def __init__(
        self,
        charts: List[str] | None,
        metric: str = "calmar",
        min_trades: int = 20,
        max_mdd: float | None = None,
        seed: int | None = None,
    ) -> None:
        self.metric = metric
        self.min_trades = int(min_trades)
        self.max_mdd = float(max_mdd) if max_mdd is not None else None
        self.seed = seed
        self.charts = self._resolve_charts(charts)

    def _resolve_charts(self, charts: List[str] | None) -> List[str]:
        if charts is None or len(charts) == 0:
            return list_active_chart_paths()
        out: List[str] = []
        for t in charts:
            if os.path.isabs(t) and os.path.exists(t):
                out.append(t)
                continue
            p = os.path.join(ACTIVE_CHARTS_DIR, t)
            if os.path.exists(p):
                out.append(p)
                continue
            if not t.lower().endswith(".csv"):
                p2 = os.path.join(ACTIVE_CHARTS_DIR, f"{t}.csv")
                if os.path.exists(p2):
                    out.append(p2)
        if not out:
            # fallback
            return list_active_chart_paths()
        return out

    def _suggest_params(self, trial: optuna.trial.Trial) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        for name, values in TEST_RANGES.items():
            if not values:
                continue
            # TEST_RANGES contains lists of possible values
            if len(values) == 1:
                # Single value - use it directly
                params[name] = values[0]
            else:
                # Multiple values - let Optuna choose
                if all(isinstance(v, int) for v in values):
                    params[name] = trial.suggest_categorical(name, values)
                elif all(isinstance(v, (int, float)) for v in values):
                    # Mixed int/float or all float - use categorical for exact values
                    params[name] = trial.suggest_categorical(name, values)
                else:
                    # Fallback for other types
                    params[name] = trial.suggest_categorical(name, values)
        return params

    def _calc_objective(self, per_chart_stats: List[Dict[str, Any]]) -> float:
        # Aggregate chosen metric across charts
        vals: List[float] = []
        for st in per_chart_stats:
            stats = st.get("stats", {})
            if not stats:
                continue
                
            if self.metric == "calmar":
                val = stats.get("Calmar Ratio")
                vals.append(float(val) if val is not None else 0.0)
            elif self.metric == "sharpe":
                val = stats.get("Sharpe Ratio")
                vals.append(float(val) if val is not None else 0.0)
            elif self.metric == "composite":
                # Ad-hoc composite; can be made configurable
                cal = stats.get("Calmar Ratio")
                shp = stats.get("Sharpe Ratio")
                pf = stats.get("Profit Factor")
                cal = float(cal) if cal is not None else 0.0
                shp = float(shp) if shp is not None else 0.0
                pf = float(pf) if pf is not None else 0.0
                vals.append(cal + 0.5 * shp + 0.25 * pf)
        if not vals:
            return 0.0
        return float(np.mean(vals))

    def _run_backtests(self, params: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
        """Run backtests for given parameters across all charts.
        
        Separated from __call__ to allow latent-guided objectives to use custom parameters.
        """
        per_chart_stats: List[Dict[str, Any]] = []
        total_trades_all = 0

        for i, chart_path in enumerate(self.charts):
            price = load_chart_from_path(chart_path)
            entries, exits, _ = compute_signals(price, params, TOGGLES)

            cfg = {
                "init_cash": float(getattr(B, "INIT_CAPITAL", 10000.0)),
                "fees": float(getattr(B, "DEFAULT_FEES", 0.001)),
                "max_layers": int(getattr(B, "MAX_PYRAMID_LAYERS", 3)),
                "position_size": float(getattr(B, "POSITION_SIZE", 1.0)),
            }
            pf = run_backtest(price, entries, exits, backtest_overrides=cfg)
            stats = pf.stats()

            # Convert stats to JSON-serializable dict
            stats_dict = _make_json_serializable(stats)

            # Collect
            per_chart_stats.append({
                "chart": os.path.basename(chart_path),
                "stats": stats_dict,
            })
            total_trades_all += int(stats_dict.get("Total Trades", 0))

        return per_chart_stats, total_trades_all

    def __call__(self, trial: optuna.trial.Trial) -> float:
        # 1) Suggest parameters
        params = self._suggest_params(trial)

        # 2) Run backtests using separated method
        per_chart_stats, total_trades_all = self._run_backtests(params)

        # 3) Intermediate reporting for pruning
        for i, _ in enumerate(per_chart_stats):
            trial.report(self._calc_objective(per_chart_stats[:i+1]), step=i)
            if trial.should_prune():
                raise optuna.exceptions.TrialPruned()

        # 4) Constraints
        if total_trades_all < self.min_trades:
            raise optuna.exceptions.TrialPruned("constraint: min_trades")
        if self.max_mdd is not None:
            # Handle potential None values returned from _make_json_serializable
            worst_mdd = max((float(st["stats"].get("Max Drawdown [%]") or 0.0) for st in per_chart_stats), default=0.0)
            if worst_mdd > float(self.max_mdd):
                raise optuna.exceptions.TrialPruned("constraint: max_mdd")

        # 5) Final objective
        value = self._calc_objective(per_chart_stats)

        # Persist details for later conversion (ensure JSON serializable)
        trial.set_user_attr("per_chart_stats", _make_json_serializable(per_chart_stats))
        return value


