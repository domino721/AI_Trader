"""One rebalance from cash, for synthetic research only; no external broker I/O."""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from ai_trader.domain import ExecutionBar, Fill, Simulation, Snapshot


def simulate_from_cash(
    snapshot: Snapshot,
    targets: dict[str, Decimal],
    bars: tuple[ExecutionBar, ...],
    *,
    initial_cash: Decimal = Decimal("10000.00"),
    fee_bps: Decimal = Decimal("10"),
    slippage_bps: Decimal = Decimal("5"),
) -> Simulation:
    if not initial_cash.is_finite() or initial_cash <= 0:
        raise ValueError("initial cash must be positive and finite")
    for cost in (fee_bps, slippage_bps):
        if not cost.is_finite() or not Decimal("0") <= cost <= Decimal("10000"):
            raise ValueError("invalid execution cost")
    symbols = {row.symbol for row in snapshot.observations}
    if set(targets) != symbols:
        raise ValueError("targets must cover the decision universe")
    if any(not w.is_finite() or not Decimal("0") <= w <= 1 for w in targets.values()):
        raise ValueError("invalid target weight")
    if sum(targets.values()) > 1:
        raise ValueError("cash-only simulation cannot use leverage")
    by_symbol = {bar.symbol: bar for bar in bars}
    if len(by_symbol) != len(bars) or set(by_symbol) != symbols:
        raise ValueError("execution bars must cover each symbol exactly once")
    if any(bar.timestamp <= snapshot.as_of for bar in bars):
        raise ValueError("execution must occur strictly after the decision")
    cash = initial_cash
    fills = []
    for symbol, weight in sorted(targets.items()):
        bar = by_symbol[symbol]
        # Next-open prices are only used for execution, never for analyst decisions.
        price = (bar.open * (1 + slippage_bps / 10000)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        budget = initial_cash * weight
        quantity = int(
            (budget / (price * (1 + fee_bps / 10000))).to_integral_value(rounding=ROUND_DOWN)
        )
        if quantity == 0:
            continue
        fee = (price * quantity * fee_bps / 10000).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        notional = (price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cost = notional + fee
        if cost > cash:
            raise ValueError("insufficient cash after execution costs")
        cash -= cost
        fills.append(
            Fill(symbol=symbol, timestamp=bar.timestamp, quantity=quantity, price=price, fee=fee)
        )
    return Simulation(
        initial_cash=initial_cash,
        remaining_cash=cash,
        fills=tuple(fills),
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )
