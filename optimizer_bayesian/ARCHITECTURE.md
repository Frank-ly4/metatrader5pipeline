# Architecture: Bayesian + Latent-Space Optimizer Integration

## Overview

This module integrates Optuna (Bayesian optimization) with optional latent-space reasoning and the existing v4.2.5 backtesting engine. It provides both pure Bayesian optimization and an advanced latent-enhanced mode that learns from historical optimization data.

## Data Flow

### Pure Bayesian Mode
```
run_optimizer_bayesian.bat
  -> optimizer_bayesian/run.py (CLI)
    -> storage.get_or_create_study()  (Optuna study + SQLite storage)
    -> Objective(...)                 (bridges to v4.2.5 engine)
      -> for each trial: suggest params from TEST_RANGES
      -> for each chart: load_chart_from_path()
           -> compute_signals(params, TOGGLES)
           -> run_backtest(price, entries, exits, overrides)
           -> collect stats; report intermediate for pruning
      -> aggregate objective; set user_attrs; return value
    -> results_converter.save_study_results(study)
      -> writes outputs/runs/bayesian_<study>_<timestamp>.json
```

### Latent-Enhanced Mode
```
run_optimizer_bayesian.bat --use-latent
  -> optimizer_bayesian/run.py (CLI)
    -> latent/data_collector.py (if --train-vae)
      -> extract params+performance from outputs/runs/*.json
      -> save outputs/latent_models/training_data.parquet
    -> latent/vae_model.py (if --train-vae)
      -> train parameter embeddings (62 params -> 6 latent dims)
      -> save outputs/latent_models/parameter_vae.pkl
    -> latent/surrogate.py (if --train-surrogate)  
      -> train XGBoost performance predictor
      -> save outputs/latent_models/surrogate_model.pkl
    -> latent/latent_objective.py
      -> load trained models
      -> hybrid strategy: exploration + latent-guided exploitation
      -> sample near historically good parameters
      -> use surrogate for candidate screening
    -> results saved same as pure Bayesian mode
```

## Key Connection Points

- **Search Space**: `config/strategy_params_v2.py::TEST_RANGES` (62 parameters)
- **Backtest Engine**: `src/engine/backtest.py` (VectorBT integration)
- **Strategy Signals**: `src/strategy/bands_v2.py::compute_signals` (bands_v2 strategy)
- **Runtime Settings**: `config/backtest_user_inputs.py` (capital, fees, size, max layers)
- **Chart Data**: `src/io/data_loader.py::load_chart_from_path`, `config/data.py::ACTIVE_CHARTS_DIR`
- **Study Storage**: `outputs/bayesian_studies/<study>.db` (SQLite, resumable)
- **Model Storage**: `outputs/latent_models/` (VAE, surrogate, training data)
- **Results Output**: `outputs/runs/bayesian_<study>_<ts>.json` (Query GUI compatible)

## Objective

Default objective maximizes Calmar Ratio averaged across selected charts. Constraints prune trials early if:

- Total trades across charts < `--min-trades`
- Worst Max Drawdown [%] across charts > `--max-mdd` (if provided)

## Resumability

Studies are stored under `outputs/bayesian_studies/` in SQLite DBs; re-running with the same `--study-name` resumes.

## Latent-Space Components

### Parameter VAE (Variational Autoencoder)
- **Purpose**: Learn 6-dimensional embedding of 62-parameter space
- **Architecture**: MLPRegressor encoder/decoder with PCA initialization
- **Training**: Reconstruction loss on normalized parameter vectors
- **Usage**: Sample new parameters near historically good ones

### Surrogate Model
- **Purpose**: Fast performance prediction (XGBoost or scikit-learn)
- **Training**: Parameter vectors → Calmar ratio prediction
- **Uncertainty**: Ensemble of 5 models provides confidence estimates
- **Usage**: Screen candidates before expensive backtest evaluation

### Hybrid Strategy
- **Exploration Phase**: Pure Bayesian search (30% of trials by default)
- **Exploitation Phase**: Latent-guided search near good parameter regions
- **Adaptive**: Increases exploitation when finding performance improvements
- **Fallback**: Gracefully degrades to pure Bayesian if models unavailable

## GUI Compatibility

`results_converter.py` emits a JSON with `{"results": [...]}` where each row:

- Includes `method="bayesian"`, `trial_uid`, `chart`, metrics, and all chosen parameters (no `param_` prefix).
- Additional metadata: `strategy="bayesian_exploration"` or `strategy="latent_guided"`
- Can be loaded directly by the Query GUI for analysis and regime studies.


