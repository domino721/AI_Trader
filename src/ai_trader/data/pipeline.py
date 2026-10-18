from datetime import UTC, date, datetime

import httpx

from ai_trader.data.archive import Archive, snapshot_digest
from ai_trader.data.calendar import session_close, sessions
from ai_trader.data.http import SourceClient, SourceFailure
from ai_trader.data.models import UNIVERSE, DataSnapshot, Issue
from ai_trader.data.providers import sec_filings, yahoo_prices
from ai_trader.data.quality import inspect_data
from ai_trader.settings import Settings


def collect(
    settings: Settings,
    start: date,
    end: date,
    symbols: tuple[str, ...] | None = None,
    *,
    refresh: bool = False,
    client: httpx.Client | None = None,
    source: SourceClient | None = None,
) -> DataSnapshot:
    settings.prepare_state()
    selected = tuple(symbols or (item.symbol for item in UNIVERSE))
    known = {item.symbol: item for item in UNIVERSE}
    if not selected or len(set(selected)) != len(selected) or set(selected) - known.keys():
        raise ValueError("choose unique symbols from the configured universe")
    if end > datetime.now(UTC).date():
        raise ValueError("request must contain completed trading sessions only")
    expected = sessions(start, end)
    if not expected or session_close(expected[-1]) > datetime.now(UTC):
        raise ValueError("request must contain completed trading sessions only")
    archive = Archive(settings.state_dir)
    owns_client = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=False)
    source = source or SourceClient(archive, client, refresh=refresh)
    instruments = tuple(known[symbol] for symbol in sorted(selected))
    prices, actions, filings, issues = [], [], [], []

    def failure(symbol: str, provider: str, error: Exception):
        code = error.code if isinstance(error, SourceFailure) else "malformed_response"
        issues.append(Issue(code=code, symbol=symbol, detail=f"{provider}: {code}"))

    try:
        for item in instruments:
            try:
                rows, events = yahoo_prices(source, item, start, end)
                prices.extend(rows)
                actions.extend(events)
            except (
                SourceFailure,
                ValueError,
                KeyError,
                IndexError,
                TypeError,
                ArithmeticError,
            ) as error:
                failure(item.symbol, "yahoo", error)
            if item.kind == "stock":
                try:
                    filings.extend(sec_filings(source, item, start, end, settings.sec_user_agent))
                except (
                    SourceFailure,
                    ValueError,
                    KeyError,
                    IndexError,
                    TypeError,
                    ArithmeticError,
                ) as error:
                    failure(item.symbol, "sec", error)
    finally:
        if owns_client:
            client.close()
    prices.sort(key=lambda row: (row.symbol, row.session))
    actions.sort(key=lambda row: (row.symbol, row.session, row.kind))
    filings.sort(key=lambda row: (row.symbol, row.accepted_at, row.accession))
    receipts = tuple(
        sorted(
            {row.request_key: row for row in source.receipts}.values(),
            key=lambda row: row.request_key,
        )
    )
    quality = inspect_data(instruments, start, end, prices, actions, filings, issues)
    snapshot = DataSnapshot(
        snapshot_id="",
        instruments=instruments,
        start=start,
        end=end,
        receipts=receipts,
        prices=tuple(prices),
        actions=tuple(actions),
        filings=tuple(filings),
        quality=quality,
    )
    snapshot = snapshot.model_copy(update={"snapshot_id": snapshot_digest(snapshot)})
    archive.save_snapshot(snapshot)
    return snapshot


def replay(settings: Settings, snapshot_id: str) -> dict:
    settings.prepare_state()
    archive = Archive(settings.state_dir)
    saved = archive.load_snapshot(snapshot_id)
    for receipt in saved.receipts:
        archive.read(receipt)
    if not saved.quality.research_approved:
        return {
            "snapshot_id": snapshot_id,
            "integrity": "passed",
            "replay": "not_run_blocked_snapshot",
        }
    archive.verify_exports(saved.snapshot_id)
    with httpx.Client(transport=httpx.MockTransport(_no_network)) as client:
        source = SourceClient(archive, client, pinned_receipts=saved.receipts)
        result = collect(
            settings,
            saved.start,
            saved.end,
            tuple(item.symbol for item in saved.instruments),
            client=client,
            source=source,
        )
    if result != saved:
        raise ValueError("replayed normalization or quality result differs")
    return {"snapshot_id": snapshot_id, "integrity": "passed", "replay": "identical"}


def _no_network(request: httpx.Request) -> httpx.Response:
    raise RuntimeError("network access is forbidden during replay")


def summary(snapshot: DataSnapshot) -> dict:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "status": snapshot.quality.status,
        "research_approved": snapshot.quality.research_approved,
        "historical_backtest_approved": False,
        "trading_approved": False,
        "price_rows": len(snapshot.prices),
        "corporate_actions": len(snapshot.actions),
        "filing_metadata_rows": len(snapshot.filings),
        "issues": [issue.model_dump() for issue in snapshot.quality.issues],
    }
