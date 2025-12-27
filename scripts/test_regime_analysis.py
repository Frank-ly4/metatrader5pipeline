#!/usr/bin/env python3
"""
Test script to debug regime analysis issues
"""
import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_imports():
    """Test all imports work"""
    print("Testing imports...")
    try:
        from src.io.data_loader import load_chart_from_path
        print("✓ data_loader imported")
    except Exception as e:
        print(f"✗ data_loader import failed: {e}")
        
    try:
        from src.strategy.bands_v2 import compute_signals
        print("✓ bands_v2 imported")
    except Exception as e:
        print(f"✗ bands_v2 import failed: {e}")
        
    try:
        from src.engine.backtest import run_backtest
        print("✓ backtest imported")
    except Exception as e:
        print(f"✗ backtest import failed: {e}")
        
    try:
        from config.user_inputs import TOGGLES
        print("✓ TOGGLES imported")
    except Exception as e:
        print(f"✗ TOGGLES import failed: {e}")
        
    try:
        import vectorbt as vbt
        print(f"✓ vectorbt imported (version: {vbt.__version__})")
    except Exception as e:
        print(f"✗ vectorbt import failed: {e}")

def test_trial_load():
    """Test loading a trial"""
    print("\nTesting trial load...")
    test_uid = "20251008_124610:1918"
    
    # Find runs directory
    runs_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'runs')
    print(f"Looking in: {runs_dir}")
    
    if not os.path.exists(runs_dir):
        print("✗ Runs directory not found")
        return
        
    # List JSON files
    jsons = [f for f in os.listdir(runs_dir) if f.lower().endswith('.json')]
    print(f"Found {len(jsons)} JSON files")
    
    # Search for UID
    found = False
    for json_file in jsons:
        try:
            with open(os.path.join(runs_dir, json_file), 'r') as f:
                data = json.load(f)
            results = data.get('results', [])
            for r in results:
                if r.get('trial_uid') == test_uid or r.get('uid') == test_uid:
                    print(f"✓ Found UID in {json_file}")
                    print(f"  Chart: {r.get('chart')}")
                    print(f"  Fold: {r.get('fold_id')}")
                    found = True
                    break
        except Exception as e:
            print(f"Error reading {json_file}: {e}")
        if found:
            break
    
    if not found:
        print(f"✗ UID {test_uid} not found in any file")

def test_chart_load():
    """Test loading a chart"""
    print("\nTesting chart load...")
    chart_name = "XAUUSD_1h_cl_2.csv"
    chart_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'active_charts')
    chart_path = os.path.join(chart_dir, chart_name)
    
    if os.path.exists(chart_path):
        print(f"✓ Chart file exists: {chart_path}")
        try:
            from src.io.data_loader import load_chart_from_path
            price_data = load_chart_from_path(chart_path)
            print(f"✓ Chart loaded: {len(price_data)} bars")
        except Exception as e:
            print(f"✗ Chart load failed: {e}")
    else:
        print(f"✗ Chart file not found: {chart_path}")

def test_backtest():
    """Test running a minimal backtest"""
    print("\nTesting backtest...")
    try:
        from src.io.data_loader import load_chart_from_path
        from src.strategy.bands_v2 import compute_signals
        from src.engine.backtest import run_backtest
        from config.user_inputs import TOGGLES
        
        # Load chart
        chart_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'active_charts', 'XAUUSD_1h_cl_2.csv')
        price_data = load_chart_from_path(chart_path)
        
        # Simple params
        params = {
            'base_fast_len': 20,
            'base_slow_len': 50,
            'volatility_atr_short': 5,
            'volatility_atr_long': 100,
            'max_holding_period': 100,
            'adx_period': 14,
            'adx_threshold': 25,
            'chandelier_atr_period': 22,
            'chandelier_atr_multiplier': 3.0,
            'ranging_trigger_window': 3,
            'stoch_k': 14,
            'stoch_d': 3,
            'stoch_smooth': 3,
            'atr_len': 14,
            'upper_outer_mult': 2.0,
            'lower_outer_mult': 2.0,
            'upper_inner_mult': 1.2,
            'lower_inner_mult': 1.2,
            'momentum_len': 14,
            'momentum_threshold': 0.70,
            'momentum_lookback': 75,
            'slope_lookback': 1,
            'rsi_len': 14,
            'rsi_oversold': 30,
            'trailing_atr_mult': 1.5,
            'catastrophic_stop_atr_mult': 0.5,
            'ranging_confirm_bar': True,
            'slope_len': 10,
            'adx_floor': 12,
            'cooldown_bars': 3,
            'atr_pct_floor': 0.0002,
            'atr_pct_cap': 0.015,
            'init_atr_mult': 1.5,
            'dma_buffer_mult': 0.5,
            'partial_pct': 0.5,
            'be_buffer': 0.2,
            'trail_dma_buffer': 0.5,
            'dead_bars': 10,
            'adx_dead_threshold': 15,
            'max_equity_heat_pct': 100.0,
            'max_consec_losses': 3,
            'friday_cutoff_bars': 4,
            'min_addon_distance_ATR': 0.8,
        }
        
        # Compute signals
        entries, exits, _ = compute_signals(price_data, params, TOGGLES)
        print(f"✓ Signals computed: {entries.sum()} entries, {exits.sum()} exits")
        
        # Run backtest
        backtest_config = {
            'init_cash': 10000,
            'max_layers': 3,
            'fees': 0.001,
            'size': 1.0,
        }
        
        pf = run_backtest(price_data, entries, exits, backtest_overrides=backtest_config)
        print("✓ Backtest completed")
        
        # Test stats
        stats = pf.stats()
        print(f"  Total Return: {stats.get('Total Return [%]', 0):.2f}%")
        print(f"  Total Trades: {stats.get('Total Trades', 0)}")
        
        # Test trades access
        try:
            trades = pf.trades.records_readable
            print(f"✓ Trades accessed: {len(trades)} trades")
            if len(trades) > 0:
                print(f"  Columns: {list(trades.columns)}")
        except Exception as e:
            print(f"✗ Trades access failed: {e}")
            
    except Exception as e:
        print(f"✗ Backtest failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("=== REGIME ANALYSIS DEBUG TEST ===\n")
    test_imports()
    test_trial_load()
    test_chart_load()
    test_backtest()
    print("\n=== END OF TEST ===")
