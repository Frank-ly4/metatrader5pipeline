import itertools
import os
import numbers
import numpy as np
import pandas as pd
from src.engine.backtest import run_backtest
from src.metrics.metrics import cagr_frac, max_drawdown_frac, calmar, profit_factor, ulcer_index, expectancy, avg_hold_hours
from config.user_inputs import BACKTEST_CONFIG as USER_BACKTEST_CONFIG


def sample_int(u: float, low: int, high: int) -> int:
    # u in [0,1); inclusive high
    return int(np.floor(low + u * (high - low + 1)))

def clamp(v: float | int, low: float | int, high: float | int) -> float | int:
    return max(low, min(high, v))

def _avg_hold_hours_safe(pf) -> float | None:
    try:
        trades = pf.trades.records_readable
        if len(trades) == 0:
            return None
        durations = (trades['Exit Date'] - trades['Entry Date']).dt.total_seconds() / 3600.0
        return float(durations.mean()) if len(durations) > 0 else None
    except Exception:
        return None


def _infer_bars_per_year(index) -> int:
    try:
        import pandas as _pd
        if isinstance(index, _pd.DatetimeIndex) and len(index) > 1:
            inferred = _pd.infer_freq(index)
            if inferred:
                f = inferred.upper()
                if f.endswith('T'):
                    mins = int(f[:-1]) if f[:-1].isdigit() else 1
                    return int(round(525600 / max(mins, 1)))
                if f.endswith('H'):
                    hrs = int(f[:-1]) if f[:-1].isdigit() else 1
                    return int(round(8760 / max(hrs, 1)))
                if f.endswith('D'):
                    return 365
        # fallback by median delta
        deltas = _pd.Series(index).diff().dropna()
        if len(deltas) > 0:
            minutes = max(1, int(round(deltas.median().total_seconds() / 60)))
            if minutes < 60:
                return int(round(525600 / minutes))
            if minutes < 1440:
                return int(round(8760 / (minutes / 60)))
            return 365
    except Exception:
        pass
    return 365


def _compute_drawdown_series(equity_series) -> tuple[float | None, float | None]:
    try:
        import numpy as _np
        eq = _np.asarray(equity_series, dtype=float)
        if eq.size == 0:
            return None, None
        peak = -_np.inf
        dd = []
        for v in eq:
            peak = v if v > peak else peak
            dd.append(0.0 if peak <= 0 else (v - peak) / peak)
        import pandas as _pd
        dd_ser = _pd.Series(dd, index=getattr(equity_series, 'index', None))
        max_dd = float(dd_ser.min())  # negative
        ui = float((dd_ser.pow(2).mean()) ** 0.5)
        return max_dd, ui
    except Exception:
        return None, None


def _try_pf_equity_returns(pf):
    equity = None
    rets = None
    try:
        equity = pf.value()
    except Exception:
        try:
            equity = pf.portfolio.value
        except Exception:
            equity = None
    try:
        rets = pf.returns()
    except Exception:
        try:
            rets = pf.returns
        except Exception:
            rets = None
    return equity, rets


def _omega_ratio(returns, threshold: float = 0.0) -> float | None:
    try:
        import numpy as _np
        r = _np.asarray(returns, dtype=float)
        if r.size == 0:
            return None
        gains = _np.maximum(r - threshold, 0.0).sum()
        losses = _np.maximum(threshold - r, 0.0).sum()
        return None if losses == 0 else float(gains / losses)
    except Exception:
        return None


def _compute_regime_stats(trades: pd.DataFrame, toggles: dict) -> dict | None:
    """Best-effort regime attribution by joining trades with chart parquet data.

    Uses chart_name from toggles to locate the corresponding parquet file in
    data/active_charts/, then merges trade entries with indicator context
    (e.g., ATR/ADX) and aggregates simple performance stats by regime.
    """
    try:
        if trades is None or trades.empty:
            return None

        chart_name = toggles.get('chart_name')
        if not chart_name:
            return None

        import os
        parquet_name = chart_name.replace('.csv', '.parquet')
        parquet_path = os.path.join('data', 'active_charts', parquet_name)
        if not os.path.exists(parquet_path):
            return None

        indicators = pd.read_parquet(parquet_path)

        # Ensure datetime index for indicators
        if not isinstance(indicators.index, pd.DatetimeIndex):
            time_col = None
            for cand in ('time', 'Time', 'datetime', 'Date'):
                if cand in indicators.columns:
                    time_col = cand
                    break
            if time_col is None:
                return None
            indicators = indicators.set_index(pd.to_datetime(indicators[time_col], errors='coerce'))

        indicators = indicators.sort_index()

        # Prepare trades entry times
        if 'Entry Date' not in trades.columns:
            return None

        t = trades.copy()
        t['Entry Date'] = pd.to_datetime(t['Entry Date'], errors='coerce')
        t = t.dropna(subset=['Entry Date'])
        if t.empty:
            return None

        # Choose a return-like column for attribution
        ret_col = None
        for cand in ('Return', 'return', 'PnL', 'pnl'):
            if cand in t.columns:
                ret_col = cand
                break
        if ret_col is None:
            return None

        merged = pd.merge_asof(
            t.sort_values('Entry Date'),
            indicators,
            left_on='Entry Date',
            right_index=True,
            direction='backward',
        )

        stats: dict = {}

        # Volatility buckets via ATR, if available
        if 'atr' in merged.columns:
            try:
                merged['vol_bucket'] = pd.qcut(
                    merged['atr'],
                    4,
                    labels=['Low', 'MedLow', 'MedHigh', 'High'],
                )
                vol_grp = (
                    merged.groupby('vol_bucket')[ret_col]
                    .agg(['count', 'mean'])
                    .rename(columns={'count': 'trades', 'mean': 'avg_return'})
                )
                stats['volatility_buckets'] = vol_grp.to_dict(orient='index')
            except Exception:
                pass

        # Trend buckets via ADX, if available
        if 'adx' in merged.columns:
            try:
                merged['trend_bucket'] = pd.qcut(
                    merged['adx'],
                    4,
                    labels=['Weak', 'Moderate', 'Strong', 'Extreme'],
                )
                trend_grp = (
                    merged.groupby('trend_bucket')[ret_col]
                    .agg(['count', 'mean'])
                    .rename(columns={'count': 'trades', 'mean': 'avg_return'})
                )
                stats['trend_buckets'] = trend_grp.to_dict(orient='index')
            except Exception:
                pass

        return stats or None
    except Exception:
        # Never let attribution break optimization; it's best-effort only
        return None


def _directional_metrics(trades: pd.DataFrame) -> dict:
    """Compute directional aggregates without full trade-log storage."""
    if trades is None or trades.empty or 'Direction' not in trades.columns:
        return {}

    def _pick_returns(df: pd.DataFrame):
        for cand in ('Return [%]', 'return', 'Return', 'PnL', 'pnl'):
            if cand in df.columns:
                return pd.to_numeric(df[cand], errors='coerce')
        return None

    out: dict = {}
    for side in ('Long', 'Short'):
        side_df = trades[trades['Direction'].str.lower() == side.lower()]
        if side_df.empty:
            continue
        rets = _pick_returns(side_df)
        wins = None
        if rets is not None:
            rets = rets.dropna()
            wins = rets[rets > 0]
        out[f"{side.lower()}_trades"] = int(len(side_df))
        out[f"{side.lower()}_win_rate"] = float((len(wins) / len(side_df)) * 100) if wins is not None and len(side_df) > 0 else 0.0
        out[f"{side.lower()}_expectancy"] = float(rets.mean()) if rets is not None and len(rets) > 0 else None
    return out


def evaluate_collect(price: pd.DataFrame, params: dict, toggles: dict, compute_signals_func) -> tuple[dict, pd.DataFrame]:
    """Evaluate one parameter set and also return per-trade records (readable).
    
    Handles both 3-tuple (legacy long-only) and 5-tuple (bidirectional) return shapes.
    """
    # Ensure broker spec is in toggles for margin-aware simulation
    if 'broker_spec' not in toggles:
        import os
        import json
        spec_path = os.path.join('config', 'mt5_broker_spec.json')
        if os.path.exists(spec_path):
            with open(spec_path, 'r') as f:
                toggles['broker_spec'] = json.load(f)

    result = compute_signals_func(price, params, toggles)

    # Detect return shape: 3-tuple (legacy) or 5-tuple (bidirectional)
    if len(result) == 5:
        # Bidirectional: (long_entries, long_exits, short_entries, short_exits, debug)
        long_entries, long_exits, short_entries, short_exits, _ = result
        pf = run_backtest(
            price, 
            long_entries, 
            long_exits,
            short_entries=short_entries,
            short_exits=short_exits,
            backtest_overrides=USER_BACKTEST_CONFIG
        )
    else:
        # Legacy 3-tuple: (entries, exits, debug)
        entries, exits, _ = result
        pf = run_backtest(price, entries, exits, backtest_overrides=USER_BACKTEST_CONFIG)
    stats = pf.stats()
    try:
        trades = pf.trades.records_readable.copy()
    except Exception:
        trades = pd.DataFrame()
    # Additional metrics
    equity, rets = _try_pf_equity_returns(pf)
    max_dd, ui = _compute_drawdown_series(equity) if equity is not None else (None, None)
    # calmar_rb, dbg = _robust_calmar(price.index, start_val, end_val, max_dd_pct, ui, rets)
    omega0 = _omega_ratio(rets, 0.0)

    # Sanitize metrics that might be NaN or Inf from vectorbt
    def _sanitize_metric(value, default=0.0):
        if pd.isna(value) or np.isinf(value):
            return default
        return value

    total_return_val = _sanitize_metric(stats.get('Total Return [%]'))
    sharpe_ratio_val = _sanitize_metric(stats.get('Sharpe Ratio'))
    sortino_ratio_val = _sanitize_metric(stats.get('Sortino Ratio'))
    calmar_ratio_val = _sanitize_metric(stats.get('Calmar Ratio'))
    max_drawdown_val = _sanitize_metric(stats.get('Max Drawdown [%]'))
    win_rate_val = _sanitize_metric(stats.get('Win Rate [%]'))
    total_trades_val = _sanitize_metric(stats.get('Total Trades'), default=0)
    profit_factor_val = _sanitize_metric(stats.get('Profit Factor'))
    expectancy_val = _sanitize_metric(stats.get('Expectancy'))
    avg_hold_hours_val = _avg_hold_hours_safe(pf)

    # Manual adjustment for win_rate if total_trades is 0 (vectorbt might return NaN)
    if total_trades_val == 0:
        win_rate_val = 0.0

    # fees threshold approx per-bar: use configured fees as baseline (small proxy)
    fees_thr = 0.0
    try:
        fees_thr = float(USER_BACKTEST_CONFIG.get('fees', 0.0))
    except Exception:
        fees_thr = 0.0
    omegaf = _omega_ratio(rets, fees_thr)

    row = {
        'total_return': total_return_val,
        'sharpe_ratio': sharpe_ratio_val,
        'sortino_ratio': sortino_ratio_val,
        'calmar_ratio': calmar_ratio_val / 100.0 if calmar_ratio_val != 0 else 0.0,  # Convert from percentage mismatch
        'max_drawdown': max_drawdown_val,
        'win_rate': win_rate_val,
        'total_trades': total_trades_val,
        'profit_factor': profit_factor_val,
        'expectancy': expectancy_val,
        'start_capital': stats.get('Start Value'),
        'end_capital': stats.get('End Value'),
        'avg_hold_hours': avg_hold_hours_val,
        'ulcer_index': ui,
        'omega_0': omega0,
        'omega_fees': omegaf,
        # 'calmar_robust': calmar_rb,
        # 'val_days': dbg.get('val_days'),
        # 'cagr_adj': dbg.get('cagr_adj'),
        # 'maxdd_obs_frac': dbg.get('maxdd_obs_frac'),
        # 'dd_floor': dbg.get('dd_floor'),
        # 'dd_adj': dbg.get('dd_adj'),
        'params': params.copy()
    }

    try:
        row.update(_directional_metrics(trades))
    except Exception:
        pass

    # Best-effort regime attribution (parquet-based)
    try:
        regime_stats = _compute_regime_stats(trades, toggles)
        if regime_stats:
            row['regime_stats'] = regime_stats
    except Exception:
        # Do not let attribution affect core optimization
        pass

    return row, trades


def _longest_lookback_bars(params: dict) -> int:
    # Consider slow_max_len, atr_len, dma_atr_len, momentum_len, and mcg_dma smoothing (100)
    candidates = [
        int(params.get('slow_max_len', 50)),
        int(params.get('atr_len', 14)),
        int(params.get('dma_atr_len', 14)),
        int(params.get('momentum_len', 14)),
        100,
    ]
    return max(candidates)


def evaluate_collect_kfold(
    price: pd.DataFrame,
    params: dict,
    toggles: dict,
    compute_signals_func,
    *,
    k_folds: int = 3,
    embargo_frac: float = 0.05,
) -> tuple[list[dict], pd.DataFrame]:
    """Evaluate one parameter set over K time-based folds with an embargo.

    Returns a list of per-fold result rows and a concatenated trades DataFrame (with fold_id).
    """
    n = len(price)
    if n < 10:
        return [], pd.DataFrame()
    lookback = _longest_lookback_bars(params)
    embargo = max(int(round(embargo_frac * n)), 3 * lookback)
    # Compute validation block size - increase minimum size to allow more trades
    v = max(lookback + 1, int((n - embargo) // max(1, min(k_folds, 3))))
    rows = []
    all_trades = []
    for fold in range(k_folds):
        val_start = fold * v
        val_end = min(n, (fold + 1) * v)
        if val_start >= n or val_end - val_start <= lookback:
            continue
        train_end = max(0, val_start - embargo)
        if train_end <= lookback:
            # not enough warmup for indicators
            continue
        train_price = price.iloc[:train_end]
        val_price = price.iloc[val_start:val_end]
        # Train on train_price to fit thresholds; our strategy is parameteric without fitting,
        # so we simply evaluate on val_price to compute performance for this fold.
        result = compute_signals_func(val_price, params, toggles)
        
        # Detect return shape: 3-tuple (legacy) or 5-tuple (bidirectional)
        if len(result) == 5:
            # Bidirectional: (long_entries, long_exits, short_entries, short_exits, debug)
            long_entries, long_exits, short_entries, short_exits, _ = result
            pf = run_backtest(
                val_price,
                long_entries,
                long_exits,
                short_entries=short_entries,
                short_exits=short_exits,
                backtest_overrides=USER_BACKTEST_CONFIG
            )
        else:
            # Legacy 3-tuple: (entries, exits, debug)
            entries, exits, _ = result
            pf = run_backtest(val_price, entries, exits, backtest_overrides=USER_BACKTEST_CONFIG)
        stats = pf.stats()
        # extra metrics
        equity, rets = _try_pf_equity_returns(pf)
        max_dd, ui = _compute_drawdown_series(equity) if equity is not None else (None, None)
        # calmar_rb, dbg = _robust_calmar(val_price.index, stats.get('Start Value'), stats.get('End Value'), stats.get('Max Drawdown [%]'), ui, rets)
        omega0 = _omega_ratio(rets, 0.0)
        
        # Fees threshold for Omega ratio
        fees_thr = 0.0
        try:
            fees_thr = float(USER_BACKTEST_CONFIG.get('fees', 0.0))
        except Exception:
            fees_thr = 0.0
        omegaf = _omega_ratio(rets, fees_thr)

        # Sanitize metrics that might be NaN or Inf from vectorbt
        def _sanitize_metric_kfold(value, default=0.0):
            if pd.isna(value) or np.isinf(value):
                return default
            return value

        total_return_val = _sanitize_metric_kfold(stats.get('Total Return [%]'))
        sharpe_ratio_val = _sanitize_metric_kfold(stats.get('Sharpe Ratio'))
        sortino_ratio_val = _sanitize_metric_kfold(stats.get('Sortino Ratio'))
        calmar_ratio_val = _sanitize_metric_kfold(stats.get('Calmar Ratio'))
        max_drawdown_val = _sanitize_metric_kfold(stats.get('Max Drawdown [%]'))
        win_rate_val = _sanitize_metric_kfold(stats.get('Win Rate [%]'))
        total_trades_val = _sanitize_metric_kfold(stats.get('Total Trades'), default=0)
        profit_factor_val = _sanitize_metric_kfold(stats.get('Profit Factor'))
        expectancy_val = _sanitize_metric_kfold(stats.get('Expectancy'))
        avg_hold_hours_val = _avg_hold_hours_safe(pf)

        # Manual adjustment for win_rate if total_trades is 0 (vectorbt might return NaN)
        if total_trades_val == 0:
            win_rate_val = 0.0

        # Ensure timezone-naive timestamps for Excel compatibility
        val_start_ts = val_price.index[0]
        val_end_ts = val_price.index[-1]
        
        # Strip timezone information if present
        if hasattr(val_start_ts, 'tz_localize'):
            try:
                val_start_ts = val_start_ts.tz_localize(None) if val_start_ts.tz is not None else val_start_ts
            except Exception:
                pass
        if hasattr(val_end_ts, 'tz_localize'):
            try:
                val_end_ts = val_end_ts.tz_localize(None) if val_end_ts.tz is not None else val_end_ts
            except Exception:
                pass
        
        row = {
            'fold_id': fold + 1,
            'bars_total': int(n),
            'bars_train': int(train_end),
            'bars_embargo': int(embargo),
            'bars_val': int(val_end - val_start),
            'val_start': val_start_ts,
            'val_end': val_end_ts,
            'total_return': total_return_val,
            'sharpe_ratio': sharpe_ratio_val,
            'sortino_ratio': sortino_ratio_val,
            'calmar_ratio': calmar_ratio_val / 100.0 if calmar_ratio_val != 0 else 0.0,  # Convert from percentage mismatch
            'max_drawdown': max_drawdown_val,
            'win_rate': win_rate_val,
            'total_trades': total_trades_val,
            'profit_factor': profit_factor_val,
            'expectancy': expectancy_val,
            'avg_hold_hours': avg_hold_hours_val,
            'ulcer_index': ui,
            'omega_0': omega0,
            'omega_fees': omegaf,
            # 'calmar_robust': calmar_rb,
            # 'val_days': dbg.get('val_days'),
            # 'cagr_adj': dbg.get('cagr_adj'),
            # 'maxdd_obs_frac': dbg.get('maxdd_obs_frac'),
            # 'dd_floor': dbg.get('dd_floor'),
            # 'dd_adj': dbg.get('dd_adj'),
            'params': params.copy(),
        }
        try:
            row.update(_directional_metrics(tdf))
        except Exception:
            pass
        rows.append(row)
        try:
            tdf = pf.trades.records_readable.copy()
            if len(tdf) > 0:
                tdf['fold_id'] = fold + 1
                all_trades.append(tdf)
        except Exception:
            pass
    trades_df = pd.concat(all_trades, ignore_index=True, sort=False) if len(all_trades) > 0 else pd.DataFrame()
    return rows, trades_df


def grid_search(price: pd.DataFrame, param_ranges: dict, toggles: dict, max_combinations: int = 500, metric: str = 'total_return', seed: int = 42) -> pd.DataFrame:
    # Use the unified sampler
    param_sets = sample_param_sets(param_ranges, method='grid', n=max_combinations, seed=seed)
    
    results = []
    trades_all = []

    for i, params in enumerate(param_sets):
        res, trades = evaluate_collect(price, params, toggles)
        if res is not None:
            res['trial_id'] = i
            results.append(res)
            if trades is not None and len(trades) > 0:
                trades['trial_id'] = i
                trades_all.append(trades)

    df = pd.DataFrame(results)
    if len(df) > 0:
        df = df.sort_values(metric, ascending=False)
        
    trades_df = pd.concat(trades_all, ignore_index=True) if trades_all else pd.DataFrame()
    return df, trades_df


def random_search(price: pd.DataFrame, param_ranges: dict, toggles: dict, n_trials: int = 200, metric: str = 'total_return', seed: int = 42) -> pd.DataFrame:
    # Re-use the unified sampler logic
    param_sets = sample_param_sets(param_ranges, method='random', n=n_trials, seed=seed)
    
    results = []
    trades_all = []
    
    for i, params in enumerate(param_sets):
        # Use the robust, unified evaluation path
        res, trades = evaluate_collect(price, params, toggles)
        if res is not None:
            res['trial_id'] = i  # Add trial ID for traceability
            results.append(res)
            if trades is not None and len(trades) > 0:
                trades['trial_id'] = i
                trades_all.append(trades)

    df = pd.DataFrame(results)
    
    if len(df) > 0:
        # Sorting is now simpler as there's no separate 'suspect' logic from _evaluate
        df = df.sort_values(by=metric, ascending=False)
        
    # Concatenate all trades at the end for efficiency
    trades_df = pd.concat(trades_all, ignore_index=True) if trades_all else pd.DataFrame()
    
    return df, trades_df


def lhs_search(price: pd.DataFrame, param_ranges: dict, toggles: dict, n_trials: int = 200, metric: str = 'total_return', seed: int = 42) -> pd.DataFrame:
    """Latin Hypercube Sampling over normalized parameter lists.

    Uses SciPy QMC if available; otherwise, a numpy-only stratified fallback.
    """
    param_sets = sample_param_sets(param_ranges, method='lhs', n=n_trials, seed=seed)
    
    results = []
    trades_all = []

    for i, params in enumerate(param_sets):
        res, trades = evaluate_collect(price, params, toggles)
        if res is not None:
            res['trial_id'] = i
            results.append(res)
            if trades is not None and len(trades) > 0:
                trades['trial_id'] = i
                trades_all.append(trades)

    df = pd.DataFrame(results)
    if len(df) > 0:
        df = df.sort_values(metric, ascending=False)

    trades_df = pd.concat(trades_all, ignore_index=True) if trades_all else pd.DataFrame()
    return df, trades_df


def sobol_search(price: pd.DataFrame, param_ranges: dict, toggles: dict, n_trials: int = 200, metric: str = 'total_return', seed: int = 42) -> pd.DataFrame:
    """Sobol low-discrepancy sampling over normalized parameter lists.

    Falls back to LHS when SciPy QMC is not available.
    """
    param_sets = sample_param_sets(param_ranges, method='sobol', n=n_trials, seed=seed)
    
    results = []
    trades_all = []

    for i, params in enumerate(param_sets):
        res, trades = evaluate_collect(price, params, toggles)
        if res is not None:
            res['trial_id'] = i
            results.append(res)
            if trades is not None and len(trades) > 0:
                trades['trial_id'] = i
                trades_all.append(trades)

    df = pd.DataFrame(results)
    if len(df) > 0:
        df = df.sort_values(metric, ascending=False)
        
    trades_df = pd.concat(trades_all, ignore_index=True) if trades_all else pd.DataFrame()
    return df, trades_df


def _try_qmc_sample(method: str, dim: int, n: int, seed: int) -> np.ndarray | None:
    """Try to sample from SciPy QMC; return None if unavailable."""
    try:
        from scipy.stats import qmc  # type: ignore
        if method == 'sobol':
            sampler = qmc.Sobol(d=dim, scramble=True, seed=seed)
            return sampler.random(n)
        if method == 'lhs':
            sampler = qmc.LatinHypercube(d=dim, seed=seed)
            return sampler.random(n)
    except Exception:
        return None
    return None


def _lhs_fallback(dim: int, n: int, seed: int) -> np.ndarray:
    """Pure numpy Latin-hypercube-style stratified sample in [0,1]^dim."""
    rng = np.random.RandomState(seed)
    # Create n strata per dimension and sample one point from each, then shuffle per-dimension
    u = (rng.rand(n, dim) + np.arange(n)[:, None]) / float(n)
    for j in range(dim):
        rng.shuffle(u[:, j])
    return u


def _unit_hypercube_samples(method: str, dim: int, n: int, seed: int) -> np.ndarray:
    """Return (n, dim) samples in [0,1]^dim using the requested method with graceful fallback."""
    m = method.lower()
    if m in ('sobol', 'lhs'):
        arr = _try_qmc_sample(m, dim, n, seed)
        if arr is not None:
            return arr
        # Fallbacks: prefer LHS for both methods when QMC unavailable
        return _lhs_fallback(dim, n, seed)
    # default random
    rng = np.random.RandomState(seed)
    return rng.rand(n, dim)


def _map_unit_to_params(param_space: dict, names: list[str], unit_samples: np.ndarray) -> list[dict]:
    out = []
    debug_assert = os.getenv("OPT_DEBUG_ASSERTS", "").lower() in ("1", "true", "yes")
    for row in unit_samples:
        params = {}
        for j, nm in enumerate(names):
            spec = param_space[nm]
            u = row[j]
            ptype = spec[0]
            if ptype == 'int':
                # spec: ('int', low, high, step|None)
                _, lo, hi, step = spec
                if step is None:
                    val = clamp(sample_int(u, int(lo), int(hi)), int(lo), int(hi))
                else:
                    count = int(((hi - lo) / step) + 1)
                    idx = clamp(int(np.floor(u * count)), 0, count - 1)
                    val = int(round(lo + idx * step))
            elif ptype == 'float':
                _, lo, hi, step = spec
                if step is None:
                    val = clamp(lo + u * (hi - lo), lo, hi)
                else:
                    count = int(((hi - lo) / step) + 1)
                    idx = clamp(int(np.floor(u * count)), 0, count - 1)
                    val = lo + idx * step
            else:  # 'cat'
                _, values = spec
                values = list(values)
                if len(values) == 0:
                    continue
                idx = int(np.floor(u * len(values)))
                if idx >= len(values):
                    idx = len(values) - 1
                val = values[idx]
                if debug_assert:
                    assert val in values, f"Categorical sample {val} not in candidates for {nm}"
            params[nm] = val
        out.append(params)
    return out


def sample_param_sets(param_ranges: dict, *, method: str = 'random', n: int = 200, seed: int = 42) -> list[dict]:
    """Generate a list of parameter dicts using a sampling method over normalized ranges.

    Methods: 'random', 'grid' (random subset up to n), 'lhs', 'sobol'.
    """
    normalized_ranges = normalize_param_ranges(param_ranges)
    param_space = build_param_space(normalized_ranges) # includes numeric + categorical
    names = list(param_space.keys())
    if method == 'grid':
        # Check grid size before building to prevent memory explosion
        total_combos = 1
        for k in names:
            total_combos *= len(normalized_ranges[k])
            if total_combos > 1_000_000:  # Early exit if too large
                # Use random sampling instead
                print(f"WARNING: Grid size too large ({total_combos:,}+), falling back to random sampling")
                rng = np.random.RandomState(seed)
                return [{k: rng.choice(normalized_ranges[k]) for k in names} for _ in range(n)]
        
        # Safe to build grid
        combos = list(itertools.product(*[normalized_ranges[k] for k in names]))
        rng = np.random.RandomState(seed)
        if len(combos) > n:
            idx = rng.choice(len(combos), n, replace=False)
            combos = [combos[i] for i in idx]
        return [dict(zip(names, c)) for c in combos]
    if method in ('lhs', 'sobol'):
        dim = len(names)
        samples = _unit_hypercube_samples(method, dim, n, seed)
        return _map_unit_to_params(param_space, names, samples)
    # default random (supports categorical via rng.choice)
    rng = np.random.RandomState(seed)
    return [{k: rng.choice(normalized_ranges[k]) for k in names} for _ in range(n)]


# --- Range normalization helpers ---

def normalize_param_ranges(param_ranges: dict) -> dict:
    """Accept lists or strings; return dict[str, list]."""
    out = {}
    for k, v in param_ranges.items():
        if isinstance(v, dict):
            out[k] = v
        elif isinstance(v, str):
            out[k] = _parse_range_string(v)
        elif isinstance(v, (list, tuple, np.ndarray)):
            out[k] = list(v)
        else:
            out[k] = [v]
        # dedupe and sort
        try:
            out[k] = sorted(set(out[k]))
        except Exception:
            pass
        # domain constraints
        if k == 'momentum_threshold':
            try:
                out[k] = [min(1.0, max(0.0, float(x))) for x in out[k]]
                # re-dedupe/sort after clamping
                out[k] = sorted(set(out[k]))
            except Exception:
                pass
    return out

def build_param_space(param_ranges: dict) -> dict:
    """Infer sampling spec per parameter.

    Returns dict[str, tuple]:
      - ('int', low, high)
      - ('float', low, high)
      - ('cat', values_list)  # default for lists/tuples/ndarrays
      - explicit dict schema for ranges:
        {"mode": "range", "dtype": "int|float", "low": ..., "high": ..., "step": optional}
        {"mode": "cat", "values": [...]}

    This enables optimizing discrete/categorical parameters (e.g., HTF timeframes).
    """
    param_space: dict = {}
    for k, spec in param_ranges.items():
        # Explicit dict schema
        if isinstance(spec, dict):
            mode = spec.get("mode")
            if mode == "range":
                dtype = spec.get("dtype", "float")
                if dtype not in ("int", "float"):
                    raise ValueError(f"{k}: dtype must be int|float, got {dtype}")
                if not all(x in spec for x in ("low", "high")):
                    raise ValueError(f"{k}: range schema requires low/high")
                low = spec["low"]; high = spec["high"]; step = spec.get("step")
                if not isinstance(low, numbers.Real) or not isinstance(high, numbers.Real):
                    raise TypeError(f"{k}: low/high must be numeric")
                if step is not None and not isinstance(step, numbers.Real):
                    raise TypeError(f"{k}: step must be numeric when provided")
                param_space[k] = (dtype, low, high, step)
                continue
            if mode == "cat":
                values = spec.get("values", [])
                if not isinstance(values, (list, tuple, np.ndarray)) or len(values) == 0:
                    raise ValueError(f"{k}: categorical schema must include non-empty values")
                param_space[k] = ('cat', list(values))
                continue
            raise ValueError(f"{k}: unknown schema mode {mode}")

        # Default: lists/tuples/ndarrays are categorical
        if not isinstance(spec, (list, tuple, np.ndarray)):
            raise ValueError(f"Param range for {k} must be list/tuple/ndarray or schema dict, got {type(spec)}")
        if len(spec) == 0:
            raise ValueError(f"Param range for {k} is empty")
        param_space[k] = ('cat', list(spec))
    return param_space

def _frange(start: float, end: float, step: float) -> list:
    if step == 0:
        return [start]
    # ensure direction
    n = int(round((end - start) / step))
    n = max(n, 0)
    vals = [start + i * step for i in range(n + 1)]
    # fix floating point drift near end
    if len(vals) > 0:
        vals[-1] = end
    return vals


def _parse_range_string(spec: str) -> list:
    s = str(spec).strip()
    if not s:
        return []
    # comma-separated list
    if ',' in s and '-' not in s:
        parts = [p.strip() for p in s.split(',') if p.strip() != '']
        out = []
        for p in parts:
            try:
                out.append(int(p))
            except ValueError:
                out.append(float(p))
        return out
    # range with optional step: start-end[:step]
    step = None
    if ':' in s:
        s, step_str = s.split(':', 1)
        try:
            step = float(step_str)
        except Exception:
            step = None
    if '-' in s:
        a_str, b_str = s.split('-', 1)
        a_str, b_str = a_str.strip(), b_str.strip()
        # infer int vs float by presence of dot
        is_float = ('.' in a_str) or ('.' in b_str) or (step is not None and not float(step).is_integer())
        a = float(a_str) if is_float else int(a_str)
        b = float(b_str) if is_float else int(b_str)
        if step is None:
            step = 1.0 if is_float else 1
        vals = _frange(float(a), float(b), float(step))
        if not is_float:
            vals = [int(round(v)) for v in vals]
        return vals
    # fallback single value
    try:
        return [int(s)]
    except ValueError:
        return [float(s)]

