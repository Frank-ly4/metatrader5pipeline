import argparse
import json
import os
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List

try:
    import yaml  # pyyaml
except Exception:
    yaml = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _flatten_params(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in row.items():
        if isinstance(k, str) and k.startswith('param_'):
            out[k.replace('param_', '')] = v
    return out


def _derive_uid(row: Dict[str, Any]) -> str:
    # Prefer trial_uid or compose from run_id:trial_id
    uid = row.get('trial_uid') or row.get('trial_id')
    run_id = row.get('run_id') or row.get('run')
    chart = row.get('chart')
    if run_id is not None and row.get('trial_id') is not None:
        uid = f"{run_id}:{row.get('trial_id')}"
    if chart:
        return f"{uid}"  # chart is referenced elsewhere
    return str(uid)


def _aggregate_metrics(row: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        'total_return', 'sharpe_ratio', 'sortino_ratio', 'calmar_ratio', 'max_drawdown',
        'profit_factor', 'omega_0', 'omega_fees', 'ulcer_index', 'upi', 'tail_ratio',
        'cvar_95', 'equity_r2', 'turnover', 'time_in_market'
    ]
    agg = {k: row.get(k) for k in keys}
    return agg


def build_strategy_card(row: Dict[str, Any], repo_path: str) -> Dict[str, Any]:
    uid = _derive_uid(row)
    params = _flatten_params(row)
    card = {
        'uid': uid,
        'version': 'opt_4.2.4',
        'owner': '',
        'created_utc': _utc_now(),
        'last_updated_utc': _utc_now(),
        'code': {
            'repo_path': repo_path,
            'commit_hash': ''
        },
        'data': {
            'charts': [row.get('chart')] if row.get('chart') else [],
            'run_id': row.get('run_id'),
            'trial_id': row.get('trial_id'),
            'trial_uid': row.get('trial_uid') or uid,
            'data_hash': ''
        },
        'params': params,
        'backtest_config': {
            'fees': row.get('fees'),
            'position_size': row.get('position_size'),
            'size_type': row.get('size_type'),
            'max_orders': row.get('max_orders'),
            'data_freq': row.get('data_freq')
        },
        'metrics': {
            'is_oos': bool(row.get('is_fold_summary', False)),
            'aggregate': _aggregate_metrics(row),
            'per_fold': []
        },
        'latent': {
            'embedder_version': '',
            'umap_version': '',
            'z': [],
            'recon_error': None,
            'cluster_id': '',
            'cluster_prob': None
        },
        'lineage': {
            'parents': [],
            'method': ''
        },
        'approvals': {
            'state': 'draft',
            'reviewers': [],
            'notes': ''
        },
        'attachments': {
            'artifacts': [],
            'comments': []
        }
    }
    return card


def load_runs(runs_dir: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for name in os.listdir(runs_dir):
        if not name.lower().endswith('.json'):
            continue
        path = os.path.join(runs_dir, name)
        try:
            data = json.load(open(path, 'r'))
        except Exception:
            continue
        results = data.get('results') if isinstance(data, dict) else None
        if isinstance(results, list):
            for row in results:
                row['run_file'] = path
                out.append(row)
    return out


def build_graph(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    nodes = []
    edges = []
    for c in cards:
        uid = c['uid']
        nodes.append({
            'id': uid,
            'type': 'uid',
            'label': uid,
            'z': c.get('latent', {}).get('z') or [],
            'cluster_id': c.get('latent', {}).get('cluster_id') or '',
            'metrics': c.get('metrics', {}).get('aggregate') or {}
        })
        # lineage edges (optional if parents present)
        for p in c.get('lineage', {}).get('parents', []):
            edges.append({
                'source': p,
                'target': uid,
                'method': c.get('lineage', {}).get('method') or 'manual'
            })
    graph = {
        'version': '0.1.0',
        'generated_at_utc': _utc_now(),
        'model_versions': {},
        'nodes': nodes,
        'edges': edges
    }
    return graph


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs_dir', required=True, help='Path to main project outputs/runs')
    ap.add_argument('--out_dir', required=True, help='Output base directory (this Latent folder)')
    ap.add_argument('--repo_path', default='C:/Users/frank/Desktop/opt_4/4.2/4.2.4')
    ap.add_argument('--uids', nargs='*', default=None, help='Optional list of trial_uids to include')
    args = ap.parse_args()

    runs = load_runs(args.runs_dir)
    if args.uids:
        uids = set(args.uids)
        runs = [r for r in runs if (r.get('trial_uid') in uids) or (str(r.get('trial_id')) in uids)]

    cards_dir = os.path.join(args.out_dir, 'cards')
    reg_dir = os.path.join(args.out_dir, 'registry')
    _ensure_dir(cards_dir)
    _ensure_dir(reg_dir)

    cards: List[Dict[str, Any]] = []
    for row in runs:
        card = build_strategy_card(row, args.repo_path)
        uid = card['uid']
        path = os.path.join(cards_dir, f'strategy_card_{uid}.yaml')
        if yaml is None:
            # Fall back to JSON if pyyaml not installed
            path = os.path.join(cards_dir, f'strategy_card_{uid}.json')
            with open(path, 'w') as f:
                json.dump(card, f, indent=2, default=str)
        else:
            with open(path, 'w') as f:
                yaml.safe_dump(card, f, sort_keys=False)
        cards.append(card)

    graph = build_graph(cards)
    with open(os.path.join(reg_dir, 'graph.json'), 'w') as f:
        json.dump(graph, f, indent=2)

    print(f'Wrote {len(cards)} strategy card(s) to {cards_dir}')
    print(f'Wrote registry graph to {os.path.join(reg_dir, "graph.json")}')


if __name__ == '__main__':
    main()
