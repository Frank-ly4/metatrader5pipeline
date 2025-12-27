"""
Read-Only Attribution Join
--------------------------

Joins per-bar analyzer features (Parquet) to trade records by timestamp for a run,
with strict parity checks using bars_hash and (first_ts,last_ts,bar_count,tz).

Outputs CSV reports under reports/attribution/<run_uid>/:
- kpi_by_trend.csv
- kpi_by_regime.csv (if available)
- kpi_by_pattern.csv (aggregated per pattern; includes 'none' bucket)
- counts.csv
- heatmap_regime_x_pattern.csv (if applicable)
"""

from __future__ import annotations

import os
from typing import Dict, Optional
import numpy as np
from scipy.stats import mannwhitneyu
import pandas as pd


def _benjamini_hochberg(pvals: pd.Series, alpha: float = 0.05) -> pd.Series:
    """Return boolean Series of which hypotheses are rejected under BH control."""
    p = pd.Series(pvals).astype(float).copy()
    n = p.notna().sum()
    if n == 0:
        return pd.Series([False] * len(p), index=p.index)
    ranked = p.rank(method='first').astype(float)
    thresh = (ranked / n) * alpha
    return (p <= thresh).fillna(False)

def _cliffs_delta(sample_a: pd.Series | np.ndarray, sample_b: pd.Series | np.ndarray) -> float:
    a = pd.Series(sample_a).dropna().values
    b = pd.Series(sample_b).dropna().values
    if len(a) == 0 or len(b) == 0:
        return float('nan')
    # Relation to U statistic: delta ≈ 2U/(mn) - 1
    try:
        U, _ = mannwhitneyu(a, b, alternative='two-sided')
        m, n = len(a), len(b)
        return float(2 * U / (m * n) - 1)
    except Exception:
        return float('nan')


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _load_run_json(json_path: str) -> Dict:
    import json
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _guess_symbol_timeframe_from_chart(chart_name: str) -> tuple[str, Optional[str]]:
    # Best-effort: 'XAUUSD_4h_cl_1.csv' -> ('XAUUSD','4h')
    base = os.path.splitext(os.path.basename(chart_name))[0]
    parts = base.split('_')
    sym = parts[0] if parts else base
    tf = None
    for token in parts[1:]:
        if token.endswith(('m','h','d')) and token[:-1].isdigit():
            tf = token
            break
    return sym, tf


def _parity_check(price_meta: pd.Series, feat_meta: pd.Series) -> None:
    fields = ['bars_hash','first_ts','last_ts','bar_count','tz']
    for f in fields:
        if str(price_meta.get(f)) != str(feat_meta.get(f)):
            raise ValueError(f"Parity check failed on {f}: price={price_meta.get(f)} vs features={feat_meta.get(f)}")


def join_and_report(
    *,
    run_json_path: str,
    trades_df: pd.DataFrame,
    features_parquet_path: str,
    output_dir: str,
    price_meta: Optional[pd.Series] = None,
    execution_alignment: str = 'at_bar_close',  # 'at_bar_close'|'next_bar_open'|'intrabar_mid'
    alias_map: Optional[Dict[str, str]] = None,
    nan_policy: str = 'drop',  # 'drop' or 'unknown_bucket'
    heatmap_axis_cap: int = 12,
    expected_feature_version: Optional[str] = None,
) -> tuple[Dict[str, str], Dict[str, object]]:
    """Perform read-only join and emit CSV reports. Returns dict of output paths."""
    _ensure_dir(output_dir)
    feats = pd.read_parquet(features_parquet_path)
    # Extract meta from features (assumed constant per file)
    meta_fields = ['bars_hash','bar_count','first_ts','last_ts','tz','symbol','timeframe','provider','feature_version','run_uid','created_at']
    feat_meta = feats.iloc[0][meta_fields]
    # Enforce feature_version expectation if provided
    if expected_feature_version is not None:
        if str(feat_meta['feature_version']) != str(expected_feature_version):
            raise ValueError(f"Feature version mismatch: expected {expected_feature_version}, found {feat_meta['feature_version']}")

    # Trades must have entry timestamp. Use 'Entry Date' column per vectorbt records_readable.
    if 'Entry Date' not in trades_df.columns:
        raise ValueError("trades_df must have 'Entry Date' column for joins")

    # Align trade timestamps per execution alignment
    t = trades_df.copy()
    t['timestamp'] = pd.to_datetime(t['Entry Date'])
    # Inject symbol/timeframe from features meta when trades lack them
    if 'symbol' not in t.columns:
        t['symbol'] = feat_meta['symbol']
    if 'timeframe' not in t.columns:
        t['timeframe'] = feat_meta['timeframe']
    # Apply alias map if needed
    if str(t['symbol'].iloc[0]) != str(feat_meta['symbol']):
        if not alias_map:
            raise ValueError(f"Symbol mismatch and no alias map provided: trades={t['symbol'].iloc[0]} features={feat_meta['symbol']}")
        t['symbol'] = t['symbol'].map(lambda s: alias_map.get(str(s), str(s)))
        if str(t['symbol'].iloc[0]) != str(feat_meta['symbol']):
            raise ValueError(f"Symbol mismatch after alias mapping: trades={t['symbol'].iloc[0]} features={feat_meta['symbol']}")

    # Parity checks require price-side meta
    if price_meta is None:
        raise ValueError('price_meta is required for parity checks')
    _parity_check(price_meta, feat_meta)

    # Perform left join; preserve duplicate trades on same timestamp via trade_id if present
    # Ensure a stable trade identifier
    if 'Id' in t.columns:
        trade_id_col = 'Id'
    elif 'trade_id' in t.columns:
        trade_id_col = 'trade_id'
    else:
        trade_id_col = None
        t = t.reset_index().rename(columns={'index': 'trade_row'})
        trade_id_col = 'trade_row'

    # Timestamp alignment mechanics
    if execution_alignment == 'at_bar_close':
        aligned_ts = t['timestamp']
    else:
        fts = feats[['timestamp']].drop_duplicates().sort_values('timestamp').reset_index(drop=True)
        if execution_alignment == 'next_bar_open':
            aligned = pd.merge_asof(
                t[['timestamp']].sort_values('timestamp'),
                fts,
                on='timestamp',
                direction='forward'
            )
            aligned_ts = aligned['timestamp']
        elif execution_alignment == 'intrabar_mid':
            aligned = pd.merge_asof(
                t[['timestamp']].sort_values('timestamp'),
                fts,
                on='timestamp',
                direction='nearest'
            )
            aligned_ts = aligned['timestamp']
        else:
            raise ValueError(f"Unknown execution_alignment: {execution_alignment}")
        # restore original order
        aligned_ts.index = t.sort_values('timestamp').index
        aligned_ts = aligned_ts.sort_index()
        t['timestamp'] = aligned_ts

    merged = t.merge(feats, how='left', on=['timestamp','symbol','timeframe'], validate='m:1')

    # Helper to compute IQR and lift
    def _iqr(x: pd.Series) -> float:
        q75, q25 = np.nanpercentile(x, 75), np.nanpercentile(x, 25)
        return float(q75 - q25)

    global_returns = merged['Return [%]'].astype(float)
    global_mean = float(global_returns.mean(skipna=True)) if len(global_returns) else float('nan')

    # KPIs by trend_label
    out_paths: Dict[str, str] = {}
    if 'trend_label' in merged.columns:
        grp = merged.groupby('trend_label', dropna=False)
        kpi = grp['Return [%]'].agg(['count','mean','median']).reset_index()
        # add IQR, lift, and p-value vs global using Mann-Whitney U
        kpi['iqr'] = grp['Return [%]'].apply(_iqr).values
        lifts = []
        pvals = []
        for name, g in grp:
            gvals = g['Return [%]'].astype(float).values
            lifts.append(float(np.nanmean(gvals) - global_mean))
            if len(g) < 30:
                p = np.nan
            else:
                try:
                    _, p = mannwhitneyu(gvals, global_returns.values, alternative='two-sided')
                except Exception:
                    p = np.nan
            pvals.append(float(p))
        kpi['lift_vs_global'] = lifts
        kpi['mw_pvalue'] = pvals
        kpi['cliffs_delta'] = [
            _cliffs_delta(grp.get_group(k)['Return [%]'].values, global_returns.values) for k in kpi['trend_label']
        ]
        # Multiple-testing correction within this family
        kpi['bh_reject_0.05'] = _benjamini_hochberg(kpi['mw_pvalue'], alpha=0.05).values
        p = os.path.join(output_dir, 'kpi_by_trend.csv')
        kpi.to_csv(p, index=False)
        out_paths['kpi_by_trend'] = p

    # KPIs by regime_label (if exists)
    if 'regime_label' in merged.columns:
        grp = merged.groupby('regime_label', dropna=False)
        kpi = grp['Return [%]'].agg(['count','mean','median']).reset_index()
        kpi['iqr'] = grp['Return [%]'].apply(_iqr).values
        lifts = []
        pvals = []
        for name, g in grp:
            gvals = g['Return [%]'].astype(float).values
            lifts.append(float(np.nanmean(gvals) - global_mean))
            if len(g) < 30:
                p = np.nan
            else:
                try:
                    _, p = mannwhitneyu(gvals, global_returns.values, alternative='two-sided')
                except Exception:
                    p = np.nan
            pvals.append(float(p))
        kpi['lift_vs_global'] = lifts
        kpi['mw_pvalue'] = pvals
        kpi['cliffs_delta'] = [
            _cliffs_delta(grp.get_group(k)['Return [%]'].values, global_returns.values) for k in kpi['regime_label']
        ]
        kpi['bh_reject_0.05'] = _benjamini_hochberg(kpi['mw_pvalue'], alpha=0.05).values
        p = os.path.join(output_dir, 'kpi_by_regime.csv')
        kpi.to_csv(p, index=False)
        out_paths['kpi_by_regime'] = p

    # KPIs by pattern flags at entry
    pattern_cols = [
        'candle_engulf_bull','candle_engulf_bear','candle_pin_bull','candle_pin_bear',
        'candle_doji','inside_bar','outside_bar','nr7',
        'swing_hh','swing_hl','swing_lh','swing_ll'
    ]
    existing = [c for c in pattern_cols if c in merged.columns]
    if existing:
        # Build a label column: the first pattern flagged else 'none'
        def first_flag(row):
            for c in existing:
                if row.get(c, 0) == 1:
                    return c
            return 'none'
        merged['pattern_at_entry'] = merged[existing].apply(first_flag, axis=1)
        grp = merged.groupby('pattern_at_entry', dropna=False)
        kpi = grp['Return [%]'].agg(['count','mean','median']).reset_index()
        kpi['iqr'] = grp['Return [%]'].apply(_iqr).values
        lifts = []
        pvals = []
        for name, g in grp:
            gvals = g['Return [%]'].astype(float).values
            lifts.append(float(np.nanmean(gvals) - global_mean))
            if len(g) < 30:
                p = np.nan
            else:
                try:
                    _, p = mannwhitneyu(gvals, global_returns.values, alternative='two-sided')
                except Exception:
                    p = np.nan
            pvals.append(float(p))
        kpi['lift_vs_global'] = lifts
        kpi['mw_pvalue'] = pvals
        kpi['cliffs_delta'] = [
            _cliffs_delta(grp.get_group(k)['Return [%]'].values, global_returns.values) for k in kpi['pattern_at_entry']
        ]
        kpi['bh_reject_0.05'] = _benjamini_hochberg(kpi['mw_pvalue'], alpha=0.05).values
        p = os.path.join(output_dir, 'kpi_by_pattern.csv')
        kpi.to_csv(p, index=False)
        out_paths['kpi_by_pattern'] = p

        # Counts and heatmap if regime exists
        counts = merged['pattern_at_entry'].value_counts(dropna=False).reset_index()
        counts.columns = ['pattern','count']
        p_counts = os.path.join(output_dir, 'counts.csv')
        counts.to_csv(p_counts, index=False)
        out_paths['counts'] = p_counts

        if 'regime_label' in merged.columns:
            n_reg = merged['regime_label'].nunique(dropna=False)
            n_pat = merged['pattern_at_entry'].nunique(dropna=False)
            if n_reg <= heatmap_axis_cap and n_pat <= heatmap_axis_cap:
                heat = merged.pivot_table(index='regime_label', columns='pattern_at_entry', values='Return [%]', aggfunc='count', fill_value=0)
                p_heat = os.path.join(output_dir, 'heatmap_regime_x_pattern.csv')
                heat.to_csv(p_heat)
                out_paths['heatmap_regime_x_pattern'] = p_heat

    # Class imbalance flags for patterns
    imbalance = {}
    if 'pattern_at_entry' in merged.columns:
        total = float(len(merged)) if len(merged) else 1.0
        rates = merged['pattern_at_entry'].value_counts(normalize=True, dropna=False).to_dict()
        for k, v in rates.items():
            if k == 'none':
                continue
            if v < 0.01 or v > 0.90:
                imbalance[k] = 'kill-candidate'
            else:
                imbalance[k] = 'ok'

    # Simple permutation check on pattern labels (one-per-run)
    permutation = {}
    if 'pattern_at_entry' in merged.columns:
        # Observed mean absolute lift across patterns (exclude 'none')
        obs = merged.groupby('pattern_at_entry')['Return [%]'].mean()
        if 'none' in obs:
            obs = obs.drop(index='none')
        obs_lift = float(np.nanmean((obs - global_mean).abs())) if len(obs) else float('nan')
        # Permute labels randomly and recompute
        rng = np.random.default_rng(42)
        shuffled = merged['pattern_at_entry'].sample(frac=1.0, random_state=42).values
        tmp = merged.copy()
        tmp['pattern_at_entry'] = shuffled
        sim = tmp.groupby('pattern_at_entry')['Return [%]'].mean()
        if 'none' in sim:
            sim = sim.drop(index='none')
        sim_lift = float(np.nanmean((sim - global_mean).abs())) if len(sim) else float('nan')
        permutation = {'observed_mean_abs_lift': obs_lift, 'permuted_mean_abs_lift': sim_lift}

    info = {
        'feature_meta': {k: feat_meta[k] for k in meta_fields},
        'class_imbalance': imbalance,
        'pattern_rates': merged['pattern_at_entry'].value_counts(dropna=False).to_dict() if 'pattern_at_entry' in merged.columns else {},
        'permutation_check': permutation,
        'execution_alignment': execution_alignment,
        'nan_policy': nan_policy,
    }

    return out_paths, info


