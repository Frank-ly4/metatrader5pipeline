import argparse
import os
from typing import List

from optimizer_bayesian.storage import get_or_create_study
from optimizer_bayesian.objective import Objective
from optimizer_bayesian.results_converter import save_study_results

from src.io.data_loader import list_active_chart_paths


def _resolve_charts_arg(arg: str | None) -> List[str]:
    if not arg or arg.lower() == "all":
        return list_active_chart_paths()
    tokens = [t.strip() for t in arg.split(',') if t.strip()]
    return tokens


def main():
    p = argparse.ArgumentParser(description="Bayesian optimizer (Optuna) for v4.2.5 pipeline")
    p.add_argument("--study-name", required=True, help="Unique study name (used for DB file)")
    p.add_argument("--n-trials", type=int, default=50, help="Number of trials")
    p.add_argument("--timeout-s", type=int, default=None, help="Time budget in seconds")
    p.add_argument("--n-jobs", type=int, default=1, help="Parallel workers")
    p.add_argument("--charts", type=str, default="all", help="Comma list of chart names/paths or 'all'")
    p.add_argument("--objective", type=str, choices=["calmar", "sharpe", "composite"], default="calmar")
    p.add_argument("--min-trades", type=int, default=20, help="Minimum total trades across charts")
    p.add_argument("--max-mdd", type=float, default=None, help="Max allowed drawdown [%], e.g., 8.0")
    p.add_argument("--seed", type=int, default=42, help="Random seed")
    p.add_argument("--sampler", type=str, choices=["tpe"], default="tpe")
    p.add_argument("--no-prune", action="store_true", help="Disable pruning")
    
    # Latent-space options
    p.add_argument("--use-latent", action="store_true", help="Enable latent-space guided optimization")
    p.add_argument("--train-vae", action="store_true", help="Train VAE model before optimization")
    p.add_argument("--train-surrogate", action="store_true", help="Train surrogate model before optimization")
    p.add_argument("--exploration-ratio", type=float, default=0.3, help="Fraction of trials for pure exploration")
    
    args = p.parse_args()

    charts = _resolve_charts_arg(args.charts)
    
    # Handle latent model training if requested
    here = os.path.dirname(__file__)
    runs_dir = os.path.normpath(os.path.join(here, "..", "outputs", "runs"))
    models_dir = os.path.normpath(os.path.join(here, "..", "outputs", "latent_models"))
    
    if args.train_vae or args.train_surrogate:
        print("Training latent models...")
        
        if args.train_vae:
            try:
                from optimizer_bayesian.latent.vae_model import train_vae_from_runs
                vae, vae_metrics = train_vae_from_runs(runs_dir, models_dir)
                print(f"VAE training completed (reconstruction error: {vae_metrics['reconstruction_error']:.6f})")
            except Exception as e:
                print(f"VAE training failed: {e}")
        
        if args.train_surrogate:
            try:
                from optimizer_bayesian.latent.surrogate import train_surrogate_from_data
                data_path = os.path.join(models_dir, "training_data.parquet")
                if os.path.exists(data_path):
                    surrogate, surr_metrics = train_surrogate_from_data(data_path, models_dir, args.objective)
                    print(f"Surrogate training completed (score: {surr_metrics['main_model_score']:.4f})")
                else:
                    print("Training data not found. Run with --train-vae first.")
            except Exception as e:
                print(f"Surrogate training failed: {e}")
    
    study = get_or_create_study(
        study_name=args.study_name,
        sampler_name=args.sampler,
        seed=args.seed,
        direction="maximize",
        use_pruner=(not args.no_prune),
    )

    # Create base objective
    base_objective = Objective(
        charts=charts,
        metric=args.objective,
        min_trades=args.min_trades,
        max_mdd=args.max_mdd,
        seed=args.seed,
    )
    
    # Optionally wrap with latent guidance
    if args.use_latent:
        try:
            from optimizer_bayesian.latent.latent_objective import create_latent_objective
            objective = create_latent_objective(
                base_objective=base_objective,
                models_dir=models_dir,
                exploration_ratio=args.exploration_ratio
            )
            print(f"Using latent-guided optimization (exploration ratio: {args.exploration_ratio})")
        except Exception as e:
            print(f"Latent guidance failed, using base objective: {e}")
            objective = base_objective
    else:
        objective = base_objective
        print("Using pure Bayesian optimization")

    study.optimize(
        objective,
        n_trials=int(args.n_trials),
        timeout=int(args.timeout_s) if args.timeout_s else None,
        n_jobs=int(args.n_jobs),
        gc_after_trial=True,
        show_progress_bar=False,
    )

    # Convert to GUI-compatible JSON
    here = os.path.dirname(__file__)
    out_runs_dir = os.path.normpath(os.path.join(here, "..", "outputs", "runs"))
    fpath = save_study_results(study, out_runs_dir)
    print(f"Saved results: {os.path.abspath(fpath)}")


if __name__ == "__main__":
    main()


