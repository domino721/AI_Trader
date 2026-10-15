import asyncio
import json
import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal

import duckdb
import httpx
import pytest

from ai_trader.api import create_app
from ai_trader.data.archive import Archive
from ai_trader.data.calendar import default_range, session_close, sessions
from ai_trader.data.http import SourceClient, SourceFailure
from ai_trader.data.models import UNIVERSE
from ai_trader.data.pipeline import collect, replay
from ai_trader.data.quality import inspect_data
from ai_trader.settings import Settings

START, END = date(2026, 1, 5), date(2026, 1, 6)
CONTACT = "AI_Trader automated-tests@tests.local"


def chart(symbol="AAPL"):
    timestamps = [int(datetime(2026, 1, day, 14, 30, tzinfo=UTC).timestamp()) for day in (5, 6)]
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "meta": {"symbol": symbol, "currency": "USD"},
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": [100, 100],
                                "high": [102, 102],
                                "low": [98, 98],
                                "close": [100, 100],
                                "volume": [1000, 1000],
                            }
                        ],
                        "adjclose": [{"adjclose": [99, 99]}],
                    },
                    "events": {
                        "dividends": {"event": {"date": timestamps[1], "amount": 0.5}},
                        "splits": {
                            "event": {"date": timestamps[0], "numerator": 2, "denominator": 1}
                        },
                    },
                }
            ],
        }
    }


def filing_rows():
    return {
        "accessionNumber": ["0000320193-26-000001"],
        "filingDate": ["2026-01-06"],
        "reportDate": ["2025-12-31"],
        "acceptanceDateTime": ["2026-01-06T21:10:00Z"],
        "form": ["8-K"],
        "primaryDocument": ["report.htm"],
    }


def submissions(cik="0000320193"):
    return {"cik": int(cik), "filings": {"recent": filing_rows(), "files": []}}


def response_for(request):
    if request.url.host == "query1.finance.yahoo.com":
        return httpx.Response(200, json=chart(request.url.path.rsplit("/", 1)[1]))
    cik = request.url.path.rsplit("/", 1)[1][3:-5]
    return httpx.Response(200, json=submissions(cik))


def settings_for(tmp_path):
    return Settings(state_dir=tmp_path, sec_user_agent=CONTACT, _env_file=None)


def gather(tmp_path, handler=response_for, *, symbols=("AAPL",), refresh=False, settings=None):
    settings = settings or settings_for(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        source = SourceClient(Archive(tmp_path), client, refresh=refresh, sleep=lambda _: None)
        return collect(settings, START, END, symbols, client=client, source=source)


def no_network(request):
    raise AssertionError("unexpected network request")


def test_complete_universe_has_coverage_actions_and_filing_metadata(tmp_path):
    result = gather(tmp_path, symbols=tuple(item.symbol for item in UNIVERSE))
    assert result.quality.research_approved
    assert not result.quality.historical_backtest_approved
    assert not result.quality.trading_approved
    assert len(result.prices) == 14 and len(result.filings) == 5
    assert len(result.actions) == 14 and len(result.receipts) == 12
    assert not any(row.symbol in {"SPY", "IWM"} for row in result.filings)
    assert {row.kind for row in result.actions} == {"split", "dividend"}
    assert result.prices[0].close == 100 and result.prices[0].adjusted_close == 99


def test_cache_checkpoint_is_idempotent_without_network(tmp_path):
    first = gather(tmp_path)
    second = gather(tmp_path, no_network)
    assert first == second
    with sqlite3.connect(Archive(tmp_path).database) as connection:
        assert connection.execute("SELECT count(*) FROM receipts").fetchone()[0] == 2
    assert len(list((tmp_path / "market" / "snapshots").glob("*.json"))) == 1


def test_approved_snapshot_exports_queryable_parquet_and_checksums(tmp_path):
    snapshot = gather(tmp_path)
    archive = Archive(tmp_path)
    path = archive.root / "normalized" / snapshot.snapshot_id / "prices.parquet"
    with duckdb.connect(":memory:") as connection:
        rows = connection.read_parquet(str(path)).fetchall()
    assert len(rows) == 2
    archive.verify_exports(snapshot.snapshot_id)
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="export checksum"):
        replay(settings_for(tmp_path), snapshot.snapshot_id)


def test_refresh_preserves_old_version_and_replay_pins_original_raw(tmp_path):
    first = gather(tmp_path)

    def revised(request):
        if request.url.host == "query1.finance.yahoo.com":
            body = chart()
            body["chart"]["result"][0]["indicators"]["quote"][0]["close"][0] = 101
            return httpx.Response(200, json=body)
        return response_for(request)

    second = gather(tmp_path, revised, refresh=True)
    assert first.snapshot_id != second.snapshot_id
    archive = Archive(tmp_path)
    assert archive.load_snapshot(first.snapshot_id) == first
    assert archive.load_snapshot(second.snapshot_id) == second
    # Replay deliberately needs no SEC identity or external access.
    settings = Settings(state_dir=tmp_path, _env_file=None)
    assert replay(settings, first.snapshot_id)["replay"] == "identical"


@pytest.mark.parametrize(
    "problem,code",
    [
        ("null", "null_price_or_volume"),
        ("length", "misaligned_price_columns"),
        ("currency", "instrument_or_currency_mismatch"),
        ("symbol", "instrument_or_currency_mismatch"),
        ("empty", "empty_price_response"),
        ("volume", "invalid_volume_type"),
    ],
)
def test_invalid_price_responses_are_blocked_without_silent_imputation(tmp_path, problem, code):
    def broken(request):
        if request.url.host != "query1.finance.yahoo.com":
            return response_for(request)
        body = chart()
        result = body["chart"]["result"][0]
        if problem == "null":
            result["indicators"]["quote"][0]["close"][0] = None
        elif problem == "length":
            result["indicators"]["quote"][0]["close"] = [100]
        elif problem == "volume":
            result["indicators"]["quote"][0]["volume"][0] = True
        elif problem in {"currency", "symbol"}:
            result["meta"][problem] = "WRONG"
        else:
            result["timestamp"] = []
        return httpx.Response(200, json=body)

    result = gather(tmp_path, broken)
    assert result.quality.status == "blocked"
    assert not result.quality.research_approved
    assert code in {issue.code for issue in result.quality.issues}
    assert (tmp_path / "market" / "quarantine" / f"{result.snapshot_id}.json").exists()


@pytest.mark.parametrize(
    "problem,code",
    [
        ("duplicate", "duplicate_session"),
        ("missing", "missing_sessions"),
        ("ohlc", "invalid_ohlc"),
        ("negative", "invalid_price"),
        ("volume", "volume_or_currency"),
        ("early", "incomplete_or_future_bar"),
    ],
)
def test_independent_quality_gate_rejects_bad_normalized_inputs(tmp_path, problem, code):
    snapshot = gather(tmp_path)
    prices = list(snapshot.prices)
    if problem == "duplicate":
        prices.append(prices[0])
    elif problem == "missing":
        prices.pop()
    else:
        updates = {
            "ohlc": {"high": Decimal("90")},
            "negative": {"close": Decimal("-1")},
            "volume": {"volume": -1},
            "early": {"available_at": datetime(2026, 1, 5, 14, tzinfo=UTC)},
        }
        prices[0] = prices[0].model_copy(update=updates[problem])
    result = inspect_data(snapshot.instruments, START, END, prices, [], [], [])
    assert not result.research_approved
    assert result.status == "quarantined"
    assert code in {issue.code for issue in result.issues}


def test_future_filing_cannot_pass_quality_gate(tmp_path):
    def future(request):
        if request.url.host != "data.sec.gov":
            return response_for(request)
        body = submissions()
        body["filings"]["recent"]["acceptanceDateTime"] = ["2099-01-01T00:00:00Z"]
        return httpx.Response(200, json=body)

    result = gather(tmp_path, future)
    assert result.quality.status == "quarantined"
    assert "future_filing" in {issue.code for issue in result.quality.issues}


def test_invalid_json_still_pins_original_bytes_in_blocked_audit_record(tmp_path):
    def broken(request):
        if request.url.host == "query1.finance.yahoo.com":
            return httpx.Response(200, content=b"{not valid JSON")
        return response_for(request)

    result = gather(tmp_path, broken)
    assert not result.quality.research_approved
    assert len(result.receipts) == 2
    raw = [Archive(tmp_path).read(receipt) for receipt in result.receipts]
    assert b"{not valid JSON" in raw


def test_sec_archive_pagination_and_overlapping_metadata_are_deduplicated(tmp_path):
    calls = []

    def paginated(request):
        calls.append(request.url.path)
        if "-submissions-" in request.url.path:
            return httpx.Response(200, json=filing_rows())
        if request.url.host != "data.sec.gov":
            return response_for(request)
        body = submissions()
        body["filings"]["files"] = [
            {
                "name": "CIK0000320193-submissions-001.json",
                "filingFrom": "2026-01-01",
                "filingTo": "2026-01-06",
            }
        ]
        return httpx.Response(200, json=body)

    result = gather(tmp_path, paginated)
    assert result.quality.research_approved
    assert len(result.filings) == 1 and len(calls) == 3
    assert replay(settings_for(tmp_path), result.snapshot_id)["replay"] == "identical"


def test_sec_column_mismatch_and_identity_absence_block_approval(tmp_path):
    def broken(request):
        if request.url.host != "data.sec.gov":
            return response_for(request)
        body = submissions()
        body["filings"]["recent"]["acceptanceDateTime"] = []
        return httpx.Response(200, json=body)

    result = gather(tmp_path, broken)
    assert "misaligned_sec_columns" in {issue.code for issue in result.quality.issues}
    no_identity = Settings(state_dir=tmp_path, _env_file=None)
    result = gather(tmp_path, settings=no_identity)
    assert "missing_sec_user_agent" in {issue.code for issue in result.quality.issues}
    assert not result.quality.research_approved


@pytest.mark.parametrize("status", [403, 404])
def test_permanent_http_error_is_not_retried(tmp_path, status):
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(status)
        )
    ) as client:
        source = SourceClient(Archive(tmp_path), client, sleep=lambda _: None)
        with pytest.raises(SourceFailure, match=f"http_{status}"):
            source.get("https://data.sec.gov/test", "sec", CONTACT)
    assert len(calls) == 1


def test_rate_limit_honors_retry_after_then_checkpoints_success(tmp_path):
    calls, delays = [], []

    def limited(request):
        calls.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "2"})
            if len(calls) == 1
            else (httpx.Response(200, json={"ok": True}))
        )

    with httpx.Client(transport=httpx.MockTransport(limited)) as client:
        source = SourceClient(Archive(tmp_path), client, sleep=delays.append)
        assert source.get("https://data.sec.gov/test", "sec", CONTACT) == {"ok": True}
    assert len(calls) == 2 and 2 in delays


def test_long_retry_after_defers_instead_of_ignoring_server_limit(tmp_path):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, headers={"Retry-After": "60"})
        )
    ) as client:
        source = SourceClient(Archive(tmp_path), client, sleep=lambda _: None)
        with pytest.raises(SourceFailure, match="retry_deferred"):
            source.get("https://data.sec.gov/test", "sec", CONTACT)


def test_proxy_denial_is_recorded_once_and_never_retried(tmp_path):
    calls = []

    def denied(request):
        calls.append(request)
        raise httpx.ProxyError("test proxy denied")

    archive = Archive(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(denied)) as client:
        source = SourceClient(archive, client, sleep=lambda _: None)
        with pytest.raises(SourceFailure, match="proxy_error"):
            source.get("https://data.sec.gov/test", "sec", CONTACT)
    assert len(calls) == 1
    with sqlite3.connect(archive.database) as connection:
        assert connection.execute("SELECT outcome FROM attempts").fetchall() == [("proxy_error",)]


def test_contact_identity_is_sent_as_header_and_not_persisted(tmp_path):
    headers = []

    def recording(request):
        if request.url.host == "data.sec.gov":
            headers.append(request.headers["User-Agent"])
        return response_for(request)

    snapshot = gather(tmp_path, recording)
    assert headers == [CONTACT]
    assert CONTACT not in snapshot.model_dump_json()
    assert CONTACT.encode() not in Archive(tmp_path).database.read_bytes()


def test_invalid_sec_archive_name_cannot_trigger_arbitrary_fetch(tmp_path):
    def broken(request):
        if request.url.host != "data.sec.gov":
            return response_for(request)
        body = submissions()
        body["filings"]["files"] = [
            {"name": "../../private.json", "filingFrom": "2026-01-01", "filingTo": "2026-01-06"}
        ]
        return httpx.Response(200, json=body)

    result = gather(tmp_path, broken)
    assert not result.quality.research_approved
    assert "invalid_sec_archive_name" in {issue.code for issue in result.quality.issues}


def test_network_timeouts_have_a_bounded_retry_count(tmp_path):
    calls = []

    def timed_out(request):
        calls.append(request)
        raise httpx.ReadTimeout("test timeout")

    with httpx.Client(transport=httpx.MockTransport(timed_out)) as client:
        source = SourceClient(Archive(tmp_path), client, sleep=lambda _: None)
        with pytest.raises(SourceFailure, match="network_error"):
            source.get("https://data.sec.gov/test", "sec", CONTACT)
    assert len(calls) == 3


def test_raw_corruption_is_detected_and_does_not_fall_back_to_network(tmp_path):
    snapshot = gather(tmp_path)
    archive = Archive(tmp_path)
    path = archive.root / "raw" / f"{snapshot.receipts[0].sha256}.json"
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        replay(settings_for(tmp_path), snapshot.snapshot_id)
    result = gather(tmp_path, no_network)
    assert not result.quality.research_approved
    assert "invalid_or_corrupt_raw_data" in {issue.code for issue in result.quality.issues}


def test_snapshot_tampering_and_path_traversal_are_rejected(tmp_path):
    snapshot = gather(tmp_path)
    archive = Archive(tmp_path)
    with pytest.raises(ValueError, match="invalid snapshot"):
        archive.load_snapshot("../receipts.db")
    path = archive.root / "snapshots" / f"{snapshot.snapshot_id}.json"
    body = json.loads(path.read_bytes())
    body["prices"][0]["close"] = "101"
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="checksum"):
        archive.load_snapshot(snapshot.snapshot_id)


def test_exchange_calendar_handles_holiday_early_close_and_partial_today():
    assert sessions(date(2026, 7, 2), date(2026, 7, 6)) == (date(2026, 7, 2), date(2026, 7, 6))
    assert session_close(date(2025, 11, 28)) == datetime(2025, 11, 28, 18, tzinfo=UTC)
    _, end = default_range(datetime(2026, 1, 6, 17, tzinfo=UTC))
    assert end == START


@pytest.mark.parametrize("symbols", [("UNKNOWN",), ("AAPL", "AAPL")])
def test_unconfigured_or_duplicate_symbol_is_rejected_before_network(tmp_path, symbols):
    with pytest.raises(ValueError, match="unique symbols"):
        gather(tmp_path, no_network, symbols=symbols)


def test_future_range_is_rejected_before_network(tmp_path):
    with pytest.raises(ValueError, match="completed trading"):
        collect(settings_for(tmp_path), date(2099, 1, 5), date(2099, 1, 6))


def test_snapshot_api_reads_immutable_record_without_collecting(tmp_path):
    snapshot = gather(tmp_path)

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(settings_for(tmp_path))),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/data/snapshots/{snapshot.snapshot_id}")
            assert response.status_code == 200
            assert response.json()["snapshot_id"] == snapshot.snapshot_id
            assert (await client.get("/data/snapshots/bad")).status_code == 422

    asyncio.run(check())


def test_cli_blocked_collection_returns_nonzero_and_machine_readable_report(
    tmp_path, monkeypatch, capsys
):
    from ai_trader import cli

    result = gather(tmp_path, settings=Settings(state_dir=tmp_path, _env_file=None))
    monkeypatch.setattr(cli, "collect", lambda *args, **kwargs: result)
    monkeypatch.setattr(
        "sys.argv", ["ai-trader", "data", "collect", "--start", str(START), "--end", str(END)]
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert json.loads(capsys.readouterr().out)["research_approved"] is False
