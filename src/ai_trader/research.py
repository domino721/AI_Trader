"""Deterministic stand-ins for future cited, structured LLM analyst outputs."""

from decimal import Decimal

from ai_trader.domain import Deliberation, Opinion, Snapshot


def deliberate(snapshot: Snapshot) -> Deliberation:
    opinions: list[Opinion] = []
    objections = []
    targets = {}
    for row in snapshot.observations:
        evidence = (row.source_id,)
        value = (
            Decimal("0.10")
            if (
                row.close / row.book_value_per_share < Decimal("1.5")
                and row.return_on_equity > 0.10
            )
            else Decimal("0")
        )
        momentum = Decimal("0.10") if row.momentum_12m > 0 else Decimal("0")
        quant = (
            Decimal("0.05")
            if (row.annualized_volatility < 0.30 and row.momentum_12m > 0)
            else Decimal("0")
        )
        for role, weight, reason in (
            ("value", value, "Demo rule: price/book and return on equity; not intrinsic value."),
            ("momentum", momentum, "Demo rule: positive 12-month price momentum."),
            ("quant", quant, "Demo rule: volatility ceiling and positive momentum."),
        ):
            opinions.append(
                Opinion(
                    role=role,
                    symbol=row.symbol,
                    target_weight=weight,
                    rationale=reason,
                    evidence_ids=evidence,
                )
            )
        objections.append(
            f"{row.symbol}: synthetic evidence; correlated votes are not independent proof. "
            "No licensed corpus, LLM reasoning, transaction history, or alpha validation yet."
        )
        targets[row.symbol] = ((value + momentum + quant) / 3).quantize(Decimal("0.000001"))
    return Deliberation(
        opinions=tuple(opinions), objections=tuple(objections), target_weights=targets
    )
