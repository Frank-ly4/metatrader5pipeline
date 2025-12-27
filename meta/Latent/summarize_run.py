import os
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def summarize(base_dir: str) -> dict:
    paths = {
        'features': os.path.join(base_dir, 'features', 'features.parquet'),
        'z': os.path.join(base_dir, 'models', 'z.npy'),
        'clusters': os.path.join(base_dir, 'clusters', 'clusters.parquet'),
        'cluster_summaries': os.path.join(base_dir, 'clusters', 'cluster_summaries.json'),
        'surrogate_meta': os.path.join(base_dir, 'surrogate', 'surrogate_meta.json'),
        'proposals': os.path.join(base_dir, 'proposals', 'proposals.json'),
    }
    out = {
        'timestamp_utc': utc_now(),
        'features': {'path': paths['features'], 'rows': None, 'cols': None, 'ok': False},
        'latent': {'path': paths['z'], 'n': None, 'dim': None, 'ok': False},
        'clusters': {'path': paths['clusters'], 'n_rows': None, 'n_clusters': None, 'ok': False},
        'surrogate': {'path': paths['surrogate_meta'], 'type': None, 'ok': False},
        'proposals': {'path': paths['proposals'], 'count': None, 'ok': False},
        'notes': []
    }
    # features
    try:
        df = pd.read_parquet(paths['features'])
        out['features']['rows'] = int(len(df))
        out['features']['cols'] = int(len(df.columns))
        out['features']['ok'] = True
    except Exception as e:
        out['notes'].append(f'features error: {e}')
    # z
    try:
        Z = np.load(paths['z'])
        out['latent']['n'] = int(Z.shape[0])
        out['latent']['dim'] = int(Z.shape[1]) if Z.ndim > 1 else 1
        out['latent']['ok'] = True
    except Exception as e:
        out['notes'].append(f'latent error: {e}')
    # clusters
    try:
        cdf = pd.read_parquet(paths['clusters'])
        out['clusters']['n_rows'] = int(len(cdf))
        n_clusters = int(cdf['label'].nunique()) if 'label' in cdf.columns else None
        out['clusters']['n_clusters'] = n_clusters
        out['clusters']['ok'] = True
    except Exception as e:
        out['notes'].append(f'clusters error: {e}')
    # surrogate
    try:
        meta = json.load(open(paths['surrogate_meta'], 'r'))
        out['surrogate']['type'] = meta.get('type')
        out['surrogate']['ok'] = True
    except Exception as e:
        out['notes'].append(f'surrogate error: {e}')
    # proposals
    try:
        props = json.load(open(paths['proposals'], 'r'))
        out['proposals']['count'] = int(len(props)) if isinstance(props, list) else None
        out['proposals']['ok'] = True
    except Exception as e:
        out['notes'].append(f'proposals error: {e}')
    return out


def main():
    base_dir = os.getcwd()
    summary = summarize(base_dir)
    logs_dir = os.path.join(base_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    out_path = os.path.join(logs_dir, f'latent_run_{stamp}.json')
    with open(out_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(out_path)


if __name__ == '__main__':
    main()
