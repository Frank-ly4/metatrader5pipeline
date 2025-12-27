"""JSON IO for per-run artifact under outputs/runs/.

Writes a single JSON per run with metadata, results summary, and paths.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict


def ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def write_run_json(base_outputs_dir: str, filename: str, payload: Dict[str, Any]) -> str:
    runs_dir = os.path.join(base_outputs_dir, "runs")
    ensure_dir(runs_dir)
    json_path = os.path.abspath(os.path.join(runs_dir, filename))
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return json_path



