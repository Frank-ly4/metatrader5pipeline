from __future__ import annotations

import json
import os
from pathlib import Path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_all() -> None:
    # constitution exists
    const_path = Path(__file__).resolve().parents[2] / "config" / "constitution.json"
    if not const_path.exists():
        raise FileNotFoundError(f"constitution.json missing at {const_path}")
    c = _load_json(const_path)

    # required modules
    root = Path(__file__).resolve().parents[2]
    for mod in ["strategy", "optimizer", "backtester", "io", "config", "meta"]:
        if not (root / "src" / mod).exists() and not (root / mod).exists():
            raise FileNotFoundError(f"Module missing: {mod}")

    # logs paths
    for key in ["discoveries_log", "issues_log"]:
        if key not in c.get("paths", {}):
            raise AssertionError(f"constitution.paths.{key} missing")

    # discoveries file should exist (created on first run)
    disc_path = root / c["paths"]["discoveries_log"]
    (disc_path.parent).mkdir(parents=True, exist_ok=True)
    if not disc_path.exists():
        disc_path.write_text("# Discoveries\n", encoding="utf-8")

    # issues file should exist
    issues_path = root / c["paths"]["issues_log"]
    (issues_path.parent).mkdir(parents=True, exist_ok=True)
    if not issues_path.exists():
        issues_path.write_text("# Issues\n", encoding="utf-8")

    print("meta_validator: OK")


if __name__ == "__main__":
    validate_all()


