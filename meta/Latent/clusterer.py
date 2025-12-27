import argparse
import os
import json
import numpy as np
import pandas as pd

try:
    import hdbscan
except Exception:
    hdbscan = None

try:
    from sklearn.cluster import KMeans
except Exception:
    KMeans = None


def load_z(path: str) -> np.ndarray:
    return np.load(path)


def cluster_hdbscan(Z: np.ndarray, min_cluster_size: int, min_samples: int):
    if hdbscan is None:
        raise RuntimeError('hdbscan not installed')
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples)
    labels = clusterer.fit_predict(Z)
    probs = getattr(clusterer, 'probabilities_', np.ones_like(labels, dtype=float))
    outliers = getattr(clusterer, 'outlier_scores_', np.zeros_like(labels, dtype=float))
    return labels, probs, outliers


def cluster_kmeans(Z: np.ndarray, k: int):
    if KMeans is None:
        raise RuntimeError('scikit-learn not installed for KMeans')
    km = KMeans(n_clusters=k, n_init='auto', random_state=42)
    labels = km.fit_predict(Z)
    probs = np.ones_like(labels, dtype=float)
    outliers = np.zeros_like(labels, dtype=float)
    return labels, probs, outliers


def write_outputs(out_dir: str, labels: np.ndarray, probs: np.ndarray, outlier_scores: np.ndarray):
    os.makedirs(out_dir, exist_ok=True)
    df = pd.DataFrame({
        'label': labels,
        'prob': probs,
        'outlier_score': outlier_scores
    })
    df.to_parquet(os.path.join(out_dir, 'clusters.parquet'), index=False)

    # summaries
    uniq = np.unique(labels[labels >= 0])
    summaries = {int(l): {'count': int((labels == l).sum())} for l in uniq}
    with open(os.path.join(out_dir, 'cluster_summaries.json'), 'w') as f:
        json.dump(summaries, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--z_path', required=True)
    ap.add_argument('--out_dir', required=True)
    ap.add_argument('--method', default='hdbscan', choices=['hdbscan', 'kmeans'])
    ap.add_argument('--min_cluster_size', type=int, default=30)
    ap.add_argument('--min_samples', type=int, default=10)
    ap.add_argument('--k', type=int, default=8)
    args = ap.parse_args()

    Z = load_z(args.z_path)
    if args.method == 'hdbscan':
        labels, probs, outliers = cluster_hdbscan(Z, args.min_cluster_size, args.min_samples)
    else:
        labels, probs, outliers = cluster_kmeans(Z, args.k)
    write_outputs(args.out_dir, labels, probs, outliers)
    print(f'Wrote clustering outputs to {args.out_dir}')


if __name__ == '__main__':
    main()
