from decimal import Decimal

import pytest

from ai_trader.domain import ExecutionBar
from ai_trader.execution import simulate_from_cash
from ai_trader.fixture import demo_execution_bars, demo_snapshot
from ai_trader.research import deliberate


def test_next_open_execution_accounts_for_fees_and_slippage():
    snapshot = demo_snapshot()
    targets = deliberate(snapshot).target_weights
    result = simulate_from_cash(snapshot, targets, demo_execution_bars())
    assert len(result.fills) == 1
    fill = result.fills[0]
    assert fill.symbol == "DEMO_A" and fill.quantity == 8
    assert fill.timestamp > snapshot.as_of
    assert fill.price == Decimal("101.0505")
    assert fill.fee == Decimal("0.81")
    assert result.remaining_cash == Decimal("9190.79")
    assert result.remaining_cash > 0


def test_same_bar_execution_is_rejected():
    snapshot = demo_snapshot()
    bars = tuple(
        ExecutionBar(symbol=bar.symbol, timestamp=snapshot.as_of, open=bar.open)
        for bar in demo_execution_bars()
    )
    with pytest.raises(ValueError, match="strictly after"):
        simulate_from_cash(snapshot, deliberate(snapshot).target_weights, bars)


def test_all_cash_target_has_no_fees_or_fills():
    snapshot = demo_snapshot()
    result = simulate_from_cash(
        snapshot,
        {row.symbol: Decimal("0") for row in snapshot.observations},
        demo_execution_bars(),
    )
    assert result.fills == ()
    assert result.remaining_cash == result.initial_cash


@pytest.mark.parametrize(
    "kwargs",
    [
        {"initial_cash": Decimal("-1")},
        {"fee_bps": Decimal("-1")},
        {"slippage_bps": Decimal("NaN")},
    ],
)
def test_invalid_execution_settings_fail(kwargs):
    snapshot = demo_snapshot()
    with pytest.raises(ValueError):
        simulate_from_cash(
            snapshot, deliberate(snapshot).target_weights, demo_execution_bars(), **kwargs
        )


def test_missing_or_duplicate_execution_bars_fail():
    snapshot = demo_snapshot()
    bars = demo_execution_bars()
    for invalid in (bars[:1], (bars[0], bars[0])):
        with pytest.raises(ValueError, match="exactly once"):
            simulate_from_cash(snapshot, deliberate(snapshot).target_weights, invalid)
