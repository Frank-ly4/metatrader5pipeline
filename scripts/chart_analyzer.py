import argparse
import os
import pandas as pd
from typing import List, Tuple, Dict
import json
import time
import datetime
import numpy as np
from src.io.data_loader import load_chart_from_path
from src.strategy.regime import compute_regimes, segment_by_regime, slice_equal_parts, extract_price_range, infer_timeframe
from config.data import ACTIVE_CHARTS_DIR, CHARTS_CLEAN_DIR
from src.io.data_loader import list_active_chart_paths, find_first_csv


def summarize_segments(price: pd.DataFrame, segs):
    rows = []
    for (start, end, label) in segs:
        seg = extract_price_range(price, start, end)
        if len(seg) == 0:
            continue
        duration = (end - start)
        p0, p1 = float(seg['Close'].iloc[0]), float(seg['Close'].iloc[-1])
        ret = (p1 / p0 - 1.0) * 100.0 if p0 else 0.0
        rows.append({
            'start': start, 'end': end, 'bars': len(seg), 'regime': label,
            'close_start': p0, 'close_end': p1, 'return_pct': ret
        })
    return pd.DataFrame(rows)


def save_splices(price: pd.DataFrame, ranges, base_name: str, out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i, (start, end) in enumerate(ranges, 1):
        seg = extract_price_range(price, start, end)
        if len(seg) == 0:
            continue
        out = os.path.join(out_dir, f"{base_name}_slice_{i}.csv")
        seg.to_csv(out)
        paths.append(out)
    return paths


def compute_human_summary(price: pd.DataFrame, regs: pd.DataFrame, segdf: pd.DataFrame) -> Dict:
    close = price['Close']
    n = len(price)
    start_ts, end_ts = price.index[0], price.index[-1]
    tf = infer_timeframe(price.index)
    total_ret_pct = (float(close.iloc[-1]) / float(close.iloc[0]) - 1.0) * 100.0 if n > 1 else 0.0
    # Transitions and regime lengths
    num_segments = len(segdf)
    avg_len = float(segdf['bars'].mean()) if num_segments else 0.0
    med_len = float(segdf['bars'].median()) if num_segments else 0.0
    max_len = int(segdf['bars'].max()) if num_segments else 0
    # Regime distribution by top-level and by vol bucket
    def parse_regime(label: str) -> Tuple[str, str]:
        parts = str(label).split('_')
        if len(parts) >= 3:
            trend = '_'.join(parts[:2]) if parts[0] == 'trend' else parts[0]
            vol = parts[-2] if parts[-1] == 'vol' and len(parts) >= 4 else parts[-1]
        else:
            trend = parts[0] if parts else 'unknown'
            vol = 'mid'
        # Normalize trend to 'trend_up'/'trend_down'/'range'
        if trend.startswith('trend_up'):
            t = 'trend_up'
        elif trend.startswith('trend_down'):
            t = 'trend_down'
        else:
            t = 'range'
        # Normalize volume bucket
        if 'low' in vol:
            v = 'low'
        elif 'high' in vol:
            v = 'high'
        else:
            v = 'mid'
        return t, v
    # Expand regimes to per-bar labels for robust distribution
    reg_series = regs['regime'].astype(str)
    trend_counts = {'trend_up': 0, 'trend_down': 0, 'range': 0}
    vol_counts = {'low': 0, 'mid': 0, 'high': 0}
    for label in reg_series:
        t, v = parse_regime(label)
        trend_counts[t] = trend_counts.get(t, 0) + 1
        vol_counts[v] = vol_counts.get(v, 0) + 1
    # Top best/worst segments by return
    top_best = segdf.sort_values('return_pct', ascending=False).head(3)
    top_worst = segdf.sort_values('return_pct', ascending=True).head(3)
    # Regime summary: average return per bar within regime labels
    reg_perf = None
    if not segdf.empty:
        tmp = segdf.copy()
        tmp['ret_per_bar'] = tmp['return_pct'] / tmp['bars'].replace(0, pd.NA)
        reg_perf = tmp.groupby('regime')['ret_per_bar'].mean().sort_values(ascending=False)
    
    # Convert DataFrames/Series to JSON-serializable formats
    def _segment_to_jsonable(d):
        d = dict(d)
        if 'start' in d:
            d['start'] = pd.to_datetime(d['start']).isoformat()
        if 'end' in d:
            d['end'] = pd.to_datetime(d['end']).isoformat()
        return d
    
    top_best_records = []
    if not top_best.empty:
        top_best_records = [_segment_to_jsonable(x) for x in top_best.to_dict('records')]
    
    top_worst_records = []
    if not top_worst.empty:
        top_worst_records = [_segment_to_jsonable(x) for x in top_worst.to_dict('records')]
    
    reg_perf_dict = reg_perf.to_dict() if reg_perf is not None else {}
    
    return {
        'bars': n,
        'start': start_ts,
        'end': end_ts,
        'timeframe': tf,
        'total_return_pct': total_ret_pct,
        'num_segments': num_segments,
        'avg_segment_bars': avg_len,
        'median_segment_bars': med_len,
        'max_segment_bars': max_len,
        'trend_distribution': {k: {'bars': v, 'pct': (v / n * 100.0 if n else 0.0)} for k, v in trend_counts.items()},
        'vol_distribution': {k: {'bars': v, 'pct': (v / n * 100.0 if n else 0.0)} for k, v in vol_counts.items()},
        'top_best_segments': top_best_records,
        'top_worst_segments': top_worst_records,
        'regime_avg_ret_per_bar': reg_perf_dict,
    }


def print_human_summary(chart_name: str, summary: Dict) -> None:
    print("\n" + "-" * 60)
    print(f"Chart: {chart_name}")
    print(f"Bars: {summary['bars']} | Timeframe: {summary['timeframe']}")
    print(f"Date-time range: {summary['start']} → {summary['end']}")
    print(f"Total return: {summary['total_return_pct']:.2f}%")
    print(f"Regime segments: {summary['num_segments']} | avg bars: {summary['avg_segment_bars']:.1f} | median: {summary['median_segment_bars']:.1f} | max: {summary['max_segment_bars']}")
    td = summary['trend_distribution']
    vd = summary['vol_distribution']
    print("Trend distribution (by bars): "
          f"up {td['trend_up']['pct']:.1f}% | range {td['range']['pct']:.1f}% | down {td['trend_down']['pct']:.1f}%")
    print("Vol distribution (by bars):   "
          f"low {vd['low']['pct']:.1f}% | mid {vd['mid']['pct']:.1f}% | high {vd['high']['pct']:.1f}%")
    # Top segments
    tb = summary['top_best_segments']
    tw = summary['top_worst_segments']
    if tb is not None and len(tb) > 0:
        print("Top +3 segments by return:")
        for row in tb:
            print(f"  {row['start']} → {row['end']} | {row['regime']:<20} | {row['return_pct']:>7.2f}% ({int(row['bars'])} bars)")
    if tw is not None and len(tw) > 0:
        print("Top -3 segments by return:")
        for row in tw:
            print(f"  {row['start']} → {row['end']} | {row['regime']:<20} | {row['return_pct']:>7.2f}% ({int(row['bars'])} bars)")
    # Regime average return per bar
    rp = summary['regime_avg_ret_per_bar']
    if rp is not None and len(rp) > 0:
        print("Avg return per bar by regime (bps):")
        for label, v in rp.items():
            print(f"  {label:<22}: {(v * 100):.3f}")  # convert % to bps


def plot_regimes(price: pd.DataFrame, segs, chart_title: str, save_path: str | None = None, show: bool = False) -> None:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except Exception:
        print("matplotlib not available; skipping plot.")
        return
    # Colors by regime label
    colors = {
        'trend_up_low_vol': '#b7e1cd',
        'trend_up_mid_vol': '#34a853',
        'trend_up_high_vol': '#0b8043',
        'range_low_vol': '#e8eaed',
        'range_mid_vol': '#9aa0a6',
        'range_high_vol': '#5f6368',
        'trend_down_low_vol': '#f4c7c3',
        'trend_down_mid_vol': '#ea4335',
        'trend_down_high_vol': '#a50e0e',
    }
    def color_for(label: str) -> str:
        return colors.get(label, '#cccccc')
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(price.index, price['Close'], color='black', linewidth=1.0, label='Close')
    # Shade regimes
    seen_labels = []
    for (start, end, label) in segs:
        c = color_for(label)
        ax.axvspan(start, end, facecolor=c, alpha=0.18, edgecolor='none')
        if label not in seen_labels:
            seen_labels.append(label)
    # Build legend
    legend_handles = [Patch(facecolor=colors[l], edgecolor='none', alpha=0.6, label=l) for l in seen_labels]
    if legend_handles:
        ax.legend(handles=legend_handles, loc='upper left', fontsize=8, ncol=2)
    ax.set_title(chart_title)
    ax.set_xlabel('Time')
    ax.set_ylabel('Close')
    ax.grid(True, linestyle=':', linewidth=0.5, alpha=0.5)
    fig.tight_layout()
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=150)
        print(f"Saved plot: {os.path.abspath(save_path)}")
    if show:
        plt.show()
    plt.close(fig)


def format_summary_text(chart_name: str, chart_path: str, summary: Dict, segdf: pd.DataFrame, include_segments: bool = False) -> str:
    lines = []
    lines.append(f"Chart: {chart_name}")
    if chart_path:
        lines.append(f"Path: {chart_path}")
    lines.append(f"Bars: {summary['bars']} | Timeframe: {summary['timeframe']}")
    lines.append(f"Date-time range: {summary['start']} → {summary['end']}")
    lines.append(f"Total return: {summary['total_return_pct']:.2f}%")
    lines.append(f"Regime segments: {summary['num_segments']} | avg bars: {summary['avg_segment_bars']:.1f} | median: {summary['median_segment_bars']:.1f} | max: {summary['max_segment_bars']}")
    td = summary['trend_distribution']; vd = summary['vol_distribution']
    lines.append(f"Trend distribution (by bars): up {td['trend_up']['pct']:.1f}% | range {td['range']['pct']:.1f}% | down {td['trend_down']['pct']:.1f}%")
    lines.append(f"Vol distribution (by bars):   low {vd['low']['pct']:.1f}% | mid {vd['mid']['pct']:.1f}% | high {vd['high']['pct']:.1f}%")
    tb = summary['top_best_segments']; tw = summary['top_worst_segments']
    if tb is not None and len(tb) > 0:
        lines.append("Top +3 segments by return:")
        for row in tb:
            lines.append(f"  {row['start']} → {row['end']} | {row['regime']:<20} | {row['return_pct']:>7.2f}% ({int(row['bars'])} bars)")
    if tw is not None and len(tw) > 0:
        lines.append("Top -3 segments by return:")
        for row in tw:
            lines.append(f"  {row['start']} → {row['end']} | {row['regime']:<20} | {row['return_pct']:>7.2f}% ({int(row['bars'])} bars)")
    rp = summary['regime_avg_ret_per_bar']
    if rp is not None and len(rp) > 0:
        lines.append("Avg return per bar by regime (bps):")
        for label, v in rp.items():
            lines.append(f"  {label:<22}: {(v * 100):.3f}")  # convert % to bps
    if include_segments and not segdf.empty:
        lines.append("")
        lines.append("Detected regimes (contiguous segments):")
        try:
            lines.append(segdf.to_string(index=False))
        except Exception:
            pass
    return "\n".join(lines)


def print_explainer_once():
    msg = [
        "How to read this output:",
        "- Bars: number of candles. Timeframe is interval per candle (e.g., 2h).",
        "- Regime label: trend_up/trend_down/range combined with volatility bucket low/mid/high.",
        "- Distributions show fraction of bars in each trend/vol class.",
        "- Top segments are the contiguous stretches with best/worst total return.",
        "- Avg return per bar by regime is in basis points (bps) per bar (1% = 100 bps).",
    ]
    print("\n" + "\n".join(msg))


def _json_default(o):
    """Handle JSON serialization for pandas/numpy types."""
    if isinstance(o, (pd.Timestamp, datetime.datetime, np.datetime64)):
        return pd.to_datetime(o).isoformat()
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def _atomic_write_json(path, payload):
    """Write JSON atomically using a temp file to prevent corruption."""
    tmp = f"{path}.tmp"
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=_json_default)
    os.replace(tmp, path)


def save_analysis(chart_path: str, regime_params: Dict, price: pd.DataFrame, regs: pd.DataFrame,
                  segdf: pd.DataFrame, summary: Dict, out_dir: str) -> Dict:
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(chart_path))[0]
    analysis_id = base  # Use fixed name without timestamp for easy lookup
    ts = time.strftime('%Y%m%d_%H%M%S')  # Keep timestamp for metadata
    # Serialize segments
    seg_records = []
    if not segdf.empty:
        for _, row in segdf.iterrows():
            seg_records.append({
                'start': pd.to_datetime(row['start']).isoformat(),
                'end': pd.to_datetime(row['end']).isoformat(),
                'bars': int(row['bars']),
                'regime': str(row['regime']),
                'close_start': float(row['close_start']),
                'close_end': float(row['close_end']),
                'return_pct': float(row['return_pct']),
            })
    
    json_path = os.path.join(out_dir, f"{analysis_id}.json")
    txt_path = os.path.join(out_dir, f"{analysis_id}.txt")
    
    # Ensure summary start/end are ISO strings
    payload = {
        'analysis_id': analysis_id,
        'chart': {
            'path': os.path.abspath(chart_path),
            'name': base,
        },
        'regime_params': regime_params,
        'summary': {
            **summary,
            'start': pd.to_datetime(summary['start']).isoformat() if summary.get('start') is not None else None,
            'end': pd.to_datetime(summary['end']).isoformat() if summary.get('end') is not None else None,
        },
        'segments': seg_records,
        'generated_at': ts,
        'version': 'analysis_v1'
    }
    
    # Write JSON atomically using robust serializer
    _atomic_write_json(json_path, payload)
    # Human-readable text
    text = format_summary_text(base, chart_path, summary, segdf, include_segments=True)
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(text)
    # Update index
    index_path = os.path.join(out_dir, 'index.json')
    index = {}
    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            index = json.load(f)
    except Exception:
        index = {}
    key = os.path.abspath(chart_path)
    index.setdefault(key, [])
    index[key].append({'analysis_id': analysis_id, 'path': json_path, 'generated_at': ts})
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2)
    return {'json': json_path, 'txt': txt_path}


def resolve_chart_paths(chart_arg: str | None, all_flag: bool, interactive: bool) -> List[str]:
    if all_flag:
        return list_active_chart_paths()
    if chart_arg:
        # Accept comma-separated names or absolute paths
        tokens = [x.strip() for x in chart_arg.split(',') if x.strip()]
        resolved = []
        for t in tokens:
            if os.path.isabs(t) and os.path.exists(t):
                resolved.append(t)
                continue
            # Try join with active dir
            p = os.path.join(ACTIVE_CHARTS_DIR, t)
            if os.path.exists(p):
                resolved.append(p)
                continue
            # If looks like a base name without .csv, try adding
            if not t.lower().endswith('.csv'):
                p2 = os.path.join(ACTIVE_CHARTS_DIR, f"{t}.csv")
                if os.path.exists(p2):
                    resolved.append(p2)
                    continue
        return resolved
    if interactive:
        available = list_active_chart_paths()
        if not available:
            return []
        names = [os.path.basename(x) for x in available]
        print("\nAvailable charts:")
        for i, n in enumerate(names, 1):
            print(f" {i:2d}. {n}")
        sel = input("Select by indices (e.g., 1,3-5) or 'all': ").strip().lower()
        if sel == 'all':
            return available
        idxs: list[int] = []
        for part in sel.split(','):
            part = part.strip()
            if not part:
                continue
            if '-' in part:
                a, b = part.split('-', 1)
                try:
                    ia, ib = int(a) - 1, int(b)
                    idxs.extend(list(range(ia, ib)))
                except Exception:
                    pass
            else:
                try:
                    idxs.append(int(part) - 1)
                except Exception:
                    pass
        out = []
        for i in idxs:
            if 0 <= i < len(available):
                out.append(available[i])
        return out
    # Fallback: original behavior
    path = find_first_csv(ACTIVE_CHARTS_DIR)
    return [path] if path else []


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--chart', default=None, help='Path, base filename, or comma-separated list. If omitted, uses first active chart.')
    p.add_argument('--all', action='store_true', help='Process all charts in active_charts directory')
    p.add_argument('--interactive', action='store_true', help='Interactively select charts to analyze')
    p.add_argument('--equal-parts', type=int, default=0, help='If >0, slice chart into N equal parts and save.')
    p.add_argument('--by-regime', action='store_true', help='Slice chart by detected regime boundaries and save.')
    p.add_argument('--out-dir', default=CHARTS_CLEAN_DIR, help='Output directory for spliced charts')
    # Analysis-centric defaults (not tied to strategy)
    p.add_argument('--momentum-len', type=int, default=20)
    p.add_argument('--vol-len', type=int, default=20)
    p.add_argument('--trend-threshold', type=float, default=0.0)
    p.add_argument('--no-mcg', action='store_true', help='Disable McGinley-based trend slope (use EMA/HMA proxy)')
    p.add_argument('--hma-len', type=int, default=20)
    p.add_argument('--hysteresis', type=int, default=2)
    p.add_argument('--custom', type=str, default=None, help='Custom ranges: YYYY-MM-DD:YYYY-MM-DD,(repeat)')
    p.add_argument('--gui', action='store_true', help='Show plots with regimes overlaid')
    p.add_argument('--save-plots', action='store_true', help='Save plots to disk (outputs/plots)')
    p.add_argument('--plot-dir', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'outputs', 'plots'))
    p.add_argument('--show-segments', action='store_true', help='Print full regime segments table')
    p.add_argument('--save-analysis', action='store_true', help='Save analysis JSON/TXT and update index')
    p.add_argument('--analysis-dir', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'outputs', 'analyses'))
    # New: feature writing and provider selection (opt-in)
    p.add_argument('--write-features', action='store_true', help='Write per-bar features to Parquet (opt-in)')
    p.add_argument('--features-dir', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'outputs', 'features'))
    p.add_argument('--provider', type=str, default='mcg', choices=['mcg', 'pa_only'], help='Feature provider (default mcg)')
    p.add_argument('--patterns', action='store_true', help='Enable basic candlestick/structure pattern flags (opt-in)')
    p.add_argument('--run-uid', type=str, default=None, help='Optional run UID to embed in feature Parquet and filename')
    args = p.parse_args()

    # Resolve charts to process
    paths = resolve_chart_paths(args.chart, args.all, args.interactive)
    if not paths:
        raise FileNotFoundError('No charts resolved. Provide --chart, --all, or ensure active_charts has CSVs.')
    print("=" * 48)
    print(f"CHART ANALYZER: {len(paths)} chart(s) to process")
    print("=" * 48)

    # Explain metrics once
    print_explainer_once()

    aggregate_trend = {'trend_up': 0, 'range': 0, 'trend_down': 0}
    aggregate_vol = {'low': 0, 'mid': 0, 'high': 0}
    aggregate_bars = 0

    for path in paths:
        print(f"Processing: {os.path.abspath(path)}")
        price = load_chart_from_path(path)
        base_name = os.path.splitext(os.path.basename(path))[0]
        params_used = {
            'momentum_len': args.momentum_len,
            'vol_len': args.vol_len,
            'trend_threshold': args.trend_threshold,
            'use_mcg_trend': not args.no_mcg,
            'hma_len': args.hma_len,
            'hysteresis': args.hysteresis,
        }
        regs = compute_regimes(
            price,
            momentum_len=args.momentum_len,
            vol_len=args.vol_len,
            trend_threshold=args.trend_threshold,
            use_mcg_trend=not args.no_mcg,
            hma_len=args.hma_len,
            hysteresis=args.hysteresis,
        )
        segs = segment_by_regime(price, regs['regime'])
        segdf = summarize_segments(price, segs)

        # Human-readable summary
        summary = compute_human_summary(price, regs, segdf)
        print(f"Regime params: momentum_len={args.momentum_len}, vol_len={args.vol_len}, trend_threshold={args.trend_threshold}, use_mcg_trend={not args.no_mcg}, hma_len={args.hma_len}, hysteresis={args.hysteresis}")
        print_human_summary(base_name, summary)

        # Optionally print full segments
        if args.show_segments and len(segdf) > 0:
            print("\nDetected regimes (contiguous segments):")
            print(segdf.to_string(index=False))

        # Splicing options per chart
        saved: List[str] = []
        if args.equal_parts and args.equal_parts > 0:
            eq_ranges = slice_equal_parts(price, args.equal_parts)
            saved += save_splices(price, eq_ranges, f"{base_name}_eq{args.equal_parts}", args.out_dir)
        if args.by_regime:
            reg_ranges = [(a, b) for (a, b, _) in segs]
            saved += save_splices(price, reg_ranges, f"{base_name}_byregime", args.out_dir)
        if args.custom:
            custom_ranges = []
            parts = [x.strip() for x in args.custom.split(',') if x.strip()]
            for pstr in parts:
                try:
                    a, b = pstr.split(':', 1)
                    start = pd.to_datetime(a.strip())
                    end = pd.to_datetime(b.strip())
                    custom_ranges.append((start, end))
                except Exception:
                    pass
            if custom_ranges:
                saved += save_splices(price, custom_ranges, f"{base_name}_custom", args.out_dir)
        if saved:
            print("\nSaved spliced charts:")
            for s in saved:
                print(f"  {os.path.abspath(s)}")

        # Plotting
        if args.gui or args.save_plots:
            title = f"{base_name} | {summary['timeframe']} | {summary['start']} → {summary['end']}"
            save_to = os.path.join(args.plot_dir, f"{base_name}.png") if args.save_plots else None
            plot_regimes(price, segs, title, save_path=save_to, show=args.gui)

        # Save analysis payloads
        if args.save_analysis:
            saved = save_analysis(path, params_used, price, regs, segdf, summary, args.analysis_dir)
            print(f"Saved analysis: {os.path.abspath(saved['json'])}")

        # Optional: write tidy per-bar features Parquet (opt-in, no behavior change)
        if args.write_features:
            try:
                from analyzer.feature_writer import write_features_parquet
                # Provider selection
                if args.provider == 'mcg':
                    # Map existing regime/trend to standardized columns
                    feat = regs.copy()
                    feat = feat.rename(columns={'trend': 'trend_label', 'regime': 'regime_label'})
                else:
                    from analyzer.providers.pa_only import compute_pa_trend
                    pa = compute_pa_trend(price, left=2, right=2)
                    feat = pa.copy()
                # Optional patterns
                if args.patterns:
                    from analyzer.patterns.basic import detect_patterns
                    # If provider is pa_only, reuse swing flags for patterns
                    swings = pa if args.provider == 'pa_only' else None
                    pats = detect_patterns(price, include_swings=bool(swings is not None), swings=swings)
                    
                    # Avoid joining overlapping columns if swings were passed in
                    cols_to_add = pats.columns
                    if swings is not None:
                        cols_to_add = pats.columns.difference(feat.columns)
                    
                    feat = feat.join(pats[cols_to_add], how='left')

                outp = write_features_parquet(
                    chart_path=path,
                    price=price,
                    features=feat,
                    provider=args.provider,
                    feature_version='v1',
                    out_dir=args.features_dir,
                    run_uid=args.run_uid,
                )
                print(f"Saved features Parquet: {outp}")
            except Exception as e:
                print(f"Failed to write features: {e}")

        # Aggregate distributions
        aggregate_bars += summary['bars']
        for k in aggregate_trend:
            aggregate_trend[k] += summary['trend_distribution'][k]['bars']
        for k in aggregate_vol:
            aggregate_vol[k] += summary['vol_distribution'][k]['bars']

    # Print aggregate if multiple charts
    if len(paths) > 1 and aggregate_bars > 0:
        print("\n" + "=" * 48)
        print("Aggregate distribution across charts (by bars):")
        up = aggregate_trend['trend_up'] / aggregate_bars * 100.0
        rn = aggregate_trend['range'] / aggregate_bars * 100.0
        dn = aggregate_trend['trend_down'] / aggregate_bars * 100.0
        lv = aggregate_vol['low'] / aggregate_bars * 100.0
        mv = aggregate_vol['mid'] / aggregate_bars * 100.0
        hv = aggregate_vol['high'] / aggregate_bars * 100.0
        print(f"Trend: up {up:.1f}% | range {rn:.1f}% | down {dn:.1f}%")
        print(f"Vol:   low {lv:.1f}% | mid {mv:.1f}% | high {hv:.1f}%")


def run_gui():
    try:
        # Lazy import to avoid hard dependency if user wants CLI
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QFileDialog,
            QHBoxLayout, QVBoxLayout, QFormLayout, QListWidget, QListWidgetItem,
            QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox, QLineEdit,
            QLabel, QTabWidget, QPlainTextEdit, QComboBox
        )
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
        import matplotlib.pyplot as plt
    except Exception as e:
        raise RuntimeError(f"PySide6/matplotlib not available: {e}")

    class MatplotlibWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.figure, self.ax = plt.subplots(figsize=(10, 5))
            self.canvas = FigureCanvas(self.figure)
            self.toolbar = NavigationToolbar(self.canvas, self)
            layout = QVBoxLayout(self)
            layout.addWidget(self.toolbar)
            layout.addWidget(self.canvas)
            self.setLayout(layout)

        def clear(self):
            self.figure.clf()
            self.ax = self.figure.add_subplot(111)
            self.figure.tight_layout()

        def draw_plot(self, price: pd.DataFrame, segs: List[Tuple[pd.Timestamp, pd.Timestamp, str]], title: str):
            self.clear()
            # Colors consistent with CLI plot
            colors = {
                'trend_up_low_vol': '#b7e1cd',
                'trend_up_mid_vol': '#34a853',
                'trend_up_high_vol': '#0b8043',
                'range_low_vol': '#e8eaed',
                'range_mid_vol': '#9aa0a6',
                'range_high_vol': '#5f6368',
                'trend_down_low_vol': '#f4c7c3',
                'trend_down_mid_vol': '#ea4335',
                'trend_down_high_vol': '#a50e0e',
            }
            def color_for(label: str) -> str:
                return colors.get(label, '#cccccc')
            self.ax.plot(price.index, price['Close'], color='black', linewidth=1.0)
            seen_labels = []
            for (start, end, label) in segs:
                self.ax.axvspan(start, end, facecolor=color_for(label), alpha=0.18, edgecolor='none')
                if label not in seen_labels:
                    seen_labels.append(label)
            if seen_labels:
                from matplotlib.patches import Patch
                handles = [Patch(facecolor=colors[l], edgecolor='none', alpha=0.6, label=l) for l in seen_labels]
                self.ax.legend(handles=handles, loc='upper left', fontsize=8, ncol=2)
            self.ax.set_title(title)
            self.ax.set_xlabel('Time')
            self.ax.set_ylabel('Close')
            self.ax.grid(True, linestyle=':', linewidth=0.5, alpha=0.5)
            self.figure.tight_layout()
            self.canvas.draw()

    class AnalyzerWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle('Chart Analyzer')
            self.resize(1200, 700)

            self.results: Dict[str, Dict] = {}
            self.chart_paths: List[str] = list_active_chart_paths()

            # Left panel: chart list and controls
            left_widget = QWidget()
            left_layout = QVBoxLayout(left_widget)

            self.list_charts = QListWidget()
            # Use the enum from QAbstractItemView
            from PySide6.QtWidgets import QAbstractItemView
            self.list_charts.setSelectionMode(QAbstractItemView.MultiSelection)
            self._populate_chart_list()
            left_layout.addWidget(QLabel('Charts (active_charts):'))
            left_layout.addWidget(self.list_charts)

            btn_reload = QPushButton('Reload List')
            btn_select_all = QPushButton('Select All')
            btn_clear = QPushButton('Clear Selection')
            row_actions = QHBoxLayout()
            row_actions.addWidget(btn_reload)
            row_actions.addWidget(btn_select_all)
            row_actions.addWidget(btn_clear)
            left_layout.addLayout(row_actions)

            # Options
            basic_form = QFormLayout()
            # Advanced detection parameters (hidden by default)
            self.sp_momentum = QSpinBox(); self.sp_momentum.setRange(1, 10000); self.sp_momentum.setValue(20); self.sp_momentum.setToolTip('Momentum lookback (bars) used to compute simple price change for regime context.')
            self.sp_vol = QSpinBox(); self.sp_vol.setRange(1, 10000); self.sp_vol.setValue(20); self.sp_vol.setToolTip('Volatility lookback (bars) for median(High-Low)/Close as volatility proxy.')
            self.dsb_thresh = QDoubleSpinBox(); self.dsb_thresh.setRange(0.0, 1.0); self.dsb_thresh.setDecimals(4); self.dsb_thresh.setSingleStep(0.001); self.dsb_thresh.setValue(0.0); self.dsb_thresh.setToolTip('Trend threshold on slope (positive = up, negative = down). 0 means neutral.')
            self.cb_use_mcg = QCheckBox('Use McGinley-based trend'); self.cb_use_mcg.setChecked(True); self.cb_use_mcg.setToolTip('Use McGinley/HMA slope proxy for trend classification. Uncheck to use EMA-slope approximation.')
            self.sp_hma = QSpinBox(); self.sp_hma.setRange(1, 10000); self.sp_hma.setValue(20); self.sp_hma.setToolTip('Fallback smoothing length when McGinley is disabled or unavailable.')
            self.sp_hysteresis = QSpinBox(); self.sp_hysteresis.setRange(0, 50); self.sp_hysteresis.setValue(2); self.sp_hysteresis.setToolTip('Minimum consecutive bars to accept a trend change. Reduces whipsaws.')

            # Basic options
            self.cb_show_segments = QCheckBox('Show segments in summary'); self.cb_show_segments.setChecked(False)
            self.cb_save_plots = QCheckBox('Save plots'); self.cb_save_plots.setToolTip('Save a PNG of the regime-highlighted plot for each analyzed chart.')
            self.cb_save_analysis = QCheckBox('Save analysis (JSON/TXT)'); self.cb_save_analysis.setToolTip('Save machine-readable JSON and a text summary of the analysis.')
            self.le_plot_dir = QLineEdit(os.path.join(os.path.dirname(__file__), '..', 'outputs', 'plots'))
            self.cb_by_regime = QCheckBox('Splice by regime')
            self.sp_equal_parts = QSpinBox(); self.sp_equal_parts.setRange(0, 1000); self.sp_equal_parts.setValue(0)
            self.le_custom = QLineEdit('YYYY-MM-DD:YYYY-MM-DD, ...')
            self.le_out_dir = QLineEdit(CHARTS_CLEAN_DIR)

            # Assemble basic form
            basic_form.addRow(self.cb_show_segments)
            basic_form.addRow(self.cb_save_plots)
            basic_form.addRow(self.cb_save_analysis)
            basic_form.addRow('Plot dir:', self.le_plot_dir)
            basic_form.addRow(self.cb_by_regime)
            basic_form.addRow('Equal parts:', self.sp_equal_parts)
            basic_form.addRow('Custom ranges:', self.le_custom)
            basic_form.addRow('Splice out dir:', self.le_out_dir)
            left_layout.addLayout(basic_form)

            # Advanced container (collapsible)
            self.cb_advanced = QCheckBox('Show advanced settings')
            left_layout.addWidget(self.cb_advanced)
            self.advanced_widget = QWidget()
            advanced_form = QFormLayout(self.advanced_widget)
            advanced_form.addRow('Momentum len (bars):', self.sp_momentum)
            advanced_form.addRow('Volatility len (bars):', self.sp_vol)
            advanced_form.addRow('Trend threshold (slope):', self.dsb_thresh)
            advanced_form.addRow(self.cb_use_mcg)
            advanced_form.addRow('HMA len (fallback):', self.sp_hma)
            advanced_form.addRow('Hysteresis:', self.sp_hysteresis)
            self.advanced_widget.setVisible(False)
            left_layout.addWidget(self.advanced_widget)

            btn_analyze = QPushButton('Analyze Selected')
            btn_explain = QPushButton('Explain Settings')
            btn_splice = QPushButton('Splice Selected')
            row_run = QHBoxLayout()
            row_run.addWidget(btn_analyze)
            row_run.addWidget(btn_explain)
            row_run.addWidget(btn_splice)
            left_layout.addLayout(row_run)

            # Right panel: tabs with summary and plot
            right_widget = QWidget()
            right_layout = QVBoxLayout(right_widget)
            self.tabs = QTabWidget()

            self.summary_text = QPlainTextEdit(); self.summary_text.setReadOnly(True)
            summary_tab = QWidget(); v = QVBoxLayout(summary_tab); v.addWidget(self.summary_text)

            self.plot_widget = MatplotlibWidget()
            self.combo_current_chart = QComboBox()
            plot_tab = QWidget(); pv = QVBoxLayout(plot_tab); pv.addWidget(self.combo_current_chart); pv.addWidget(self.plot_widget)

            self.tabs.addTab(summary_tab, 'Summary')
            self.tabs.addTab(plot_tab, 'Plot')
            right_layout.addWidget(self.tabs)

            # Main layout
            central = QWidget()
            main_layout = QHBoxLayout(central)
            main_layout.addWidget(left_widget, 0)
            main_layout.addWidget(right_widget, 1)
            self.setCentralWidget(central)

            # Signals
            btn_reload.clicked.connect(self._populate_chart_list)
            btn_select_all.clicked.connect(self._select_all)
            btn_clear.clicked.connect(self.list_charts.clearSelection)
            btn_analyze.clicked.connect(self._analyze_selected)
            btn_splice.clicked.connect(self._splice_selected)
            btn_explain.clicked.connect(self._explain_settings)
            self.combo_current_chart.currentTextChanged.connect(self._display_chart)
            self.cb_advanced.stateChanged.connect(self._toggle_advanced)

        def _populate_chart_list(self):
            self.list_charts.clear()
            self.chart_paths = list_active_chart_paths()
            for p in self.chart_paths:
                item = QListWidgetItem(os.path.basename(p))
                item.setData(Qt.UserRole, p)
                self.list_charts.addItem(item)

        def _select_all(self):
            self.list_charts.selectAll()

        def _selected_paths(self) -> List[str]:
            return [i.data(Qt.UserRole) for i in self.list_charts.selectedItems()]

        def _params(self) -> Dict:
            return {
                'momentum_len': int(self.sp_momentum.value()),
                'vol_len': int(self.sp_vol.value()),
                'trend_threshold': float(self.dsb_thresh.value()),
                'use_mcg_trend': bool(self.cb_use_mcg.isChecked()),
                'hma_len': int(self.sp_hma.value()),
                'hysteresis': int(self.sp_hysteresis.value()),
            }

        def _format_summary(self, chart_name: str, summary: Dict, segdf: pd.DataFrame) -> str:
            lines = []
            lines.append(f"Chart: {chart_name}")
            lines.append(f"Bars: {summary['bars']} | Timeframe: {summary['timeframe']}")
            lines.append(f"Date-time range: {summary['start']} → {summary['end']}")
            lines.append(f"Total return: {summary['total_return_pct']:.2f}%")
            lines.append(f"Segments: {summary['num_segments']} | avg {summary['avg_segment_bars']:.1f} | median {summary['median_segment_bars']:.1f} | max {summary['max_segment_bars']}")
            td = summary['trend_distribution']; vd = summary['vol_distribution']
            lines.append(f"Trend: up {td['trend_up']['pct']:.1f}% | range {td['range']['pct']:.1f}% | down {td['trend_down']['pct']:.1f}%")
            lines.append(f"Vol  : low {vd['low']['pct']:.1f}% | mid {vd['mid']['pct']:.1f}% | high {vd['high']['pct']:.1f}%")
            tb = summary['top_best_segments']; tw = summary['top_worst_segments']
            if tb is not None and len(tb) > 0:
                lines.append('Top +3 segments:')
                for row in tb:
                    lines.append(f"  {row['start']} → {row['end']} | {row['regime']:<20} | {row['return_pct']:>7.2f}% ({int(row['bars'])} bars)")
            if tw is not None and len(tw) > 0:
                lines.append('Top -3 segments:')
                for row in tw:
                    lines.append(f"  {row['start']} → {row['end']} | {row['regime']:<20} | {row['return_pct']:>7.2f}% ({int(row['bars'])} bars)")
            rp = summary['regime_avg_ret_per_bar']
            if rp is not None and len(rp) > 0:
                lines.append('Avg return per bar by regime (bps):')
                for label, v in rp.items():
                    lines.append(f"  {label:<22}: {(v * 100):.3f}")  # convert % to bps
            if self.cb_show_segments.isChecked() and not segdf.empty:
                lines.append('')
                lines.append('Segments:')
                try:
                    lines.append(segdf.to_string(index=False))
                except Exception:
                    pass
            return '\n'.join(lines)

        def _analyze_selected(self):
            paths = self._selected_paths()
            if not paths:
                self.summary_text.setPlainText('Select one or more charts to analyze.')
                return
            self.results.clear()
            self.combo_current_chart.blockSignals(True)
            self.combo_current_chart.clear()
            self.combo_current_chart.blockSignals(False)

            params = self._params()
            for path in paths:
                try:
                    price = load_chart_from_path(path)
                    regs = compute_regimes(price, **params)
                    segs = segment_by_regime(price, regs['regime'])
                    segdf = summarize_segments(price, segs)
                    summary = compute_human_summary(price, regs, segdf)
                    base_name = os.path.splitext(os.path.basename(path))[0]
                    self.results[base_name] = {
                        'path': path,
                        'price': price,
                        'regs': regs,
                        'segs': segs,
                        'segdf': segdf,
                        'summary': summary,
                    }
                except Exception as e:
                    self.summary_text.appendPlainText(f"Error processing {os.path.basename(path)}: {e}")

            # Populate chart selector and display first
            names = list(self.results.keys())
            self.combo_current_chart.addItems(names)
            if names:
                self._display_chart(names[0])

            # Save plots if requested
            if self.cb_save_plots.isChecked():
                plot_dir = self.le_plot_dir.text().strip()
                os.makedirs(plot_dir, exist_ok=True)
                for name, data in self.results.items():
                    title = f"{name} | {data['summary']['timeframe']} | {data['summary']['start']} → {data['summary']['end']}"
                    # Use embedded widget to render and save
                    self.plot_widget.draw_plot(data['price'], data['segs'], title)
                    save_path = os.path.join(plot_dir, f"{name}.png")
                    self.plot_widget.figure.savefig(save_path, dpi=150)

            # Save analysis JSON/TXT if requested
            if self.cb_save_analysis.isChecked():
                analysis_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'analyses')
                os.makedirs(analysis_dir, exist_ok=True)
                regime_params = self._params()
                for name, data in self.results.items():
                    try:
                        save_analysis(data['path'], regime_params, data['price'], data['regs'], data['segdf'], data['summary'], analysis_dir)
                    except Exception as e:
                        self.summary_text.appendPlainText(f"Error saving analysis for {name}: {e}")

        def _display_chart(self, name: str):
            if not name or name not in self.results:
                return
            data = self.results[name]
            text = self._format_summary(name, data['summary'], data['segdf'])
            self.summary_text.setPlainText(text)
            title = f"{name} | {data['summary']['timeframe']} | {data['summary']['start']} → {data['summary']['end']}"
            self.plot_widget.draw_plot(data['price'], data['segs'], title)

        def _parse_custom_ranges(self) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
            txt = self.le_custom.text().strip()
            if not txt or 'YYYY' in txt:
                return []
            out = []
            for token in [t.strip() for t in txt.split(',') if t.strip()]:
                try:
                    a, b = token.split(':', 1)
                    out.append((pd.to_datetime(a.strip()), pd.to_datetime(b.strip())))
                except Exception:
                    pass
            return out

        def _splice_selected(self):
            paths = self._selected_paths()
            if not paths:
                self.summary_text.setPlainText('Select one or more charts to splice.')
                return
            out_dir = self.le_out_dir.text().strip() or CHARTS_CLEAN_DIR
            os.makedirs(out_dir, exist_ok=True)
            eq_parts = int(self.sp_equal_parts.value())
            do_by_regime = self.cb_by_regime.isChecked()
            custom_ranges = self._parse_custom_ranges()

            for path in paths:
                price = load_chart_from_path(path)
                base_name = os.path.splitext(os.path.basename(path))[0]
                saved = []
                if eq_parts and eq_parts > 0:
                    eq_ranges = slice_equal_parts(price, eq_parts)
                    saved += save_splices(price, eq_ranges, f"{base_name}_eq{eq_parts}", out_dir)
                if do_by_regime:
                    # compute regimes quickly
                    regs = compute_regimes(price, **self._params())
                    segs = segment_by_regime(price, regs['regime'])
                    reg_ranges = [(a, b) for (a, b, _) in segs]
                    saved += save_splices(price, reg_ranges, f"{base_name}_byregime", out_dir)
                if custom_ranges:
                    saved += save_splices(price, custom_ranges, f"{base_name}_custom", out_dir)
                if saved:
                    self.summary_text.appendPlainText(f"Saved splices for {base_name}:\n  " + '\n  '.join(saved))

        def _explain_settings(self):
            text = (
                'Settings Guide\n\n'
                '- Momentum len: lookback (bars) for price momentum context.\n'
                '- Volatility len: lookback to measure volatility via median(High-Low)/Close.\n'
                '- Trend threshold: slope threshold to classify trend_up/down vs range.\n'
                '- Use McGinley-based trend: enables adaptive smoother slope; otherwise uses EMA slope.\n'
                '- HMA len (fallback): length used when McGinley is off/unavailable.\n'
                '- Hysteresis: bars required to confirm trend change and avoid whipsaws.\n'
                '\nThis analyzer is strategy-agnostic. It does not run entries/exits; it labels regimes and summarizes price behavior.'
            )
            self.summary_text.setPlainText(text)

        def _toggle_advanced(self):
            self.advanced_widget.setVisible(self.cb_advanced.isChecked())

    import sys
    app = QApplication(sys.argv)
    win = AnalyzerWindow()
    win.show()
    app.exec()


if __name__ == '__main__':
    import sys
    if '--cli' in sys.argv:
        main()
    else:
        try:
            run_gui()
        except Exception as e:
            print(f"GUI launch failed ({e}). Falling back to CLI.")
            main()


