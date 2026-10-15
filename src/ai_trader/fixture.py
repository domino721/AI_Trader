"""Fabricated inputs for plumbing checks; no historical market performance claims."""

from datetime import UTC, datetime
from decimal import Decimal

from ai_trader.domain import ExecutionBar, Observation, Snapshot


def demo_snapshot() -> Snapshot:
    as_of = datetime(2026, 1, 5, 21, tzinfo=UTC)
    return Snapshot(
        as_of=as_of,
        observations=(
            Observation(
                symbol="DEMO_A",
                available_at=as_of,
                source_id="synthetic:demo-a:v1",
                close=Decimal("100"),
                book_value_per_share=Decimal("90"),
                return_on_equity=0.15,
                momentum_12m=0.12,
                annualized_volatility=0.20,
            ),
            Observation(
                symbol="DEMO_B",
                available_at=as_of,
                source_id="synthetic:demo-b:v1",
                close=Decimal("50"),
                book_value_per_share=Decimal("12"),
                return_on_equity=0.04,
                momentum_12m=-0.12,
                annualized_volatility=0.40,
            ),
        ),
    )


def demo_execution_bars() -> tuple[ExecutionBar, ...]:
    next_open = datetime(2026, 1, 6, 14, 30, tzinfo=UTC)
    return (
        ExecutionBar(symbol="DEMO_A", timestamp=next_open, open=Decimal("101")),
        ExecutionBar(symbol="DEMO_B", timestamp=next_open, open=Decimal("49")),
    )
