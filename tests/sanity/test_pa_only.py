import pandas as pd

from analyzer.providers.pa_only import compute_pa_trend


def _bars(seq):
    return pd.DataFrame(seq, index=pd.date_range('2020-01-01', periods=len(seq), freq='D'))


def test_pa_only_determinism_uptrend():
    # Monotonic HH/HL sequence should yield 'up' trend
    seq = [
        {'Open': 10, 'High': 11, 'Low': 9, 'Close': 10.5},
        {'Open': 10.6, 'High': 11.5, 'Low': 10.1, 'Close': 11.2},
        {'Open': 11.1, 'High': 12.0, 'Low': 10.8, 'Close': 11.8},
        {'Open': 11.7, 'High': 12.5, 'Low': 11.3, 'Close': 12.2},
        {'Open': 12.1, 'High': 13.0, 'Low': 11.8, 'Close': 12.7},
    ]
    df = _bars(seq)
    out = compute_pa_trend(df, left=1, right=1)
    assert out['trend_label'].iloc[-1] == 'up'


def test_pa_only_determinism_downtrend():
    # Monotonic LL/LH sequence should yield 'down' trend
    seq = [
        {'Open': 13, 'High': 13.5, 'Low': 12.5, 'Close': 13.2},
        {'Open': 12.9, 'High': 13.0, 'Low': 12.0, 'Close': 12.3},
        {'Open': 12.4, 'High': 12.6, 'Low': 11.4, 'Close': 11.8},
        {'Open': 11.7, 'High': 11.9, 'Low': 11.0, 'Close': 11.2},
        {'Open': 11.0, 'High': 11.2, 'Low': 10.4, 'Close': 10.6},
    ]
    df = _bars(seq)
    out = compute_pa_trend(df, left=1, right=1)
    assert out['trend_label'].iloc[-1] == 'down'


def test_pa_only_choppy_range():
    # Choppy sequence should yield 'range'
    seq = [
        {'Open': 10, 'High': 11, 'Low': 9, 'Close': 10.5},
        {'Open': 10.4, 'High': 10.8, 'Low': 9.8, 'Close': 10.3},
        {'Open': 10.2, 'High': 11.1, 'Low': 9.9, 'Close': 10.6},
        {'Open': 10.5, 'High': 10.7, 'Low': 10.0, 'Close': 10.2},
        {'Open': 10.1, 'High': 10.9, 'Low': 9.8, 'Close': 10.4},
    ]
    df = _bars(seq)
    out = compute_pa_trend(df, left=1, right=1)
    assert out['trend_label'].iloc[-1] == 'range'


