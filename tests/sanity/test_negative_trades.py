import pytest

from tests.sanity.utils import run_single_backtest
from config.user_inputs import TOGGLES


@pytest.mark.sanity
def test_negative_trades_present(price_df, sample_params):
    """Ensure at least one losing trade exists in a non-trivial run."""
    row, trades = run_single_backtest(price_df, sample_params, TOGGLES)
    if trades is None or len(trades) == 0:
        pytest.skip("No trades generated for sample_params; cannot test losses presence")

    # Assume trades DF has PnL column or End-Capital info; fallback simple profit calc
    if 'PnL' in trades.columns:
        losses = (trades['PnL'] < 0).sum()
    elif 'Return' in trades.columns:
        losses = (trades['Return'] < 0).sum()
    else:
        # Compute from Entry/Exit prices if needed
        if {'Entry Price', 'Exit Price'}.issubset(trades.columns):
            ret = trades['Exit Price'] / trades['Entry Price'] - 1.0
            losses = (ret < 0).sum()
        else:
            pytest.skip("Trade DF lacks PnL/Return fields to test negative trades")

    assert losses > 0, "No losing trades detected; result likely unrealistic (PF == ∞)"
