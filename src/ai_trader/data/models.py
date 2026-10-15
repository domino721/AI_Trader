from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field

from ai_trader.domain import Record


class Instrument(Record):
    symbol: str = Field(pattern=r"^[A-Z]{1,5}$")
    kind: Literal["stock", "etf"]
    cik: str | None = Field(default=None, pattern=r"^\d{10}$")
    currency: Literal["USD"] = "USD"


UNIVERSE_VERSION = "research-smoke-v1"
UNIVERSE = (
    Instrument(symbol="AAPL", kind="stock", cik="0000320193"),
    Instrument(symbol="MSFT", kind="stock", cik="0000789019"),
    Instrument(symbol="GOOGL", kind="stock", cik="0001652044"),
    Instrument(symbol="AMZN", kind="stock", cik="0001018724"),
    Instrument(symbol="JPM", kind="stock", cik="0000019617"),
    Instrument(symbol="SPY", kind="etf"),
    Instrument(symbol="IWM", kind="etf"),
)


class Receipt(Record):
    request_key: str
    provider: str
    url: str
    sha256: str
    fetched_at: AwareDatetime


class PriceBar(Record):
    symbol: str
    session: date
    currency: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal
    volume: int
    available_at: AwareDatetime


class CorporateAction(Record):
    symbol: str
    session: date
    kind: Literal["dividend", "split"]
    amount: Decimal = Field(gt=0)
    # amount is cash per share for dividends, new/old share ratio for splits.
    observed_at: AwareDatetime


class Filing(Record):
    symbol: str
    cik: str
    accession: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    form: str
    filed_on: date
    report_date: date | None
    accepted_at: AwareDatetime
    observed_at: AwareDatetime
    primary_document: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    url: str


class Issue(Record):
    code: str
    symbol: str
    detail: str
    severity: Literal["error", "warning"] = "error"


class QualityReport(Record):
    status: Literal["passed", "quarantined", "blocked"]
    research_approved: bool
    historical_backtest_approved: Literal[False] = False
    trading_approved: Literal[False] = False
    issues: tuple[Issue, ...]


class DataSnapshot(Record):
    schema_version: Literal["1.0"] = "1.0"
    snapshot_id: str
    universe_version: str = UNIVERSE_VERSION
    instruments: tuple[Instrument, ...]
    start: date
    end: date
    receipts: tuple[Receipt, ...]
    prices: tuple[PriceBar, ...]
    actions: tuple[CorporateAction, ...]
    filings: tuple[Filing, ...]
    quality: QualityReport
