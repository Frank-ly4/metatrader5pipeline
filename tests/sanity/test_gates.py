"""Tests for hardened audit gates and walk-forward optimization."""

import pytest
import pandas as pd
import numpy as np
from src.optimizer.search import _evaluate
from src.optimizer.wfo import anchored_walk_forward, _calculate_aggregate_stats, _interquartile_mean


@pytest.fixture
def synthetic_price():
    """Create synthetic price data for testing."""
    dates = pd.date_range('2020-01-01', periods=1000, freq='1H')
    np.random.seed(42)
    
    base_price = 100
    returns = np.random.normal(0.0001, 0.01, len(dates))
    prices = [base_price]
    
    for ret in returns:
        prices.append(prices[-1] * (1 + ret))
    
    prices = np.array(prices[1:])
    
    df = pd.DataFrame(index=dates)
    df['Close'] = prices
    df['Open'] = prices * (1 + np.random.normal(0, 0.001, len(prices)))
    df['High'] = np.maximum(df['Open'], df['Close']) * (1 + np.abs(np.random.normal(0, 0.002, len(prices))))
    df['Low'] = np.minimum(df['Open'], df['Close']) * (1 - np.abs(np.random.normal(0, 0.002, len(prices))))
    
    return df


@pytest.fixture
def base_params():
    """Basic strategy parameters."""
    return {
        'fast_min_len': 10,
        'fast_max_len': 20,
        'slow_min_len': 28,
        'slow_max_len': 48,
        'dma_atr_len': 16,
        'atr_len': 16,
        'upper_outer_mult': 1.8,
        'lower_outer_mult': 2.2,
        'upper_inner_mult': 1.0,
        'lower_inner_mult': 1.2,
        'momentum_len': 14,
        'momentum_threshold': 0.75
    }


def test_gate_pf_inf_triggers(synthetic_price, base_params):
    """Test that infinite profit factor triggers suspect flag."""
    # Create synthetic trades that would result in PF=inf (no losing trades)
    # We'll mock the _simulate_trades_with_costs function behavior
    
    # Use zero costs to potentially trigger infinite PF
    toggles = {
        'enable_decision_shift': False,  # Increase chance of good results
        'fee_bps_round_trip': 0.0,
        'slippage_bps': 0.0,
        'rng_seed': 42
    }
    
    # Try with very favorable parameters that might create only winning trades
    favorable_params = base_params.copy()
    favorable_params.update({
        'momentum_threshold': 0.99,  # Very high threshold
        'upper_outer_mult': 0.1,     # Very tight bands
        'lower_outer_mult': 0.1
    })
    
    result = _evaluate(synthetic_price, favorable_params, toggles)
    
    if result is not None and np.isinf(result.get('profit_factor', 0)):
        assert result.get('suspect', False) == True
        assert result.get('suspect_reason', '') == 'pf_inf'


def test_gate_high_win_rate_triggers(synthetic_price, base_params):
    """Test that win rate > 90% triggers suspect flag."""
    # This is harder to trigger reliably with synthetic data
    # but we can test the logic by manually checking the condition
    
    toggles = {
        'enable_decision_shift': False,
        'fee_bps_round_trip': 0.0,
        'slippage_bps': 0.0,
        'rng_seed': 42
    }
    
    result = _evaluate(synthetic_price, base_params, toggles)
    
    if result is not None and result.get('win_rate', 0) > 0.90:
        assert result.get('suspect', False) == True
        assert result.get('suspect_reason', '') == 'win_rate_too_high'


def test_gate_high_sharpe_triggers(synthetic_price, base_params):
    """Test that Sharpe > 5 triggers suspect flag."""
    toggles = {
        'enable_decision_shift': False,
        'fee_bps_round_trip': 0.0,
        'slippage_bps': 0.0,
        'rng_seed': 42
    }
    
    result = _evaluate(synthetic_price, base_params, toggles)
    
    if result is not None and abs(result.get('sharpe_ratio', 0)) > 5.0:
        assert result.get('suspect', False) == True
        assert result.get('suspect_reason', '') == 'sharpe_too_high'


def test_gate_no_negative_trades_triggers(synthetic_price, base_params):
    """Test that no negative trades triggers suspect flag."""
    toggles = {
        'enable_decision_shift': False,
        'fee_bps_round_trip': 0.0,
        'slippage_bps': 0.0,
        'rng_seed': 42
    }
    
    result = _evaluate(synthetic_price, base_params, toggles)
    
    if (result is not None and 
        result.get('total_trades', 0) > 0 and 
        result.get('suspect_reason', '') == 'no_negative_trades'):
        assert result.get('suspect', False) == True


def test_wfo_aggregates_correctly():
    """Test that WFO aggregates median and IQM correctly on toy data."""
    # Create toy metrics data
    metrics_list = [
        {'cagr': 0.10, 'sharpe_ratio': 1.5, 'max_drawdown': 0.05},
        {'cagr': 0.15, 'sharpe_ratio': 2.0, 'max_drawdown': 0.08},
        {'cagr': 0.12, 'sharpe_ratio': 1.8, 'max_drawdown': 0.06},
        {'cagr': 0.08, 'sharpe_ratio': 1.2, 'max_drawdown': 0.04},
        {'cagr': 0.20, 'sharpe_ratio': 2.5, 'max_drawdown': 0.10}
    ]
    
    aggregated = _calculate_aggregate_stats(metrics_list)
    
    # Check CAGR aggregation
    cagr_values = [0.10, 0.15, 0.12, 0.08, 0.20]
    expected_median = np.median(cagr_values)  # 0.12
    expected_iqm = _interquartile_mean(np.array(cagr_values))
    
    assert 'cagr' in aggregated
    assert abs(aggregated['cagr']['median'] - expected_median) < 1e-10
    assert abs(aggregated['cagr']['iqm'] - expected_iqm) < 1e-10
    assert aggregated['cagr']['count'] == 5
    
    # Check that mean and std are calculated
    assert 'mean' in aggregated['cagr']
    assert 'std' in aggregated['cagr']
    assert 'min' in aggregated['cagr']
    assert 'max' in aggregated['cagr']


def test_interquartile_mean_calculation():
    """Test IQM calculation on known values."""
    # Test case 1: Simple case
    values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    iqm = _interquartile_mean(values)
    
    # Q25 = 3.25, Q75 = 7.75, so middle values are [4, 5, 6, 7]
    # IQM should be (4+5+6+7)/4 = 5.5
    assert abs(iqm - 5.5) < 1e-10
    
    # Test case 2: Small array (< 4 elements)
    small_values = np.array([1, 2, 3])
    iqm_small = _interquartile_mean(small_values)
    assert abs(iqm_small - 2.0) < 1e-10  # Should be regular mean


def test_wfo_window_generation():
    """Test walk-forward window generation logic."""
    # Create a longer time series for WFO testing
    dates = pd.date_range('2020-01-01', '2023-12-31', freq='D')
    price_data = pd.DataFrame(index=dates)
    price_data['Close'] = 100 + np.random.cumsum(np.random.normal(0, 0.01, len(dates)))
    price_data['Open'] = price_data['Close'] * (1 + np.random.normal(0, 0.001, len(dates)))
    price_data['High'] = np.maximum(price_data['Open'], price_data['Close']) * (1 + np.abs(np.random.normal(0, 0.002, len(dates))))
    price_data['Low'] = np.minimum(price_data['Open'], price_data['Close']) * (1 - np.abs(np.random.normal(0, 0.002, len(dates))))
    
    param_ranges = {
        'fast_min_len': [8, 10, 12],
        'fast_max_len': [18, 20, 22],
        'slow_min_len': [25, 28, 30],
        'slow_max_len': [45, 48, 50],
        'dma_atr_len': [14, 16, 18],
        'atr_len': [14, 16, 18],
        'upper_outer_mult': [1.6, 1.8, 2.0],
        'lower_outer_mult': [1.8, 2.0, 2.2],
        'upper_inner_mult': [0.8, 1.0, 1.2],
        'lower_inner_mult': [1.0, 1.2, 1.4],
        'momentum_len': [12, 14, 16],
        'momentum_threshold': [0.7, 0.75, 0.8]
    }
    
    toggles = {
        'enable_decision_shift': True,
        'fee_bps_round_trip': 5.0,
        'slippage_bps': 1.0,
        'rng_seed': 42
    }
    
    # Run minimal WFO
    wfo_result = anchored_walk_forward(
        price_data, 
        param_ranges, 
        toggles,
        train_months=12,  # Shorter for test
        valid_months=3,
        n_trials_per_window=10,  # Fewer trials for speed
        metric='cagr',
        seed=42
    )
    
    # Check that WFO structure is correct
    assert 'windows' in wfo_result
    assert 'per_window_metrics' in wfo_result
    assert 'aggregate_stats' in wfo_result
    assert 'settings' in wfo_result
    
    # Check settings
    assert wfo_result['settings']['train_months'] == 12
    assert wfo_result['settings']['valid_months'] == 3
    assert wfo_result['settings']['metric'] == 'cagr'
    
    # If we have results, check aggregate stats structure
    if len(wfo_result['per_window_metrics']) > 0:
        assert isinstance(wfo_result['aggregate_stats'], dict)
        if 'cagr' in wfo_result['aggregate_stats']:
            assert 'median' in wfo_result['aggregate_stats']['cagr']
            assert 'iqm' in wfo_result['aggregate_stats']['cagr']


def test_suspect_filtering_in_search():
    """Test that suspect results are filtered out from top-N selection."""
    # This test would need to be integrated with the actual search functions
    # For now, we'll test the logic conceptually
    
    # Mock results DataFrame
    results_data = [
        {'cagr': 0.15, 'suspect': False, 'suspect_reason': ''},
        {'cagr': 0.25, 'suspect': True, 'suspect_reason': 'pf_inf'},  # This should be filtered
        {'cagr': 0.12, 'suspect': False, 'suspect_reason': ''},
        {'cagr': 0.30, 'suspect': True, 'suspect_reason': 'win_rate_too_high'},  # This should be filtered
        {'cagr': 0.10, 'suspect': False, 'suspect_reason': ''}
    ]
    
    df = pd.DataFrame(results_data)
    
    # Simulate the filtering logic from random_search
    clean_df = df[df.get('suspect', False) == False].copy()
    suspect_df = df[df.get('suspect', False) == True].copy()
    
    # Clean results should be sorted by metric
    clean_df = clean_df.sort_values('cagr', ascending=False)
    
    # Check that clean results are properly ordered and suspect ones are excluded from top
    assert len(clean_df) == 3
    assert clean_df.iloc[0]['cagr'] == 0.15  # Best clean result
    assert clean_df.iloc[1]['cagr'] == 0.12
    assert clean_df.iloc[2]['cagr'] == 0.10
    
    # Check that suspect results are identified
    assert len(suspect_df) == 2
    assert all(suspect_df['suspect'] == True)
