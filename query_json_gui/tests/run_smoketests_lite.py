#!/usr/bin/env python3
"""
Smoke Tests for Optimization Console Lite
==========================================
Headless quick checks for core functionality.
"""

import sys
import tempfile
import json
from pathlib import Path
import pandas as pd

# Add parent directory to path to import the lite app
sys.path.insert(0, str(Path(__file__).parent.parent))

from opt_console_lite import (
    _normalize_percent_tokens,
    _apply_layered_filters,
    _apply_query_sort_limit,
    _build_sorted_df_for_topn,
    detect_metric_columns
)


def test_percent_normalization():
    """Test percentage token normalization."""
    print("Testing percentage normalization...")
    
    tests = [
        ("8%", "0.08"),
        ("8 %", "0.08"),
        ("10.5%", "0.105"),
        ("max_drawdown < 8%", "max_drawdown < 0.08"),
        ("win_rate > 60 %", "win_rate > 0.6"),
        ("mdd < 0.08", "mdd < 0.08"),  # No change
    ]
    
    for input_str, expected in tests:
        result = _normalize_percent_tokens(input_str)
        assert result == expected, f"Failed: {input_str} -> {result} (expected {expected})"
    
    print("  ✓ Percentage normalization passed")


def test_layered_filters():
    """Test layered filter AND logic."""
    print("Testing layered filters...")
    
    df = pd.DataFrame({
        'calmar_ratio': [0.8, 1.2, 1.5, 0.5],
        'profit_factor': [1.3, 1.7, 2.0, 1.1],
        'max_drawdown': [0.10, 0.08, 0.06, 0.12]
    })
    
    # Test single filter
    filter_rows = [('calmar_ratio', '>=', '1.0')]
    expr, result = _apply_layered_filters(df, filter_rows)
    assert len(result) == 2, f"Single filter failed: {len(result)} rows"
    
    # Test multiple filters (AND)
    filter_rows = [
        ('calmar_ratio', '>=', '1.0'),
        ('profit_factor', '>=', '1.5')
    ]
    expr, result = _apply_layered_filters(df, filter_rows)
    assert len(result) == 2, f"Multiple filters failed: {len(result)} rows"
    
    # Test with percentage
    filter_rows = [('max_drawdown', '<', '10%')]
    expr, result = _apply_layered_filters(df, filter_rows)
    assert len(result) == 2, f"Percentage filter failed: {len(result)} rows"
    
    print("  ✓ Layered filters passed")


def test_query_sort_limit():
    """Test query, sort, and limit operations."""
    print("Testing query/sort/limit...")
    
    df = pd.DataFrame({
        'calmar_ratio': [1.5, 0.8, 1.2, 2.0, 1.0],
        'profit_factor': [1.7, 1.3, 2.0, 1.5, 1.8],
        'num_trades': [30, 15, 25, 40, 20]
    })
    
    # Test filter only
    result = _apply_query_sort_limit(df, "num_trades >= 20", "", 0)
    assert len(result) == 4, f"Filter failed: {len(result)} rows"
    
    # Test sort only (descending)
    result = _apply_query_sort_limit(df, "", "-calmar_ratio", 0)
    assert result.iloc[0]['calmar_ratio'] == 2.0, "Sort descending failed"
    
    # Test multi-key sort
    result = _apply_query_sort_limit(df, "", "-calmar_ratio,profit_factor", 0)
    assert result.iloc[0]['calmar_ratio'] == 2.0, "Multi-key sort failed"
    
    # Test limit
    result = _apply_query_sort_limit(df, "", "", 3)
    assert len(result) == 3, f"Limit failed: {len(result)} rows"
    
    # Test combined
    result = _apply_query_sort_limit(df, "num_trades >= 20", "-calmar_ratio", 2)
    assert len(result) == 2, f"Combined failed: {len(result)} rows"
    assert result.iloc[0]['calmar_ratio'] == 2.0, "Combined sort failed"
    
    print("  ✓ Query/sort/limit passed")


def test_topn_sorting():
    """Test Top-N sorting with metric priority."""
    print("Testing Top-N sorting...")
    
    df = pd.DataFrame({
        'calmar_ratio': [1.5, 0.8, 1.2, 2.0, 1.0],
        'profit_factor': [1.7, 1.3, 2.0, 1.5, 1.8],
        'num_trades': [30, 15, 25, 40, 20]
    })
    
    # Test descending (best first)
    result = _build_sorted_df_for_topn(df, 'calmar_ratio', desc=True, user_sort_by='')
    assert result.iloc[0]['calmar_ratio'] == 2.0, "Top-N desc failed"
    
    # Test ascending (lowest first)
    result = _build_sorted_df_for_topn(df, 'calmar_ratio', desc=False, user_sort_by='')
    assert result.iloc[0]['calmar_ratio'] == 0.8, "Top-N asc failed"
    
    # Test with user sort keys
    result = _build_sorted_df_for_topn(df, 'calmar_ratio', desc=True, user_sort_by='profit_factor')
    assert result.iloc[0]['calmar_ratio'] == 2.0, "Top-N with user sort failed"
    
    print("  ✓ Top-N sorting passed")


def test_metric_detection():
    """Test automatic metric column detection."""
    print("Testing metric detection...")
    
    df = pd.DataFrame({
        'calmar_ratio': [1.5],
        'sharpe_ratio': [1.2],
        'max_drawdown': [0.08],
        'profit_factor': [1.7],
        'param_lookback': [20],
        'param_threshold': [0.5],
        'chart': ['EURUSD'],
        'id': [1],
        'unknown_metric': [42.0]
    })
    
    metrics = detect_metric_columns(df)
    
    # Check higher-is-better
    assert 'calmar_ratio' in metrics['higher'], "calmar_ratio not in higher"
    assert 'sharpe_ratio' in metrics['higher'], "sharpe_ratio not in higher"
    assert 'profit_factor' in metrics['higher'], "profit_factor not in higher"
    
    # Check lower-is-better
    assert 'max_drawdown' in metrics['lower'], "max_drawdown not in lower"
    
    # Check exclusions
    assert 'param_lookback' not in metrics['higher'] + metrics['lower'] + metrics['other'], \
        "param_ column not excluded"
    assert 'chart' not in metrics['higher'] + metrics['lower'] + metrics['other'], \
        "chart not excluded"
    assert 'id' not in metrics['higher'] + metrics['lower'] + metrics['other'], \
        "id not excluded"
    
    # Check other
    assert 'unknown_metric' in metrics['other'], "unknown_metric not in other"
    
    print("  ✓ Metric detection passed")


def test_load_json_fixtures():
    """Test loading JSON files with various formats."""
    print("Testing JSON loading...")
    
    # Create temporary directory with test files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Good file 1
        good1 = tmppath / "good1.json"
        good1.write_text(json.dumps({
            "metadata": {"chart": "EURUSD"},
            "results": [
                {"calmar_ratio": 1.5, "profit_factor": 1.7},
                {"calmar_ratio": 1.2, "profit_factor": 1.5}
            ]
        }))
        
        # Good file 2
        good2 = tmppath / "good2.json"
        good2.write_text(json.dumps({
            "results": [
                {"calmar_ratio": 2.0, "profit_factor": 2.2}
            ]
        }))
        
        # Malformed file
        bad = tmppath / "bad.json"
        bad.write_text("{invalid json")
        
        # Simulate loading (manual since we're not testing UI)
        all_rows = []
        errors = []
        
        for json_file in tmppath.glob("*.json"):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                metadata = data.get('metadata', {})
                results = data.get('results', [data])
                
                for result in results:
                    if isinstance(result, dict):
                        row = {**metadata, **result}
                        row['_source_file'] = json_file.name
                        all_rows.append(row)
            except Exception as e:
                errors.append((json_file.name, str(e)))
        
        # Verify results
        assert len(all_rows) == 3, f"Expected 3 rows, got {len(all_rows)}"
        assert len(errors) == 1, f"Expected 1 error, got {len(errors)}"
        assert errors[0][0] == "bad.json", f"Expected bad.json error, got {errors[0][0]}"
        
        df = pd.DataFrame(all_rows)
        assert '_source_file' in df.columns, "_source_file column missing"
        assert 'chart' in df.columns, "metadata merge failed"
        assert df['chart'].notna().sum() == 2, "metadata propagation failed"
    
    print("  ✓ JSON loading passed")


def test_filter_topn_integration():
    """Test integration of filters with Top-N."""
    print("Testing filter + Top-N integration...")
    
    df = pd.DataFrame({
        'calmar_ratio': [1.5, 0.8, 1.2, 2.0, 1.0, 1.8, 0.5],
        'profit_factor': [1.7, 1.3, 2.0, 1.5, 1.8, 2.2, 1.0],
        'num_trades': [30, 15, 25, 40, 20, 35, 10]
    })
    
    # Apply filter first
    filtered = df.query("num_trades >= 20", engine="python")
    
    # Apply Top-N
    sorted_df = _build_sorted_df_for_topn(filtered, 'calmar_ratio', desc=True, user_sort_by='')
    topn = sorted_df.head(3)
    
    assert len(topn) == 3, f"Top-N after filter failed: {len(topn)} rows"
    assert topn.iloc[0]['calmar_ratio'] == 2.0, "Top-N after filter sorting failed"
    assert all(topn['num_trades'] >= 20), "Filter not applied before Top-N"
    
    print("  ✓ Filter + Top-N integration passed")


def test_percent_filter_parity():
    """Test that percentage formats produce identical results."""
    print("Testing percentage filter parity...")
    
    df = pd.DataFrame({
        'max_drawdown': [0.05, 0.08, 0.10, 0.12, 0.06]
    })
    
    # Test three equivalent formats
    formats = ["max_drawdown < 8%", "max_drawdown < 8 %", "max_drawdown < 0.08"]
    results = []
    
    for fmt in formats:
        result = _apply_query_sort_limit(df, fmt, "", 0)
        results.append(len(result))
    
    assert all(r == results[0] for r in results), \
        f"Percentage format parity failed: {results}"
    assert results[0] == 2, f"Expected 2 rows, got {results[0]}"
    
    print("  ✓ Percentage filter parity passed")


def run_all_tests():
    """Run all smoke tests."""
    print("=" * 60)
    print("Running Optimization Console Lite Smoke Tests")
    print("=" * 60)
    
    try:
        test_percent_normalization()
        test_layered_filters()
        test_query_sort_limit()
        test_topn_sorting()
        test_metric_detection()
        test_load_json_fixtures()
        test_filter_topn_integration()
        test_percent_filter_parity()
        
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        return 0
    
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())

