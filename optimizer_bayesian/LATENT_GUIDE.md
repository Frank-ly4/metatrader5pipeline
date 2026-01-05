# Latent-Space Optimization Guide

## Overview

The latent-space enhancement learns from your historical optimization runs to guide future parameter searches more intelligently. Instead of treating parameters as independent dimensions, it discovers parameter interactions and focuses search on regions that have historically produced good results.

## When to Use Latent-Space Optimization

### ✅ **Use Latent-Space When:**
- You have >500 historical optimization trials from previous runs
- Parameter space is high-dimensional (>10 parameters)  
- You want to find better solutions with fewer trials
- You're doing production optimization runs (not initial exploration)

### ❌ **Use Pure Bayesian When:**
- First time running optimization (no historical data)
- Exploring completely new parameter ranges
- Quick experimentation with different objectives
- Parameter space is simple (<5 parameters)

## Step-by-Step Usage

### Step 1: Prepare Training Data
Ensure you have existing optimization results in `outputs/runs/`:
```bash
# Check if you have enough data
ls outputs/runs/*.json | wc -l  # Should show >5 files with >100 trials each
```

### Step 2: Train Models
Train the VAE and surrogate models on your historical data:
```bash
run_optimizer_bayesian.bat --study-name model_training --train-vae --train-surrogate
```

This creates:
- `outputs/latent_models/parameter_vae.pkl` - Parameter embedding model
- `outputs/latent_models/surrogate_model.pkl` - Fast performance predictor  
- `outputs/latent_models/training_data.parquet` - Processed training data

### Step 3: Run Latent-Guided Optimization
```bash
run_optimizer_bayesian.bat --study-name production --n-trials 100 --use-latent --exploration-ratio 0.2
```

## Understanding the Hybrid Strategy

### Exploration vs Exploitation Balance
- **Exploration (30% default)**: Pure Bayesian search in unexplored regions
- **Exploitation (70%)**: Latent-guided search near historically good parameters

### Adaptive Behavior
- **Early trials**: More exploration to gather diverse data
- **Later trials**: More exploitation as good regions are identified
- **Performance-based**: Increases exploitation when finding improvements

## Model Training Details

### Parameter VAE (Variational Autoencoder)
- **Purpose**: Learn meaningful parameter embeddings
- **Architecture**: Neural network encoder/decoder with 6-dimensional latent space
- **Training**: Uses reconstruction loss to preserve parameter relationships
- **Output**: Can sample new parameters "near" high-performing ones

### Surrogate Model  
- **Purpose**: Fast performance prediction without running full backtests
- **Model**: XGBoost (preferred) or scikit-learn Gradient Boosting
- **Uncertainty**: Ensemble of 5 models provides confidence estimates
- **Usage**: Screen candidates before expensive backtest evaluation

## Performance Expectations

### Convergence Speed
- **Pure Random**: Linear improvement, needs 1000+ trials
- **Pure Bayesian**: 3-5x faster than random
- **Latent-Enhanced**: 2-3x faster than pure Bayesian

### Quality of Solutions
- **Latent-Enhanced**: Often finds better final solutions by exploiting parameter interactions
- **Robustness**: Less sensitive to local optima due to latent-space smoothing

## Troubleshooting

### "No latent models found"
- Run with `--train-vae --train-surrogate` first
- Ensure `outputs/runs/` contains optimization JSON files

### "Insufficient training data"
- Need >100 historical trials for effective training
- Run more basic optimization first to build training data

### "VAE training failed"
- Check that historical data has consistent parameter names
- Ensure scikit-learn is installed: `pip install scikit-learn`

### Poor latent performance
- Try different `--exploration-ratio` (0.1 to 0.5)
- Retrain models if parameter ranges have changed significantly
- Verify training data quality (remove degenerate trials)

## Advanced Usage

### Custom Exploration Ratios
```bash
# More exploitation (faster convergence, risk of local optima)
--exploration-ratio 0.1

# More exploration (slower but more robust)
--exploration-ratio 0.5
```

### Model Retraining
Retrain models when you have new optimization data:
```bash
run_optimizer_bayesian.bat --study-name retrain --train-vae --train-surrogate
```

### Combining with Query GUI
1. Run latent-enhanced optimization
2. Load results in Query GUI for analysis
3. Use "Set as Baseline" for promising parameter sets
4. Run regime analysis for detailed performance breakdown

## Technical Notes

- **Parameter Normalization**: All parameters normalized to [0,1] for VAE training
- **Memory Usage**: Models are lightweight (~1-10MB each)
- **Training Time**: VAE ~2-5 minutes, Surrogate ~1-2 minutes on typical datasets
- **Thread Safety**: Models are loaded per-process, safe for parallel optimization
