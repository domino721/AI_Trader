import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_trader.api import create_app
from ai_trader.ops.backup import backup, restore
from ai_trader.ops.locking import HostLock
from ai_trader.ops.readiness import readiness
from ai_trader.ops.runner import GRAPH, Operator
from ai_trader.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-test-token-not-a-secret-000000"


def config(root, **changes):
    return Settings(state_dir=root, knowledge_root=ROOT, _env_file=None, **changes)


def test_environment_mixing_and_insecure_production_are_rejected(tmp_path):
    dev = config(tmp_path / "state")
    dev.prepare_state()
    with pytest.raises(ValueError, match="another environment"):
        config(tmp_path / "state", environment="prod", api_token=TOKEN).prepare_state()
    with pytest.raises(ValidationError):
        Settings(environment="prod", _env_file=None)
    with pytest.raises(ValidationError):
        config(tmp_path / "other", environment="prod", api_token="short")
    with pytest.raises(ValidationError):
        config(tmp_path / "other", capital_usd=100, max_daily_loss_usd=101)
    with pytest.raises(ValidationError):
        config(tmp_path / "other", ops_schedule_seconds=1)


def test_ops_pipeline_records_dependencies_and_replays_across_restart(tmp_path):
    op = Operator(config(tmp_path))
    first = op.submit("once")
    assert first["status"] == "queued"
    result = op.execute("once")
    assert result["status"] == "succeeded"
    assert [s["name"] for s in result["steps"]] == [n for n, _ in GRAPH]
    assert all(s["status"] == "succeeded" for s in result["steps"])
    assert result["steps"][-1]["summary"]["offline_only"]
    again = Operator(config(tmp_path))
    assert again.submit("once")["status"] == "succeeded"
    assert again.execute("once") == result
    with pytest.raises(ValueError, match="conflict"):
        again.submit("once", datetime(2026, 10, 1, tzinfo=UTC))


def test_failure_blocks_downstream_and_error_text_is_not_disclosed(tmp_path, monkeypatch):
    op = Operator(config(tmp_path))
    op.submit("failure")

    def failing(*args):
        def bad():
            raise ValueError("sensitive raw document or secret")

        return {"verify_sources": bad}

    monkeypatch.setattr(op, "_tasks", failing)
    result = op.execute("failure")
    assert result["status"] == "failed"
    assert result["steps"][0]["status"] == "failed"
    assert all(s["status"] == "blocked" for s in result["steps"][1:])
    assert "sensitive raw" not in json.dumps(result)
    assert op.store.alerts()[0]["code"] == "validation_failed"


def test_single_host_lock_and_claim_prevent_duplicate_work(tmp_path):
    op = Operator(config(tmp_path))
    op.submit("one")
    op.submit("two")
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(lambda x: op.store.claim(x, x), ["one", "two"]))
    assert sum(claimed) == 1
    with HostLock(tmp_path):
        with pytest.raises(ValueError, match="already_active"):
            with HostLock(tmp_path):
                pass
        with pytest.raises(ValueError):
            backup(config(tmp_path), tmp_path.parent / "blocked-backup")


def test_dependency_checks_and_lost_owner_are_fenced(tmp_path):
    op = Operator(config(tmp_path))
    op.submit("crashed")
    assert op.store.claim("crashed", "old")
    with pytest.raises(ValueError, match="dependencies"):
        op.store.transition("crashed", "old", "offline_model", "running")
    with pytest.raises(ValueError, match="incomplete"):
        op.store.finish("crashed", "old", "succeeded")
    op.store.transition("crashed", "old", "verify_sources", "running")
    recovered = op.store.recover_stale(5, datetime.now(UTC) + timedelta(seconds=6))
    assert recovered == 1
    result = op.store.get("crashed")
    assert result["status"] == "interrupted"
    assert result["steps"][0]["status"] == "interrupted"
    assert all(s["status"] == "blocked" for s in result["steps"][1:])
    with pytest.raises(ValueError, match="lease_lost"):
        op.store.transition("crashed", "old", "verify_sources", "succeeded")
    assert op.execute("crashed")["status"] == "interrupted"


def test_process_death_releases_host_lock_and_recovery_does_not_redispatch(tmp_path):
    op = Operator(config(tmp_path))
    op.submit("process-crash")
    script = """
import os,sys
from pathlib import Path
from ai_trader.ops.locking import HostLock
from ai_trader.ops.store import OpsStore
root=Path(sys.argv[1])
with HostLock(root):
    store=OpsStore(root)
    assert store.claim('process-crash','dead-process')
    store.transition('process-crash','dead-process','verify_sources','running')
    os._exit(17)
"""
    completed = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True)
    assert completed.returncode == 17
    with HostLock(tmp_path):
        pass
    assert op.store.recover_stale(5, datetime.now(UTC) + timedelta(seconds=6)) == 1
    assert op.execute("process-crash")["status"] == "interrupted"


def test_schedule_restart_is_idempotent_and_missed_slots_raise_alert(tmp_path):
    cfg = config(tmp_path, ops_schedule_seconds=60)
    now = datetime(2026, 10, 18, tzinfo=UTC)
    Operator(cfg).schedule(now)
    Operator(cfg).schedule(now)
    assert len(Operator(cfg).store.list_runs()) == 1
    Operator(cfg).schedule(now + timedelta(minutes=3))
    op = Operator(cfg)
    assert len(op.store.list_runs()) == 2
    assert op.store.alerts()[0]["code"] == "missed_schedule_slots"
    assert all(r["status"] == "queued" for r in op.store.list_runs())


def test_backup_restore_checksums_and_environment(tmp_path):
    cfg = config(tmp_path / "state")
    op = Operator(cfg)
    op.submit("saved")
    op.execute("saved")
    target = tmp_path / "backup"
    assert backup(cfg, target)["status"] == "completed"
    destination = config(tmp_path / "restored")
    assert restore(destination, target)["status"] == "completed"
    assert Operator(destination).store.get("saved")["status"] == "succeeded"
    if os.name != "nt":
        assert (destination.state_dir / "operations.db").stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="new_state"):
        restore(destination, target)
    with pytest.raises(ValueError, match="environment"):
        restore(config(tmp_path / "wrong-env", environment="test"), target)
    path = target / "operations.db"
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="checksum"):
        restore(config(tmp_path / "corrupt"), target)
    assert not (tmp_path / "corrupt").exists()


def test_backup_rejects_symlink_and_restore_rejects_traversal(tmp_path):
    cfg = config(tmp_path / "state")
    cfg.prepare_state()
    (cfg.state_dir / "outside").symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError, match="symlink"):
        backup(cfg, tmp_path / "bad-backup")
    source = tmp_path / "malicious"
    source.mkdir()
    identity = (cfg.state_dir / ".environment.db").read_bytes()
    (source / ".environment.db").write_bytes(identity)
    (source / "backup-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "environment": "dev",
                "files": {
                    ".environment.db": hashlib.sha256(identity).hexdigest(),
                    "../escape": "x",
                },
            }
        )
    )
    with pytest.raises(ValueError, match="path_escape"):
        restore(config(tmp_path / "never-created"), source)
    assert not (tmp_path / "never-created").exists()


def test_production_api_requires_auth_and_does_not_expose_secrets(tmp_path):
    app = create_app(config(tmp_path, environment="prod", api_token=TOKEN))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ops").status_code == 200
        assert client.get("/ops/runs").status_code == 401
        assert client.post("/demo/runs", json={"request_id": "new-request"}).status_code == 401
        assert client.get("/openapi.json").status_code == 404
        headers = {"Authorization": "Bearer " + TOKEN}
        report = client.get("/ops/readiness", headers=headers).json()
        assert report["live_trading_ready"] is False
        assert "capital_not_configured" in report["live_blockers"]
        assert TOKEN not in json.dumps(report)
        assert client.get("/ops/runs", headers=headers).headers["Cache-Control"] == "no-store"
        response = client.post("/ops/runs", headers=headers, json={"run_id": "api-run"})
        assert response.status_code == 202
        for _ in range(50):
            result = client.get("/ops/runs/api-run", headers=headers).json()
            if result["status"] == "succeeded":
                break
            time.sleep(0.05)
        assert result["status"] == "succeeded"
        assert client.get("/ready", headers=headers).status_code == 200
        script = client.get("/ops/app.js").text
        assert "innerHTML" not in script and "localStorage" not in script
        assert (
            client.post("/ops/runs", headers=headers, json={"run_id": "../bad"}).status_code == 422
        )
        assert (
            client.post(
                "/ops/runs",
                headers=headers,
                json={"run_id": "api-run", "decision_time": "2020-01-01T00:00:00Z"},
            ).status_code
            == 409
        )


def test_readiness_is_false_when_worker_or_storage_is_unavailable(tmp_path, monkeypatch):
    op = Operator(config(tmp_path))
    assert not readiness(op)["runtime_ready"]
    op.worker_alive = True
    assert readiness(op)["runtime_ready"]

    def broken():
        raise sqlite3.OperationalError("sensitive database detail")

    monkeypatch.setattr(op.store, "connect", broken)
    result = readiness(op)
    assert not result["runtime_ready"]
    assert "sensitive" not in json.dumps(result)
