from __future__ import annotations

import json
import os
from typing import Tuple


def ensure_unicode_workspace(base_dir: str) -> str:
    name = "tmp_📈测试"
    path = os.path.join(base_dir, name)
    os.makedirs(path, exist_ok=True)
    return path


def write_valid_json(path: str, filename: str, chart: str, fold_id: int, rows=3) -> str:
    data = {
        "metadata": {"chart": chart, "fold_id": fold_id},
        "results": []
    }
    for i in range(rows):
        data["results"].append({
            "calmar_ratio": 1.0 + i * 0.1,
            "max_drawdown": 0.05 + (i * 0.01),
            "profit_factor": 1.4 + i * 0.2,
            "sharpe_ratio": 1.1 + i * 0.1,
            "win_rate": 0.55 + i * 0.05,
            "num_trades": 30 + i * 10,
            "param_lookback": 10 + i,
        })
    fpath = os.path.join(path, filename)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return fpath


def write_malformed_json(path: str, filename: str) -> str:
    fpath = os.path.join(path, filename)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("{ this is not valid json ")
    return fpath


def generate_fixtures(base_dir: str) -> Tuple[str, list[str]]:
    ws = ensure_unicode_workspace(base_dir)
    files = []
    files.append(write_valid_json(ws, "valid_A.json", "EURUSD", 1))
    files.append(write_valid_json(ws, "valid_B.json", "GBPUSD", 2))
    files.append(write_malformed_json(ws, "malformed.json"))
    return ws, files


