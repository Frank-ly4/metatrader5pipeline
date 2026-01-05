import os
import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner


def _sqlite_url(db_path: str) -> str:
    # Ensure SQLite URL is valid across platforms
    norm = os.path.abspath(db_path).replace("\\", "/")
    return f"sqlite:///{norm}"


def get_or_create_study(
    study_name: str,
    sampler_name: str = "tpe",
    seed: int | None = None,
    direction: str = "maximize",
    use_pruner: bool = True,
):
    """Create or load an Optuna study backed by a SQLite DB under outputs/bayesian_studies/.

    Args:
        study_name: Unique study name.
        sampler_name: 'tpe' (default) | future: 'cmaes'.
        seed: Random seed for reproducibility.
        direction: 'maximize' or 'minimize'.
        use_pruner: Enable MedianPruner.
    """
    # Resolve DB path under project outputs
    here = os.path.dirname(__file__)
    db_dir = os.path.normpath(os.path.join(here, "..", "outputs", "bayesian_studies"))
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, f"{study_name}.db")

    # Sampler
    sampler = TPESampler(seed=seed)

    # Pruner
    pruner = MedianPruner(n_warmup_steps=3) if use_pruner else None

    storage_url = _sqlite_url(db_path)
    study = optuna.create_study(
        study_name=study_name,
        direction=direction,
        storage=storage_url,
        load_if_exists=True,
        sampler=sampler,
        pruner=pruner,
    )
    return study


