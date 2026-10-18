import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path


def timestamp(value: datetime | None = None) -> str:
    return (value or datetime.now(UTC)).astimezone(UTC).isoformat()


class OpsStore:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "operations.db"
        self.path.touch(mode=0o600, exist_ok=True)
        self.path.chmod(0o600)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                  run_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, pipeline TEXT NOT NULL,
                  status TEXT NOT NULL, decision_time TEXT NOT NULL, created_at TEXT NOT NULL,
                  started_at TEXT, heartbeat_at TEXT, finished_at TEXT,
                  owner TEXT, error_code TEXT);
                CREATE TABLE IF NOT EXISTS steps (
                  run_id TEXT NOT NULL, name TEXT NOT NULL, dependencies TEXT NOT NULL,
                  status TEXT NOT NULL, started_at TEXT, finished_at TEXT, summary TEXT,
                  error_code TEXT, PRIMARY KEY(run_id,name));
                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, step TEXT,
                  level TEXT NOT NULL, code TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS schedule_cursor (
                  interval INTEGER PRIMARY KEY, slot INTEGER);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, run_id, fingerprint, pipeline, decision_time, graph):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT fingerprint FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row:
                if row["fingerprint"] != fingerprint:
                    raise ValueError("request_id_conflict")
                return False
            now = timestamp()
            db.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,NULL,NULL,NULL,NULL,NULL)",
                (run_id, fingerprint, pipeline, "queued", decision_time or now, now),
            )
            db.executemany(
                "INSERT INTO steps VALUES (?,?,?,?,NULL,NULL,NULL,NULL)",
                [(run_id, name, json.dumps(deps), "pending") for name, deps in graph],
            )
            return True

    def _event(self, db, run_id, step, level, code):
        db.execute(
            "INSERT INTO events(run_id,step,level,code,created_at) VALUES (?,?,?,?,?)",
            (run_id, step, level, code, timestamp()),
        )

    def claim(self, run_id, owner):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM runs WHERE status='running'").fetchone():
                return False
            changed = db.execute(
                "UPDATE runs SET status='running',owner=?,started_at=?,heartbeat_at=? "
                "WHERE run_id=? AND status='queued'",
                (owner, timestamp(), timestamp(), run_id),
            ).rowcount
            return changed == 1

    def heartbeat(self, run_id, owner):
        with self.connect() as db:
            return (
                db.execute(
                    "UPDATE runs SET heartbeat_at=? WHERE run_id=? AND owner=? "
                    "AND status='running'",
                    (timestamp(), run_id, owner),
                ).rowcount
                == 1
            )

    def transition(self, run_id, owner, step, status, summary=None, error_code=None):
        if status not in {"running", "succeeded", "failed"}:
            raise ValueError("invalid_step_status")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute(
                "SELECT 1 FROM runs WHERE run_id=? AND owner=? AND status='running'",
                (run_id, owner),
            ).fetchone():
                raise ValueError("execution_lease_lost")
            old = db.execute(
                "SELECT status,dependencies FROM steps WHERE run_id=? AND name=?", (run_id, step)
            ).fetchone()
            expected = "pending" if status == "running" else "running"
            if not old or old["status"] != expected:
                raise ValueError("invalid_step_transition")
            if status == "running":
                done = {
                    r["name"]
                    for r in db.execute(
                        "SELECT name FROM steps WHERE run_id=? AND status='succeeded'", (run_id,)
                    )
                }
                if not set(json.loads(old["dependencies"])) <= done:
                    raise ValueError("dependencies_not_ready")
                db.execute(
                    "UPDATE steps SET status=?,started_at=? WHERE run_id=? AND name=?",
                    (status, timestamp(), run_id, step),
                )
            else:
                db.execute(
                    "UPDATE steps SET status=?,finished_at=?,summary=?,error_code=? "
                    "WHERE run_id=? AND name=?",
                    (status, timestamp(), json.dumps(summary or {}), error_code, run_id, step),
                )
            if error_code:
                self._event(db, run_id, step, "error", error_code)

    def finish(self, run_id, owner, status, error_code=None):
        if status not in {"succeeded", "failed", "interrupted"}:
            raise ValueError("invalid_run_status")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                status == "succeeded"
                and db.execute(
                    "SELECT 1 FROM steps WHERE run_id=? AND status!='succeeded'", (run_id,)
                ).fetchone()
            ):
                raise ValueError("cannot_finish_with_incomplete_steps")
            changed = db.execute(
                "UPDATE runs SET status=?,finished_at=?,error_code=? "
                "WHERE run_id=? AND owner=? AND status='running'",
                (status, timestamp(), error_code, run_id, owner),
            ).rowcount
            if changed != 1:
                raise ValueError("execution_lease_lost")
            db.execute(
                "UPDATE steps SET status='blocked',finished_at=?,error_code=? "
                "WHERE run_id=? AND status='pending'",
                (timestamp(), error_code or "upstream_not_completed", run_id),
            )
            if error_code:
                self._event(db, run_id, None, "error", error_code)

    def recover_stale(self, lease_seconds, now=None):
        cutoff = timestamp((now or datetime.now(UTC)) - timedelta(seconds=lease_seconds))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT run_id FROM runs WHERE status='running' AND heartbeat_at<?", (cutoff,)
            ).fetchall()
            for row in rows:
                rid = row["run_id"]
                db.execute(
                    "UPDATE runs SET status='interrupted',finished_at=?,error_code=? "
                    "WHERE run_id=?",
                    (timestamp(), "worker_heartbeat_expired", rid),
                )
                db.execute(
                    "UPDATE steps SET status=CASE status WHEN 'running' THEN 'interrupted' "
                    "ELSE 'blocked' END,finished_at=?,error_code=? "
                    "WHERE run_id=? AND status IN ('running','pending')",
                    (timestamp(), "worker_heartbeat_expired", rid),
                )
                self._event(db, rid, None, "error", "worker_heartbeat_expired")
            return len(rows)

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result.pop("owner")
            result.pop("fingerprint")
            result["steps"] = []
            for step in db.execute("SELECT * FROM steps WHERE run_id=? ORDER BY rowid", (run_id,)):
                data = dict(step)
                data["dependencies"] = json.loads(data["dependencies"])
                data["summary"] = json.loads(data["summary"]) if data["summary"] else None
                result["steps"].append(data)
            return result

    def list_runs(self, limit=50):
        if not 1 <= limit <= 100:
            raise ValueError("invalid_limit")
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT run_id,pipeline,status,created_at,finished_at,error_code FROM runs "
                    "ORDER BY rowid DESC LIMIT ?",
                    (limit,),
                )
            ]

    def alerts(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")]

    def next_queued(self):
        with self.connect() as db:
            row = db.execute(
                "SELECT run_id FROM runs WHERE status='queued' ORDER BY rowid LIMIT 1"
            ).fetchone()
            return row[0] if row else None

    def record_schedule_slot(self, interval, slot, run_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT slot FROM schedule_cursor WHERE interval=?", (interval,)
            ).fetchone()
            if previous and slot > previous[0] + 1:
                self._event(db, run_id, None, "warning", "missed_schedule_slots")
            db.execute(
                "INSERT INTO schedule_cursor VALUES (?,?) ON CONFLICT(interval) "
                "DO UPDATE SET slot=max(slot,excluded.slot)",
                (interval, slot),
            )
