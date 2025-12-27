import pandas as pd
from src.io.data_loader import load_first_chart
from src.strategy.bands import compute_signals
from src.engine.backtest import run_backtest
from config.user_inputs import BACKTEST_CONFIG as USER_BACKTEST_CONFIG, TOGGLES
from config.strategy_params import BASELINE_PARAMS


def main():
    price = load_first_chart()
    entries, exits, _ = compute_signals(price, BASELINE_PARAMS, TOGGLES)
    pf = run_backtest(price, entries, exits, backtest_overrides=USER_BACKTEST_CONFIG)
    stats = pf.stats()
    subset = {k: stats.get(k) for k in [
        'Total Return [%]','Sharpe Ratio','Sortino Ratio','Calmar Ratio','Max Drawdown [%]','Total Trades']}
    print("\n=== Baseline Backtest (simple) ===")
    for k,v in subset.items():
        print(f"{k}: {v}")


if __name__ == '__main__':
    main()


