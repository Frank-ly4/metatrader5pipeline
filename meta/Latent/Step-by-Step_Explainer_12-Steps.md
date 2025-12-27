## Latent-Space Integration – Step-by-Step Explainer (12 Steps)

This guide explains each step in enough detail for a newcomer to execute and reason about the system. Paths refer to v4.2.4.

### Step 1 — Approve Data Contracts
- Purpose: Lock the schemas used downstream so artifacts remain stable and reproducible.
- Inputs: `outputs/runs/*.json`, CSV summaries, v4.3 metric additions.
- Outputs: Two schemas documented in `meta/architecture.md`:
  - FeatureRow: params_feat[p], outcomes_feat[q], market_feat[r], keys: uid, run_id, trial_id, chart.
  - LatentPoint: z[d], recon_error, embedder_version, umap_version, cluster_id, cluster_prob.
- Actions:
  1) Enumerate v4.3 metrics to include (CAGR, Calmar, Omega, UPI, UI, tail ratio, CVaR, equity R^2, turnover, time-in-market, fee-sensitivity deltas; regime metrics if enabled).
  2) Define parameter feature rules: z-score continuous; one-hot toggles; include constraint flags; optional finite-diff sensitivities.
  3) Define market features: realized vol/quarticity, ADX/momentum slope, ACF(1), seasonality.
- Validation: Create a one-row example (gold 2h) and verify downstream consumers can parse.
- Owner: Research Eng; Gate: PM/Lead sign-off.

### Step 2 — Build FeatureBuilder (`src/latent/feature_builder.py`)
- Purpose: Transform optimizer/backtester outputs into model-ready FeatureRow parquet.
- Inputs: `outputs/runs/*.json`, CSVs per run; `config/*` for fees/freq.
- Outputs: `outputs/latent/features/feature_rows.parquet` (append-only) keyed by `run_id, trial_id, chart`.
- Actions:
  1) Load results, normalize param types/keys; scale continuous; one-hot toggles; add constraint flags.
  2) Merge with outcome metrics; compute shape features (Hurst, drawdown histogram, run-length stats).
  3) Compute market features over each trial’s time window.
  4) Write parquet with stable column order and dtypes.
- Validation: Row count equals trial count; random spot-check feature values and index alignment.
- Owner: Research Eng; Gate: Schema validation passes; data snapshot recorded.

### Step 3 — Implement AE Embedder (`src/latent/embedder.py`)
- Purpose: Learn a compact latent z representing params+outcomes+market semantics.
- Inputs: FeatureRow parquet.
- Outputs: `outputs/latent/models/` (AE weights, config, training metrics), `outputs/latent/latent_points.parquet` (z, recon error, versions).
- Actions:
  1) Choose AE architecture (dense or small TCN if using sequence channels); latent size d=8–16.
  2) Training losses: reconstruction + auxiliary heads to predict a few target metrics (Sharpe/Calmar/UPI) for semantically aligned z; add denoising/noise.
  3) Train/validate; store model card with hashes of data split and config.
  4) Inference: compute z and recon error for all FeatureRows; append to latent_points.
- Validation: CV curve stable; recon error distributions reasonable; auxiliary R^2 acceptable.
- Owner: ML Eng; Gate: Model card and hashes recorded.

### Step 4 — UMAP for Visualization (Display Only)
- Purpose: Create 2D/3D embeddings for GUI; AE z remains authoritative.
- Inputs: `latent_points.parquet`.
- Outputs: `outputs/latent/umap/umap_points.parquet` with coords and versions.
- Actions: Fit UMAP on AE z (seed fixed); store params and seed; do not replace z.
- Validation: Visual coherence; clusters visibly separable; deterministic across runs with same seed.
- Owner: ML Eng; Gate: UMAP config versioned.

### Step 5 — Clusterer (`src/latent/clusterer.py`)
- Purpose: Identify niches (high-performing regions), detect outliers, compute cluster scorecards.
- Inputs: AE z; optional density-aware k-NN graph.
- Outputs: `cluster_assignments.parquet`, `cluster_summary.json`.
- Actions: Run HDBSCAN (min_cluster_size≈30, min_samples≈10 to start); compute medians/IQRs of metrics, stability (IS/OOS gaps), size, density.
- Validation: Fraction of outliers reasonable; top clusters align with strong metrics; stability checks pass.
- Owner: ML Eng; Gate: Cluster report reviewed.

### Step 6 — Surrogate Model (`src/latent/surrogate.py`)
- Purpose: Predict multi-objective scores from z for smooth optimization and uncertainty-aware search.
- Inputs: z, target vector of metrics; scalarization function.
- Outputs: Pickled model + SHAP attributions.
- Actions: Train GP or XGBoost; cross-validate; choose acquisition (e.g., Expected Improvement) for BO.
- Validation: CV/RMSE acceptable; SHAP sensible (no single-axis dominance without reason).
- Owner: Research Eng; Gate: CV/SHAP review.

### Step 7 — Navigator (`src/latent/navigator.py`)
- Purpose: Propose new UIDs via trust-region, BO in z, centroid decoding, and MAP-Elites.
- Inputs: Surrogate, cluster stats, z neighborhood around selected seeds.
- Outputs: `outputs/latent/proposals/*.json` with `proposal_id`, `parent_uid`, `z_target`, `decoded_params`, `method`.
- Actions: Sample inside cluster ellipsoids; run BO steps; perform latent arithmetic for targeted changes; decode to params; clamp and validate constraints.
- Validation: Proposed params within allowed ranges; diversity preserved; predicted scores plausible.
- Owner: Research Eng; Gate: Proposal sanity review and quota controls.

### Step 8 — Proposal Runner (`scripts/run_proposals.py`)
- Purpose: Execute proposals through the existing backtester; append results to outputs.
- Inputs: Proposal JSONs; active charts.
- Outputs: Standard outputs under `outputs/*`; eligible for FeatureBuilder ingestion next cycle.
- Actions: Batch backtests; log trial_uid and linkage to proposal_id; write trades/summary artifacts.
- Validation: Success rate; runtime within budget; no schema drift.
- Owner: Research Eng; Gate: Dry run on a small manifest.

### Step 9 — GUI Extensions (`scripts/run_interface.py` and app assets)
- Purpose: Visualize the latent map, clusters, proposals, and run results interactively.
- Inputs: `latent_points.parquet`, `umap_points.parquet`, cluster assignments, proposals and results.
- Outputs: Interactive panels (latent map, cluster lens, proposals, drift).
- Actions: Add panels: map (color-by metric), lasso-selection → Navigator; cluster scorecards; drift distance vs home cluster; proposal run/inspect.
- Validation: Deterministic refresh by hashes; usability checks.
- Owner: App Eng; Gate: UX/QA pass.

### Step 10 — UID Registry & Strategy Cards (`src/latent/registry.py`)
- Purpose: Formalize UID provenance, reproducibility, and promotion lifecycle.
- Inputs: Proposal lineage, z, cluster labels, metrics, code/data hashes.
- Outputs: `strategy_card.yaml` per UID; `graph.json` of lineage.
- Actions: Write cards on creation/update; link edges: centroid-decode/BO/MAP-Elites; store approvals.
- Validation: Cards can reproduce a run end-to-end from hashes.
- Owner: PM/Lead; Gate: 4-eyes review before promotion.

### Step 11 — Governance & Approval Gates
- Purpose: Prevent overfit deployments and ensure robustness.
- Inputs: Cluster stability, robustness scores, drift distance.
- Outputs: Promotion decisions recorded on cards.
- Actions: Thresholds for median/worst metrics; HDBSCAN prob floor; robustness score; drift compatibility.
- Validation: Audit trail present; any override documented.
- Owner: PM/Lead; Gate: Review board sign-off.

### Step 12 — Cadence, Monitoring, and Drift Handling
- Purpose: Sustain the system over time with repeatable cycles and drift-aware recommendations.
- Inputs: New runs, new market windows, live z_m (optional).
- Outputs: Periodic retrain of AE/UMAP/Clusterer; updated proposals; drift alerts.
- Actions: Cycle size: 200–400 seed UIDs; refine 50–100 per top cluster; retrain AE/UMAP/clusterer every 1–2 cycles; monitor recon error/outlier rates; adjust BO exploration if uncertainty spikes.
- Validation: Stable performance; diversity across z maintained; anomaly rates under control.
- Owner: Research/ML Eng; Gate: Cycle review meeting.

### Glossary
- AE: Autoencoder (dense or TCN); UMAP: Uniform Manifold Approximation and Projection; HDBSCAN: clusterer; BO: Bayesian Optimization; MAP-Elites: quality-diversity grid.


