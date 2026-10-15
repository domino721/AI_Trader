import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from ai_trader.data.http import SourceClient, SourceFailure
from ai_trader.data.models import CorporateAction, Filing, Instrument, PriceBar

NY = ZoneInfo("America/New_York")


def yahoo_prices(
    source: SourceClient,
    instrument: Instrument,
    start: date,
    end: date,
) -> tuple[list[PriceBar], list[CorporateAction]]:
    query = urlencode(
        {
            "period1": int(datetime.combine(start, datetime.min.time(), NY).timestamp()),
            "period2": int(
                datetime.combine(end + timedelta(days=1), datetime.min.time(), NY).timestamp()
            ),
            "interval": "1d",
            "events": "div,splits",
        }
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{instrument.symbol}?{query}"
    body = source.get(url, "yahoo", "AI_Trader/0.1 personal-research")
    if body["chart"].get("error") or len(body["chart"].get("result") or []) != 1:
        raise SourceFailure("provider_chart_error")
    result = body["chart"]["result"][0]
    if result["meta"]["symbol"] != instrument.symbol or result["meta"]["currency"] != "USD":
        raise SourceFailure("instrument_or_currency_mismatch")
    timestamps = result.get("timestamp") or []
    if not timestamps:
        raise SourceFailure("empty_price_response")
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"]["adjclose"][0]["adjclose"]
    columns = [quote[field] for field in ("open", "high", "low", "close", "volume")]
    if any(len(column) != len(timestamps) for column in [*columns, adjusted]):
        raise SourceFailure("misaligned_price_columns")
    receipt = source.receipts[-1]
    prices = []
    for index, timestamp in enumerate(timestamps):
        day = datetime.fromtimestamp(timestamp, NY).date()
        if not start <= day <= end:
            continue
        # Null OHLC is a quality failure, not silently omitted or forward-filled.
        values = [column[index] for column in [*columns, adjusted]]
        if any(value is None for value in values):
            raise SourceFailure("null_price_or_volume")
        if type(quote["volume"][index]) is not int:
            raise SourceFailure("invalid_volume_type")
        prices.append(
            PriceBar(
                symbol=instrument.symbol,
                session=day,
                currency=result["meta"]["currency"],
                open=Decimal(str(quote["open"][index])),
                high=Decimal(str(quote["high"][index])),
                low=Decimal(str(quote["low"][index])),
                close=Decimal(str(quote["close"][index])),
                adjusted_close=Decimal(str(adjusted[index])),
                volume=quote["volume"][index],
                # Adjusted histories may contain later revisions; keep actual receipt time.
                available_at=receipt.fetched_at,
            )
        )
    actions = []
    for section, kind in (("dividends", "dividend"), ("splits", "split")):
        for item in result.get("events", {}).get(section, {}).values():
            day = datetime.fromtimestamp(item["date"], NY).date()
            if not start <= day <= end:
                continue
            amount = (
                Decimal(str(item["amount"]))
                if kind == "dividend"
                else (Decimal(str(item["numerator"])) / Decimal(str(item["denominator"])))
            )
            actions.append(
                CorporateAction(
                    symbol=instrument.symbol,
                    session=day,
                    kind=kind,
                    amount=amount,
                    observed_at=receipt.fetched_at,
                )
            )
    return prices, actions


def sec_filings(
    source: SourceClient,
    instrument: Instrument,
    start: date,
    end: date,
    user_agent: str | None,
) -> list[Filing]:
    if not source.offline and (
        not user_agent or not re.search(r"[^\s@]+@[^\s@]+\.[^\s@]+", user_agent)
    ):
        raise SourceFailure("missing_sec_user_agent")
    if not source.offline and re.search(
        r"@(example\.(com|org|net)|.*\.invalid)\b", user_agent, re.I
    ):
        raise SourceFailure("placeholder_sec_user_agent")
    if instrument.cik is None:
        return []
    url = f"https://data.sec.gov/submissions/CIK{instrument.cik}.json"
    body = source.get(url, "sec", user_agent or "offline-replay")
    if str(body["cik"]).zfill(10) != instrument.cik:
        raise SourceFailure("cik_mismatch")
    chunks = [(body["filings"]["recent"], source.receipts[-1].fetched_at)]
    historical = [
        item
        for item in body["filings"].get("files", [])
        if date.fromisoformat(item["filingFrom"]) <= end
        and date.fromisoformat(item["filingTo"]) >= start
    ]
    if len(historical) > 12:
        raise SourceFailure("sec_archive_limit_exceeded")
    for item in historical:
        if not re.fullmatch(r"CIK\d{10}-submissions-\d{3}\.json", item["name"]):
            raise SourceFailure("invalid_sec_archive_name")
        chunk = source.get(
            f"https://data.sec.gov/submissions/{item['name']}",
            "sec",
            user_agent or "offline-replay",
        )
        chunks.append((chunk, source.receipts[-1].fetched_at))
    result: dict[str, Filing] = {}
    fields = (
        "accessionNumber",
        "filingDate",
        "reportDate",
        "acceptanceDateTime",
        "form",
        "primaryDocument",
    )
    for rows, fetched_at in chunks:
        length = len(rows["accessionNumber"])
        if any(len(rows[field]) != length for field in fields):
            raise SourceFailure("misaligned_sec_columns")
        for i in range(length):
            filed_on = date.fromisoformat(rows["filingDate"][i])
            if not start <= filed_on <= end:
                continue
            accession = rows["accessionNumber"][i]
            primary = rows["primaryDocument"][i]
            filing = Filing(
                symbol=instrument.symbol,
                cik=instrument.cik,
                accession=accession,
                form=rows["form"][i],
                filed_on=filed_on,
                report_date=rows["reportDate"][i] or None,
                accepted_at=rows["acceptanceDateTime"][i],
                observed_at=fetched_at,
                primary_document=primary,
                url=f"https://www.sec.gov/Archives/edgar/data/{int(instrument.cik)}/"
                f"{accession.replace('-', '')}/{primary}",
            )
            if accession in result and result[accession] != filing:
                # Receipt times can differ across overlapping chunks, but content must agree.
                old = result[accession].model_dump(exclude={"observed_at"})
                if old != filing.model_dump(exclude={"observed_at"}):
                    raise SourceFailure("conflicting_filing_duplicate")
            else:
                result[accession] = filing
    return sorted(result.values(), key=lambda row: (row.accepted_at, row.accession))
