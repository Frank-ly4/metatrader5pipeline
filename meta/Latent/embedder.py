import argparse
import os
import numpy as np
import pandas as pd

try:
    from sklearn.decomposition import PCA
except Exception:
    PCA = None

try:
    import umap
except Exception:
    umap = None


def load_features(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)


def _robust_clip(df: pd.DataFrame, lower_q: float = 0.005, upper_q: float = 0.995) -> pd.DataFrame:
    clipped = df.copy()
    for c in clipped.columns:
        s = clipped[c]
        finite = s[np.isfinite(s)]
        if finite.empty:
            continue
        lo = finite.quantile(lower_q)
        hi = finite.quantile(upper_q)
        if pd.isna(lo) or pd.isna(hi) or lo >= hi:
            continue
        clipped[c] = s.clip(lower=lo, upper=hi)
    return clipped


def make_numeric_matrix(df: pd.DataFrame) -> tuple[np.ndarray, list]:
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        raise RuntimeError('No numeric columns available for embedding')
    Xdf = df[numeric_cols].astype(float)
    # Replace inf with NaN then drop all-NaN columns
    Xdf = Xdf.replace([np.inf, -np.inf], np.nan)
    all_nan = Xdf.columns[Xdf.isna().all()].tolist()
    if all_nan:
        Xdf = Xdf.drop(columns=all_nan)
        numeric_cols = [c for c in numeric_cols if c not in all_nan]
    # Impute NaNs
    means = Xdf.mean(axis=0).fillna(0.0)
    Xdf = Xdf.fillna(means)
    # Robust clip to limit extreme values
    Xdf = _robust_clip(Xdf, 0.005, 0.995)
    X = Xdf.values
    return X, list(Xdf.columns)


def run_pca_umap(features_path: str, out_dir: str, latent_dim: int = 12, use_umap: bool = True, umap_neighbors: int = 30, umap_min_dist: float = 0.1):
    os.makedirs(out_dir, exist_ok=True)
    df = load_features(features_path)
    if df.empty:
        raise RuntimeError('Empty features')
    X, cols = make_numeric_matrix(df)

    if PCA is None:
        raise RuntimeError('scikit-learn is required for PCA')
    n_comp = int(min(latent_dim, X.shape[1], max(1, X.shape[0]-1)))
    pca = PCA(n_components=n_comp)
    Z = pca.fit_transform(X)

    np.save(os.path.join(out_dir, 'z.npy'), Z)
    with open(os.path.join(out_dir, 'pca_cols.txt'), 'w') as f:
        f.write('\n'.join(cols))

    if use_umap and umap is not None:
        reducer = umap.UMAP(n_neighbors=umap_neighbors, min_dist=umap_min_dist, random_state=42)
        V = reducer.fit_transform(Z)
        np.save(os.path.join(out_dir, 'viz.npy'), V)
        try:
            import pickle
            with open(os.path.join(out_dir, 'umap.pkl'), 'wb') as f:
                pickle.dump(reducer, f)
        except Exception:
            pass

    print(f'Wrote latent Z to {os.path.join(out_dir, "z.npy")} and optional viz.npy')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--features_path', required=True)
    ap.add_argument('--out_dir', required=True)
    ap.add_argument('--latent_dim', type=int, default=12)
    ap.add_argument('--use_umap', action='store_true')
    ap.add_argument('--umap_neighbors', type=int, default=30)
    ap.add_argument('--umap_min_dist', type=float, default=0.1)
    args = ap.parse_args()

    run_pca_umap(
        features_path=args.features_path,
        out_dir=args.out_dir,
        latent_dim=args.latent_dim,
        use_umap=args.use_umap,
        umap_neighbors=args.umap_neighbors,
        umap_min_dist=args.umap_min_dist,
    )


if __name__ == '__main__':
    main()
