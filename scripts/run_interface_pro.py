#!/usr/bin/env python3
"""
Professional Quantitative Trading Interface

Features:
- Advanced strategy analysis and filtering
- Risk-adjusted performance metrics
- Market regime analysis
- Strategy correlation analysis
- MQL5/MT5 integration preparation
- Professional reporting and export
"""
import os
import sys
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
import warnings

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.io.data_loader import list_active_chart_paths, load_chart_from_path


class QuantAnalyzer:
    """Professional quantitative analysis tools."""
    
    def __init__(self, results_dir: str = None):
        self.results_dir = results_dir or os.path.join(os.path.dirname(__file__), '..', 'outputs')
        self.runs_dir = os.path.join(self.results_dir, 'runs')
        self.notebooks_dir = os.path.join(self.results_dir, 'notebooks')
    
    def list_available_runs(self) -> List[Dict]:
        """List all optimization runs with metadata."""
        if not os.path.exists(self.runs_dir):
            return []
        
        runs = []
        for filename in sorted(os.listdir(self.runs_dir), reverse=True):
            if filename.lower().endswith('.json'):
                try:
                    filepath = os.path.join(self.runs_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    metadata = data.get('metadata', {})
                    results = data.get('results', [])
                    
                    if results:
                        df = pd.DataFrame(results)
                        
                        # Calculate advanced statistics
                        stats = self._calculate_run_statistics(df)
                        
                        runs.append({
                            'filename': filename,
                            'run_id': metadata.get('run_id', 'unknown'),
                            'method': metadata.get('method', 'unknown'),
                            'timestamp': metadata.get('timestamp', ''),
                            'trials_count': len(results),
                            'charts': metadata.get('charts', []),
                            'best_metrics': metadata.get('best', {}),
                            'advanced_stats': stats,
                            'data': data
                        })
                except Exception:
                    continue
        
        return runs
    
    def _calculate_run_statistics(self, df: pd.DataFrame) -> Dict:
        """Calculate advanced statistics for a run."""
        stats = {}
        
        # Basic statistics
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in ['total_return', 'sharpe_ratio', 'sortino_ratio', 'calmar_robust', 'max_drawdown']:
            if col in numeric_cols:
                values = df[col].dropna()
                if len(values) > 0:
                    stats[f'{col}_mean'] = values.mean()
                    stats[f'{col}_std'] = values.std()
                    stats[f'{col}_min'] = values.min()
                    stats[f'{col}_max'] = values.max()
                    stats[f'{col}_q75'] = values.quantile(0.75)
                    stats[f'{col}_q25'] = values.quantile(0.25)
        
        # Risk-adjusted metrics
        if 'total_return' in df.columns and 'max_drawdown' in df.columns:
            returns = df['total_return'].dropna()
            drawdowns = df['max_drawdown'].dropna()
            if len(returns) > 0 and len(drawdowns) > 0:
                stats['return_to_dd_ratio'] = returns.mean() / drawdowns.mean() if drawdowns.mean() > 0 else 0
        
        # Consistency metrics
        if 'sharpe_ratio' in df.columns:
            sharpe_values = df['sharpe_ratio'].dropna()
            if len(sharpe_values) > 0:
                stats['sharpe_consistency'] = len(sharpe_values[sharpe_values > 1.0]) / len(sharpe_values)
                stats['sharpe_above_2'] = len(sharpe_values[sharpe_values > 2.0]) / len(sharpe_values)
        
        # Strategy diversity
        if 'chart' in df.columns:
            stats['charts_tested'] = df['chart'].nunique()
            chart_performance = df.groupby('chart')['total_return'].mean()
            stats['chart_consistency'] = chart_performance.std() if len(chart_performance) > 1 else 0
        
        return stats
    
    def analyze_strategy_performance(self, trial_uid: str, run_data: Dict) -> Dict:
        """Detailed analysis of a specific strategy."""
        results = run_data['data'].get('results', [])
        df = pd.DataFrame(results)
        
        strategy_rows = df[df['trial_uid'] == trial_uid]
        if len(strategy_rows) == 0:
            return {}
        
        # Multi-chart analysis
        analysis = {
            'trial_uid': trial_uid,
            'charts_tested': len(strategy_rows),
            'performance_by_chart': {},
            'risk_metrics': {},
            'consistency_metrics': {},
            'parameter_analysis': {}
        }
        
        # Performance by chart
        for _, row in strategy_rows.iterrows():
            chart = row.get('chart', 'unknown')
            analysis['performance_by_chart'][chart] = {
                'total_return': row.get('total_return', 0),
                'sharpe_ratio': row.get('sharpe_ratio', 0),
                'max_drawdown': row.get('max_drawdown', 0),
                'total_trades': row.get('total_trades', 0),
                'win_rate': row.get('win_rate', 0),
                'profit_factor': row.get('profit_factor', 0)
            }
        
        # Aggregate risk metrics
        returns = [row.get('total_return', 0) for _, row in strategy_rows.iterrows()]
        sharpe_ratios = [row.get('sharpe_ratio', 0) for _, row in strategy_rows.iterrows()]
        drawdowns = [row.get('max_drawdown', 0) for _, row in strategy_rows.iterrows()]
        
        analysis['risk_metrics'] = {
            'avg_return': np.mean(returns),
            'return_volatility': np.std(returns),
            'avg_sharpe': np.mean(sharpe_ratios),
            'sharpe_consistency': np.std(sharpe_ratios),
            'worst_drawdown': max(drawdowns) if drawdowns else 0,
            'avg_drawdown': np.mean(drawdowns),
            'return_to_risk_ratio': np.mean(returns) / np.mean(drawdowns) if np.mean(drawdowns) > 0 else 0
        }
        
        # Extract parameters
        first_row = strategy_rows.iloc[0]
        params = {}
        for k, v in first_row.items():
            if isinstance(k, str) and k.startswith('param_'):
                params[k.replace('param_', '')] = v
        analysis['parameter_analysis'] = params
        
        return analysis
    
    def find_robust_strategies(self, runs: List[Dict], min_sharpe: float = 1.5, 
                             min_charts: int = 3, max_drawdown: float = 10.0) -> List[Dict]:
        """Find strategies that perform well across multiple charts."""
        robust_strategies = []
        
        for run in runs:
            results = run['data'].get('results', [])
            df = pd.DataFrame(results)
            
            if 'trial_uid' not in df.columns:
                continue
            
            # Group by trial_uid to analyze multi-chart performance
            for uid, group in df.groupby('trial_uid'):
                if len(group) < min_charts:
                    continue
                
                # Check performance criteria
                avg_sharpe = group['sharpe_ratio'].mean() if 'sharpe_ratio' in group.columns else 0
                max_dd = group['max_drawdown'].max() if 'max_drawdown' in group.columns else float('inf')
                min_return = group['total_return'].min() if 'total_return' in group.columns else -float('inf')
                
                if avg_sharpe >= min_sharpe and max_dd <= max_drawdown and min_return > 0:
                    robust_strategies.append({
                        'trial_uid': uid,
                        'run_id': run['run_id'],
                        'charts_tested': len(group),
                        'avg_sharpe': avg_sharpe,
                        'avg_return': group['total_return'].mean() if 'total_return' in group.columns else 0,
                        'worst_return': min_return,
                        'max_drawdown': max_dd,
                        'consistency_score': avg_sharpe * (1 - group['sharpe_ratio'].std() / avg_sharpe) if avg_sharpe > 0 else 0
                    })
        
        # Sort by consistency score
        robust_strategies.sort(key=lambda x: x['consistency_score'], reverse=True)
        return robust_strategies
    
    def analyze_parameter_sensitivity(self, run_data: Dict) -> Dict:
        """Analyze parameter sensitivity and optimal ranges."""
        results = run_data['data'].get('results', [])
        df = pd.DataFrame(results)
        
        param_cols = [col for col in df.columns if col.startswith('param_')]
        if not param_cols or 'total_return' not in df.columns:
            return {}
        
        sensitivity_analysis = {}
        
        for param_col in param_cols:
            param_name = param_col.replace('param_', '')
            
            # Group by parameter value and calculate statistics
            param_groups = df.groupby(param_col)['total_return'].agg([
                'mean', 'std', 'count', 'min', 'max'
            ]).reset_index()
            
            if len(param_groups) > 1:
                # Find optimal range
                best_values = param_groups.nlargest(3, 'mean')[param_col].tolist()
                worst_values = param_groups.nsmallest(3, 'mean')[param_col].tolist()
                
                sensitivity_analysis[param_name] = {
                    'optimal_values': best_values,
                    'worst_values': worst_values,
                    'value_range': [param_groups[param_col].min(), param_groups[param_col].max()],
                    'performance_variance': param_groups['mean'].std(),
                    'sensitivity_score': param_groups['mean'].std() / param_groups['mean'].mean() if param_groups['mean'].mean() > 0 else 0
                }
        
        return sensitivity_analysis
    
    def generate_mql5_analysis_report(self, strategy_analysis: Dict) -> str:
        """Generate MQL5-focused analysis report."""
        report = []
        report.append("//+------------------------------------------------------------------+")
        report.append("//|                    Strategy Analysis Report                       |")
        report.append("//|                     Generated by QuantAnalyzer                   |")
        report.append("//+------------------------------------------------------------------+")
        report.append("")
        
        # Strategy overview
        uid = strategy_analysis.get('trial_uid', 'Unknown')
        report.append(f"// Strategy UID: {uid}")
        report.append(f"// Charts Tested: {strategy_analysis.get('charts_tested', 0)}")
        report.append("")
        
        # Risk metrics
        risk_metrics = strategy_analysis.get('risk_metrics', {})
        report.append("// === RISK ANALYSIS ===")
        report.append(f"// Average Return: {risk_metrics.get('avg_return', 0):.2f}%")
        report.append(f"// Return Volatility: {risk_metrics.get('return_volatility', 0):.2f}%")
        report.append(f"// Average Sharpe: {risk_metrics.get('avg_sharpe', 0):.2f}")
        report.append(f"// Worst Drawdown: {risk_metrics.get('worst_drawdown', 0):.2f}%")
        report.append(f"// Return/Risk Ratio: {risk_metrics.get('return_to_risk_ratio', 0):.2f}")
        report.append("")
        
        # Parameters for MQL5 implementation
        params = strategy_analysis.get('parameter_analysis', {})
        if params:
            report.append("// === OPTIMAL PARAMETERS FOR MQL5 ===")
            for param, value in params.items():
                report.append(f"input {self._get_mql5_type(value)} {param} = {value}; // Optimized value")
        
        report.append("")
        report.append("// === IMPLEMENTATION NOTES ===")
        report.append("// - Test on multiple currency pairs for robustness")
        report.append("// - Consider spread and slippage in live trading")
        report.append("// - Monitor performance degradation over time")
        report.append("// - Implement proper risk management")
        
        return "\n".join(report)
    
    def _get_mql5_type(self, value) -> str:
        """Get appropriate MQL5 input type for a parameter value."""
        if isinstance(value, bool):
            return "bool"
        elif isinstance(value, int):
            return "int"
        elif isinstance(value, float):
            return "double"
        else:
            return "string"


def main():
    """Main professional interface."""
    analyzer = QuantAnalyzer()
    
    print("🏦 PROFESSIONAL QUANTITATIVE TRADING INTERFACE")
    print("=" * 80)
    print("Advanced Strategy Analysis & MQL5 Integration Tools")
    print()
    
    while True:
        print("📊 MAIN MENU:")
        print("1. Strategy Performance Analysis")
        print("2. Robust Strategy Scanner")
        print("3. Parameter Sensitivity Analysis") 
        print("4. Chart Analyzer & Splicing")
        print("5. Market Regime Analysis")
        print("6. MQL5 Integration Tools")
        print("7. Advanced Filtering & Search")
        print("8. Export Professional Reports")
        print("9. Risk Management Analysis")
        print("0. Exit")
        print()
        
        choice = input("Select option (1-9): ").strip()
        
        if choice == '1':
            strategy_analysis_menu(analyzer)
        elif choice == '2':
            robust_strategy_scanner(analyzer)
        elif choice == '3':
            parameter_sensitivity_menu(analyzer)
        elif choice == '4':
            chart_analyzer_menu()
        elif choice == '5':
            market_regime_analysis(analyzer)
        elif choice == '6':
            mql5_integration_menu(analyzer)
        elif choice == '7':
            advanced_search_menu(analyzer)
        elif choice == '8':
            export_reports_menu(analyzer)
        elif choice == '9':
            risk_management_menu(analyzer)
        elif choice == '0':
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")
        
        print("\n" + "="*80 + "\n")


def strategy_analysis_menu(analyzer: QuantAnalyzer):
    """Strategy performance analysis menu."""
    print("\n📈 STRATEGY PERFORMANCE ANALYSIS")
    print("-" * 50)
    
    runs = analyzer.list_available_runs()
    if not runs:
        print("No optimization runs found.")
        return
    
    # Show recent runs
    print("Recent optimization runs:")
    for i, run in enumerate(runs[:5], 1):
        stats = run['advanced_stats']
        best = run['best_metrics']
        print(f"{i}. {run['run_id']} | {run['method'].upper()} | {run['trials_count']} trials")
        print(f"   Best Return: {best.get('total_return', 0):.2f}% | Avg Sharpe: {stats.get('sharpe_ratio_mean', 0):.2f}")
    
    try:
        run_choice = int(input(f"\nSelect run (1-{min(5, len(runs))}): ")) - 1
        if 0 <= run_choice < len(runs):
            selected_run = runs[run_choice]
            
            # Show top strategies from this run
            results = selected_run['data'].get('results', [])
            df = pd.DataFrame(results)
            
            # Enhanced metric selection
            metrics = [
                ('total_return', 'Total Return %'),
                ('sharpe_ratio', 'Sharpe Ratio'), 
                ('sortino_ratio', 'Sortino Ratio'),
                ('calmar_robust', 'Calmar Ratio (Robust)'),
                ('profit_factor', 'Profit Factor'),
                ('win_rate', 'Win Rate %')
            ]
            
            print(f"\nAvailable metrics for {selected_run['run_id']}:")
            for i, (key, name) in enumerate(metrics, 1):
                if key in df.columns:
                    print(f"{i}. {name}")
            
            metric_choice = int(input("Select metric: ")) - 1
            if 0 <= metric_choice < len(metrics):
                metric_key, metric_name = metrics[metric_choice]
                
                if metric_key in df.columns:
                    top_strategies = df.nlargest(10, metric_key)
                    
                    print(f"\n🏆 TOP 10 STRATEGIES BY {metric_name.upper()}")
                    print("-" * 80)
                    
                    for i, (_, row) in enumerate(top_strategies.iterrows(), 1):
                        uid = row.get('trial_uid', 'N/A')
                        chart = row.get('chart', 'N/A')
                        value = row.get(metric_key, 0)
                        sharpe = row.get('sharpe_ratio', 0)
                        dd = row.get('max_drawdown', 0)
                        
                        print(f"{i:2d}. {uid} | {chart[:20]:20} | {metric_name}: {value:7.2f} | Sharpe: {sharpe:5.2f} | DD: {dd:5.2f}%")
                    
                    # Detailed analysis option
                    detail_choice = input(f"\nAnalyze strategy in detail? (enter row number or 'n'): ").strip()
                    if detail_choice.isdigit():
                        row_idx = int(detail_choice) - 1
                        if 0 <= row_idx < len(top_strategies):
                            strategy_uid = top_strategies.iloc[row_idx]['trial_uid']
                            detailed_analysis = analyzer.analyze_strategy_performance(strategy_uid, selected_run)
                            display_detailed_analysis(detailed_analysis)
                
    except (ValueError, IndexError):
        print("Invalid selection.")


def robust_strategy_scanner(analyzer: QuantAnalyzer):
    """Scan for robust strategies across multiple runs."""
    print("\n🛡️  ROBUST STRATEGY SCANNER")
    print("-" * 50)
    
    runs = analyzer.list_available_runs()
    if not runs:
        print("No optimization runs found.")
        return
    
    print("Scanning for strategies with consistent performance across multiple charts...")
    
    # Get user criteria
    try:
        min_sharpe = float(input("Minimum average Sharpe ratio [1.5]: ") or "1.5")
        min_charts = int(input("Minimum number of charts tested [3]: ") or "3")
        max_drawdown = float(input("Maximum drawdown % [10.0]: ") or "10.0")
    except ValueError:
        print("Invalid input. Using defaults.")
        min_sharpe, min_charts, max_drawdown = 1.5, 3, 10.0
    
    robust_strategies = analyzer.find_robust_strategies(runs, min_sharpe, min_charts, max_drawdown)
    
    if robust_strategies:
        print(f"\n🎯 FOUND {len(robust_strategies)} ROBUST STRATEGIES")
        print("-" * 80)
        print(f"{'Rank':4} {'UID':25} {'Run ID':15} {'Charts':7} {'Avg Sharpe':10} {'Avg Return':10} {'Worst Return':12} {'Max DD':8} {'Score':8}")
        print("-" * 80)
        
        for i, strategy in enumerate(robust_strategies[:20], 1):
            print(f"{i:4d} {strategy['trial_uid'][:24]:25} {strategy['run_id'][:14]:15} "
                  f"{strategy['charts_tested']:7d} {strategy['avg_sharpe']:10.2f} "
                  f"{strategy['avg_return']:9.2f}% {strategy['worst_return']:11.2f}% "
                  f"{strategy['max_drawdown']:7.2f}% {strategy['consistency_score']:8.3f}")
    else:
        print("No strategies found matching the criteria.")


def parameter_sensitivity_menu(analyzer: QuantAnalyzer):
    """Parameter sensitivity analysis."""
    print("\n🔧 PARAMETER SENSITIVITY ANALYSIS")
    print("-" * 50)
    
    runs = analyzer.list_available_runs()
    if not runs:
        print("No optimization runs found.")
        return
    
    # Show recent runs
    for i, run in enumerate(runs[:5], 1):
        print(f"{i}. {run['run_id']} | {run['trials_count']} trials")
    
    try:
        run_choice = int(input(f"Select run (1-{min(5, len(runs))}): ")) - 1
        if 0 <= run_choice < len(runs):
            selected_run = runs[run_choice]
            
            print(f"\nAnalyzing parameter sensitivity for {selected_run['run_id']}...")
            sensitivity = analyzer.analyze_parameter_sensitivity(selected_run)
            
            if sensitivity:
                print(f"\n📊 PARAMETER SENSITIVITY RESULTS")
                print("-" * 80)
                
                for param, data in sensitivity.items():
                    print(f"\n{param.upper()}:")
                    print(f"  Optimal values: {data['optimal_values']}")
                    print(f"  Worst values: {data['worst_values']}")
                    print(f"  Value range: {data['value_range']}")
                    print(f"  Sensitivity score: {data['sensitivity_score']:.3f}")
                    
                    if data['sensitivity_score'] > 0.5:
                        print(f"  ⚠️  HIGH SENSITIVITY - Parameter significantly affects performance")
                    elif data['sensitivity_score'] < 0.1:
                        print(f"  ✅ LOW SENSITIVITY - Parameter has stable performance")
            else:
                print("No parameter sensitivity data available.")
                
    except (ValueError, IndexError):
        print("Invalid selection.")


def market_regime_analysis(analyzer: QuantAnalyzer):
    """Analyze strategy performance across different market regimes."""
    print("\n📈 MARKET REGIME ANALYSIS")
    print("-" * 50)
    print("Feature coming soon: Analysis of strategy performance in different market conditions")
    print("- Bull/Bear market performance")
    print("- Volatility regime adaptation") 
    print("- Correlation with market indicators")
    print("- Seasonal performance patterns")


def chart_analyzer_menu():
    """Interactive wrapper around scripts/chart_analyzer.py"""
    print("\n🧪 CHART ANALYZER & SPLICING")
    print("-" * 50)
    try:
        chart = input("Chart path (leave blank to use first in active_charts): ").strip()
        equal_parts = input("Equal parts (blank to skip): ").strip()
        by_regime = input("Slice by detected regimes? [y/N]: ").strip().lower() == 'y'
        momentum_len = int(input("Momentum length [20]: ") or "20")
        vol_len = int(input("Volatility window [20]: ") or "20")
        trend_thr = float(input("Trend threshold [0.0]: ") or "0.0")
        use_mcg = input("Use McGinley-based trend? [Y/n]: ").strip().lower() != 'n'
        hma_len = int(input("HMA proxy length [20]: ") or "20")
        hysteresis = int(input("Hysteresis bars [2]: ") or "2")
        custom = input("Custom ranges (YYYY-MM-DD:YYYY-MM-DD, ... or blank): ").strip()

        cmd = [sys.executable, os.path.join(os.path.dirname(__file__), 'chart_analyzer.py')]
        if chart:
            cmd += ['--chart', chart]
        if equal_parts:
            try:
                int(equal_parts)
                cmd += ['--equal-parts', equal_parts]
            except Exception:
                pass
        if by_regime:
            cmd += ['--by-regime']
        if not use_mcg:
            cmd += ['--no-mcg']
        if custom:
            cmd += ['--custom', custom]
        cmd += ['--momentum-len', str(momentum_len), '--vol-len', str(vol_len), '--trend-threshold', str(trend_thr), '--hma-len', str(hma_len), '--hysteresis', str(hysteresis)]

        print("\nRunning:")
        print(' '.join(cmd))
        os.system(' '.join(cmd))
    except Exception as e:
        print(f"Error: {e}")


def mql5_integration_menu(analyzer: QuantAnalyzer):
    """MQL5 integration and code generation tools."""
    print("\n💻 MQL5 INTEGRATION TOOLS")
    print("-" * 50)
    
    print("1. Generate MQL5 Expert Advisor from strategy")
    print("2. Create MQL5 parameter optimization ranges")
    print("3. Export strategy for MetaTrader 5 backtesting")
    print("4. Generate risk management code")
    print("5. Create position sizing calculator")
    
    choice = input("Select option (1-5): ").strip()
    
    if choice == '1':
        print("🔄 MQL5 EA Generation will be integrated with the code generator.")
        print("This will allow generating both PineScript and MQL5 code from the same strategy.")
    else:
        print("Feature coming soon!")


def advanced_search_menu(analyzer: QuantAnalyzer):
    """Advanced filtering and search capabilities."""
    print("\n🔍 ADVANCED SEARCH & FILTERING")
    print("-" * 50)
    
    print("1. Query results by performance and portfolio conditions")
    print("2. Feature coming soon: Multi-metric filtering")
    print("3. Feature coming soon: Parameter range filtering") 
    print("4. Feature coming soon: Chart-specific performance")
    print("5. Feature coming soon: Time-based analysis")
    print("6. Feature coming soon: Custom scoring functions")
    print("0. Back to Main Menu")
    
    choice = input("Select option (0-6): ").strip()
    
    if choice == '1':
        run_advanced_query_interactive()
    elif choice == '0':
        return
    else:
        print("Invalid choice or feature not yet implemented. Please try again.")


def run_advanced_query_interactive():
    """Interactive wrapper for scripts/query_advanced.py"""
    print("\n🚀 RUN ADVANCED RESULTS QUERY")
    print("-" * 50)
    
    try:
        source_path = input("Path to results (e.g., outputs/notebooks/optimizer_central.xlsx) [outputs/notebooks/optimizer_central.xlsx]: ").strip()
        if not source_path: source_path = os.path.join('outputs', 'notebooks', 'optimizer_central.xlsx')

        charts = input("Comma-separated chart names (e.g., BingX_ETHUSDT_2h.csv, BingX_Gold_1d.csv or blank for all): ").strip()
        min_return = input("Minimum total return %% (e.g., 10.0 for 10%% or blank for 0.0): ").strip()
        fees = input("Exact fee value (e.g., 0.00045 or blank for any): ").strip()
        size_pct = input("Exact position size %% (e.g., 0.30 or blank for any): ").strip()
        init_capital = input("Exact starting capital (e.g., 500.0 or blank for any): ").strip()
        top_n = input("Number of top results to display [20]: ").strip()
        export_path = input("Optional path to export filtered results to CSV (e.g., filtered_strategies.csv or blank to skip): ").strip()

        cmd = [sys.executable, os.path.join(os.path.dirname(__file__), 'query_advanced.py'), '--source', source_path]
        if charts: cmd += ['--charts', charts]
        if min_return: cmd += ['--min-return', min_return]
        if fees: cmd += ['--fees', fees]
        if size_pct: cmd += ['--size-pct', size_pct]
        if init_capital: cmd += ['--init-capital', init_capital]
        if top_n: cmd += ['--top', top_n]
        if export_path: cmd += ['--export', export_path]

        print("\nRunning advanced query:")
        print(' '.join(cmd))
        os.system(' '.join(cmd))
    except Exception as e:
        print(f"Error running advanced query: {e}")


def export_reports_menu(analyzer: QuantAnalyzer):
    """Export professional reports."""
    print("\n📄 EXPORT PROFESSIONAL REPORTS")
    print("-" * 50)
    print("Feature coming soon: Professional report generation")
    print("- PDF strategy analysis reports")
    print("- Excel performance dashboards")
    print("- LaTeX academic papers")
    print("- HTML interactive reports")


def risk_management_menu(analyzer: QuantAnalyzer):
    """Risk management analysis tools."""
    print("\n⚠️  RISK MANAGEMENT ANALYSIS")
    print("-" * 50)
    print("Feature coming soon: Advanced risk analysis")
    print("- Value at Risk (VaR) calculations")
    print("- Expected Shortfall analysis")
    print("- Correlation analysis")
    print("- Portfolio optimization")
    print("- Stress testing scenarios")


def display_detailed_analysis(analysis: Dict):
    """Display detailed strategy analysis."""
    print(f"\n🔬 DETAILED ANALYSIS: {analysis.get('trial_uid', 'Unknown')}")
    print("=" * 80)
    
    # Performance by chart
    print("📊 PERFORMANCE BY CHART:")
    perf_by_chart = analysis.get('performance_by_chart', {})
    for chart, metrics in perf_by_chart.items():
        print(f"  {chart[:30]:30} | Return: {metrics.get('total_return', 0):7.2f}% | "
              f"Sharpe: {metrics.get('sharpe_ratio', 0):5.2f} | DD: {metrics.get('max_drawdown', 0):5.2f}%")
    
    # Risk metrics
    print(f"\n⚠️  RISK ANALYSIS:")
    risk = analysis.get('risk_metrics', {})
    print(f"  Average Return: {risk.get('avg_return', 0):7.2f}%")
    print(f"  Return Volatility: {risk.get('return_volatility', 0):7.2f}%")
    print(f"  Average Sharpe: {risk.get('avg_sharpe', 0):7.2f}")
    print(f"  Worst Drawdown: {risk.get('worst_drawdown', 0):7.2f}%")
    print(f"  Return/Risk Ratio: {risk.get('return_to_risk_ratio', 0):7.2f}")
    
    # Parameters
    print(f"\n🔧 STRATEGY PARAMETERS:")
    params = analysis.get('parameter_analysis', {})
    for param, value in params.items():
        print(f"  {param}: {value}")


if __name__ == '__main__':
    main()
