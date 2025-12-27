import os
import json


def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path)


def write_json(data: dict, out_dir: str, filename: str):
    ensure_dir(out_dir)
    with open(os.path.join(out_dir, filename), 'w') as f:
        json.dump(data, f, indent=2, default=str)


