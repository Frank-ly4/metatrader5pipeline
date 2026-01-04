import argparse
import os
import shutil
import csv
import re
from datetime import datetime, timedelta
import pandas as pd


def _infer_interval_from_index(dt_index: pd.DatetimeIndex) -> tuple[str, str]:
    inferred = pd.infer_freq(dt_index)
    if inferred:
        alias = inferred.upper()
        mapping = {
            'T': ('1m', '1T'), '5T': ('5m', '5T'), '15T': ('15m', '15T'), '30T': ('30m', '30T'),
            'H': ('1h', '1H'), '2H': ('2h', '2H'), '3H': ('3h', '3H'), '4H': ('4h', '4H'),
            'D': ('1d', '1D')
        }
        if alias in mapping:
            return mapping[alias]
        if alias.endswith('T') and alias[:-1].isdigit():
            num = int(alias[:-1])
            return (f"{num}m", f"{num}T")
        if alias.endswith('H') and alias[:-1].isdigit():
            num = int(alias[:-1])
            return (f"{num}h", f"{num}H")
        if alias.endswith('D'):
            return ('1d', '1D')
    s = pd.Series(dt_index).sort_values()
    diffs = s.diff().dropna()
    if len(diffs) == 0:
        return ('1h', '1H')
    try:
        delta: timedelta = diffs.mode().iloc[0]
    except Exception:
        delta = diffs.median()
    minutes = max(1, int(round(delta.total_seconds() / 60)))
    candidates = [1, 5, 15, 30, 60, 120, 180, 240, 1440]
    closest = min(candidates, key=lambda c: abs(c - minutes))
    if closest < 60:
        return (f"{closest}m", f"{closest}T")
    if closest == 1440:
        return ("1d", "1D")
    return (f"{closest // 60}h", f"{closest // 60}H")


def parse_symbol_from_filename(filename: str) -> str | None:
    """Extract symbol from filename.
    
    Examples:
        USDJPY_H4_202207110000_202411151600.csv -> USDJPY
        USDJPY!_H4_202207110000_202411151600.csv -> USDJPY
        XAUUSD_4h_cl_1.csv -> XAUUSD
    """
    base = os.path.splitext(filename)[0]
    parts = base.split('_')
    if not parts:
        return None
    
    symbol = parts[0]
    # Remove trailing special chars like ! or #
    symbol = re.sub(r'[^A-Z0-9]+$', '', symbol.upper())
    return symbol if symbol else None


def parse_timeframe_from_filename(filename: str) -> str | None:
    """Extract and normalize timeframe from filename.
    
    Examples:
        USDJPY_H4_202207110000_202411151600.csv -> 4h
        USDJPY_Daily_201907110000_202511140000.csv -> 1d
        XAUUSD_4h_cl_1.csv -> 4h
    """
    base = os.path.splitext(filename)[0]
    parts = base.split('_')
    if len(parts) < 2:
        return None
    
    tf = parts[1]
    # Normalize timeframe names
    tf_map = {
        'Daily': '1d', 'D': '1d', 'daily': '1d',
        'H4': '4h', 'h4': '4h',
        'H1': '1h', 'h1': '1h',
        'H': '1h', 'h': '1h',
    }
    return tf_map.get(tf, tf.lower())


def get_raw_file_selection(src_dir: str) -> list[str]:
    """List files in charts_raw and allow user to select which to process."""
    files = sorted([f for f in os.listdir(src_dir) if f.lower().endswith('.csv')])
    if not files:
        print(f"No CSV files found in {src_dir}")
        return []
    
    print("\n📦 RAW CHARTS AVAILABLE:")
    print("=" * 60)
    for i, f in enumerate(files, 1):
        size_kb = os.path.getsize(os.path.join(src_dir, f)) // 1024
        print(f"  {i:2}. {f:<50} ({size_kb:>5} KB)")
    print(f"  {len(files)+1:2}. ALL FILES")
    print("=" * 60)
    
    while True:
        try:
            sel = input(f"\nSelect files to standardize (1-{len(files)+1}, or comma-separated indices): ").strip()
            if not sel:
                continue
            
            if sel == str(len(files) + 1):
                return files
            
            selected_indices = []
            for part in sel.split(','):
                part = part.strip()
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    selected_indices.extend(range(start, end + 1))
                else:
                    selected_indices.append(int(part))
            
            out = []
            for idx in selected_indices:
                if 1 <= idx <= len(files):
                    out.append(files[idx-1])
            
            if out:
                return out
        except ValueError:
            print("Invalid input. Use numbers like '1,3,5' or '1-5'.")


def normalize_chart(path: str) -> tuple[pd.DataFrame, str, str]:
    def _try_default_parser(p: str) -> pd.DataFrame:
        df0 = pd.read_csv(p, index_col=0)
        dt_parsed = pd.to_datetime(df0.index, errors='coerce')
        if dt_parsed.notna().sum() < 3:
            raise ValueError('Too few valid dates in default parse')
        df0.index = dt_parsed
        df0 = df0.sort_index()
        return df0

    def _try_mt5_daily_parser(p: str) -> pd.DataFrame:
        """Parse MT5 Daily format: tab-separated with <DATE> header and YYYY.MM.DD dates."""
        try:
            # Try reading as tab-separated with header
            df1 = pd.read_csv(p, sep='\t', header=0, dtype=str)
            if df1.empty:
                raise ValueError('Empty dataframe')
            
            # Check if first column looks like date column (has <DATE> header or YYYY.MM.DD format)
            first_col = df1.columns[0].strip()
            if first_col.startswith('<') or first_col.lower() in ['date', 'time']:
                # Find OHLC columns (case-insensitive)
                col_map = {}
                for col in df1.columns:
                    col_lower = col.strip().lower()
                    if '<open>' in col_lower or col_lower == 'open':
                        col_map['Open'] = col
                    elif '<high>' in col_lower or col_lower == 'high':
                        col_map['High'] = col
                    elif '<low>' in col_lower or col_lower == 'low':
                        col_map['Low'] = col
                    elif '<close>' in col_lower or col_lower == 'close':
                        col_map['Close'] = col
                
                if len(col_map) == 4:
                    # Parse date column
                    date_col = df1.iloc[:, 0]
                    dt = pd.to_datetime(date_col, format='%Y.%m.%d', errors='coerce')
                    if dt.isna().all():
                        # Try without format specification
                        dt = pd.to_datetime(date_col, errors='coerce')
                    
                    if dt.notna().sum() >= 3:
                        df2 = pd.DataFrame({
                            'Open': pd.to_numeric(df1[col_map['Open']], errors='coerce'),
                            'High': pd.to_numeric(df1[col_map['High']], errors='coerce'),
                            'Low': pd.to_numeric(df1[col_map['Low']], errors='coerce'),
                            'Close': pd.to_numeric(df1[col_map['Close']], errors='coerce'),
                        }, index=dt)
                        df2 = df2.dropna(how='any').sort_index()
                        if len(df2) >= 3:
                            return df2
        except Exception:
            pass
        
        # Fallback: regex-based parsing for tab-separated Daily format
        try:
            lines = open(p, 'r', encoding='utf-8', errors='ignore').read().splitlines()
            if not lines:
                raise ValueError('Empty file')
            
            # Skip header line starting with '<'
            start_idx = 0
            if lines[0].startswith('<'):
                start_idx = 1
            
            # Pattern for Daily: YYYY.MM.DD followed by OHLC (tab or space separated)
            pattern = re.compile(r"^(\d{4}\.\d{2}\.\d{2})[\t\s]+([0-9.]+)[\t\s]+([0-9.]+)[\t\s]+([0-9.]+)[\t\s]+([0-9.]+)")
            recs = []
            for line in lines[start_idx:]:
                m = pattern.match(line.strip())
                if not m:
                    continue
                date, o, h, l, c = m.groups()
                try:
                    ts = pd.to_datetime(date, format='%Y.%m.%d')
                except Exception:
                    continue
                recs.append((ts, float(o), float(h), float(l), float(c)))
            
            if len(recs) >= 3:
                df2 = pd.DataFrame(recs, columns=['Timestamp','Open','High','Low','Close']).set_index('Timestamp')
                df2 = df2.sort_index()
                return df2
        except Exception:
            pass
        
        raise ValueError('Failed to parse MT5 Daily format')

    def _try_mt5_parser(p: str) -> pd.DataFrame:
        """Parse MT5 format with time component (H4, H1, etc.)."""
        import re
        try:
            df1 = pd.read_csv(p, sep=r"[;,\s]+", engine='python', header=None, dtype=str)
            df1 = df1.dropna(axis=1, how='all')
            if df1.shape[1] >= 6:
                dt_str = (df1.iloc[:, 0].astype(str).str.strip() + ' ' + df1.iloc[:, 1].astype(str).str.strip())
                dt = pd.to_datetime(dt_str, format='%Y.%m.%d %H:%M:%S', errors='coerce')
                if dt.isna().all():
                    dt = pd.to_datetime(dt_str, errors='coerce')
                if not dt.isna().all():
                    df2 = pd.DataFrame({
                        'Open': pd.to_numeric(df1.iloc[:, 2], errors='coerce'),
                        'High': pd.to_numeric(df1.iloc[:, 3], errors='coerce'),
                        'Low': pd.to_numeric(df1.iloc[:, 4], errors='coerce'),
                        'Close': pd.to_numeric(df1.iloc[:, 5], errors='coerce'),
                    }, index=dt)
                    df2 = df2.dropna(how='any').sort_index()
                    if len(df2) >= 3:
                        return df2
        except Exception:
            pass

        # Fallback: fixed-width / no-delimiter lines (common MT5 ASCII export)
        lines = open(p, 'r', encoding='utf-8', errors='ignore').read().splitlines()
        if not lines:
            raise ValueError('Empty file')
        # Skip header line starting with '<'
        if lines[0].startswith('<'):
            lines = lines[1:]
        pattern = re.compile(r"^(\d{4}\.\d{2}\.\d{2})\s*(\d{2}:\d{2}:\d{2})\s*([0-9.]+)\s*([0-9.]+)\s*([0-9.]+)\s*([0-9.]+)")
        recs = []
        for line in lines:
            m = pattern.match(line.strip())
            if not m:
                continue
            date, t, o, h, l, c = m.groups()
            try:
                ts = pd.to_datetime(f"{date} {t}")
            except Exception:
                continue
            recs.append((ts, float(o), float(h), float(l), float(c)))
        if len(recs) < 3:
            raise ValueError('Too few valid rows after MT5 regex parse')
        df2 = pd.DataFrame(recs, columns=['Timestamp','Open','High','Low','Close']).set_index('Timestamp')
        df2 = df2.sort_index()
        return df2

    # Attempt default parser first
    try:
        df = _try_default_parser(path)
        rename = {c.lower(): c for c in ['Open','High','Low','Close']}
        cols = {c: rename.get(c.lower(), c) for c in df.columns}
        df = df.rename(columns=cols)
        for req in ['Open','High','Low','Close']:
            if req not in df.columns:
                raise KeyError(req)
    except Exception:
        # Try MT5 Daily parser (for Daily charts without time component)
        try:
            df = _try_mt5_daily_parser(path)
        except Exception:
            # Fallback to MT5-style flexible parser (for H4, H1, etc. with time component)
            df = _try_mt5_parser(path)

    interval_lbl, pandas_freq = _infer_interval_from_index(df.index)
    try:
        df = df.asfreq(pandas_freq).ffill()
    except Exception:
        pass
    return df[['Open','High','Low','Close']], interval_lbl, pandas_freq


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--from', dest='src', default=os.path.join('data','charts_raw'))
    p.add_argument('--to', dest='dst', default=os.path.join('data','charts_cl'))
    p.add_argument('--also-copy-active', action='store_true')
    p.add_argument('--asset', dest='asset', default=None)
    p.add_argument('--log', dest='log_path', default=os.path.join('outputs', 'standardize_log.csv'))
    p.add_argument('--run-analyzer', action='store_true', default=True)
    p.add_argument('--skip-analyzer', action='store_false', dest='run_analyzer')
    p.add_argument('--all', action='store_true', help='Standardize all files without prompting')
    args = p.parse_args()

    os.makedirs(args.dst, exist_ok=True)
    active_dir = os.path.join('data','active_charts')
    if args.also_copy_active:
        os.makedirs(active_dir, exist_ok=True)
    
    # Selection
    if args.all:
        files_to_process = sorted([f for f in os.listdir(args.src) if f.lower().endswith('.csv')])
    else:
        files_to_process = get_raw_file_selection(args.src)
    
    if not files_to_process:
        return

    # ensure log directory exists
    log_file = None
    log_writer = None
    if args.log_path:
        os.makedirs(os.path.dirname(args.log_path), exist_ok=True)
        log_headers = [
            'run_ts','asset','interval','source_file','dest_file','assigned_name','size_bytes','status','reason',
            'rows_in','rows_out','start_ts_in','end_ts_in','start_ts_out','end_ts_out','columns_in'
        ]
        write_header = not os.path.exists(args.log_path)
        log_file = open(args.log_path, mode='a', newline='', encoding='utf-8')
        log_writer = csv.DictWriter(log_file, fieldnames=log_headers)
        if write_header:
            log_writer.writeheader()

    asset_override = args.asset
    
    # Determine next sequential index based on existing chart_cl_#.csv files
    def get_max_existing_index(directories, prefix_pattern: re.Pattern):
        max_idx = 0
        for directory in directories:
            if not os.path.isdir(directory):
                continue
            for fname in os.listdir(directory):
                m = prefix_pattern.match(fname)
                if m:
                    try:
                        max_idx = max(max_idx, int(m.group(1)))
                    except ValueError:
                        continue
        return max_idx

    next_index_cache = {}
    
    # Track newly standardized charts for analysis
    newly_standardized = []

    count = 0
    for fname in files_to_process:
        src_path = os.path.join(args.src, fname)
        
        # Auto-detect symbol per file (in case of mixed symbols)
        file_symbol = asset_override or parse_symbol_from_filename(fname)
        if not file_symbol:
            file_symbol = input(f"Could not detect symbol for {fname}. Enter symbol: ").strip() or "ASSET"
        
        try:
            # gather pre-normalization metadata
            raw_df = pd.read_csv(src_path, index_col=0)
            raw_index_dt = pd.to_datetime(raw_df.index, errors='coerce')
            start_in = pd.NaT if raw_index_dt.isna().all() else raw_index_dt.min()
            end_in = pd.NaT if raw_index_dt.isna().all() else raw_index_dt.max()
            rows_in = len(raw_df)
            cols_in = list(raw_df.columns)

            # normalize
            df, interval_lbl, _ = normalize_chart(src_path)
            
            # Try to detect timeframe from filename, otherwise use inferred
            detected_tf = parse_timeframe_from_filename(fname)
            if detected_tf:
                interval_lbl = detected_tf
            
            # assign sequential destination name using detected symbol + interval
            prefix = f"{file_symbol}_{interval_lbl}_cl_"
            if prefix not in next_index_cache:
                pattern = re.compile(rf'^{re.escape(prefix)}(\d+)\.csv$', re.IGNORECASE)
                next_index_cache[prefix] = get_max_existing_index([args.dst, active_dir], pattern) + 1
            seq_num = next_index_cache[prefix]
            assigned_name = f"{prefix}{seq_num}.csv"
            while os.path.exists(os.path.join(args.dst, assigned_name)):
                seq_num += 1
                assigned_name = f"{prefix}{seq_num}.csv"
            next_index_cache[prefix] = seq_num + 1
            out_path = os.path.join(args.dst, assigned_name)
            df.to_csv(out_path)
            
            # Track for analysis
            if args.also_copy_active:
                active_path = os.path.join(active_dir, assigned_name)
                shutil.copy2(out_path, active_path)
                newly_standardized.append(active_path)
            else:
                newly_standardized.append(out_path)
            # remove original raw file after successful write
            try:
                os.remove(src_path)
            except Exception:
                pass
            print(f"Standardized: {fname} -> {assigned_name}")
            count += 1
            # write success log row
            if args.log_path:
                log_writer.writerow({
                    'run_ts': datetime.utcnow().isoformat(timespec='seconds'),
                    'asset': file_symbol,
                    'interval': interval_lbl,
                    'source_file': src_path,
                    'dest_file': out_path,
                    'assigned_name': assigned_name,
                    'size_bytes': os.path.getsize(src_path) if os.path.exists(src_path) else '',
                    'status': 'standardized',
                    'reason': '',
                    'rows_in': rows_in,
                    'rows_out': len(df),
                    'start_ts_in': '' if pd.isna(start_in) else start_in.isoformat(),
                    'end_ts_in': '' if pd.isna(end_in) else end_in.isoformat(),
                    'start_ts_out': '' if df.index.size == 0 else pd.to_datetime(df.index[0]).isoformat(),
                    'end_ts_out': '' if df.index.size == 0 else pd.to_datetime(df.index[-1]).isoformat(),
                    'columns_in': ';'.join(map(str, cols_in)),
                })
        except Exception as e:
            print(f"Skip {fname}: {e}")
            # write failure log row
            if args.log_path:
                log_writer.writerow({
                    'run_ts': datetime.utcnow().isoformat(timespec='seconds'),
                    'asset': file_symbol,
                    'interval': '',
                    'source_file': src_path,
                    'dest_file': '',
                    'assigned_name': '',
                    'size_bytes': os.path.getsize(src_path) if os.path.exists(src_path) else '',
                    'status': 'skipped',
                    'reason': str(e),
                    'rows_in': '',
                    'rows_out': '',
                    'start_ts_in': '',
                    'end_ts_in': '',
                    'start_ts_out': '',
                    'end_ts_out': '',
                    'columns_in': '',
                })
    # close log file if opened
    if log_file is not None:
        try:
            log_file.close()
        except Exception:
            pass
    print(f"Done. {count} chart(s) standardized to {args.dst}")
    
    # Run chart analyzer on newly standardized charts
    if newly_standardized:
        print("\n" + "=" * 60)
        print(f"Running chart analyzer on {len(newly_standardized)} newly standardized chart(s)...")
        print("=" * 60)
        
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from scripts.chart_analyzer import (
                load_chart_from_path, compute_regimes, segment_by_regime,
                summarize_segments, compute_human_summary, save_analysis
            )
            
            analysis_dir = os.path.join('outputs', 'analyses')
            os.makedirs(analysis_dir, exist_ok=True)
            
            # Default regime parameters (matching chart_analyzer defaults)
            regime_params = {
                'momentum_len': 20,
                'vol_len': 20,
                'trend_threshold': 0.0,
                'use_mcg_trend': True,
                'hma_len': 20,
                'hysteresis': 2,
            }
            
            for chart_path in newly_standardized:
                try:
                    price = load_chart_from_path(chart_path)
                    base_name = os.path.splitext(os.path.basename(chart_path))[0]
                    
                    regs = compute_regimes(price, **regime_params)
                    segs = segment_by_regime(price, regs['regime'])
                    segdf = summarize_segments(price, segs)
                    summary = compute_human_summary(price, regs, segdf)
                    
                    saved = save_analysis(chart_path, regime_params, price, regs, segdf, summary, analysis_dir)
                    print(f"  Analyzed: {base_name} -> {os.path.basename(saved['json'])}")
                except Exception as e:
                    print(f"  Warning: Failed to analyze {os.path.basename(chart_path)}: {e}")
            
            print(f"\nChart analysis completed. Results saved to {analysis_dir}")
        except ImportError as e:
            print(f"\nWarning: Could not import chart analyzer modules: {e}")
            print("Skipping analysis. Run manually: python scripts/chart_analyzer.py --all --save-analysis")
        except Exception as e:
            print(f"\nWarning: Chart analyzer failed: {e}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    main()


