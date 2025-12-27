from src.io.data_loader import load_first_chart
from src.strategy.bands import compute_signals
from src.engine.backtest import run_backtest
from src.validation.report import human_readable_report
from config.user_inputs import TOGGLES, BACKTEST_CONFIG as USER_BACKTEST_CONFIG
from config.strategy_params import BASELINE_PARAMS as BEST_PARAMS


# Example: paste best params here to re-validate
BEST_PARAMS = BEST_PARAMS


def main():
    price = load_first_chart()
    entries, exits, _ = compute_signals(price, BEST_PARAMS, TOGGLES)
    pf = run_backtest(price, entries, exits, backtest_overrides=USER_BACKTEST_CONFIG)
    stats = pf.stats()
    print("\n=== Validation Stats ===")
    print(stats)
    lines = human_readable_report(stats)
    print("\n--- Human-Readable Report ---")
    for line in lines:
        print("-", line)


if __name__ == '__main__':
    main()


