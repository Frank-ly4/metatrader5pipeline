import pandas as pd

from analyzer.patterns.basic import detect_patterns


def _make_bar(o, h, l, c):
    return {'Open': o, 'High': h, 'Low': l, 'Close': c}


def test_detect_patterns_minimal_synthetic():
    rows = [
        _make_bar(10, 11, 9, 9.5),   # bear body
        _make_bar(9.6, 11.5, 9.1, 11.2),  # bull engulf current
        _make_bar(11.2, 11.8, 10.8, 11.0),
        _make_bar(11.0, 11.1, 10.0, 10.1),  # long lower wick (pin bull)
        _make_bar(10.1, 11.2, 10.0, 10.2),
        _make_bar(10.2, 10.25, 10.15, 10.21),  # doji small body
        _make_bar(10.21, 10.3, 10.2, 10.25),
        _make_bar(10.25, 10.5, 10.0, 10.1),  # outside bar
        _make_bar(10.1, 10.15, 10.05, 10.1),  # inside bar
    ]
    df = pd.DataFrame(rows)
    idx = pd.date_range('2020-01-01', periods=len(df), freq='D')
    df.index = idx
    pats = detect_patterns(df)
    assert pats['candle_engulf_bull'].iloc[1] == 1
    assert pats['candle_pin_bull'].iloc[3] == 1
    assert pats['candle_doji'].iloc[5] == 1
    assert pats['outside_bar'].iloc[7] == 1
    assert pats['inside_bar'].iloc[8] == 1


