import numpy as np
from numba import njit


@njit(cache=True, nogil=True)
def mcg_dma_fast(source, min_len, max_len, atr_len, atr_smoothing_len=100):
    dma = np.full_like(source, np.nan)
    volatility = np.full_like(source, np.nan)
    tr = np.zeros_like(source)
    for i in range(1, len(source)):
        tr[i] = np.maximum(source[i-1], source[i]) - np.minimum(source[i-1], source[i])
    alpha_atr = 2.0 / (atr_len + 1)
    atr = np.full_like(source, np.nan)
    if len(source) > 0:
        dma[0] = source[0]
    if atr_len <= len(source):
        atr[atr_len-1] = np.mean(tr[0:atr_len])
    for i in range(max(atr_len, 1), len(source)):
        atr[i] = alpha_atr * tr[i] + (1 - alpha_atr) * atr[i-1]
    min_len = int(min_len) if min_len > 1 else 1
    max_len = int(max_len) if max_len > min_len else (min_len + 1)
    mid_len = (min_len + max_len) // 2
    # Delay adaptivity until ATR exists
    for i in range(1, len(source)):
        prev_dma = dma[i-1]
        if not np.isfinite(prev_dma):
            dma[i] = source[i]
            continue

        # If atr or price invalid, fallback to midpoint
        if i < atr_len or (not np.isfinite(atr[i])) or (source[i] == 0.0) or (not np.isfinite(source[i])):
            final_len = mid_len
        else:
            # Compute volatility safely
            volatility[i] = atr[i] / source[i]
            if not np.isfinite(volatility[i]):
                final_len = mid_len
            else:
                # Check subwindow for finite values
                start = 0 if i < atr_smoothing_len else i - atr_smoothing_len
                has_valid = False
                vol_min = 0.0  # float scalar
                vol_max = 0.0  # float scalar
                for j in range(start, i+1):
                    if np.isfinite(volatility[j]):
                        val = volatility[j]
                        if not has_valid:
                            vol_min = val
                            vol_max = val
                            has_valid = True
                        else:
                            if val < vol_min:
                                vol_min = val
                            if val > vol_max:
                                vol_max = val
                if not has_valid:
                    final_len = mid_len
                else:
                    clamped_vol = volatility[i] if volatility[i] > 0.001 else 0.001
                    vrange = vol_max - vol_min
                    denom = vrange if vrange > 1e-9 else 1.0
                    vol_index = (clamped_vol - vol_min) / denom
                    if vol_index < 0.0:
                        vol_index = 0.0
                    elif vol_index > 1.0:
                        vol_index = 1.0
                    dynamic_len = max_len - (max_len - min_len) * vol_index
                    # Avoid np.round to keep scalar type in nopython
                    final_len = int(dynamic_len + 0.5)

        if final_len < 1:
            final_len = 1
        if final_len < min_len:
            final_len = min_len
        elif final_len > max_len:
            final_len = max_len
        alpha_dma = 2.0 / (final_len + 1.0)
        dma[i] = alpha_dma * source[i] + (1.0 - alpha_dma) * prev_dma
    return dma


def vbt_mcg_dma_indicator():
    from vectorbt.indicators.factory import IndicatorFactory
    return IndicatorFactory(
        class_name='McGinleyDMA',
        short_name='mcg_dma',
        input_names=['close'],
        param_names=['min_len', 'max_len', 'atr_len'],
        output_names=['real']
    ).from_apply_func(
        lambda close, min_len, max_len, atr_len: mcg_dma_fast((close.values[:, 0] if hasattr(close, 'values') and close.values.ndim == 2 else close.values), min_len, max_len, atr_len),
        min_len=10,
        max_len=20,
        atr_len=14,
        keep_pd=True
    )


