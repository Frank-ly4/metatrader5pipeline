"""Sanity tests for ratio calculations and execution model."""

import pytest
import pandas as pd
import numpy as np
from src.metrics.metrics import cagr_frac, max_drawdown_frac, calmar, profit_factor, ulcer_index, expectancy, avg_hold_hours
from src.strategy.bands import compute_signals
from src.optimizer.search import _evaluate


@pytest.fixture
def synthetic_price():
    """Create synthetic price data for testing."""
    dates = pd.date_range('2023-01-01', periods=100, freq='1H')
    np.random.seed(42)
    
    # Create trending then ranging price action
    base_price = 100
    price_changes = np.concatenate([
        np.random.normal(0.001, 0.01, 50),  # Uptrend
        np.random.normal(0, 0.005, 50)      # Ranging
    ])
    
    prices = [base_price]
    for change in price_changes:
        prices.append(prices[-1] * (1 + change))
    
    prices = np.array(prices[1:])  # Remove initial base_price
    
    # Create OHLC data
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


def test_decision_shift_reduces_metrics(synthetic_price, base_params):
    """Test that decision shift materially reduces performance metrics."""
    # Test A: shift OFF, zero fees
    toggles_off = {
        'enable_decision_shift': False,
        'fee_bps_round_trip': 0.0,
        'slippage_bps': 0.0,
        'rng_seed': 42
    }
    
    # Test B: shift ON, zero fees  
    toggles_on = {
        'enable_decision_shift': True,
        'fee_bps_round_trip': 0.0,
        'slippage_bps': 0.0,
        'rng_seed': 42
    }
    
    result_off = _evaluate(synthetic_price, base_params, toggles_off)
    result_on = _evaluate(synthetic_price, base_params, toggles_on)
    
    if result_off is None or result_on is None:
        pytest.skip("Insufficient trades for comparison")
    
    pf_off = result_off['profit_factor']
    pf_on = result_on['profit_factor']
    win_off = result_off['win_rate']
    win_on = result_on['win_rate']
    
    # Assert material drop: PF must drop by ≥10% OR Win% must drop by ≥5pp
    pf_drop = (pf_off - pf_on) / pf_off if pf_off > 0 else 0
    win_drop = win_off - win_on
    
    assert pf_drop >= 0.10 or win_drop >= 0.05, f"Shift should cause material drop: PF {pf_off:.3f}->{pf_on:.3f}, Win {win_off:.3f}->{win_on:.3f}"


def test_profit_factor_finite_with_costs(synthetic_price, base_params):
    """Test that profit factor is finite with realistic costs."""
    toggles = {
        'enable_decision_shift': True,
        'fee_bps_round_trip': 10.0,  # 10 bps
        'slippage_bps': 1.0,         # 1 bp
        'rng_seed': 42
    }
    
    result = _evaluate(synthetic_price, base_params, toggles)
    
    if result is None:
        pytest.skip("No trades generated")
    
    assert np.isfinite(result['profit_factor']), f"PF should be finite with costs, got {result['profit_factor']}"


def test_negative_trades_present(synthetic_price, base_params):
    """Test that there are negative trades with realistic costs."""
    toggles = {
        'enable_decision_shift': True,
        'fee_bps_round_trip': 10.0,
        'slippage_bps': 1.0,
        'rng_seed': 42
    }
    
    result = _evaluate(synthetic_price, base_params, toggles)
    
    if result is None or result['total_trades'] == 0:
        pytest.skip("No trades generated")
    
    assert not result['suspect'] or result['suspect_reason'] != 'no_negative_trades', \
        "Should have negative trades with realistic costs"


def test_calmar_units():
    """Test Calmar ratio calculation with known values."""
    # Create equity curve where CAGR=0.12 and maxDD=0.20
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='D')
    
    # Construct equity to achieve target CAGR and drawdown
    equity = pd.Series(index=dates)
    equity.iloc[0] = 1000
    
    # Growth to achieve 12% CAGR
    daily_growth = (1.12) ** (1/365) - 1
    for i in range(1, len(equity)):
        if i < len(equity) * 0.3:  # First 30% - growth
            equity.iloc[i] = equity.iloc[i-1] * (1 + daily_growth + np.random.normal(0, 0.005))
        elif i < len(equity) * 0.5:  # 20% period - drawdown
            equity.iloc[i] = equity.iloc[i-1] * (1 - 0.01)  # 1% daily decline
        else:  # Recovery
            equity.iloc[i] = equity.iloc[i-1] * (1 + daily_growth * 1.5)
    
    cagr = cagr_frac(equity, dates)
    max_dd = max_drawdown_frac(equity)
    calmar_ratio = calmar(cagr, max_dd)
    
    expected_calmar = cagr / max_dd if max_dd > 1e-6 else np.nan
    
    assert abs(calmar_ratio - expected_calmar) < 1e-6, f"Calmar calculation error: {calmar_ratio} vs {expected_calmar}"


def test_fee_sensitivity_monotone(synthetic_price, base_params):
    """Test that metrics decline monotonically with increasing fees."""
    toggles_base = {
        'enable_decision_shift': True,
        'slippage_bps': 1.0,
        'rng_seed': 42
    }
    
    fee_levels = [0, 10, 25]
    profit_factors = []
    
    for fee_bps in fee_levels:
        toggles = toggles_base.copy()
        toggles['fee_bps_round_trip'] = fee_bps
        
        result = _evaluate(synthetic_price, base_params, toggles)
        if result is None:
            pytest.skip("Insufficient trades for fee sensitivity test")
        
        profit_factors.append(result['profit_factor'])
    
    # Check non-strict monotone decrease with 1% tolerance
    for i in range(1, len(profit_factors)):
        if np.isfinite(profit_factors[i-1]) and np.isfinite(profit_factors[i]):
            # Allow 1% deviation from strict monotone
            tolerance = 0.01
            assert profit_factors[i] <= profit_factors[i-1] * (1 + tolerance), \
                f"PF should decrease with fees: {profit_factors}"


def test_metrics_basic_properties():
    """Test basic properties of metric calculations."""
    # Test data
    equity = pd.Series([1000, 1100, 1050, 1200, 1000, 1150])
    dates = pd.date_range('2023-01-01', periods=6, freq='D')
    
    # Test CAGR
    cagr = cagr_frac(equity, dates)
    assert isinstance(cagr, float)
    
    # Test max drawdown
    max_dd = max_drawdown_frac(equity)
    assert 0 <= max_dd <= 1
    
    # Test Ulcer Index
    ulcer = ulcer_index(equity)
    assert ulcer >= 0
    
    # Test trade data
    trades_df = pd.DataFrame({
        'open_time': ['2023-01-01', '2023-01-02'],
        'close_time': ['2023-01-01 01:00', '2023-01-02 02:00'],
        'pnl_net': [10, -5]
    })
    
    # Test expectancy
    exp = expectancy(trades_df['pnl_net'])
    assert exp == 2.5  # (10 + (-5)) / 2
    
    # Test profit factor
    pf = profit_factor(trades_df['pnl_net'])
    assert pf == 2.0  # 10 / 5
