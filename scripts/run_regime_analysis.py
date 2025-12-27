#!/usr/bin/env python3
"""
Regime-Based Performance Analysis Tool

Performs deep-dive analysis on a single trial by:
1. Loading trial parameters from optimizer results
2. Running backtest using existing 4.2.5 engine
3. Loading chart analysis (regime segments)
4. Tagging each trade by regime
5. Generating detailed regime breakdown report

Usage:
    python run_regime_analysis.py --uid 20251018_112307:28 --capital 10000 --fees 0.001

Outputs JSON to stdout for Query GUI consumption.
"""

import argparse
import sys
import os
import json
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def load_trial_by_uid(trial_uid: str, run_json_path: Optional[str] = None) -> Tuple[Dict, str]:
    """Load trial data by UID from run JSON file."""
    if not run_json_path:
        # Search all JSON files in outputs/runs
        runs_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'runs')
        if not os.path.exists(runs_dir):
            raise FileNotFoundError(f"Runs directory not found: {runs_dir}")
        
        jsons = [os.path.join(runs_dir, f) for f in os.listdir(runs_dir) if f.lower().endswith('.json')]
        if not jsons:
            raise FileNotFoundError('No run JSON found in outputs/runs')
        
        # Search through all JSON files for the UID
        for json_path in jsons:
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                results = data.get('results', [])
                if not results:
                    continue
                    
                df = pd.DataFrame(results)
                
                # Match UID
                uid_col = 'trial_uid' if 'trial_uid' in df.columns else 'uid'
                if uid_col not in df.columns:
                    continue
                
                matching = df[df[uid_col] == trial_uid]
                if len(matching) > 0:
                    return matching.iloc[0].to_dict(), json_path
                    
            except Exception:
                # Skip files that can't be loaded
                continue
        
        # If we get here, UID wasn't found in any file
        raise ValueError(f"Trial UID not found in any JSON file: {trial_uid}")
    
    else:
        # Use specified file
        with open(run_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        results = data.get('results', [])
        df = pd.DataFrame(results)
        
        # Match UID
        uid_col = 'trial_uid' if 'trial_uid' in df.columns else 'uid'
        if uid_col not in df.columns:
            raise ValueError("No UID column (trial_uid or uid) found in results")
        
        matching = df[df[uid_col] == trial_uid]
        if len(matching) == 0:
            raise ValueError(f"Trial UID not found: {trial_uid}")
        
        return matching.iloc[0].to_dict(), run_json_path


def extract_params(trial_data: Dict) -> Dict:
    """Extract strategy parameters from trial data."""
    params = {}
    skip_cols = {'_source_file', 'fold_id', 'bars_total', 'bars_train', 'bars_embargo',
                'bars_val', 'val_start', 'val_end', 'total_return', 'sharpe_ratio',
                'sortino_ratio', 'calmar_ratio', 'max_drawdown', 'win_rate',
                'total_trades', 'profit_factor', 'expectancy', 'start_capital',
                'end_capital', 'avg_hold_hours', 'ulcer_index', 'omega_0', 'omega_fees',
                'chart', 'trial_id', 'method', 'trial_uid', 'uid', 'score', 'is_pareto',
                'stability_score', 'group_rank'}
    
    for k, v in trial_data.items():
        if isinstance(k, str):
            # Handle both param_ prefixed and non-prefixed
            if k.startswith('param_'):
                params[k.replace('param_', '')] = v
            elif k not in skip_cols:
                params[k] = v
    
    if not params:
        raise ValueError("No parameters found in trial data")
    
    return params


def load_chart_analysis(chart_name: str) -> Optional[Dict]:
    """Load chart analysis JSON for regime segments."""
    analyses_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'analyses')
    
    # Strip .csv extension if present
    base_name = os.path.splitext(chart_name)[0]
    analysis_file = os.path.join(analyses_dir, f"{base_name}.json")
    
    sys.stderr.write(f"Looking for chart analysis at: {analysis_file}\n")
    
    if not os.path.exists(analysis_file):
        return None
    
    try:
        with open(analysis_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to load chart analysis: {e}\n")
        return None


def tag_trade_by_regime(trade_entry_time: pd.Timestamp, segments: List[Dict]) -> str:
    """Tag a trade with its regime based on entry time."""
    for segment in segments:
        seg_start = pd.to_datetime(segment['start'])
        seg_end = pd.to_datetime(segment['end'])
        
        if seg_start <= trade_entry_time <= seg_end:
            return segment.get('regime', 'unknown')
    
    return 'unknown'


def run_backtest_with_regime_tagging(trial_data: Dict, params: Dict, capital: float, fees: float, 
                                     max_positions: int, chart_analysis: Optional[Dict]) -> Dict:
    """Run backtest using existing 4.2.5 engine and tag trades by regime."""
    from src.io.data_loader import load_chart_from_path
    from src.strategy.bands_v2 import compute_signals
    from src.engine.backtest import run_backtest
    from config.user_inputs import TOGGLES
    
    # Get chart name and load data
    chart_name = trial_data.get('chart')
    if not chart_name:
        raise ValueError("No chart name in trial data")
    
    # Construct path to chart
    chart_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'active_charts')
    chart_path = os.path.join(chart_dir, chart_name)
    
    if not os.path.exists(chart_path):
        raise FileNotFoundError(f"Chart not found: {chart_path}")
    
    # Load price data
    price_data = load_chart_from_path(chart_path)
    
    # Filter to validation period if available
    val_start = trial_data.get('val_start')
    val_end = trial_data.get('val_end')
    
    if val_start and val_end:
        try:
            val_start_dt = pd.to_datetime(val_start)
            val_end_dt = pd.to_datetime(val_end)
            # Filter price data to validation period
            price_data = price_data[(price_data.index >= val_start_dt) & (price_data.index <= val_end_dt)]
        except Exception:
            # If date parsing fails, use full data
            pass
    
    # Compute signals
    entries, exits, _ = compute_signals(price_data, params, TOGGLES)
    
    # Prepare backtest config
    backtest_config = {
        'init_cash': capital,
        'max_layers': max_positions,
        'fees': fees,
        'size': 1.0,
    }
    
    # Run backtest using existing engine
    pf = run_backtest(price_data, entries, exits, backtest_overrides=backtest_config)
    stats = pf.stats()
    
    # Extract trades
    trades_list = []
    try:
        trades_df = pf.trades.records_readable
        if trades_df is not None and len(trades_df) > 0:
            # Get regime segments if available
            segments = []
            if chart_analysis and 'segments' in chart_analysis:
                segments = chart_analysis['segments']
            
            for _, trade in trades_df.iterrows():
                entry_time = pd.to_datetime(trade['Entry Timestamp'])
                exit_time = pd.to_datetime(trade['Exit Timestamp'])
                
                # Tag trade by regime
                regime = 'unknown'
                if segments:
                    regime = tag_trade_by_regime(entry_time, segments)
                
                trade_dict = {
                    'entry_time': str(entry_time),
                    'exit_time': str(exit_time),
                    'direction': str(trade.get('Direction', 'Long')),
                    'size': float(trade.get('Size', 0)),
                    'entry_price': float(trade.get('Avg Entry Price', 0)),
                    'exit_price': float(trade.get('Avg Exit Price', 0)),
                    'pnl': float(trade.get('PnL', 0)),
                    'pnl_pct': float(trade.get('Return', 0) * 100),  # Convert to percentage
                    'regime': regime,
                }
                
                # Calculate duration
                if entry_time and exit_time:
                    duration_hours = (exit_time - entry_time).total_seconds() / 3600.0
                    trade_dict['duration_hours'] = duration_hours
                
                trades_list.append(trade_dict)
    except Exception as e:
        # Log but don't fail - trades are optional
        import sys
        sys.stderr.write(f"Warning: Could not extract trades: {e}\n")
    
    # Build result
    return {
        'chart': chart_name,
        'fold_id': trial_data.get('fold_id', 'N/A'),
        'val_start': str(trial_data.get('val_start', '')),
        'val_end': str(trial_data.get('val_end', '')),
        'bars_train': int(trial_data.get('bars_train', 0)),
        'bars_embargo': int(trial_data.get('bars_embargo', 0)),
        'bars_val': int(trial_data.get('bars_val', 0)),
        'start_capital': float(stats.get('Start Value', capital)),
        'end_capital': float(stats.get('End Value', capital)),
        'total_return': float(stats.get('Total Return [%]', 0)),
        'sharpe_ratio': float(stats.get('Sharpe Ratio', 0)),
        'sortino_ratio': float(stats.get('Sortino Ratio', 0)),
        'calmar_ratio': float(stats.get('Calmar Ratio', 0)),
        'max_drawdown': float(stats.get('Max Drawdown [%]', 0)),
        'total_trades': int(stats.get('Total Trades', 0)),
        'win_rate': float(stats.get('Win Rate [%]', 0)),
        'profit_factor': float(stats.get('Profit Factor', 0)),
        'expectancy': float(stats.get('Expectancy', 0)),
        'trades': trades_list,
        'chart_analysis_available': chart_analysis is not None,
    }


def calculate_regime_breakdown(trades: List[Dict], chart_analysis: Optional[Dict]) -> Dict:
    """Calculate performance metrics per regime."""
    if not trades:
        sys.stderr.write(f"No trades to analyze for regime breakdown\n")
        return {}
    if not chart_analysis:
        sys.stderr.write(f"No chart analysis available for regime breakdown\n")
        return {}
    
    sys.stderr.write(f"Analyzing {len(trades)} trades for regime breakdown\n")
    
    # Get regime distribution from chart analysis
    summary = chart_analysis.get('summary', {})
    trend_dist = summary.get('trend_distribution', {})
    vol_dist = summary.get('vol_distribution', {})
    
    # Group trades by regime
    regime_trades = {}
    for trade in trades:
        regime = trade.get('regime', 'unknown')
        if regime not in regime_trades:
            regime_trades[regime] = []
        regime_trades[regime].append(trade)
    
    # Calculate metrics per regime
    regime_breakdown = {}
    for regime, regime_trade_list in regime_trades.items():
        winning_trades = [t for t in regime_trade_list if t['pnl'] > 0]
        losing_trades = [t for t in regime_trade_list if t['pnl'] <= 0]
        
        total_pnl = sum(t['pnl'] for t in regime_trade_list)
        win_rate = (len(winning_trades) / len(regime_trade_list) * 100) if regime_trade_list else 0
        avg_pnl = total_pnl / len(regime_trade_list) if regime_trade_list else 0
        
        # Sort trades by PnL
        sorted_trades = sorted(regime_trade_list, key=lambda t: t['pnl'], reverse=True)
        
        regime_breakdown[regime] = {
            'trade_count': len(regime_trade_list),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'top_3_trades': sorted_trades[:3],
            'worst_3_trades': sorted_trades[-3:] if len(sorted_trades) >= 3 else sorted_trades,
        }
    
    return regime_breakdown


def generate_report(trial_uid: str, trial_data: Dict, result: Dict, 
                   regime_breakdown: Dict, config: Dict) -> str:
    """Generate human-readable regime analysis report."""
    lines = []
    
    lines.append("="*80)
    lines.append("REGIME PERFORMANCE ANALYSIS")
    lines.append("="*80)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Trial UID: {trial_uid}")
    lines.append(f"Chart: {result['chart']}")
    lines.append(f"Fold: {result['fold_id']}")
    lines.append("")
    lines.append(f"Backtest Configuration:")
    lines.append(f"  Capital: ${config['capital']:,.2f}")
    lines.append(f"  Fees: {config['fees']*100:.3f}%")
    lines.append(f"  Max Positions: {config['max_positions']}")
    lines.append("")
    
    # Overall metrics
    lines.append("-"*80)
    lines.append("OVERALL PERFORMANCE")
    lines.append("-"*80)
    lines.append(f"  Total Return: {result['total_return']:.2f}%")
    lines.append(f"  Sharpe Ratio: {result['sharpe_ratio']:.4f}")
    lines.append(f"  Sortino Ratio: {result['sortino_ratio']:.4f}")
    lines.append(f"  Calmar Ratio: {result['calmar_ratio']:.4f}")
    lines.append(f"  Max Drawdown: {result['max_drawdown']:.2f}%")
    lines.append(f"  Total Trades: {result['total_trades']}")
    lines.append(f"  Win Rate: {result['win_rate']:.2f}%")
    lines.append(f"  Profit Factor: {result['profit_factor']:.2f}")
    lines.append("")
    
    # Regime breakdown
    if regime_breakdown:
        lines.append("-"*80)
        lines.append("BREAKDOWN BY REGIME")
        lines.append("-"*80)
        
        # Sort regimes by trade count
        sorted_regimes = sorted(regime_breakdown.items(), 
                               key=lambda x: x[1]['trade_count'], 
                               reverse=True)
        
        for regime, metrics in sorted_regimes:
            pct_of_trades = (metrics['trade_count'] / result['total_trades'] * 100) if result['total_trades'] > 0 else 0
            
            lines.append(f"\n{regime.upper()}:")
            lines.append(f"  Trades: {metrics['trade_count']} ({pct_of_trades:.1f}% of total)")
            lines.append(f"  Winners: {metrics['winning_trades']} | Losers: {metrics['losing_trades']}")
            lines.append(f"  Win Rate: {metrics['win_rate']:.2f}%")
            lines.append(f"  Total PnL: ${metrics['total_pnl']:.2f}")
            lines.append(f"  Avg PnL/trade: ${metrics['avg_pnl']:.2f}")
            
            # Top 3 trades
            if metrics['top_3_trades']:
                lines.append(f"  Top 3 Trades:")
                for i, trade in enumerate(metrics['top_3_trades'], 1):
                    lines.append(f"    {i}. ${trade['pnl']:.2f} ({trade['pnl_pct']:.2f}%) | "
                               f"{trade['direction']} | Entry: {trade['entry_time']}")
            
            # Worst 3 trades
            if metrics['worst_3_trades']:
                lines.append(f"  Worst 3 Trades:")
                for i, trade in enumerate(metrics['worst_3_trades'], 1):
                    lines.append(f"    {i}. ${trade['pnl']:.2f} ({trade['pnl_pct']:.2f}%) | "
                               f"{trade['direction']} | Entry: {trade['entry_time']}")
    else:
        lines.append("-"*80)
        lines.append("REGIME BREAKDOWN: Not Available")
        lines.append("-"*80)
        lines.append("Chart analysis file not found. Run chart analyzer first:")
        lines.append(f"  python scripts/chart_analyzer.py --chart {result['chart']} --save-analysis")
        lines.append("")
    
    lines.append("")
    lines.append("="*80)
    lines.append("END OF REPORT")
    lines.append("="*80)
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='Regime-based performance analysis')
    parser.add_argument('--uid', required=True, help='Trial UID (e.g., 20251018_112307:28)')
    parser.add_argument('--capital', type=float, default=10000, help='Starting capital')
    parser.add_argument('--fees', type=float, default=0.001, help='Fees as decimal (e.g., 0.001 = 0.1%%)')
    parser.add_argument('--max-positions', type=int, default=3, help='Max concurrent positions')
    parser.add_argument('--run-json', type=str, default=None, help='Path to run JSON file (optional)')
    
    args = parser.parse_args()
    
    try:
        # Load trial data
        trial_data, run_json_path = load_trial_by_uid(args.uid, args.run_json)
        
        # Extract parameters
        params = extract_params(trial_data)
        
        # Load chart analysis
        chart_name = trial_data.get('chart', '')
        chart_analysis = load_chart_analysis(chart_name)
        
        # Run backtest with regime tagging
        config = {
            'capital': args.capital,
            'fees': args.fees,
            'max_positions': args.max_positions,
        }
        
        result = run_backtest_with_regime_tagging(
            trial_data, params, args.capital, args.fees, args.max_positions, chart_analysis
        )
        
        # Calculate regime breakdown
        sys.stderr.write(f"Result has {len(result['trades'])} trades\n")
        sys.stderr.write(f"Chart analysis available: {chart_analysis is not None}\n")
        regime_breakdown = calculate_regime_breakdown(result['trades'], chart_analysis)
        
        # Generate text report
        report_text = generate_report(args.uid, trial_data, result, regime_breakdown, config)
        
        # Build JSON output
        output = {
            'success': True,
            'meta': {
                'trial_uid': args.uid,
                'chart': result['chart'],
                'fold_id': result['fold_id'],
                'capital': args.capital,
                'fees': args.fees,
                'max_positions': args.max_positions,
            },
            'overall_performance': {
                'total_return': result['total_return'],
                'sharpe_ratio': result['sharpe_ratio'],
                'sortino_ratio': result['sortino_ratio'],
                'calmar_ratio': result['calmar_ratio'],
                'max_drawdown': result['max_drawdown'],
                'total_trades': result['total_trades'],
                'win_rate': result['win_rate'],
                'profit_factor': result['profit_factor'],
            },
            'regime_breakdown': regime_breakdown,
            'report_text': report_text,
            'chart_analysis_available': result['chart_analysis_available'],
        }
        
        # Output JSON to stdout
        print(json.dumps(output, indent=2))
        
    except Exception as e:
        # Output error JSON
        error_output = {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__,
        }
        print(json.dumps(error_output, indent=2))
        sys.exit(1)


if __name__ == '__main__':
    main()

