from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai_trader.domain import Snapshot
from ai_trader.fixture import demo_snapshot
from ai_trader.research import deliberate


def test_demo_proposals_have_all_roles_and_known_evidence():
    snapshot = demo_snapshot()
    result = deliberate(snapshot)
    assert result.engine == "deterministic_demo"
    for row in snapshot.observations:
        opinions = [o for o in result.opinions if o.symbol == row.symbol]
        assert {o.role for o in opinions} == {"value", "momentum", "quant"}
        assert all(o.evidence_ids == (row.source_id,) for o in opinions)
    assert result.target_weights["DEMO_A"] == Decimal("0.083333")
    assert result.target_weights["DEMO_B"] == 0
    assert len(result.objections) == 2


@pytest.mark.parametrize("days, message", [(1, "future evidence"), (-8, "stale")])
def test_unavailable_or_stale_evidence_is_rejected(days, message):
    snapshot = demo_snapshot()
    data = snapshot.model_dump()
    data["observations"][0]["available_at"] = snapshot.as_of + timedelta(days=days)
    with pytest.raises(ValidationError, match=message):
        Snapshot.model_validate(data)


def test_naive_decision_time_is_rejected():
    data = demo_snapshot().model_dump()
    data["as_of"] = data["as_of"].replace(tzinfo=None)
    with pytest.raises(ValidationError, match="timezone"):
        Snapshot.model_validate(data)


def test_duplicate_symbol_is_rejected():
    data = demo_snapshot().model_dump()
    data["observations"] = [data["observations"][0], data["observations"][0]]
    with pytest.raises(ValidationError, match="duplicate symbols"):
        Snapshot.model_validate(data)


def test_nonfinite_signal_is_rejected():
    data = demo_snapshot().model_dump()
    data["observations"][0]["momentum_12m"] = float("nan")
    with pytest.raises(ValidationError):
        Snapshot.model_validate(data)
