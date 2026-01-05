import json
import os
import time
from typing import Any, Dict, List

import optuna


def _map_stats_to_schema(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Map vectorbt stats keys to GUI schema keys.

    Expects keys similar to 'Total Return [%]', 'Sharpe Ratio', 'Calmar Ratio',
    'Max Drawdown [%]', 'Total Trades', 'Win Rate [%]', 'Profit Factor'.
    """
    return {
        "total_return": float(stats.get("Total Return [%]", 0.0)),
        "sharpe_ratio": float(stats.get("Sharpe Ratio", 0.0)),
        "calmar_ratio": float(stats.get("Calmar Ratio", 0.0)),
        "max_drawdown": float(stats.get("Max Drawdown [%]", 0.0)),
        "total_trades": int(stats.get("Total Trades", 0)),
        "win_rate": float(stats.get("Win Rate [%]", 0.0)),
        "profit_factor": float(stats.get("Profit Factor", 0.0)),
    }


def save_study_results(study: optuna.Study, out_runs_dir: str) -> str:
    """Convert study trials to Query GUI-compatible JSON results and save one file.

    Returns path to the saved JSON file.
    """
    os.makedirs(out_runs_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    fname = f"bayesian_{study.study_name}_{ts}.json"
    fpath = os.path.join(out_runs_dir, fname)

    rows: List[Dict[str, Any]] = []

    for tr in study.trials:
        if tr.state != optuna.trial.TrialState.COMPLETE:
            continue

        trial_uid = f"{study.study_name}:{tr.number}"
        params = dict(tr.params)
        per_chart = tr.user_attrs.get("per_chart_stats", [])

        # If we have per-chart stats, emit one result per chart
        if per_chart:
            for st in per_chart:
                chart = st.get("chart", "unknown")
                metrics = _map_stats_to_schema(st.get("stats", {}))
                row = {
                    "method": "bayesian",
                    "trial_uid": trial_uid,
                    "uid": trial_uid,
                    "chart": chart,
                    **metrics,
                    # parameters without param_ prefix (GUI can handle either)
                    **params,
                }
                rows.append(row)
        else:
            # Fallback: a single aggregated row
            row = {
                "method": "bayesian",
                "trial_uid": trial_uid,
                "uid": trial_uid,
                **params,
            }
            rows.append(row)

    payload = {"results": rows}
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return fpath


