import json
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai_trader.cli import main
from ai_trader.llm.fixture import fixture_request
from ai_trader.llm.models import InvocationPolicy, ModelRequest, ProviderReply
from ai_trader.llm.provider import FixtureProvider, ProviderTimeout, RetryableBeforeDispatch
from ai_trader.llm.runtime import InvocationJournal, invoke

NOW = datetime(2026, 10, 17, tzinfo=UTC)


def policy(**changes):
    values = dict(
        enabled=True,
        monthly_call_limit=10,
        monthly_reservation_limit_usd=Decimal("0.10"),
        attempt_reservation_usd=Decimal("0.01"),
        max_attempts=3,
        timeout_seconds=2,
    )
    values.update(changes)
    return InvocationPolicy(**values)


def run(tmp_path, *, request_id="test", provider=None, config=None, now=NOW):
    return invoke(
        fixture_request(request_id),
        config or policy(),
        provider or FixtureProvider(),
        tmp_path,
        clock=lambda: now,
    )


def attempts(tmp_path):
    with sqlite3.connect(tmp_path / "llm/invocations.db") as db:
        return db.execute(
            "SELECT outcome,raw_text,reservation FROM attempts ORDER BY rowid"
        ).fetchall()


def test_disabled_by_default_and_live_provider_configuration_unavailable(tmp_path):
    provider = FixtureProvider()
    result = run(tmp_path, provider=provider, config=InvocationPolicy())
    assert result.reason == "invocation_disabled"
    assert provider.calls == 0
    assert attempts(tmp_path) == []
    with pytest.raises(ValidationError):
        InvocationPolicy(provider_id="paid_provider")


def test_response_request_policy_and_usage_are_persisted_without_order_authority(tmp_path):
    provider = FixtureProvider(('{"instruction":"submit a trade"}',))
    result = run(tmp_path, provider=provider)
    assert result.status == "completed"
    assert result.untrusted_proposal_only and not result.trading_approved
    assert result.reserved_usd == Decimal("0.01")
    assert provider.timeouts == [2]
    assert "submit a trade" not in json.dumps(result.summary())
    assert attempts(tmp_path)[0][:2] == ("response_received", '{"instruction":"submit a trade"}')
    with sqlite3.connect(tmp_path / "llm/invocations.db") as db:
        request_json, policy_json, result_json = db.execute(
            "SELECT request_json,policy_json,result_json FROM runs"
        ).fetchone()
        usage = json.loads(db.execute("SELECT reply_json FROM attempts").fetchone()[0])
    assert json.loads(request_json)["context"]["snapshot_id"] == "a" * 64
    assert json.loads(policy_json)["model_id"] == "fixture-v1"
    assert json.loads(result_json)["offline_only"] is True
    assert usage["input_tokens"] == usage["output_tokens"] == 0
    if os.name != "nt":
        assert (tmp_path / "llm/invocations.db").stat().st_mode & 0o777 == 0o600


def test_same_id_replays_saved_response_after_restart_and_even_when_disabled(tmp_path):
    first = run(tmp_path)
    other = FixtureProvider((RuntimeError("must never run"),))
    assert run(tmp_path, provider=other, config=InvocationPolicy()) == first
    assert other.calls == 0
    assert len(attempts(tmp_path)) == 1


def test_reusing_id_with_different_input_is_rejected_without_overwriting(tmp_path):
    original = run(tmp_path)
    payload = fixture_request("test").model_dump()
    payload["task"] = "different task"
    provider = FixtureProvider()
    result = invoke(ModelRequest(**payload), policy(), provider, tmp_path, clock=lambda: NOW)
    assert result.reason == "request_id_conflict"
    assert provider.calls == 0
    assert run(tmp_path) == original


def test_pending_or_crashed_run_is_never_silently_reissued(tmp_path):
    journal = InvocationJournal(tmp_path)
    request = fixture_request("test")
    assert journal.start(request, policy(), NOW) is None
    assert journal.reserve("test", policy(), NOW) is None
    provider = FixtureProvider()
    result = run(tmp_path, provider=provider)
    assert result.reason == "inflight_or_interrupted"
    assert result.reserved_usd == Decimal("0.01")
    assert provider.calls == 0


@pytest.mark.parametrize(
    "config,reason",
    [
        (policy(monthly_call_limit=0), "monthly_call_limit"),
        (policy(monthly_reservation_limit_usd=Decimal("0")), "monthly_reservation_limit"),
    ],
)
def test_budget_blocks_before_dispatch(tmp_path, config, reason):
    provider = FixtureProvider()
    assert run(tmp_path, config=config, provider=provider).reason == reason
    assert provider.calls == 0


def test_atomic_budget_cannot_be_overspent_by_concurrent_requests(tmp_path):
    provider = FixtureProvider()
    InvocationJournal(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda name: run(
                    tmp_path,
                    request_id=name,
                    provider=provider,
                    config=policy(monthly_call_limit=1),
                ),
                ("first", "second"),
            )
        )
    assert sorted(r.status for r in results) == ["abstained", "completed"]
    assert provider.calls == 1
    assert len(attempts(tmp_path)) == 1


def test_same_id_concurrent_execution_dispatches_only_once(tmp_path):
    provider = FixtureProvider()
    InvocationJournal(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(tmp_path, provider=provider), range(2)))
    assert any(r.status == "completed" for r in results)
    assert provider.calls == 1


def test_retryable_failure_reserves_each_attempt_and_preserves_outcomes(tmp_path):
    provider = FixtureProvider((RetryableBeforeDispatch(), '{"ok":true}'))
    result = run(tmp_path, provider=provider)
    assert result.status == "completed" and result.attempts == 2
    assert result.reserved_usd == Decimal("0.02")
    assert [a[0] for a in attempts(tmp_path)] == ["retryable_before_dispatch", "response_received"]


def test_retry_stops_at_budget_and_at_attempt_limit(tmp_path):
    provider = FixtureProvider((RetryableBeforeDispatch(),))
    first = run(tmp_path, provider=provider, config=policy(monthly_call_limit=1))
    assert first.reason == "monthly_call_limit" and provider.calls == 1
    second = run(tmp_path / "other", provider=provider, config=policy(max_attempts=2))
    assert second.reason == "retry_limit" and second.attempts == 2


def test_timeout_does_not_retry_refund_or_redispatch_after_restart(tmp_path):
    provider = FixtureProvider((ProviderTimeout("secret in exception"), '{"ok":true}'))
    first = run(tmp_path, provider=provider)
    assert first.reason == "timeout_uncertain"
    assert first.attempts == provider.calls == 1
    assert first.reserved_usd == Decimal("0.01")
    assert run(tmp_path, provider=provider) == first
    assert provider.calls == 1
    with sqlite3.connect(tmp_path / "llm/invocations.db") as db:
        assert "secret in exception" not in repr(db.execute("SELECT * FROM attempts").fetchall())


@pytest.mark.parametrize(
    "raw,reason",
    [
        ("broken JSON", "invalid_response_json"),
        ("null", "invalid_response_shape"),
        ("[]", "invalid_response_shape"),
        ('{"x":NaN}', "invalid_response_json"),
        ('{"x":1e999}', "invalid_response_json"),
        ('{"x":1,"x":2}', "invalid_response_json"),
        ("x" * 65537, "response_too_large"),
    ],
    ids=["broken", "null", "array", "nan", "infinity", "duplicate-key", "oversized"],
)
def test_bad_response_abstains_preserves_bounded_raw_and_never_retries(tmp_path, raw, reason):
    provider = FixtureProvider((raw,))
    result = run(tmp_path, provider=provider)
    assert result.reason == reason and provider.calls == 1
    assert attempts(tmp_path)[0][1] == raw[:65536]
    with sqlite3.connect(tmp_path / "llm/invocations.db") as db:
        truncated = db.execute("SELECT truncated FROM attempts").fetchone()[0]
    assert bool(truncated) == (len(raw) > 65536)


def test_monthly_limit_uses_attempt_time_utc_instead_of_historical_decision_time(tmp_path):
    config = policy(monthly_call_limit=1)
    run(tmp_path, config=config)
    assert run(tmp_path, request_id="blocked", config=config).reason == "monthly_call_limit"
    assert (
        run(
            tmp_path, request_id="next-month", config=config, now=datetime(2026, 11, 1, tzinfo=UTC)
        ).status
        == "completed"
    )


def test_wrong_identity_empty_evidence_and_adapter_errors_fail_closed(tmp_path):
    wrong = FixtureProvider()
    wrong.model_id = "another-model"
    assert run(tmp_path, provider=wrong).reason == "provider_identity_mismatch"
    assert wrong.calls == 0
    request = fixture_request("empty").model_dump()
    request["context"]["hits"] = []
    result = invoke(ModelRequest(**request), policy(), FixtureProvider(), tmp_path)
    assert result.reason == "no_eligible_evidence"
    bad = FixtureProvider((RuntimeError("sensitive provider failure"),))
    assert run(tmp_path, request_id="error", provider=bad).reason == "provider_error"


def test_response_model_is_checked_even_if_adapter_identity_matches(tmp_path):
    class WrongResponse(FixtureProvider):
        def generate(self, request, *, timeout_seconds):
            return ProviderReply(model_id="wrong", raw_text="{}", input_tokens=0, output_tokens=0)

    assert run(tmp_path, provider=WrongResponse()).reason == "response_model_mismatch"


def test_invalid_reply_envelopes_are_sanitized_and_not_retried(tmp_path):
    provider = FixtureProvider(("\ud800",))
    assert run(tmp_path, provider=provider).reason == "provider_error"
    assert provider.calls == 1


def test_naive_clock_and_input_limits_are_rejected(tmp_path):
    with pytest.raises(ValidationError):
        run(tmp_path, now=NOW.replace(tzinfo=None))
    payload = fixture_request().model_dump()
    payload["task"] = "x" * 4001
    with pytest.raises(ValidationError):
        ModelRequest(**payload)


def test_model_smoke_cli_sanitizes_storage_error(monkeypatch, capsys):
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("sensitive storage detail")

    monkeypatch.setattr("ai_trader.llm.runtime.InvocationJournal", broken)
    monkeypatch.setattr(sys, "argv", ["ai-trader", "llm-smoke"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    output = capsys.readouterr().err
    assert "OperationalError" in output and "sensitive storage detail" not in output


@pytest.mark.parametrize("change", ["purpose", "future", "checksum", "decision_time"])
def test_context_validation_before_provider_call(change):
    payload = fixture_request().model_dump()
    if change == "purpose":
        payload["context"]["purpose"] = "indexing"
    elif change == "future":
        payload["context"]["hits"][0]["available_at"] = NOW
    elif change == "checksum":
        payload["context"]["hits"][0]["text"] = "changed text"
    else:
        payload["decision_time"] = NOW
    with pytest.raises(ValidationError):
        ModelRequest(**payload)


def test_cli_smoke_is_offline_summarized_and_restart_safe(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AI_TRADER_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["ai-trader", "llm-smoke"])
    main()
    first = json.loads(capsys.readouterr().out)
    main()
    second = json.loads(capsys.readouterr().out)
    assert first == second
    assert first["offline_only"] and first["status"] == "completed"
    assert first["cost_basis"] == "synthetic_reservation_not_billing"
    assert "response" not in first
    assert len(attempts(tmp_path)) == 1
