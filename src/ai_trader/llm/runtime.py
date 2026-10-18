"""Offline invocation journal with atomic reservations and conservative duplicate handling."""

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import AwareDatetime, TypeAdapter

from ai_trader.llm.models import InvocationPolicy, InvocationResult, ModelRequest, ProviderReply
from ai_trader.llm.provider import Provider, ProviderTimeout, RetryableBeforeDispatch

MAX_RESPONSE_CHARS = 65536


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("nonfinite JSON number")


class InvocationJournal:
    def __init__(self, state_dir: Path):
        directory = state_dir / "llm"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "invocations.db"
        self.path.touch(mode=0o600, exist_ok=True)
        self.path.chmod(0o600)
        with self.connect() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS runs (request_id TEXT PRIMARY KEY, "
                "fingerprint TEXT NOT NULL, request_json TEXT NOT NULL, policy_json TEXT NOT NULL, "
                "started_at TEXT NOT NULL, result_json TEXT);"
                "CREATE TABLE IF NOT EXISTS attempts (request_id TEXT NOT NULL, "
                "number INTEGER NOT NULL, month TEXT NOT NULL, reservation TEXT NOT NULL, "
                "outcome TEXT NOT NULL, raw_text TEXT, raw_sha256 TEXT, truncated INTEGER, "
                "reply_json TEXT, PRIMARY KEY(request_id, number));"
            )

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def start(
        self, request: ModelRequest, policy: InvocationPolicy, now: datetime
    ) -> InvocationResult | str | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT fingerprint,result_json FROM runs WHERE request_id=?",
                (request.request_id,),
            ).fetchone()
            if row:
                if row[0] != request.fingerprint:
                    return "request_id_conflict"
                if row[1] is not None:
                    return InvocationResult.model_validate_json(row[1])
                # Another process may be active, or the previous one may have crashed.
                return "inflight_or_interrupted"
            db.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,NULL)",
                (
                    request.request_id,
                    request.fingerprint,
                    request.model_dump_json(),
                    policy.model_dump_json(),
                    now.isoformat(),
                ),
            )
        return None

    def reserve(self, request_id: str, policy: InvocationPolicy, now: datetime) -> str | None:
        month = now.astimezone(UTC).strftime("%Y-%m")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT reservation FROM attempts WHERE month=?", (month,)).fetchall()
            if len(rows) >= policy.monthly_call_limit:
                return "monthly_call_limit"
            total = sum((Decimal(row[0]) for row in rows), Decimal("0"))
            if total + policy.attempt_reservation_usd > policy.monthly_reservation_limit_usd:
                return "monthly_reservation_limit"
            number = (
                db.execute(
                    "SELECT count(*) FROM attempts WHERE request_id=?", (request_id,)
                ).fetchone()[0]
                + 1
            )
            db.execute(
                "INSERT INTO attempts VALUES (?,?,?,?,?,NULL,NULL,0,NULL)",
                (request_id, number, month, str(policy.attempt_reservation_usd), "reserved"),
            )
        return None

    def record(self, request_id: str, outcome: str, reply: ProviderReply | None = None) -> None:
        raw = reply.raw_text if reply else None
        # Preserve bounded original replies, including invalid JSON. Oversized content
        # retains a prefix and original hash, with explicit truncation in the journal.
        digest = hashlib.sha256(raw.encode()).hexdigest() if raw is not None else None
        truncated = raw is not None and len(raw) > MAX_RESPONSE_CHARS
        payload = reply.model_dump(exclude={"raw_text"}) if reply else None
        with self.connect() as db:
            db.execute(
                "UPDATE attempts SET outcome=?,raw_text=?,raw_sha256=?,truncated=?,reply_json=? "
                "WHERE request_id=? AND number="
                "(SELECT max(number) FROM attempts WHERE request_id=?)",
                (
                    outcome,
                    raw[:MAX_RESPONSE_CHARS] if raw is not None else None,
                    digest,
                    int(truncated),
                    json.dumps(payload) if payload else None,
                    request_id,
                    request_id,
                ),
            )

    def result(
        self, request_id: str, reason: str, response: dict | None = None
    ) -> InvocationResult:
        with self.connect() as db:
            rows = db.execute(
                "SELECT reservation FROM attempts WHERE request_id=?", (request_id,)
            ).fetchall()
        return InvocationResult(
            request_id=request_id,
            status="completed" if response is not None else "abstained",
            reason=reason,
            attempts=len(rows),
            reserved_usd=sum((Decimal(row[0]) for row in rows), Decimal("0")),
            response=response,
        )

    def finish(self, result: InvocationResult) -> InvocationResult:
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE runs SET result_json=? WHERE request_id=? AND result_json IS NULL",
                (result.model_dump_json(), result.request_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("run cannot be overwritten")
        return result


def invoke(
    request: ModelRequest,
    policy: InvocationPolicy,
    provider: Provider,
    state_dir: Path,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> InvocationResult:
    journal = InvocationJournal(state_dir)

    def now() -> datetime:
        return TypeAdapter(AwareDatetime).validate_python(clock())

    existing = journal.start(request, policy, now())
    if isinstance(existing, InvocationResult):
        return existing
    if existing is not None:
        return journal.result(request.request_id, existing)

    def stop(reason: str) -> InvocationResult:
        return journal.finish(journal.result(request.request_id, reason))

    if not policy.enabled:
        return stop("invocation_disabled")
    if provider.provider_id != policy.provider_id or provider.model_id != policy.model_id:
        return stop("provider_identity_mismatch")
    if not request.context.hits:
        return stop("no_eligible_evidence")
    for _ in range(policy.max_attempts):
        if blocked := journal.reserve(request.request_id, policy, now()):
            return stop(blocked)
        try:
            reply = ProviderReply.model_validate(
                provider.generate(request, timeout_seconds=policy.timeout_seconds)
            )
        except RetryableBeforeDispatch:
            journal.record(request.request_id, "retryable_before_dispatch")
            continue
        except ProviderTimeout:
            journal.record(request.request_id, "timeout_uncertain")
            return stop("timeout_uncertain")
        except Exception:
            # Provider exceptions can contain credentials or source text; never retain them.
            journal.record(request.request_id, "provider_error")
            return stop("provider_error")
        journal.record(request.request_id, "response_received", reply)
        if reply.model_id != policy.model_id:
            return stop("response_model_mismatch")
        if len(reply.raw_text) > MAX_RESPONSE_CHARS:
            return stop("response_too_large")
        try:
            parsed = json.loads(
                reply.raw_text, object_pairs_hook=_unique_object, parse_constant=_nonfinite
            )
            # Floats such as 1e999 also need rejecting, including nested values.
            json.dumps(parsed, allow_nan=False)
            if not isinstance(parsed, dict):
                return stop("invalid_response_shape")
        except (ValueError, RecursionError):
            return stop("invalid_response_json")
        return journal.finish(journal.result(request.request_id, "offline_response", parsed))
    return stop("retry_limit")
