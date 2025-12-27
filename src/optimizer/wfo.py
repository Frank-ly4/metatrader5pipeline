"""Anchored walk-forward optimization with proper train/validation splits."""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from src.optimizer.search import evaluate_collect
from src.strategy.bands_v1 import compute_signals
from src.metrics.metrics import cagr_frac, max_drawdown_frac, calmar, profit_factor, ulcer_index


def _evaluate(price: pd.DataFrame, params: dict, toggles: dict) -> dict | None:
    """Wrapper for evaluate_collect that returns just the metrics dict."""
    try:
        result, _ = evaluate_collect(price, params, toggles, compute_signals)
        return result
    except Exception:
        return None


def anchored_walk_forward(
    price: pd.DataFrame, 
    param_ranges: dict, 
    toggles: dict,
    train_months: int = 24,
    valid_months: int = 3,
    n_trials_per_window: int = 100,
    metric: str = 'cagr',
    seed: int = 42
) -> Dict:
    """
    Perform anchored walk-forward optimization.
    
    Args:
        price: Price data with datetime index
        param_ranges: Parameter ranges for optimization
        toggles: Strategy toggles
        train_months: Training window size in months
        valid_months: Validation window size in months  
        n_trials_per_window: Number of optimization trials per window
        metric: Metric to optimize
        seed: Random seed
        
    Returns:
        Dictionary with per-window results and aggregated statistics
    """
    np.random.seed(seed)
    
    # Ensure price has datetime index
    if not isinstance(price.index, pd.DatetimeIndex):
        price.index = pd.to_datetime(price.index)
    
    # Calculate window boundaries
    windows = _generate_windows(price.index, train_months, valid_months)
    
    if len(windows) == 0:
        return {'error': 'Insufficient data for walk-forward analysis'}
    
    results = {
        'windows': [],
        'per_window_metrics': [],
        'aggregate_stats': {},
        'settings': {
            'train_months': train_months,
            'valid_months': valid_months,
            'n_trials_per_window': n_trials_per_window,
            'metric': metric
        }
    }
    
    for i, (train_start, train_end, valid_start, valid_end) in enumerate(windows):
        print(f"Processing window {i+1}/{len(windows)}: train {train_start} to {train_end}, valid {valid_start} to {valid_end}")
        
        # Split data
        train_data = price[(price.index >= train_start) & (price.index <= train_end)]
        valid_data = price[(price.index >= valid_start) & (price.index <= valid_end)]
        
        if len(train_data) < 100 or len(valid_data) < 20:
            print(f"Skipping window {i+1}: insufficient data")
            continue
        
        # Optimize on training data
        best_params = _optimize_window(train_data, param_ranges, toggles, n_trials_per_window, metric, seed + i)
        
        if best_params is None:
            print(f"No valid parameters found for window {i+1}")
            continue
        
        # Evaluate on validation data
        valid_result = _evaluate(valid_data, best_params, toggles)
        
        if valid_result is None or valid_result.get('suspect', False):
            print(f"Invalid validation result for window {i+1}")
            continue
        
        # Store window results
        window_result = {
            'window_id': i + 1,
            'train_start': train_start,
            'train_end': train_end,
            'valid_start': valid_start,
            'valid_end': valid_end,
            'best_params': best_params,
            'validation_metrics': valid_result
        }
        
        results['windows'].append(window_result)
        results['per_window_metrics'].append(valid_result)
    
    # Calculate aggregate statistics
    if len(results['per_window_metrics']) > 0:
        results['aggregate_stats'] = _calculate_aggregate_stats(results['per_window_metrics'])
    
    return results


def _generate_windows(dt_index: pd.DatetimeIndex, train_months: int, valid_months: int) -> List[Tuple]:
    """Generate anchored walk-forward windows."""
    windows = []
    
    start_date = dt_index[0]
    end_date = dt_index[-1]
    
    # Start with minimum training period
    current_train_end = start_date + pd.DateOffset(months=train_months)
    
    while current_train_end < end_date:
        valid_start = current_train_end + pd.Timedelta(days=1)
        valid_end = valid_start + pd.DateOffset(months=valid_months)
        
        if valid_end > end_date:
            break
        
        windows.append((start_date, current_train_end, valid_start, valid_end))
        
        # Move to next validation period (anchored training)
        current_train_end = valid_end
    
    return windows


def _optimize_window(price: pd.DataFrame, param_ranges: dict, toggles: dict, 
                    n_trials: int, metric: str, seed: int) -> Dict | None:
    """Optimize parameters on a single training window."""
    np.random.seed(seed)
    
    best_result = None
    best_params = None
    best_score = -np.inf
    
    for _ in range(n_trials):
        # Sample parameters
        params = {}
        for key, values in param_ranges.items():
            if isinstance(values, str):
                # Handle range strings like "10-20"
                if '-' in values:
                    if ':' in values:
                        range_part, step_part = values.split(':')
                        start, end = map(float, range_part.split('-'))
                        step = float(step_part)
                        params[key] = np.random.choice(np.arange(start, end + step, step))
                    else:
                        start, end = map(int, values.split('-'))
                        params[key] = np.random.randint(start, end + 1)
                else:
                    # Handle comma-separated values
                    choices = [float(x) if '.' in x else int(x) for x in values.split(',')]
                    params[key] = np.random.choice(choices)
            else:
                params[key] = np.random.choice(values)
        
        # Evaluate parameters
        result = _evaluate(price, params, toggles)
        
        if result is None or result.get('suspect', False):
            continue
        
        score = result.get(metric, -np.inf)
        if score > best_score:
            best_score = score
            best_params = params.copy()
            best_result = result
    
    return best_params


def _calculate_aggregate_stats(metrics_list: List[Dict]) -> Dict:
    """Calculate aggregate statistics across windows."""
    if len(metrics_list) == 0:
        return {}
    
    # Extract key metrics
    metrics_to_aggregate = ['cagr', 'sharpe_ratio', 'calmar_ratio', 'max_drawdown', 
                           'win_rate', 'profit_factor', 'ulcer_index', 'expectancy']
    
    aggregated = {}
    
    for metric in metrics_to_aggregate:
        values = []
        for window_metrics in metrics_list:
            val = window_metrics.get(metric, np.nan)
            if not pd.isna(val) and np.isfinite(val):
                values.append(val)
        
        if len(values) > 0:
            values = np.array(values)
            aggregated[metric] = {
                'median': np.median(values),
                'mean': np.mean(values),
                'std': np.std(values),
                'min': np.min(values),
                'max': np.max(values),
                'iqm': _interquartile_mean(values),  # Interquartile mean
                'count': len(values)
            }
    
    return aggregated


def _interquartile_mean(values: np.ndarray) -> float:
    """Calculate interquartile mean (mean of middle 50%)."""
    if len(values) < 4:
        return np.mean(values)
    
    q25, q75 = np.percentile(values, [25, 75])
    middle_values = values[(values >= q25) & (values <= q75)]
    
    return np.mean(middle_values)


def check_parameter_fragility(
    price: pd.DataFrame,
    best_params: dict,
    param_ranges: dict,
    toggles: dict,
    reference_metric: float,
    metric_name: str = 'cagr',
    wobble_steps: int = 1,
    price_jitter_runs: int = 30,
    tick_size: float = 0.0001
) -> Dict:
    """
    Check parameter and price fragility of the best strategy.
    
    Args:
        price: Price data
        best_params: Best parameters to test
        param_ranges: Parameter ranges for wobbling
        toggles: Strategy toggles
        reference_metric: Reference metric value
        metric_name: Name of metric to test
        wobble_steps: Number of steps to wobble parameters
        price_jitter_runs: Number of price jitter Monte Carlo runs
        tick_size: Tick size for price jitter
        
    Returns:
        Fragility test results
    """
    results = {
        'parameter_fragility': {},
        'price_fragility': {},
        'is_fragile': False,
        'fragility_reasons': []
    }
    
    # Parameter wobble test
    param_variations = []
    
    for param_name, param_value in best_params.items():
        if param_name not in param_ranges:
            continue
        
        param_range = param_ranges[param_name]
        
        # Generate wobble values
        wobble_values = _generate_wobble_values(param_value, param_range, wobble_steps)
        
        for wobble_value in wobble_values:
            if wobble_value == param_value:
                continue
            
            wobbled_params = best_params.copy()
            wobbled_params[param_name] = wobble_value
            
            result = _evaluate(price, wobbled_params, toggles)
            if result is not None and not result.get('suspect', False):
                metric_value = result.get(metric_name, np.nan)
                if not pd.isna(metric_value):
                    param_variations.append(metric_value)
    
    # Analyze parameter fragility
    if len(param_variations) > 0:
        param_std = np.std(param_variations)
        param_mean = np.mean(param_variations)
        
        # Check if variations are within 1 standard deviation
        reference_within_1sigma = abs(reference_metric - param_mean) <= param_std
        
        results['parameter_fragility'] = {
            'variations': param_variations,
            'std': param_std,
            'mean': param_mean,
            'reference_within_1sigma': reference_within_1sigma
        }
        
        if not reference_within_1sigma:
            results['is_fragile'] = True
            results['fragility_reasons'].append('parameter_wobble_fail')
    
    # Price jitter test
    jitter_variations = []
    
    for _ in range(price_jitter_runs):
        # Add random jitter to prices
        jittered_price = price.copy()
        jitter = np.random.normal(0, tick_size, len(price))
        
        jittered_price['Open'] += jitter
        jittered_price['High'] += jitter
        jittered_price['Low'] += jitter
        jittered_price['Close'] += jitter
        
        result = _evaluate(jittered_price, best_params, toggles)
        if result is not None and not result.get('suspect', False):
            metric_value = result.get(metric_name, np.nan)
            if not pd.isna(metric_value):
                jitter_variations.append(metric_value)
    
    # Analyze price fragility
    if len(jitter_variations) > 0:
        jitter_std = np.std(jitter_variations)
        jitter_mean = np.mean(jitter_variations)
        
        # Check if dispersion is reasonable (coefficient of variation < 0.5)
        cv = jitter_std / abs(jitter_mean) if jitter_mean != 0 else np.inf
        dispersion_acceptable = cv < 0.5
        
        results['price_fragility'] = {
            'variations': jitter_variations,
            'std': jitter_std,
            'mean': jitter_mean,
            'coefficient_of_variation': cv,
            'dispersion_acceptable': dispersion_acceptable
        }
        
        if not dispersion_acceptable:
            results['is_fragile'] = True
            results['fragility_reasons'].append('price_jitter_high_dispersion')
    
    return results


def _generate_wobble_values(current_value, param_range, steps: int):
    """Generate parameter wobble values around current value."""
    wobble_values = [current_value]
    
    if isinstance(param_range, str):
        if '-' in param_range:
            if ':' in param_range:
                range_part, step_part = param_range.split(':')
                start, end = map(float, range_part.split('-'))
                step = float(step_part)
                
                # Add wobble values
                for i in range(1, steps + 1):
                    lower = current_value - (step * i)
                    upper = current_value + (step * i)
                    if start <= lower <= end:
                        wobble_values.append(lower)
                    if start <= upper <= end:
                        wobble_values.append(upper)
            else:
                start, end = map(int, param_range.split('-'))
                for i in range(1, steps + 1):
                    lower = current_value - i
                    upper = current_value + i
                    if start <= lower <= end:
                        wobble_values.append(lower)
                    if start <= upper <= end:
                        wobble_values.append(upper)
    else:
        # List-based parameter range
        try:
            current_idx = param_range.index(current_value)
            for i in range(1, steps + 1):
                if current_idx - i >= 0:
                    wobble_values.append(param_range[current_idx - i])
                if current_idx + i < len(param_range):
                    wobble_values.append(param_range[current_idx + i])
        except ValueError:
            pass  # Current value not in range
    
    return wobble_values
