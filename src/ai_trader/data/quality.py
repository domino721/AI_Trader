from collections import Counter
from datetime import date
from decimal import Decimal

from ai_trader.data.calendar import session_close, sessions
from ai_trader.data.models import (
    CorporateAction,
    Filing,
    Instrument,
    Issue,
    PriceBar,
    QualityReport,
)


def inspect_data(
    instruments: tuple[Instrument, ...],
    start: date,
    end: date,
    prices: list[PriceBar],
    actions: list[CorporateAction],
    filings: list[Filing],
    source_issues: list[Issue],
) -> QualityReport:
    issues = list(source_issues)
    expected = set(sessions(start, end))
    symbols = {item.symbol for item in instruments}
    for instrument in instruments:
        rows = [row for row in prices if row.symbol == instrument.symbol]
        found = {row.session for row in rows}
        if missing := expected - found:
            issues.append(
                Issue(
                    code="missing_sessions",
                    symbol=instrument.symbol,
                    detail=",".join(str(day) for day in sorted(missing)),
                )
            )
        for day, count in Counter(row.session for row in rows).items():
            if count > 1:
                issues.append(
                    Issue(code="duplicate_session", symbol=instrument.symbol, detail=str(day))
                )
        for row in rows:
            if row.session not in expected:
                issues.append(
                    Issue(code="unexpected_session", symbol=row.symbol, detail=str(row.session))
                )
            values = (row.open, row.high, row.low, row.close, row.adjusted_close)
            if any(not value.is_finite() or value <= Decimal("0") for value in values):
                issues.append(
                    Issue(code="invalid_price", symbol=row.symbol, detail=str(row.session))
                )
            elif not row.low <= min(row.open, row.close) <= max(row.open, row.close) <= row.high:
                issues.append(
                    Issue(code="invalid_ohlc", symbol=row.symbol, detail=str(row.session))
                )
            if row.volume < 0 or row.currency != instrument.currency:
                issues.append(
                    Issue(code="volume_or_currency", symbol=row.symbol, detail=str(row.session))
                )
            if row.volume == 0:
                issues.append(
                    Issue(
                        code="zero_volume",
                        symbol=row.symbol,
                        detail=str(row.session),
                        severity="warning",
                    )
                )
            if row.session in expected and row.available_at < session_close(row.session):
                issues.append(
                    Issue(
                        code="incomplete_or_future_bar", symbol=row.symbol, detail=str(row.session)
                    )
                )
    if any(row.symbol not in symbols for row in prices):
        issues.append(
            Issue(code="unknown_price_symbol", symbol="*", detail="outside requested universe")
        )
    for key, count in Counter((row.symbol, row.session, row.kind) for row in actions).items():
        if count > 1:
            issues.append(Issue(code="duplicate_action", symbol=key[0], detail=str(key[1])))
    for action in actions:
        if action.symbol not in symbols or action.session not in expected:
            issues.append(
                Issue(code="unexpected_action", symbol=action.symbol, detail=str(action.session))
            )
    for filing in filings:
        if filing.accepted_at > filing.observed_at:
            issues.append(
                Issue(code="future_filing", symbol=filing.symbol, detail=filing.accession)
            )
        if filing.report_date and filing.report_date > filing.filed_on:
            issues.append(
                Issue(code="future_report_period", symbol=filing.symbol, detail=filing.accession)
            )
    issues.append(
        Issue(
            code="research_only",
            symbol="*",
            severity="warning",
            detail=(
                "Prototype source; current adjusted history; "
                "no survivorship/PIT certification or trading approval."
            ),
        )
    )
    errors = any(issue.severity == "error" for issue in issues)
    status = "blocked" if source_issues else ("quarantined" if errors else "passed")
    return QualityReport(status=status, research_approved=not errors, issues=tuple(issues))
