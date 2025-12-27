import argparse
import os
import json
import numpy as np


def load_z(z_path: str) -> np.ndarray:
    return np.load(z_path)


def load_clusters(clusters_path: str):
    import pandas as pd
    return pd.read_parquet(clusters_path)


def compute_cluster_stats(Z: np.ndarray, labels: np.ndarray):
    centers = {}
    covs = {}
    for l in np.unique(labels):
        if l < 0:
            continue
        idx = np.where(labels == l)[0]
        if len(idx) < 2:
            continue
        Zc = Z[idx]
        centers[int(l)] = Zc.mean(axis=0)
        covs[int(l)] = np.cov(Zc.T) + 1e-6 * np.eye(Zc.shape[1])
    return centers, covs


def sample_proposals(centers: dict, covs: dict, num_per_cluster: int, scale: float) -> list[dict]:
    props = []
    rng = np.random.default_rng(42)
    for cid, mu in centers.items():
        Sigma = covs[cid]
        try:
            L = np.linalg.cholesky(Sigma)
        except np.linalg.LinAlgError:
            L = np.linalg.cholesky(Sigma + 1e-6 * np.eye(Sigma.shape[0]))
        for i in range(num_per_cluster):
            eps = rng.standard_normal(mu.shape[0])
            z = mu + scale * (L @ eps)
            props.append({'cluster_id': cid, 'z': z.tolist(), 'method': 'trust_region'})
    return props


def decode_params_stub(z: list[float]) -> dict:
    # Placeholder decoder: map z to param placeholders.
    # In the full system, this uses the AE decoder.
    return {
        'fast_min_len': int(8 + (z[0] if len(z) > 0 else 0) % 8),
        'fast_max_len': int(16 + (z[1] if len(z) > 1 else 0) % 8),
        'slow_min_len': int(28 + (z[2] if len(z) > 2 else 0) % 12),
        'slow_max_len': int(40 + (z[3] if len(z) > 3 else 0) % 16),
        'atr_len': int(10 + abs(int(z[4] if len(z) > 4 else 0)) % 10),
    }


def write_proposals(out_dir: str, proposals: list[dict]):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'proposals.json')
    with open(path, 'w') as f:
        json.dump(proposals, f, indent=2)
    print(f'Wrote {len(proposals)} proposal(s) to {path}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--z_path', required=True)
    ap.add_argument('--clusters_path', required=True)
    ap.add_argument('--out_dir', required=True)
    ap.add_argument('--num_per_cluster', type=int, default=5)
    ap.add_argument('--scale', type=float, default=1.0)
    args = ap.parse_args()

    Z = load_z(args.z_path)
    cdf = load_clusters(args.clusters_path)
    labels = cdf['label'].values.astype(int)
    centers, covs = compute_cluster_stats(Z, labels)
    stubs = sample_proposals(centers, covs, args.num_per_cluster, args.scale)

    # Stub decode to params
    for s in stubs:
        s['decoded_params'] = decode_params_stub(s['z'])

    write_proposals(args.out_dir, stubs)


if __name__ == '__main__':
    main()
