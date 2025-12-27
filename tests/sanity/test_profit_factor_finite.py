import pytest

from tests.sanity.utils import run_single_backtest, calc_profit_factor
from config.user_inputs import TOGGLES


@pytest.mark.sanity
def test_profit_factor_finite(price_df, sample_params):
    """Profit factor should be finite (losses > 0)."""
    _, trades = run_single_backtest(price_df, sample_params, TOGGLES)
    pf = calc_profit_factor(trades)
    assert pf != float("inf"), "Profit factor is infinite (no losses) – unrealistic"
