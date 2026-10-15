from uuid import uuid4

from ai_trader.domain import DemoRun, RiskPolicy
from ai_trader.execution import simulate_from_cash
from ai_trader.fixture import demo_execution_bars, demo_snapshot
from ai_trader.research import deliberate
from ai_trader.risk import check_targets
from ai_trader.settings import Settings
from ai_trader.store import RunStore


def run_demo(request_id: str, settings: Settings) -> DemoRun:
    store = RunStore(settings.state_dir)
    existing = store.get(request_id)
    if existing is not None:
        return existing
    snapshot = demo_snapshot()
    deliberation = deliberate(snapshot)
    risk = check_targets(
        deliberation.target_weights,
        {},
        {row.symbol for row in snapshot.observations},
        RiskPolicy(),
        kill_switch=settings.kill_switch,
    )
    simulation = (
        simulate_from_cash(snapshot, deliberation.target_weights, demo_execution_bars())
        if risk.approved
        else None
    )
    return store.save(
        DemoRun(
            run_id=str(uuid4()),
            request_id=request_id,
            as_of=snapshot.as_of,
            deliberation=deliberation,
            risk=risk,
            simulation=simulation,
        )
    )
