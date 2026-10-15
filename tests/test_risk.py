from decimal import Decimal

import pytest

from ai_trader.domain import RiskPolicy
from ai_trader.risk import check_targets


@pytest.mark.parametrize(
    "targets,current,kill,reason",
    [
        ({"A": Decimal("0.11")}, {}, False, "position limit"),
        ({"A": Decimal("-0.01")}, {}, False, "short positions"),
        ({"UNKNOWN": Decimal("0.05")}, {}, False, "unknown symbol"),
        ({"A": Decimal("NaN")}, {}, False, "non-finite"),
        ({"A": Decimal("Infinity")}, {}, False, "non-finite"),
        ({"A": Decimal("0.05")}, {"A": Decimal("-0.1")}, False, "starting long-only"),
        ({"A": Decimal("0.05")}, {}, True, "kill switch"),
        ({}, {}, False, "empty target"),
        ({"A": Decimal("0.1"), "B": Decimal("0.1"), "C": Decimal("0.1")}, {}, False, "turnover"),
        ({str(i): Decimal("0.1") for i in range(9)}, {}, False, "gross exposure"),
        ({str(i): Decimal("0.1") for i in range(9)}, {}, False, "cash reserve"),
    ],
)
def test_risk_failures_block_the_plan(targets, current, kill, reason):
    symbols = {"A", "B", "C"} | {str(i) for i in range(9)}
    result = check_targets(targets, current, symbols, RiskPolicy(), kill_switch=kill)
    assert not result.approved
    assert any(reason in item for item in result.reasons)


def test_position_and_turnover_boundaries_are_inclusive():
    result = check_targets(
        {"A": Decimal("0.10"), "B": Decimal("0.10")}, {}, {"A", "B"}, RiskPolicy()
    )
    assert result.approved


def test_turnover_includes_liquidation_of_omitted_positions():
    result = check_targets({"B": Decimal("0.10")}, {"A": Decimal("0.15")}, {"A", "B"}, RiskPolicy())
    assert not result.approved
    assert "turnover limit exceeded" in result.reasons
