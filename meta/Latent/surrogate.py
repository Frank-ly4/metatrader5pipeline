import argparse
import os
import json
import numpy as np
import pandas as pd

try:
    import xgboost as xgb
except Exception:
    xgb = None

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import Ridge
except Exception:
    RandomForestRegressor = None
    Ridge = None


def load_z(z_path: str) -> np.ndarray:
    return np.load(z_path)


def load_features(features_path: str) -> pd.DataFrame:
    return pd.read_parquet(features_path)


def build_targets(df: pd.DataFrame, targets: list[str], weights: dict[str, float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cols = [t for t in targets if t in df.columns]
    if not cols:
        raise RuntimeError('No target columns found in features')
    Y = df[cols].astype(float).values
    w = np.array([weights.get(c, 0.0) for c in cols], dtype=float)
    score = (Y * w[None, :]).sum(axis=1)
    mask = np.isfinite(score)
    return Y, score, mask


def train_surrogate(Z: np.ndarray, score: np.ndarray, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    model = None
    meta = {}
    if xgb is not None:
        model = xgb.XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9, colsample_bytree=0.9, random_state=42)
        model.fit(Z, score)
        model.save_model(os.path.join(out_dir, 'surrogate.xgb.json'))
        meta = {'type': 'xgboost'}
    elif RandomForestRegressor is not None:
        model = RandomForestRegressor(n_estimators=300, max_depth=8, random_state=42)
        model.fit(Z, score)
        import joblib
        joblib.dump(model, os.path.join(out_dir, 'surrogate.rf.pkl'))
        meta = {'type': 'random_forest'}
    elif Ridge is not None:
        model = Ridge(alpha=1.0)
        model.fit(Z, score)
        import joblib
        joblib.dump(model, os.path.join(out_dir, 'surrogate.ridge.pkl'))
        meta = {'type': 'ridge'}
    else:
        raise RuntimeError('No suitable ML library found (xgboost or scikit-learn)')

    with open(os.path.join(out_dir, 'surrogate_meta.json'), 'w') as f:
        json.dump(meta, f)
    print(f'Trained surrogate: {meta}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--z_path', required=True)
    ap.add_argument('--features_path', required=True)
    ap.add_argument('--out_dir', required=True)
    ap.add_argument('--targets', nargs='*', default=['sharpe_ratio', 'upi', 'calmar_ratio'])
    ap.add_argument('--weights', nargs='*', default=['sharpe_ratio=0.5', 'upi=0.3', 'calmar_ratio=0.2'])
    args = ap.parse_args()

    Z = load_z(args.z_path)
    df = load_features(args.features_path)
    weight_map = {}
    for w in args.weights:
        k, v = w.split('=')
        weight_map[k] = float(v)
    _, score, mask = build_targets(df, args.targets, weight_map)
    # Align Z and score to mask
    if mask.shape[0] != Z.shape[0]:
        raise RuntimeError(f'Row mismatch: features ({mask.shape[0]}) vs Z ({Z.shape[0]})')
    Zm = Z[mask]
    sm = score[mask]
    if Zm.shape[0] < 5:
        raise RuntimeError('Too few valid rows after filtering NaNs to train surrogate')
    train_surrogate(Zm, sm, args.out_dir)


if __name__ == '__main__':
    main()
