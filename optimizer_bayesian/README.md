# Bayesian Optimizer (Optuna) for v4.2.5

This module adds intelligent Bayesian optimization using Optuna, with optional latent-space reasoning for industry-leading parameter search. It reuses the existing v4.2.5 backtest engine and strategy, saving results in Query GUI-compatible format.

## Features

- **Pure Bayesian**: TPE (Tree-structured Parzen Estimator) for intelligent parameter search
- **Latent-Space Enhanced**: VAE-guided parameter exploration in learned embedding space  
- **Surrogate Acceleration**: Fast performance prediction to guide expensive backtests
- **Constraint Handling**: Early pruning of infeasible solutions
- **Study Persistence**: Resume optimization runs from where you left off

## Quickstart

### Basic Bayesian Optimization
1. Ensure dependencies are installed: `pip install optuna SQLAlchemy scikit-learn`
2. Prepare your active charts under `data/active_charts/`
3. Run:

```bash
run_optimizer_bayesian.bat --study-name my_study --n-trials 50 --charts all --objective calmar --min-trades 20 --seed 42
```

### Advanced: Latent-Space Enhanced
1. First, train models on existing optimization data:
```bash
run_optimizer_bayesian.bat --study-name training --train-vae --train-surrogate
```

2. Then run latent-guided optimization:
```bash
run_optimizer_bayesian.bat --study-name advanced --n-trials 50 --use-latent --exploration-ratio 0.2
```

This creates `outputs/bayesian_studies/my_study.db` and results JSON in `outputs/runs/`.

## CLI Arguments

### Basic Options
- `--study-name` (required): Unique name; determines the DB filename.
- `--n-trials`: Number of trials (default 50).
- `--timeout-s`: Optional wall-clock limit (seconds).
- `--n-jobs`: Parallel workers (default 1).
- `--charts`: Comma list of chart names/paths or `all`.
- `--objective`: `calmar` | `sharpe` | `composite`.
- `--min-trades`: Minimum total trades across charts to accept a trial.
- `--max-mdd`: Maximum allowed drawdown in percent, e.g. `8.0`.
- `--sampler`: `tpe` (default).
- `--seed`: Random seed for sampler.
- `--no-prune`: Disable pruning (MedianPruner is enabled by default).

### Latent-Space Options
- `--use-latent`: Enable latent-space guided optimization.
- `--train-vae`: Train VAE model on existing optimization data before running.
- `--train-surrogate`: Train surrogate model for fast performance prediction.
- `--exploration-ratio`: Fraction of trials for pure exploration (default 0.3).

## Outputs

- Study DB: `outputs/bayesian_studies/<study>.db` for resuming.
- Results JSON: `outputs/runs/bayesian_<study>_<timestamp>.json` (Query GUI compatible).

## Notes

- Parameter search space comes from `config/strategy_params_v2.py::TEST_RANGES`.
- Backtest settings (capital, fees, size, max_layers) come from `config/backtest_user_inputs.py`.
- The objective runs the same `compute_signals` and `run_backtest` as other v4.2.5 tools.


