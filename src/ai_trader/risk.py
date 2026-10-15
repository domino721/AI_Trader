from decimal import Decimal

from ai_trader.domain import RiskCheck, RiskPolicy


def check_targets(
    targets: dict[str, Decimal],
    current: dict[str, Decimal],
    allowed_symbols: set[str],
    policy: RiskPolicy,
    *,
    kill_switch: bool = False,
) -> RiskCheck:
    reasons = []
    if kill_switch:
        reasons.append("kill switch enabled")
    if not targets:
        reasons.append("empty target portfolio")
    if set(targets) - allowed_symbols or set(current) - allowed_symbols:
        reasons.append("unknown symbol")
    if any(not value.is_finite() for value in [*targets.values(), *current.values()]):
        return RiskCheck(approved=False, reasons=(*reasons, "non-finite portfolio weight"))
    if any(value < 0 for value in current.values()) or sum(current.values()) > 1:
        reasons.append("invalid starting long-only portfolio")
    if any(value < 0 for value in targets.values()):
        reasons.append("short positions are disabled")
    if any(value > policy.max_position_weight for value in targets.values()):
        reasons.append("position limit exceeded")
    gross = sum((abs(weight) for weight in targets.values()), Decimal("0"))
    if gross > policy.max_gross_weight:
        reasons.append("gross exposure limit exceeded")
    if Decimal("1") - gross < policy.min_cash_weight:
        reasons.append("cash reserve below minimum")
    turnover = sum(
        (
            abs(targets.get(symbol, Decimal("0")) - current.get(symbol, Decimal("0")))
            for symbol in set(targets) | set(current)
        ),
        Decimal("0"),
    )
    if turnover > policy.max_turnover_weight:
        reasons.append("turnover limit exceeded")
    return RiskCheck(approved=not reasons, reasons=tuple(reasons))
