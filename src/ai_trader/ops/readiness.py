import sqlite3

from ai_trader.ops.runner import Operator


def readiness(operator: Operator):
    settings = operator.settings
    writable = False
    try:
        settings.prepare_state()
        with operator.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS readiness_probe (id INTEGER)")
            db.execute("INSERT INTO readiness_probe VALUES (1)")
            db.rollback()
            writable = db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    except (OSError, ValueError, sqlite3.Error):
        pass
    reasons = [
        "live_transport_not_implemented",
        "paper_observation_not_accepted",
        "strategy_validation_incomplete",
        "broker_access_review_required",
        "host_acceptance_not_recorded",
        "external_outage_alerts_not_configured",
    ]
    if settings.capital_usd is None:
        reasons.append("capital_not_configured")
    if settings.max_daily_loss_usd is None or settings.max_drawdown_fraction is None:
        reasons.append("loss_limits_not_configured")
    return {
        "environment": settings.environment,
        "execution_mode": settings.execution_mode,
        "runtime_ready": writable and operator.worker_alive,
        "checks": {
            "state_writable": writable,
            "worker_alive": operator.worker_alive,
            "api_auth_configured": settings.api_token is not None,
        },
        "live_trading_ready": False,
        "live_blockers": reasons,
        "external_broker_and_market_checks": "not_run",
        "schedule_interval_seconds": settings.ops_schedule_seconds,
    }
