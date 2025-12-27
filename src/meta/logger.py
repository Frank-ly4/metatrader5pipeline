from __future__ import annotations

import os
from datetime import datetime


def _ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def _append(path: str, block: str) -> None:
    _ensure_dir(os.path.dirname(path))
    with open(path, 'a', encoding='utf-8') as f:
        f.write(block)


def append_discovery(base_dir: str, entry: dict) -> None:
    log_path = os.path.join(base_dir, 'meta', 'discoveries.md')
    block = []
    block.append(f"\n\n## [{entry.get('version','4.2.x')}] {entry.get('date', datetime.utcnow().isoformat())} — {entry.get('experiment_id','generator')}\n")
    block.append(f"- Run: {entry.get('run_id','')}\n")
    block.append(f"- Trials: {entry.get('trials','')}\n")
    block.append(f"- trial_uid: {entry.get('trial_uid','')}\n")
    block.append(f"- Artifacts: {entry.get('artifact','')}\n")
    _append(log_path, ''.join(block))


def append_issue(base_dir: str, entry: dict) -> None:
    log_path = os.path.join(base_dir, 'meta', 'issues.md')
    block = []
    block.append(f"\n\n## {datetime.utcnow().isoformat()} — run:{entry.get('run_id','')} — Severity: {entry.get('severity','LOW')}\n")
    block.append(f"- context: {entry.get('context','')}\n")
    block.append(f"- trial_uid: {entry.get('trial_uid','')}\n")
    block.append(f"- exception: {entry.get('message','')}\n")
    block.append(f"- action: {entry.get('action','logged')}\n")
    _append(log_path, ''.join(block))



