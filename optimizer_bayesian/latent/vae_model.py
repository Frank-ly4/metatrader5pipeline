"""Parameter VAE for learning meaningful parameter embeddings."""

import os
import pickle
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split


class ParameterVAE:
    """Lightweight VAE-like model using scikit-learn for parameter embeddings.
    
    This is a simplified VAE implementation that learns to:
    1. Encode parameter vectors into a lower-dimensional latent space
    2. Decode latent vectors back to parameter space
    3. Sample new parameters near high-performing regions
    """
    
    def __init__(self, param_dim: int, latent_dim: int = 6, random_state: int = 42):
        self.param_dim = param_dim
        self.latent_dim = latent_dim
        self.random_state = random_state
        
        # Encoder: params → latent
        self.encoder = MLPRegressor(
            hidden_layer_sizes=(param_dim * 2, latent_dim * 2),
            activation='tanh',
            max_iter=1000,
            random_state=random_state,
            early_stopping=True,
            validation_fraction=0.2
        )
        
        # Decoder: latent → params
        self.decoder = MLPRegressor(
            hidden_layer_sizes=(latent_dim * 2, param_dim * 2),
            activation='tanh', 
            max_iter=1000,
            random_state=random_state,
            early_stopping=True,
            validation_fraction=0.2
        )
        
        self.param_scaler = StandardScaler()
        self.latent_scaler = StandardScaler()
        self.param_names: List[str] = []
        self.is_trained = False
    
    def fit(self, param_data: pd.DataFrame, param_cols: List[str]) -> Dict[str, float]:
        """Train the VAE on parameter data.
        
        Args:
            param_data: DataFrame with normalized parameter columns
            param_cols: List of parameter column names
            
        Returns:
            Training metrics dictionary
        """
        self.param_names = param_cols.copy()
        
        # Extract parameter matrix
        X = param_data[param_cols].values.astype(np.float32)
        
        # Scale parameters
        X_scaled = self.param_scaler.fit_transform(X)
        
        # Split for validation
        X_train, X_val = train_test_split(X_scaled, test_size=0.2, random_state=self.random_state)
        
        # Train encoder (params → latent)
        # Use PCA-like initialization for latent space
        from sklearn.decomposition import PCA
        pca = PCA(n_components=self.latent_dim, random_state=self.random_state)
        latent_init = pca.fit_transform(X_train)
        latent_scaled = self.latent_scaler.fit_transform(latent_init)
        
        print(f"Training encoder: {X_train.shape} -> {latent_scaled.shape}")
        self.encoder.fit(X_train, latent_scaled)
        
        # Train decoder (latent -> params)
        print(f"Training decoder: {latent_scaled.shape} -> {X_train.shape}")
        self.decoder.fit(latent_scaled, X_train)
        
        # Compute reconstruction error
        latent_pred = self.encoder.predict(X_val)
        params_reconstructed = self.decoder.predict(latent_pred)
        reconstruction_error = np.mean((X_val - params_reconstructed) ** 2)
        
        self.is_trained = True
        
        return {
            "reconstruction_error": float(reconstruction_error),
            "encoder_score": float(self.encoder.score(X_train, latent_scaled)),
            "decoder_score": float(self.decoder.score(latent_scaled, X_train)),
            "training_samples": len(X_train),
            "validation_samples": len(X_val)
        }
    
    def encode_params(self, param_dict: Dict[str, float]) -> np.ndarray:
        """Encode parameter dictionary to latent vector."""
        if not self.is_trained:
            raise ValueError("Model must be trained before encoding")
        
        # Convert dict to vector
        param_vector = np.array([param_dict.get(name, 0.0) for name in self.param_names])
        param_vector = param_vector.reshape(1, -1).astype(np.float32)
        
        # Scale and encode
        param_scaled = self.param_scaler.transform(param_vector)
        latent = self.encoder.predict(param_scaled)
        
        return latent[0]
    
    def decode_latent(self, latent_vector: np.ndarray) -> Dict[str, float]:
        """Decode latent vector to parameter dictionary."""
        if not self.is_trained:
            raise ValueError("Model must be trained before decoding")
        
        latent_input = latent_vector.reshape(1, -1).astype(np.float32)
        
        # Decode and unscale
        param_scaled = self.decoder.predict(latent_input)
        param_vector = self.param_scaler.inverse_transform(param_scaled)[0]
        
        # Convert back to dict and clamp to [0, 1] range
        param_dict = {}
        for i, name in enumerate(self.param_names):
            value = float(np.clip(param_vector[i], 0.0, 1.0))
            param_dict[name] = value
        
        return param_dict
    
    def sample_near_good(self, good_params: List[Dict[str, float]], 
                        n_samples: int = 10, noise_scale: float = 0.1) -> List[Dict[str, float]]:
        """Sample new parameters near high-performing ones.
        
        Args:
            good_params: List of high-performing parameter dictionaries
            n_samples: Number of new samples to generate
            noise_scale: Amount of noise to add in latent space
            
        Returns:
            List of new parameter dictionaries
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before sampling")
        
        if not good_params:
            return []
        
        # Encode good parameters to latent space
        good_latent = []
        for params in good_params:
            try:
                latent = self.encode_params(params)
                good_latent.append(latent)
            except Exception:
                continue
        
        if not good_latent:
            return []
        
        good_latent = np.array(good_latent)
        
        # Sample around good regions
        new_samples = []
        rng = np.random.RandomState(self.random_state)
        
        for _ in range(n_samples):
            # Pick a random good point
            base_idx = rng.randint(len(good_latent))
            base_point = good_latent[base_idx]
            
            # Add Gaussian noise
            noise = rng.normal(0, noise_scale, size=self.latent_dim)
            new_latent = base_point + noise
            
            # Decode to parameters
            try:
                new_params = self.decode_latent(new_latent)
                new_samples.append(new_params)
            except Exception:
                continue
        
        return new_samples
    
    def save_model(self, filepath: str) -> None:
        """Save trained model to disk."""
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")
        
        model_data = {
            'encoder': self.encoder,
            'decoder': self.decoder,
            'param_scaler': self.param_scaler,
            'latent_scaler': self.latent_scaler,
            'param_names': self.param_names,
            'param_dim': self.param_dim,
            'latent_dim': self.latent_dim,
            'random_state': self.random_state,
            'is_trained': self.is_trained
        }
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)
    
    @classmethod
    def load_model(cls, filepath: str) -> 'ParameterVAE':
        """Load trained model from disk."""
        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)
        
        # Reconstruct model
        model = cls(
            param_dim=model_data['param_dim'],
            latent_dim=model_data['latent_dim'],
            random_state=model_data['random_state']
        )
        
        model.encoder = model_data['encoder']
        model.decoder = model_data['decoder']
        model.param_scaler = model_data['param_scaler']
        model.latent_scaler = model_data['latent_scaler']
        model.param_names = model_data['param_names']
        model.is_trained = model_data['is_trained']
        
        return model


def train_vae_from_runs(runs_dir: str, output_dir: str, 
                       latent_dim: int = 6) -> Tuple[ParameterVAE, Dict[str, float]]:
    """Complete pipeline: collect data → train VAE → save model.
    
    Args:
        runs_dir: Path to outputs/runs directory
        output_dir: Path to outputs/latent_models directory
        latent_dim: Dimensionality of latent space
        
    Returns:
        Tuple of (trained_vae, training_metrics)
    """
    from optimizer_bayesian.latent.data_collector import collect_historical_data, prepare_training_data, save_training_data
    
    print("Collecting historical data...")
    df = collect_historical_data(runs_dir)
    
    print("Preparing training data...")
    clean_df, param_cols = prepare_training_data(df)
    
    print(f"Training VAE with {len(param_cols)} parameters -> {latent_dim} latent dimensions...")
    vae = ParameterVAE(param_dim=len(param_cols), latent_dim=latent_dim)
    metrics = vae.fit(clean_df, param_cols)
    
    print("Saving model and data...")
    vae_path = os.path.join(output_dir, "parameter_vae.pkl")
    vae.save_model(vae_path)
    
    data_path = save_training_data(clean_df, param_cols, output_dir)
    
    print(f"VAE training complete:")
    print(f"  Model: {vae_path}")
    print(f"  Data: {data_path}")
    print(f"  Reconstruction error: {metrics['reconstruction_error']:.6f}")
    
    return vae, metrics


if __name__ == "__main__":
    # Train VAE from existing optimization runs
    here = os.path.dirname(__file__)
    runs_dir = os.path.normpath(os.path.join(here, "..", "..", "outputs", "runs"))
    output_dir = os.path.normpath(os.path.join(here, "..", "..", "outputs", "latent_models"))
    
    try:
        vae, metrics = train_vae_from_runs(runs_dir, output_dir)
        print("VAE training completed successfully!")
    except Exception as e:
        print(f"VAE training failed: {e}")
