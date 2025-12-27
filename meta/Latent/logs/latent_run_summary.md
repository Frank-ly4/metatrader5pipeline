# Latent Pipeline Run Summary

Date (UTC): <fill>

## What worked well
- Features built from repo runs: `features/features.parquet` created.
- PCA embedder completed with NaN/Inf handling and robust clipping: `models/z.npy` generated.
- KMeans clustering fallback succeeded (HDBSCAN not installed): `clusters/clusters.parquet` and `cluster_summaries.json` written.
- Surrogate trained (RandomForest fallback): `surrogate/surrogate_meta.json`, `surrogate/surrogate.rf.pkl`.
- Navigator produced proposals: `proposals/proposals.json` (40 candidates).

## Issues encountered (bugs/errors)
- Initial PCA failed due to NaNs/Inf in features. Fixed by:
  - Replacing Inf with NaN, dropping all-NaN columns.
  - Imputing NaNs with column means.
  - Robust clipping to 0.5%–99.5% quantiles.
- HDBSCAN not installed: fell back to KMeans (works but less nuanced for variable-density manifolds).
- Surrogate training initially failed due to NaNs in target score. Fixed by filtering out rows with NaN targets and aligning mask with Z.

## Works but could be better
- Embedder: Switch to AE (denoising + multitask heads) and keep PCA as baseline.
- Clustering: Install `hdbscan` to capture density structure and outliers.
- Features: Add market/window features and equity-shape descriptors (run lengths, drawdown histogram) to enrich semantics.
- Surrogate: Prefer XGBoost/GPR with uncertainty; add CV metrics and SHAP diagnostics.
- Navigator: Replace stub decoder with real AE decoder; add BO steps and MAP-Elites.
- Logging: Turn the ad-hoc PowerShell run into `run_latent_pipeline.py` with structured logging and a single run ID.

## Artifacts
- features: `features/features.parquet`
- models: `models/z.npy`, `models/pca_cols.txt`
- clusters: `clusters/clusters.parquet`, `clusters/cluster_summaries.json`
- surrogate: `surrogate/surrogate.rf.pkl`, `surrogate/surrogate_meta.json`
- proposals: `proposals/proposals.json`
