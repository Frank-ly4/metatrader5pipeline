import pandas as pd
import pandas_ta as ta
import numpy as np

def add_regime_labels(
    df: pd.DataFrame,
    ema_period: int = 200,
    adx_period: int = 14,
    adx_threshold: float = 25.0,
    atr_period: int = 14,
    bband_period: int = 20,
    vol_low_q: float = 0.33,
    vol_high_q: float = 0.66
) -> pd.DataFrame:
    """
    Adds a 'regime' column to the DataFrame based on trend and volatility.

    Args:
        df (pd.DataFrame): Input DataFrame with OHLC columns.
        ema_period (int): Period for the trend-defining EMA.
        adx_period (int): Period for the ADX indicator.
        adx_threshold (float): ADX value above which is considered a trend.
        atr_period (int): Period for the ATR volatility indicator.
        bband_period (int): Period for the Bollinger Bands volatility indicator.
        vol_low_q (float): The quantile for defining low volatility.
        vol_high_q (float): The quantile for defining high volatility.

    Returns:
        pd.DataFrame: DataFrame with the added 'regime' column.
    """
    if df.empty or len(df) < max(ema_period, adx_period, bband_period):
        df['regime'] = 'NO_DATA'
        return df

    # 1. Trend Detection (EMA for direction, ADX for strength)
    ema = ta.ema(df['Close'], length=ema_period)
    adx_df = ta.adx(df['High'], df['Low'], df['Close'], length=adx_period)

    is_trending = (adx_df[f'ADX_{adx_period}'] > adx_threshold).fillna(False)
    is_uptrend = (df['Close'] > ema).fillna(False)

    # 2. Volatility Detection (ATR relative to price + Bollinger Band Width)
    atr_rel = (ta.atr(df['High'], df['Low'], df['Close'], length=atr_period) / df['Close']).fillna(0)
    bbands = ta.bbands(df['Close'], length=bband_period)
    bb_width = (bbands[f'BBU_{bband_period}_2.0'] - bbands[f'BBL_{bband_period}_2.0']) / bbands[f'BBM_{bband_period}_2.0']
    bb_width = bb_width.fillna(0)

    vol_composite = (atr_rel + bb_width) / 2.0
    low_vol_threshold = vol_composite.quantile(vol_low_q)
    high_vol_threshold = vol_composite.quantile(vol_high_q)

    # 3. Labeling
    conditions = [
        is_trending & is_uptrend & (vol_composite > high_vol_threshold),
        is_trending & is_uptrend & (vol_composite < low_vol_threshold),
        is_trending & is_uptrend,
        is_trending & ~is_uptrend & (vol_composite > high_vol_threshold),
        is_trending & ~is_uptrend & (vol_composite < low_vol_threshold),
        is_trending & ~is_uptrend,
        ~is_trending & (vol_composite > high_vol_threshold),
        ~is_trending & (vol_composite < low_vol_threshold),
    ]
    labels = [
        'TREND_UP_HIGH_VOL', 'TREND_UP_LOW_VOL', 'TREND_UP_MED_VOL',
        'TREND_DOWN_HIGH_VOL', 'TREND_DOWN_LOW_VOL', 'TREND_DOWN_MED_VOL',
        'RANGE_HIGH_VOL', 'RANGE_LOW_VOL',
    ]
    df['regime'] = np.select(conditions, labels, default='RANGE_MED_VOL')

    # Clean up intermediate columns created by pandas-ta
    df.drop(columns=adx_df.columns, inplace=True, errors='ignore')
    df.drop(columns=bbands.columns, inplace=True, errors='ignore')

    return df