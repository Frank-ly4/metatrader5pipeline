import os
import sys
import time
from typing import List, Optional

import optuna

from optimizer_bayesian.storage import get_or_create_study
from optimizer_bayesian.objective import Objective
from optimizer_bayesian.results_converter import save_study_results


def _project_root() -> str:
    return os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _studies_dir() -> str:
    return os.path.join(_project_root(), "outputs", "bayesian_studies")


def _runs_dir() -> str:
    return os.path.join(_project_root(), "outputs", "runs")


def _list_studies() -> List[str]:
    sdir = _studies_dir()
    if not os.path.exists(sdir):
        return []
    names: List[str] = []
    for f in os.listdir(sdir):
        if f.lower().endswith('.db'):
            names.append(os.path.splitext(f)[0])
    return sorted(names)


def _prompt(msg: str, default: str = "") -> str:
    s = input(f"{msg} [{default}]: ").strip()
    return s if s else default


def _resolve_charts(arg: str) -> List[str]:
    # Accept 'all' or comma-separated basenames. Defer actual path resolution to data loader / objective
    if not arg or arg.lower() == "all":
        return ["all"]
    toks = [t.strip() for t in arg.split(',') if t.strip()]
    return toks


def _run_optimize(study_name: str, charts: List[str], n_trials: int, objective_metric: str, min_trades: int, max_mdd: Optional[float]) -> None:
    study = get_or_create_study(study_name=study_name, seed=42, direction="maximize")
    obj = Objective(charts=charts, metric=objective_metric, min_trades=min_trades, max_mdd=max_mdd, seed=42)
    print(f"\nStarting optimization: study={study_name}, trials={n_trials}, charts={charts}, objective={objective_metric}")
    t0 = time.time()
    study.optimize(obj, n_trials=n_trials, show_progress_bar=False)
    dt = time.time() - t0
    
    # Check if any trials completed successfully
    try:
        best_value = study.best_trial.value
        print(f"Finished in {dt/60:.1f} min. Best value: {best_value:.6f}")
        fpath = save_study_results(study, _runs_dir())
        print(f"Saved results: {fpath}")
    except ValueError:
        print(f"Finished in {dt/60:.1f} min. No successful trials found (all trials were pruned).")
        print("Consider relaxing constraints (min_trades or max_mdd) or adjusting parameter ranges.")


def _show_best(study_name: str) -> None:
    storage_url = f"sqlite:///{os.path.join(_studies_dir(), study_name + '.db').replace('\\', '/')}"
    study = optuna.load_study(study_name=study_name, storage=storage_url)
    
    try:
        bt = study.best_trial
        print(f"\nBest for {study_name}: value={bt.value:.6f}")
        print("Params:")
        for k, v in bt.params.items():
            print(f"  {k}: {v}")
    except ValueError:
        print(f"\nNo successful trials found for study '{study_name}' (all trials were pruned).")
        print("The study exists but has no completed trials to report.")


def menu() -> None:
    print("\n=== Bayesian Optimizer Menu ===")
    print("1) Create new study")
    print("2) Resume existing study")
    print("3) Show best trial of a study")
    print("4) Exit")
    while True:
        choice = _prompt("Choose option", "1")
        if choice == "1":
            study = _prompt("Study name", "my_study")
            charts = _resolve_charts(_prompt("Charts (all or comma list)", "all"))
            n_trials = int(_prompt("Number of trials", "50"))
            objective_metric = _prompt("Objective (calmar/sharpe/composite)", "calmar")
            min_trades = int(_prompt("Minimum total trades", "10"))
            max_mdd_raw = _prompt("Max drawdown % (blank=disable)", "")
            max_mdd = float(max_mdd_raw) if max_mdd_raw else None
            _run_optimize(study, charts, n_trials, objective_metric, min_trades, max_mdd)
        elif choice == "2":
            studies = _list_studies()
            if not studies:
                print("No studies found.")
                continue
            print("\nExisting studies:")
            for i, s in enumerate(studies, 1):
                print(f"  {i}. {s}")
            sel = _prompt("Select study number", "1")
            try:
                idx = int(sel) - 1
                study = studies[idx]
            except Exception:
                print("Invalid selection.")
                continue
            charts = _resolve_charts(_prompt("Charts (all or comma list)", "all"))
            n_trials = int(_prompt("Additional trials", "50"))
            objective_metric = _prompt("Objective (calmar/sharpe/composite)", "calmar")
            min_trades = int(_prompt("Minimum total trades", "10"))
            max_mdd_raw = _prompt("Max drawdown % (blank=disable)", "")
            max_mdd = float(max_mdd_raw) if max_mdd_raw else None
            _run_optimize(study, charts, n_trials, objective_metric, min_trades, max_mdd)
        elif choice == "3":
            studies = _list_studies()
            if not studies:
                print("No studies found.")
                continue
            print("\nExisting studies:")
            for i, s in enumerate(studies, 1):
                print(f"  {i}. {s}")
            sel = _prompt("Select study number", "1")
            try:
                idx = int(sel) - 1
                study_name = studies[idx]
            except Exception:
                print("Invalid selection.")
                continue
            _show_best(study_name)
        elif choice == "4":
            break
        else:
            print("Invalid option.")


if __name__ == "__main__":
    menu()


