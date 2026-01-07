import os
import re
from typing import Dict

from src.strategy.regime import infer_timeframe

_TF_RE = re.compile(r"(?P<num>\d+)(?P<unit>[mhd])$", re.IGNORECASE)


def parse_chart_name(chart_path: str, price_index=None) -> Dict[str, str]:
    """
    Parse symbol/timeframe from chart filenames like XAUUSD_1h_cl_3.csv.
    Falls back to timeframe inference from the price index when absent.
    """
    base = os.path.splitext(os.path.basename(chart_path))[0]
    parts = base.split("_")
    symbol = parts[0] if parts else base
    timeframe = None
    for token in parts[1:]:
        m = _TF_RE.match(token)
        if m:
            timeframe = f"{m.group('num')}{m.group('unit').lower()}"
            break
    if timeframe is None and price_index is not None:
        try:
            timeframe = infer_timeframe(price_index)
        except Exception:
            timeframe = "unknown"
    return {"symbol": symbol, "timeframe": timeframe or "unknown", "chart": base}

