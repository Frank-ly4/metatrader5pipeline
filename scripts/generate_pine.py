import os
import re
import json
import argparse
import glob
import pandas as pd

from src.pine.generator import generate_pinescript
from src.meta.logger import append_discovery, append_issue


METRIC_CANDIDATES = [
    'total_return', 'sharpe_ratio', 'sortino_ratio', 'calmar_ratio',
    'max_drawdown', 'win_rate', 'profit_factor', 'expectancy',
    'start_value', 'end_value', 'avg_hold_hours', 'total_trades',
]


def list_runs(outputs_dir: str) -> list[str]:
    return sorted(glob.glob(os.path.join(outputs_dir, 'runs', 'trial_*.json')))


def _ensure_trial_uid(df: pd.DataFrame, run_id: str | None) -> pd.DataFrame:
    if 'trial_uid' not in df.columns and 'trial_id' in df.columns and run_id:
        df = df.copy()
        df['trial_uid'] = df['trial_id'].map(lambda x: f"{run_id}:{int(x)}")
    return df


def _preview_table(df: pd.DataFrame, metric: str | None, topn: int) -> None:
    cols_pref = ['trial_uid','trial_id','chart','method','total_return','sharpe_ratio','max_drawdown','win_rate','total_trades']
    cols = [c for c in cols_pref if c in df.columns]
    view = df
    if metric and metric in df.columns:
        view = view.sort_values(metric, ascending=False)
    print("\nTrials preview:")
    print(view[cols].head(topn).to_string(index=False))


def _extract_run_id_from_filename(path: str) -> str | None:
    # Expect names like trial_random_XX_metric_seed_YYYYMMDD_HHMMSS.json
    base = os.path.basename(path)
    m = re.search(r"(\d{8}_\d{6})", base)
    return m.group(1) if m else None


def _safe_uid_for_filename(uid: str) -> str:
    # Replace invalid filename chars (e.g., : on Windows)
    return re.sub(r"[^A-Za-z0-9._-]", "_", uid)


def pick_from_json(outputs_dir: str, *, json_path: str | None = None, trial_uid: str | None = None) -> tuple[dict, dict]:
    runs = list_runs(outputs_dir)
    if not runs:
        raise FileNotFoundError("No run JSONs found in outputs/runs/")
    # Non-interactive fast path
    if json_path and trial_uid:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        run_id = data.get('metadata',{}).get('run_id') or _extract_run_id_from_filename(json_path)
        for row in data.get('results', []):
            uid = row.get('trial_uid') or f"{run_id}:{row.get('trial_id')}"
            if uid == trial_uid:
                meta = data.get('metadata', {}) or {}
                if 'run_id' not in meta:
                    meta['run_id'] = run_id
                meta['json_path'] = json_path
                return meta, row
        raise ValueError(f"trial_uid not found in provided JSON: {trial_uid}")

    print("Select a run JSON:")
    for i, path in enumerate(runs, 1):
        print(f"  {i}. {os.path.basename(path)}")
    sel = int(input("Enter number or 0 to paste trial_uid: ").strip() or "0")
    if sel == 0:
        trial_uid = input("Enter trial_uid (run_id:trial_id): ").strip()
        for path in runs:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            run_id = data.get('metadata',{}).get('run_id')
            for row in data.get('results', []):
                uid = row.get('trial_uid') or f"{run_id}:{row.get('trial_id')}"
                if uid == trial_uid:
                    return data.get('metadata', {}), row
        raise ValueError(f"trial_uid not found: {trial_uid}")
    path = runs[sel-1]
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    results = data.get('results', [])
    run_id = data.get('metadata',{}).get('run_id') or _extract_run_id_from_filename(path)
    if not results:
        raise ValueError("Selected run has no results.")
    df = _ensure_trial_uid(pd.DataFrame(results), run_id)
    # Optional filter by chart
    charts = sorted(df['chart'].dropna().unique().tolist()) if 'chart' in df.columns else []
    if charts:
        print("Charts in this run:", ", ".join(charts))
        chart_filter = input("Filter by chart (press Enter to skip): ").strip()
        if chart_filter:
            df = df[df['chart'] == chart_filter]
            if len(df) == 0:
                raise ValueError("No trials match the selected chart filter.")
    # Metric + preview
    metrics_present = [m for m in METRIC_CANDIDATES if m in df.columns]
    default_metric = metrics_present[0] if metrics_present else None
    print("Available metrics:")
    for i, m in enumerate(metrics_present, 1):
        print(f"  {i}. {m}")
    metric = input(f"Sort by metric [{default_metric}]: ").strip() or default_metric
    try:
        topn = int(input("Show top N [20]: ").strip() or "20")
    except Exception:
        topn = 20
    _preview_table(df, metric, topn)
    # Selection
    choice = input("Enter trial_id or paste trial_uid: ").strip()
    row = None
    if ':' in choice:
        row = df[df['trial_uid'] == choice].head(1)
    else:
        try:
            tid = int(choice)
        except Exception:
            raise ValueError("Please enter a valid trial_id or trial_uid")
        row = df[df['trial_id'] == tid].head(1)
    if row is None or len(row) == 0:
        raise ValueError("Selection not found.")
    meta = data.get('metadata', {}) or {}
    if 'run_id' not in meta:
        meta['run_id'] = run_id
    meta['json_path'] = path
    return meta, row.iloc[0].to_dict()


def pick_from_excel(outputs_dir: str) -> tuple[dict, dict]:
    nb_dir = os.path.join(outputs_dir, 'notebooks')
    notebooks = sorted(glob.glob(os.path.join(nb_dir, '*.xlsx')))
    if not notebooks:
        raise FileNotFoundError("No notebooks found in outputs/notebooks/")
    print("Select a notebook:")
    for i, path in enumerate(notebooks, 1):
        print(f"  {i}. {os.path.basename(path)}")
    nb = notebooks[int(input("Enter number: ").strip()) - 1]
    print("Read AllResults by default (recommended). Alternatively paste a sheet name.")
    sheet = input("Sheet [AllResults]: ").strip() or "AllResults"
    df = pd.read_excel(nb, sheet_name=sheet)
    if len(df) == 0:
        raise ValueError("Selected sheet is empty.")
    # Optional filter by chart
    if 'chart' in df.columns:
        charts = sorted(df['chart'].dropna().unique().tolist())
        if charts:
            print("Charts:", ", ".join(charts))
            chart_filter = input("Filter by chart (press Enter to skip): ").strip()
            if chart_filter:
                df = df[df['chart'] == chart_filter]
                if len(df) == 0:
                    raise ValueError("No trials match the selected chart filter.")
    # Metric + preview
    metrics_present = [m for m in METRIC_CANDIDATES if m in df.columns]
    default_metric = metrics_present[0] if metrics_present else None
    print("Available metrics:")
    for i, m in enumerate(metrics_present, 1):
        print(f"  {i}. {m}")
    metric = input(f"Sort by metric [{default_metric}]: ").strip() or default_metric
    try:
        topn = int(input("Show top N [20]: ").strip() or "20")
    except Exception:
        topn = 20
    _preview_table(df, metric, topn)
    # Selection
    choice = input("Enter trial_id or paste trial_uid: ").strip()
    row = None
    if ':' in choice and 'trial_uid' in df.columns:
        row = df[df['trial_uid'] == choice].head(1)
    else:
        try:
            tid = int(choice)
        except Exception:
            raise ValueError("Please enter a valid trial_id or trial_uid")
        row = df[df['trial_id'] == tid].head(1)
    if row is None or len(row) == 0:
        raise ValueError("Selection not found.")
    row_dict = row.iloc[0].to_dict()
    meta = {
        'run_id': row_dict.get('run_id'),
        'chart': row_dict.get('chart'),
    }
    return meta, row_dict


def extract_params(row: dict) -> dict:
    params = {}
    for k, v in row.items():
        if isinstance(k, str) and k.startswith('param_'):
            params[k[len('param_'):]] = v
    return params


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['json','excel','prompt'], default='prompt')
    parser.add_argument('--outputs', default=os.path.join(os.path.dirname(__file__), '..', 'outputs'))
    parser.add_argument('--outdir', default=os.path.join(os.path.dirname(__file__), '..', 'outputs', 'pine'))
    parser.add_argument('--target', choices=['pine','mql5','both'], default='pine', help='Code generation target')
    # Non-interactive options
    parser.add_argument('--trial-uid', dest='trial_uid', default=None)
    parser.add_argument('--json-path', dest='json_path', default=None)
    parser.add_argument('--excel-path', dest='excel_path', default=None)
    parser.add_argument('--sheet', dest='sheet', default=None)
    args = parser.parse_args()

    # Create output directories
    pine_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'pine')
    mql5_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'mql5')
    os.makedirs(pine_dir, exist_ok=True)
    os.makedirs(mql5_dir, exist_ok=True)

    mode = args.mode
    target = args.target
    
    if mode == 'prompt':
        print("🔧 CODE GENERATOR v4.2")
        print("=" * 50)
        print("Select source: 1) JSON (outputs/runs), 2) Excel notebook")
        sel = input("Enter 1 or 2 [1]: ").strip() or '1'
        mode = 'json' if sel == '1' else 'excel'
        
        print("\nSelect target platform:")
        print("1) PineScript (TradingView)")
        print("2) MQL5 (MetaTrader 5)")  
        print("3) Both platforms")
        target_sel = input("Enter 1, 2, or 3 [1]: ").strip() or '1'
        target_map = {'1': 'pine', '2': 'mql5', '3': 'both'}
        target = target_map.get(target_sel, 'pine')

    if mode == 'json':
        meta, row = pick_from_json(args.outputs, json_path=args.json_path, trial_uid=args.trial_uid)
    else:
        meta, row = pick_from_excel(args.outputs if not args.excel_path else os.path.dirname(os.path.dirname(args.excel_path)))

    params = extract_params(row)
    # Build human-readable UID and a safe filename uid
    run_id_str = meta.get('run_id') or _extract_run_id_from_filename(meta.get('json_path','') if isinstance(meta, dict) else '') or str(row.get('run_id',''))
    trial_uid = row.get('trial_uid') or f"{run_id_str}:{row.get('trial_id')}"
    safe_uid = _safe_uid_for_filename(trial_uid)

    pine_meta = {
        'run_id': meta.get('run_id',''),
        'trial_id': row.get('trial_id',''),
        'chart': row.get('chart',''),
        'initial_capital': meta.get('portfolio',{}).get('init_cash', 500.0),
        'fees': meta.get('portfolio',{}).get('fees', 0.0005),
    }
    # Generate code based on target selection
    generated_files = []
    
    try:
        if target in ['pine', 'both']:
            # Generate PineScript
            code = generate_pinescript(params, meta=pine_meta)
            out_path = os.path.abspath(os.path.join(pine_dir, f"{safe_uid}.pine"))
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(code)
            generated_files.append(('PineScript', out_path))
            
            # Minimal lint check
            lint_ok = all(tok in code for tok in ["//@version=6", "strategy(", "fast_min_len", "slow_max_len"])
            
        if target in ['mql5', 'both']:
            # Generate MQL5
            from src.codegen.mql5_generator import MQL5Generator
            mql5_gen = MQL5Generator()
            
            # Prepare MQL5 metadata
            mql5_meta = pine_meta.copy()
            mql5_meta['strategy_name'] = f"OptimizedEA_{safe_uid}"
            mql5_meta['trial_uid'] = trial_uid
            
            mql5_code = mql5_gen.generate_expert_advisor(params, meta=mql5_meta)
            out_path = os.path.abspath(os.path.join(mql5_dir, f"{safe_uid}.mq5"))
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(mql5_code)
            generated_files.append(('MQL5', out_path))
        
        # Report generated files
        print(f"\n✅ CODE GENERATION COMPLETED")
        print("=" * 60)
        for platform, path in generated_files:
            rel_path = os.path.relpath(path, start=os.path.join(os.path.dirname(__file__), '..'))
            print(f"{platform:12}: {rel_path}")
        
        if target == 'mql5' or target == 'both':
            print(f"\n📋 MQL5 IMPLEMENTATION NOTES:")
            print("- Copy the .mq5 file to your MetaTrader 5 Experts folder")
            print("- Compile the Expert Advisor in MetaEditor")
            print("- Test on demo account before live trading")
            print("- Adjust risk parameters according to your account size")
            print("- Monitor performance and adapt parameters as needed")
        
        # Log discovery
        experiment_id = f"{target}_generator" if target != 'both' else 'code_generator'
        append_discovery(base_dir=os.path.join(os.path.dirname(__file__), '..'), entry={
            'version': '4.2.5',
            'experiment_id': experiment_id,
            'run_id': meta.get('run_id',''),
            'trials': 1,
            'trial_uid': trial_uid,
            'artifact': ', '.join([os.path.relpath(path, start=os.path.join(os.path.dirname(__file__), '..')) for _, path in generated_files]),
            'lint': 'ok' if target != 'pine' or lint_ok else 'warn'
        })
        
    except Exception as e:
        append_issue(base_dir=os.path.join(os.path.dirname(__file__), '..'), entry={
            'context': f'{target}_generator',
            'run_id': meta.get('run_id',''),
            'trial_uid': trial_uid,
            'message': str(e),
            'severity': 'MEDIUM',
            'action': 'logged'
        })
        raise


if __name__ == '__main__':
    main()


