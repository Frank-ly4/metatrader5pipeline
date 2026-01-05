"""Surrogate model for fast performance prediction."""

import os
import pickle
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional

try:
    from sklearn.ensemble import GradientBoostingRegressor
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False


class PerformanceSurrogate:
    """Fast surrogate model for predicting strategy performance from parameters.
    
    Uses XGBoost if available, falls back to scikit-learn GradientBoosting.
    Provides uncertainty estimates for acquisition function guidance.
    """
    
    def __init__(self, target_metric: str = 'calmar_ratio', random_state: int = 42):
        self.target_metric = target_metric
        self.random_state = random_state
        self.param_names: List[str] = []
        self.is_trained = False
        
        # Choose best available model
        if XGBOOST_AVAILABLE:
            self.model = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=random_state,
                n_jobs=-1
            )
            self.model_type = "xgboost"
        elif SKLEARN_AVAILABLE:
            self.model = GradientBoostingRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=random_state
            )
            self.model_type = "sklearn_gb"
        else:
            raise ImportError("Neither XGBoost nor scikit-learn available for surrogate model")
        
        # For uncertainty estimation
        self.ensemble_models: List = []
        self.n_ensemble = 5
    
    def fit(self, param_data: pd.DataFrame, param_cols: List[str]) -> Dict[str, float]:
        """Train surrogate model on parameter-performance data.
        
        Args:
            param_data: DataFrame with parameter columns and performance metrics
            param_cols: List of parameter column names
            
        Returns:
            Training metrics dictionary
        """
        self.param_names = param_cols.copy()
        
        # Prepare training data
        X = param_data[param_cols].values.astype(np.float32)
        y = param_data[self.target_metric].values.astype(np.float32)
        
        # Remove invalid targets
        valid_mask = ~(np.isnan(y) | np.isinf(y))
        X, y = X[valid_mask], y[valid_mask]
        
        if len(X) < 10:
            raise ValueError(f"Insufficient training data: {len(X)} samples")
        
        # Train main model
        print(f"Training {self.model_type} surrogate on {len(X)} samples...")
        self.model.fit(X, y)
        
        # Train ensemble for uncertainty estimation
        print("Training uncertainty ensemble...")
        from sklearn.model_selection import train_test_split
        
        self.ensemble_models = []
        ensemble_scores = []
        
        for i in range(self.n_ensemble):
            # Bootstrap sample
            n_samples = int(0.8 * len(X))
            indices = np.random.RandomState(self.random_state + i).choice(
                len(X), n_samples, replace=True
            )
            X_boot, y_boot = X[indices], y[indices]
            
            # Train ensemble member
            if XGBOOST_AVAILABLE:
                ensemble_model = xgb.XGBRegressor(
                    n_estimators=50,
                    max_depth=4,
                    learning_rate=0.15,
                    random_state=self.random_state + i,
                    n_jobs=1
                )
            else:
                ensemble_model = GradientBoostingRegressor(
                    n_estimators=50,
                    max_depth=4,
                    learning_rate=0.15,
                    random_state=self.random_state + i
                )
            
            ensemble_model.fit(X_boot, y_boot)
            self.ensemble_models.append(ensemble_model)
            
            # Validate
            y_pred = ensemble_model.predict(X)
            score = np.corrcoef(y, y_pred)[0, 1] if len(np.unique(y)) > 1 else 0.0
            ensemble_scores.append(score)
        
        # Overall validation
        y_pred_main = self.model.predict(X)
        main_score = np.corrcoef(y, y_pred_main)[0, 1] if len(np.unique(y)) > 1 else 0.0
        
        self.is_trained = True
        
        return {
            "main_model_score": float(main_score),
            "ensemble_mean_score": float(np.mean(ensemble_scores)),
            "ensemble_std_score": float(np.std(ensemble_scores)),
            "training_samples": len(X),
            "target_metric": self.target_metric
        }
    
    def predict_with_uncertainty(self, param_dict: Dict[str, float]) -> Tuple[float, float]:
        """Predict performance with uncertainty estimate.
        
        Args:
            param_dict: Parameter dictionary
            
        Returns:
            Tuple of (predicted_performance, uncertainty_std)
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")
        
        # Convert to vector
        param_vector = np.array([param_dict.get(name, 0.0) for name in self.param_names])
        X = param_vector.reshape(1, -1).astype(np.float32)
        
        # Main prediction
        main_pred = self.model.predict(X)[0]
        
        # Ensemble predictions for uncertainty
        ensemble_preds = []
        for model in self.ensemble_models:
            pred = model.predict(X)[0]
            ensemble_preds.append(pred)
        
        uncertainty = float(np.std(ensemble_preds)) if len(ensemble_preds) > 1 else 0.0
        
        return float(main_pred), uncertainty
    
    def predict_batch(self, param_dicts: List[Dict[str, float]]) -> Tuple[np.ndarray, np.ndarray]:
        """Batch prediction for efficiency.
        
        Returns:
            Tuple of (predictions, uncertainties)
        """
        if not param_dicts:
            return np.array([]), np.array([])
        
        # Convert to matrix
        X = np.array([[d.get(name, 0.0) for name in self.param_names] for d in param_dicts])
        X = X.astype(np.float32)
        
        # Main predictions
        main_preds = self.model.predict(X)
        
        # Ensemble predictions
        ensemble_preds = np.array([model.predict(X) for model in self.ensemble_models])
        uncertainties = np.std(ensemble_preds, axis=0)
        
        return main_preds, uncertainties
    
    def get_feature_importance(self) -> Dict[str, float]:
        """Get parameter importance scores."""
        if not self.is_trained:
            return {}
        
        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
        elif hasattr(self.model, 'coef_'):
            importances = np.abs(self.model.coef_)
        else:
            return {}
        
        return dict(zip(self.param_names, importances))
    
    def save_model(self, filepath: str) -> None:
        """Save trained surrogate model."""
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")
        
        model_data = {
            'model': self.model,
            'ensemble_models': self.ensemble_models,
            'param_names': self.param_names,
            'target_metric': self.target_metric,
            'model_type': self.model_type,
            'random_state': self.random_state,
            'is_trained': self.is_trained
        }
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)
    
    @classmethod
    def load_model(cls, filepath: str) -> 'PerformanceSurrogate':
        """Load trained surrogate model."""
        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)
        
        surrogate = cls(
            target_metric=model_data['target_metric'],
            random_state=model_data['random_state']
        )
        
        surrogate.model = model_data['model']
        surrogate.ensemble_models = model_data['ensemble_models']
        surrogate.param_names = model_data['param_names']
        surrogate.model_type = model_data['model_type']
        surrogate.is_trained = model_data['is_trained']
        
        return surrogate


def train_surrogate_from_data(training_data_path: str, output_dir: str,
                             target_metric: str = 'calmar_ratio') -> Tuple[PerformanceSurrogate, Dict[str, float]]:
    """Train surrogate model from prepared training data.
    
    Args:
        training_data_path: Path to training_data.parquet
        output_dir: Directory to save trained model
        target_metric: Performance metric to predict
        
    Returns:
        Tuple of (trained_surrogate, training_metrics)
    """
    # Load data
    df = pd.read_parquet(training_data_path)
    
    # Load parameter names from metadata
    meta_path = os.path.join(os.path.dirname(training_data_path), "training_metadata.json")
    if os.path.exists(meta_path):
        import json
        with open(meta_path, 'r') as f:
            metadata = json.load(f)
        param_cols = metadata['param_columns']
    else:
        # Fallback: infer parameter columns
        metric_cols = {'total_return', 'sharpe_ratio', 'calmar_ratio', 'max_drawdown', 
                      'total_trades', 'win_rate', 'profit_factor', '_source_file'}
        param_cols = [col for col in df.columns if col not in metric_cols]
    
    # Train surrogate
    surrogate = PerformanceSurrogate(target_metric=target_metric)
    metrics = surrogate.fit(df, param_cols)
    
    # Save model
    model_path = os.path.join(output_dir, "surrogate_model.pkl")
    surrogate.save_model(model_path)
    
    print(f"Surrogate model saved: {model_path}")
    print(f"Model score: {metrics['main_model_score']:.4f}")
    
    return surrogate, metrics


if __name__ == "__main__":
    # Train surrogate from existing data
    here = os.path.dirname(__file__)
    data_path = os.path.normpath(os.path.join(here, "..", "..", "outputs", "latent_models", "training_data.parquet"))
    output_dir = os.path.normpath(os.path.join(here, "..", "..", "outputs", "latent_models"))
    
    if not os.path.exists(data_path):
        print("Training data not found. Run data_collector.py first.")
    else:
        try:
            surrogate, metrics = train_surrogate_from_data(data_path, output_dir)
            print("Surrogate training completed!")
        except Exception as e:
            print(f"Surrogate training failed: {e}")
