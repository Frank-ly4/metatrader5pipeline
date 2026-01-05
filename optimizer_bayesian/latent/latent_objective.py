"""Latent-guided objective function for hybrid Bayesian optimization."""

import os
import numpy as np
import optuna
from typing import Dict, List, Any, Optional

from optimizer_bayesian.objective import Objective
from optimizer_bayesian.latent.vae_model import ParameterVAE
from optimizer_bayesian.latent.surrogate import PerformanceSurrogate
from config.strategy_params_v2 import TEST_RANGES


class LatentGuidedObjective:
    """Hybrid objective that combines Bayesian exploration with latent-space exploitation.
    
    Strategy:
    - Early trials: Pure Bayesian exploration to gather diverse data
    - Later trials: Mix of latent-guided exploitation and continued exploration
    - Adaptive: Increases exploitation as more high-quality data is collected
    """
    
    def __init__(self, 
                 base_objective: Objective,
                 vae_model: Optional[ParameterVAE] = None,
                 surrogate_model: Optional[PerformanceSurrogate] = None,
                 exploration_ratio: float = 0.3,
                 surrogate_threshold: int = 20):
        """
        Args:
            base_objective: Standard Bayesian objective function
            vae_model: Trained VAE for parameter embeddings
            surrogate_model: Trained surrogate for fast predictions
            exploration_ratio: Fraction of trials for pure exploration
            surrogate_threshold: Minimum trials before using surrogate screening
        """
        self.base_objective = base_objective
        self.vae_model = vae_model
        self.surrogate_model = surrogate_model
        self.exploration_ratio = exploration_ratio
        self.surrogate_threshold = surrogate_threshold
        
        # Track trial history for adaptive behavior
        self.trial_history: List[Dict[str, Any]] = []
        self.good_params_cache: List[Dict[str, float]] = []
        
        # Performance tracking
        self.best_performance = float('-inf')
        self.performance_history: List[float] = []
        
        # Parameter normalization info (needed for VAE)
        self._param_ranges = self._compute_param_ranges()
    
    def _compute_param_ranges(self) -> Dict[str, Dict[str, float]]:
        """Compute min/max ranges for parameter normalization."""
        ranges = {}
        for name, values in TEST_RANGES.items():
            if values:
                # Only compute ranges for numeric parameters
                try:
                    numeric_values = [float(v) for v in values]
                    ranges[name] = {
                        "min": min(numeric_values),
                        "max": max(numeric_values)
                    }
                except (ValueError, TypeError):
                    # Skip string/categorical parameters
                    continue
        return ranges
    
    def _normalize_params(self, params: Dict[str, Any]) -> Dict[str, float]:
        """Normalize parameters to [0,1] range for VAE."""
        normalized = {}
        for name, value in params.items():
            if name in self._param_ranges:
                pmin = self._param_ranges[name]["min"]
                pmax = self._param_ranges[name]["max"]
                if pmax > pmin:
                    try:
                        normalized[name] = (float(value) - pmin) / (pmax - pmin)
                    except (ValueError, TypeError):
                        # Handle string parameters - use index in range
                        valid_values = TEST_RANGES.get(name, [value])
                        if value in valid_values:
                            idx = valid_values.index(value)
                            normalized[name] = idx / max(1, len(valid_values) - 1)
                        else:
                            normalized[name] = 0.5
                else:
                    normalized[name] = 0.5
            else:
                try:
                    normalized[name] = float(value)
                except (ValueError, TypeError):
                    # String or other non-numeric - use hash-based normalization
                    normalized[name] = (hash(str(value)) % 1000) / 1000.0
        return normalized
    
    def _unnormalize_params(self, normalized_params: Dict[str, float]) -> Dict[str, Any]:
        """Convert normalized [0,1] parameters back to original ranges."""
        unnormalized = {}
        for name, norm_value in normalized_params.items():
            if name in self._param_ranges and name in TEST_RANGES:
                valid_values = TEST_RANGES[name]
                if not valid_values:
                    continue
                    
                # For numeric ranges, interpolate and find nearest valid value
                if all(isinstance(v, (int, float)) for v in valid_values):
                    pmin = self._param_ranges[name]["min"]
                    pmax = self._param_ranges[name]["max"]
                    if pmax > pmin:
                        # Convert back to original range
                        original_value = pmin + norm_value * (pmax - pmin)
                        # Round to nearest valid value from TEST_RANGES
                        unnormalized[name] = min(valid_values, key=lambda x: abs(x - original_value))
                    else:
                        unnormalized[name] = valid_values[0]
                else:
                    # For categorical/string parameters, use index
                    idx = int(norm_value * len(valid_values))
                    idx = max(0, min(len(valid_values) - 1, idx))
                    unnormalized[name] = valid_values[idx]
            else:
                # Fallback for parameters not in TEST_RANGES
                unnormalized[name] = norm_value
        return unnormalized
    
    def _should_use_latent(self, trial_number: int) -> bool:
        """Decide whether to use latent guidance for this trial."""
        # Always explore early
        if trial_number < 10:
            return False
        
        # Use exploration ratio with some randomness
        base_prob = 1.0 - self.exploration_ratio
        
        # Increase exploitation if we're finding good solutions
        if len(self.performance_history) > 5:
            recent_improvement = np.mean(self.performance_history[-5:]) > np.mean(self.performance_history[:-5])
            if recent_improvement:
                base_prob *= 1.2  # Increase exploitation when improving
        
        return np.random.random() < base_prob
    
    def _update_good_params_cache(self, params: Dict[str, Any], performance: float):
        """Update cache of high-performing parameters."""
        # Add to history
        self.performance_history.append(performance)
        
        # Update best
        if performance > self.best_performance:
            self.best_performance = performance
        
        # Keep top 20% of parameters in cache
        threshold = np.percentile(self.performance_history, 80) if len(self.performance_history) > 10 else float('-inf')
        
        if performance >= threshold:
            # Store normalized parameters for VAE
            normalized_params = self._normalize_params(params)
            self.good_params_cache.append(normalized_params)
            
            # Limit cache size
            if len(self.good_params_cache) > 50:
                # Keep best 30 based on surrogate predictions if available
                if self.surrogate_model and self.surrogate_model.is_trained:
                    try:
                        scored_params = []
                        for p in self.good_params_cache:
                            unnorm_p = self._unnormalize_params(p)
                            pred, _ = self.surrogate_model.predict_with_uncertainty(unnorm_p)
                            scored_params.append((p, pred))
                        scored_params.sort(key=lambda x: x[1], reverse=True)
                        self.good_params_cache = [p for p, _ in scored_params[:30]]
                    except Exception:
                        # Fallback: keep most recent
                        self.good_params_cache = self.good_params_cache[-30:]
                else:
                    # Keep most recent
                    self.good_params_cache = self.good_params_cache[-30:]
    
    def _latent_guided_sample(self, trial: optuna.trial.Trial) -> float:
        """Sample parameters using latent-space guidance and run backtest."""
        if not self.vae_model or not self.vae_model.is_trained or not self.good_params_cache:
            # Fallback to base objective
            return self.base_objective(trial)
        
        try:
            # Sample near good parameters in latent space
            candidate_params = self.vae_model.sample_near_good(
                self.good_params_cache[-10:],  # Use recent good parameters
                n_samples=5,
                noise_scale=0.15
            )
            
            if not candidate_params:
                return self.base_objective(trial)
            
            # If we have surrogate, screen candidates quickly
            if self.surrogate_model and self.surrogate_model.is_trained and len(candidate_params) > 1:
                # Convert normalized candidates back to original space for surrogate
                unnorm_candidates = [self._unnormalize_params(p) for p in candidate_params]
                predictions, uncertainties = self.surrogate_model.predict_batch(unnorm_candidates)
                
                # Choose candidate with best predicted performance + uncertainty bonus
                scores = predictions + 0.1 * uncertainties  # Encourage uncertain but promising regions
                best_idx = np.argmax(scores)
                chosen_normalized = candidate_params[best_idx]
                chosen_params = unnorm_candidates[best_idx]
            else:
                # Random choice from candidates
                chosen_normalized = np.random.choice(candidate_params) if len(candidate_params) > 1 else candidate_params[0]
                chosen_params = self._unnormalize_params(chosen_normalized)
            
            # Register the chosen parameters with Optuna for tracking
            for name, value in chosen_params.items():
                trial.set_user_attr(f"latent_guided_{name}", value)
            
            # Run the actual backtest with latent-guided parameters
            per_chart_stats, total_trades_all = self.base_objective._run_backtests(chosen_params)
            
            # Apply constraints
            if total_trades_all < self.base_objective.min_trades:
                raise optuna.exceptions.TrialPruned("constraint: min_trades")
            if self.base_objective.max_mdd is not None:
                worst_mdd = max((float(st["stats"].get("Max Drawdown [%]", 0.0)) for st in per_chart_stats), default=0.0)
                if worst_mdd > float(self.base_objective.max_mdd):
                    raise optuna.exceptions.TrialPruned("constraint: max_mdd")
            
            # Calculate and return objective
            value = self.base_objective._calc_objective(per_chart_stats)
            
            # Store results for Optuna
            from optimizer_bayesian.objective import _make_json_serializable
            trial.set_user_attr("per_chart_stats", _make_json_serializable(per_chart_stats))
            
            return value
            
        except optuna.exceptions.TrialPruned:
            raise  # Re-raise pruning exceptions
        except Exception as e:
            print(f"Warning: Latent guidance failed ({e}), falling back to base objective")
            return self.base_objective(trial)
    
    def __call__(self, trial: optuna.trial.Trial) -> float:
        """Main objective function with hybrid Bayesian/latent strategy."""
        trial_number = trial.number
        
        # Decide on strategy
        if self._should_use_latent(trial_number) and self.vae_model:
            performance = self._latent_guided_sample(trial)
            trial.set_user_attr("strategy", "latent_guided")
        else:
            performance = self.base_objective(trial)
            trial.set_user_attr("strategy", "bayesian_exploration")
        
        # Extract parameters for caching (use original parameters, not normalized)
        params = dict(trial.params)
        self._update_good_params_cache(params, performance)
        
        # Store additional metadata
        trial.set_user_attr("trial_performance", performance)
        trial.set_user_attr("best_so_far", self.best_performance)
        
        return performance


def create_latent_objective(base_objective: Objective, 
                           models_dir: str,
                           exploration_ratio: float = 0.3) -> LatentGuidedObjective:
    """Factory function to create latent-guided objective with optional model loading.
    
    Args:
        base_objective: Standard Bayesian objective
        models_dir: Directory containing trained VAE and surrogate models
        exploration_ratio: Fraction of trials for pure exploration
        
    Returns:
        LatentGuidedObjective instance (may fallback to base-only if models unavailable)
    """
    vae_path = os.path.join(models_dir, "parameter_vae.pkl")
    surrogate_path = os.path.join(models_dir, "surrogate_model.pkl")
    
    vae_model = None
    surrogate_model = None
    
    # Try to load VAE
    if os.path.exists(vae_path):
        try:
            vae_model = ParameterVAE.load_model(vae_path)
            print(f"Loaded VAE model: {vae_path}")
        except Exception as e:
            print(f"Failed to load VAE model: {e}")
    
    # Try to load surrogate
    if os.path.exists(surrogate_path):
        try:
            surrogate_model = PerformanceSurrogate.load_model(surrogate_path)
            print(f"Loaded surrogate model: {surrogate_path}")
        except Exception as e:
            print(f"Failed to load surrogate model: {e}")
    
    if not vae_model and not surrogate_model:
        print("No latent models found, using pure Bayesian optimization")
    
    return LatentGuidedObjective(
        base_objective=base_objective,
        vae_model=vae_model,
        surrogate_model=surrogate_model,
        exploration_ratio=exploration_ratio
    )