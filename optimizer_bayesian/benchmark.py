"""Validation benchmarks comparing optimization methods."""

import argparse
import time
import json
import os
from typing import Dict, List
import pandas as pd
import numpy as np

from optimizer_bayesian.run import _resolve_charts_arg
from optimizer_bayesian.storage import get_or_create_study
from optimizer_bayesian.objective import Objective
from optimizer_bayesian.latent.latent_objective import create_latent_objective


def run_benchmark_comparison(
    charts: List[str],
    n_trials: int = 30,
    seeds: List[int] = [42, 123, 456],
    output_dir: str = None
) -> Dict[str, List[float]]:
    """Compare Pure Bayesian vs Latent-Enhanced optimization.
    
    Args:
        charts: List of chart paths to test on
        n_trials: Number of trials per method per seed
        seeds: Random seeds for statistical significance
        output_dir: Directory to save detailed results
        
    Returns:
        Dictionary with convergence curves for each method
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "..", "outputs", "benchmarks")
    
    os.makedirs(output_dir, exist_ok=True)
    
    results = {
        "pure_bayesian": [],
        "latent_enhanced": []
    }
    
    models_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "outputs", "latent_models"))
    
    for seed_idx, seed in enumerate(seeds):
        print(f"\n=== Benchmark Run {seed_idx + 1}/{len(seeds)} (seed={seed}) ===")
        
        # Test Pure Bayesian
        print("Testing Pure Bayesian...")
        study_name = f"benchmark_pure_{seed}"
        study = get_or_create_study(study_name, seed=seed, direction="maximize")
        
        objective = Objective(
            charts=charts,
            metric="calmar",
            min_trades=10,
            seed=seed
        )
        
        start_time = time.time()
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        pure_time = time.time() - start_time
        
        # Extract convergence curve
        pure_values = [trial.value for trial in study.trials if trial.value is not None]
        pure_best_curve = [max(pure_values[:i+1]) for i in range(len(pure_values))]
        results["pure_bayesian"].append({
            "seed": seed,
            "convergence": pure_best_curve,
            "final_best": max(pure_values) if pure_values else 0.0,
            "time_seconds": pure_time,
            "trials_completed": len(pure_values)
        })
        
        # Test Latent-Enhanced (if models available)
        vae_path = os.path.join(models_dir, "parameter_vae.pkl")
        if os.path.exists(vae_path):
            print("Testing Latent-Enhanced...")
            study_name = f"benchmark_latent_{seed}"
            study = get_or_create_study(study_name, seed=seed, direction="maximize")
            
            base_objective = Objective(
                charts=charts,
                metric="calmar", 
                min_trades=10,
                seed=seed
            )
            
            latent_objective = create_latent_objective(
                base_objective=base_objective,
                models_dir=models_dir,
                exploration_ratio=0.3
            )
            
            start_time = time.time()
            study.optimize(latent_objective, n_trials=n_trials, show_progress_bar=False)
            latent_time = time.time() - start_time
            
            # Extract convergence curve
            latent_values = [trial.value for trial in study.trials if trial.value is not None]
            latent_best_curve = [max(latent_values[:i+1]) for i in range(len(latent_values))]
            results["latent_enhanced"].append({
                "seed": seed,
                "convergence": latent_best_curve,
                "final_best": max(latent_values) if latent_values else 0.0,
                "time_seconds": latent_time,
                "trials_completed": len(latent_values)
            })
        else:
            print("Skipping Latent-Enhanced (no trained models found)")
    
    # Save detailed results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    results_path = os.path.join(output_dir, f"benchmark_results_{timestamp}.json")
    
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nBenchmark results saved: {results_path}")
    
    # Print summary
    print("\n" + "="*60)
    print("BENCHMARK SUMMARY")
    print("="*60)
    
    if results["pure_bayesian"]:
        pure_finals = [r["final_best"] for r in results["pure_bayesian"]]
        pure_times = [r["time_seconds"] for r in results["pure_bayesian"]]
        print(f"Pure Bayesian:")
        print(f"  Best Performance: {np.mean(pure_finals):.4f} ± {np.std(pure_finals):.4f}")
        print(f"  Avg Time: {np.mean(pure_times):.1f}s")
    
    if results["latent_enhanced"]:
        latent_finals = [r["final_best"] for r in results["latent_enhanced"]]
        latent_times = [r["time_seconds"] for r in results["latent_enhanced"]]
        print(f"Latent-Enhanced:")
        print(f"  Best Performance: {np.mean(latent_finals):.4f} ± {np.std(latent_finals):.4f}")
        print(f"  Avg Time: {np.mean(latent_times):.1f}s")
        
        if results["pure_bayesian"]:
            improvement = (np.mean(latent_finals) - np.mean(pure_finals)) / np.mean(pure_finals) * 100
            print(f"  Performance Improvement: {improvement:+.1f}%")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Benchmark Bayesian vs Latent-Enhanced optimization")
    parser.add_argument("--charts", type=str, default="all", help="Charts to test on")
    parser.add_argument("--n-trials", type=int, default=30, help="Trials per method per seed")
    parser.add_argument("--seeds", type=str, default="42,123,456", help="Comma-separated random seeds")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory for results")
    
    args = parser.parse_args()
    
    charts = _resolve_charts_arg(args.charts)
    seeds = [int(s.strip()) for s in args.seeds.split(",")]
    
    print("OPTIMIZATION METHOD BENCHMARK")
    print("="*60)
    print(f"Charts: {len(charts)} selected")
    print(f"Trials per method: {args.n_trials}")
    print(f"Seeds: {seeds}")
    print(f"Total trials: {len(seeds) * args.n_trials * 2}")  # 2 methods
    
    results = run_benchmark_comparison(
        charts=charts,
        n_trials=args.n_trials,
        seeds=seeds,
        output_dir=args.output_dir
    )
    
    print("\nBenchmark completed!")


if __name__ == "__main__":
    main()
