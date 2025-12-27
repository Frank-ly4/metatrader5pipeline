import argparse
import os
import json
import yaml

from feature_builder import build_features
from embedder import run_pca_umap
from clusterer import load_z as load_z_np, cluster_hdbscan, cluster_kmeans, write_outputs as write_clusters
from surrogate import train_surrogate, load_z as load_z_for_surrogate, load_features as load_features_for_surrogate, build_targets
from navigator import compute_cluster_stats, sample_proposals, write_proposals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='latent_config.yaml')
    ap.add_argument('--light', action='store_true', help='Enable light mode for fast iteration')
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, 'r'))
    runs_dir = cfg['runs_dir']
    out_dir = cfg['out_dir']

    lm = cfg.get('light_mode', {}) if args.light else {}

    # 1) Features
    features_path = os.path.join(out_dir, cfg['features_path'])
    features = build_features(
        runs_dir,
        features_path,
        cfg.get('metric_columns', []),
        max_runs=lm.get('max_runs') or cfg.get('max_runs')
    )
    if features.empty:
        print('No features; exiting')
        return

    # 2) Embedder (PCA + optional UMAP)
    models_dir = os.path.join(out_dir, cfg['models_dir'])
    run_pca_umap(
        features_path=features_path,
        out_dir=models_dir,
        latent_dim=cfg.get('latent_dim', 12),
        use_umap=bool(lm.get('use_umap', cfg.get('use_umap', True))),
        umap_neighbors=cfg.get('umap_n_neighbors', 30),
        umap_min_dist=cfg.get('umap_min_dist', 0.1),
    )

    # 3) Clusterer
    z_path = os.path.join(models_dir, 'z.npy')
    Z = load_z_np(z_path)
    clusters_dir = os.path.join(out_dir, cfg['clusters_dir'])
    method = cfg.get('clusterer', 'kmeans')
    if method == 'hdbscan':
        labels, probs, outliers = cluster_hdbscan(Z, cfg.get('hdbscan_min_cluster_size', 30), cfg.get('hdbscan_min_samples', 10))
    else:
        k = int(lm.get('kmeans_k', cfg.get('kmeans_k', 8)))
        labels, probs, outliers = cluster_kmeans(Z, k)
    write_clusters(clusters_dir, labels, probs, outliers)

    # 4) Surrogate
    surrogate_dir = os.path.join(out_dir, cfg['surrogate_dir'])
    df = load_features_for_surrogate(features_path)
    targets = cfg.get('surrogate_targets', ['sharpe_ratio', 'upi', 'calmar_ratio'])
    weights = cfg.get('score_weights', {'sharpe_ratio': 0.5, 'upi': 0.3, 'calmar_ratio': 0.2})
    _, score, mask = build_targets(df, targets, weights)
    if mask.shape[0] != Z.shape[0]:
        raise RuntimeError(f'Row mismatch: features ({mask.shape[0]}) vs Z ({Z.shape[0]})')
    from numpy import array
    train_surrogate(Z[mask], score[mask], surrogate_dir)

    # 5) Navigator
    import pandas as pd
    clusters_path = os.path.join(clusters_dir, 'clusters.parquet')
    cdf = pd.read_parquet(clusters_path)
    centers, covs = compute_cluster_stats(Z, cdf['label'].values.astype(int))
    proposals_dir = os.path.join(out_dir, cfg['proposals_dir'])
    num_per_cluster = int(lm.get('num_per_cluster', cfg.get('num_proposals', 20)))
    stubs = sample_proposals(centers, covs, num_per_cluster=num_per_cluster, scale=cfg.get('trust_region_scale', 1.0))
    write_proposals(proposals_dir, stubs)

    print('Latent pipeline completed.')


if __name__ == '__main__':
    main()
