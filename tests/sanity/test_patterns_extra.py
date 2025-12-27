import pandas as pd

from analyzer.patterns.basic import detect_patterns


def _bar(o, h, l, c):
    return {'Open': o, 'High': h, 'Low': l, 'Close': c}


def test_engulf_bear_and_pin_bear_and_nr7():
    # Construct a sequence:
    # 0: small bull
    # 1: large bear engulfing
    # 2-6: varying ranges; ensure last is smallest for NR7
    rows = [
        _bar(10.0, 10.6, 9.8, 10.4),     # small bull body
        _bar(10.5, 10.6, 9.0, 9.2),      # large bear body that engulfs previous body
        _bar(9.2, 10.0, 9.0, 9.6),
        _bar(9.6, 10.4, 9.2, 9.8),
        _bar(9.8, 10.2, 9.4, 9.9),
        _bar(9.9, 10.1, 9.7, 10.0),
        _bar(10.0, 10.05, 9.98, 10.01),  # smallest range for NR7 at index 6
        _bar(10.01, 10.9, 9.9, 9.95),    # long upper wick, small body -> pin bear
    ]
    df = pd.DataFrame(rows)
    df.index = pd.date_range('2021-01-01', periods=len(df), freq='D')

    pats = detect_patterns(df)

    # Engulf bear at index 1
    assert pats['candle_engulf_bear'].iloc[1] == 1

    # NR7 at index 6
    assert pats['nr7'].iloc[6] == 1

    # Pin bear at index 7
    assert pats['candle_pin_bear'].iloc[7] == 1


