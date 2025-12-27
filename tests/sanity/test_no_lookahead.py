import pytest
import numpy as np

from tests.sanity.utils import run_single_backtest, calc_basic_metrics
from config.user_inputs import TOGGLES


@pytest.mark.sanity
def test_no_lookahead(price_df, sample_params):
    """Shift signals by +1 bar and ensure performance degrades ≥25 %."""
    # Baseline run
    base_row, _ = run_single_backtest(price_df, sample_params, TOGGLES)
    base_sharpe, base_ret, _ = calc_basic_metrics(base_row)

    # Shift price series by 1 bar forward (simulate lookahead removal)
    shifted_price = price_df.copy().shift(1).dropna()

    shifted_row, _ = run_single_backtest(shifted_price, sample_params, TOGGLES)
    shifted_sharpe, shifted_ret, _ = calc_basic_metrics(shifted_row)

    # Expect degradation ≥25 % on Sharpe OR total return
    degrade_sharpe = (base_sharpe - shifted_sharpe) / abs(base_sharpe or 1)
    degrade_ret = (base_ret - shifted_ret) / abs(base_ret or 1)

    assert degrade_sharpe > 0.25 or degrade_ret > 0.25, (
        "Metrics did not drop after removing potential lookahead. "
        f"Sharpe Δ%={degrade_sharpe:.2%}, Ret Δ%={degrade_ret:.2%}")
