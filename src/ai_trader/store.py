import sqlite3
from pathlib import Path

from ai_trader.domain import DemoRun


class RunStore:
    """Local demo audit storage. No persistent broker account or real order ledger."""

    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "runs.db"
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS runs ("
                "request_id TEXT PRIMARY KEY, run_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)"
            )

    def get(self, request_id: str) -> DemoRun | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT payload FROM runs WHERE request_id = ?", (request_id,)
            ).fetchone()
        return DemoRun.model_validate_json(row[0]) if row else None

    def save(self, run: DemoRun) -> DemoRun:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO runs (request_id, run_id, payload) VALUES (?, ?, ?) "
                "ON CONFLICT(request_id) DO NOTHING",
                (run.request_id, run.run_id, run.model_dump_json()),
            )
        saved = self.get(run.request_id)
        if saved is None:
            raise RuntimeError("audit write failed")
        return saved
