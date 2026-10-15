import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from ai_trader.data.models import DataSnapshot, Receipt


def atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Archive:
    def __init__(self, root: Path):
        self.root = root / "market"
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "receipts.db"
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS receipts (request_key TEXT PRIMARY KEY, payload TEXT)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS attempts (request_key TEXT, provider TEXT, "
                "attempted_at TEXT, outcome TEXT)"
            )

    @staticmethod
    def key(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    def log(self, url: str, provider: str, outcome: str) -> None:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "INSERT INTO attempts VALUES (?, ?, ?, ?)",
                (self.key(url), provider, datetime.now(UTC).isoformat(), outcome),
            )

    def cached(self, url: str) -> Receipt | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "SELECT payload FROM receipts WHERE request_key = ?", (self.key(url),)
            ).fetchone()
        return Receipt.model_validate_json(row[0]) if row else None

    def read(self, receipt: Receipt) -> bytes:
        body = (self.root / "raw" / f"{receipt.sha256}.json").read_bytes()
        if hashlib.sha256(body).hexdigest() != receipt.sha256:
            raise ValueError("raw artifact checksum mismatch")
        return body

    def record(self, url: str, provider: str, body: bytes) -> Receipt:
        digest = hashlib.sha256(body).hexdigest()
        receipt = Receipt(
            request_key=self.key(url),
            provider=provider,
            url=url,
            sha256=digest,
            fetched_at=datetime.now(UTC),
        )
        path = self.root / "raw" / f"{digest}.json"
        if path.exists():
            if path.read_bytes() != body:
                raise ValueError("existing raw artifact is corrupt")
        else:
            atomic_write(path, body)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "INSERT INTO receipts VALUES (?, ?) ON CONFLICT(request_key) "
                "DO UPDATE SET payload = excluded.payload",
                (receipt.request_key, receipt.model_dump_json()),
            )
        return receipt

    def save_snapshot(self, snapshot: DataSnapshot) -> None:
        location = "snapshots" if snapshot.quality.research_approved else "quarantine"
        path = self.root / location / f"{snapshot.snapshot_id}.json"
        body = snapshot.model_dump_json(indent=2).encode()
        if path.exists() and path.read_bytes() != body:
            raise ValueError("immutable snapshot differs from existing artifact")
        if not path.exists():
            atomic_write(path, body)
        if snapshot.quality.research_approved:
            self.export(snapshot)

    def export(self, snapshot: DataSnapshot) -> None:
        directory = self.root / "normalized" / snapshot.snapshot_id
        manifest = directory / "exports.json"
        if manifest.exists():
            self.verify_exports(snapshot.snapshot_id)
            return
        directory.mkdir(parents=True, exist_ok=True)
        checksums = {}
        for name in ("prices", "actions", "filings"):
            rows = getattr(snapshot, name)
            if not rows:
                continue
            descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".pending-")
            os.close(descriptor)
            try:
                frame = pd.DataFrame([row.model_dump() for row in rows])
                with duckdb.connect(":memory:") as connection:
                    connection.from_df(frame).write_parquet(temporary)
                target = directory / f"{name}.parquet"
                os.replace(temporary, target)
                checksums[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
            finally:
                Path(temporary).unlink(missing_ok=True)
        atomic_write(manifest, json.dumps(checksums, sort_keys=True).encode())

    def verify_exports(self, snapshot_id: str) -> None:
        directory = self.root / "normalized" / snapshot_id
        manifest = json.loads((directory / "exports.json").read_bytes())
        if not isinstance(manifest, dict) or "prices.parquet" not in manifest:
            raise ValueError("incomplete export manifest")
        for name, digest in manifest.items():
            if name not in {"prices.parquet", "actions.parquet", "filings.parquet"}:
                raise ValueError("invalid export manifest")
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
                raise ValueError("normalized export checksum mismatch")

    def load_snapshot(self, snapshot_id: str) -> DataSnapshot:
        if len(snapshot_id) != 64 or any(c not in "0123456789abcdef" for c in snapshot_id):
            raise ValueError("invalid snapshot ID")
        for location in ("snapshots", "quarantine"):
            path = self.root / location / f"{snapshot_id}.json"
            if path.exists():
                snapshot = DataSnapshot.model_validate_json(path.read_bytes())
                if snapshot.snapshot_id != snapshot_id or snapshot_digest(snapshot) != snapshot_id:
                    raise ValueError("snapshot checksum mismatch")
                return snapshot
        raise FileNotFoundError("snapshot not found")


def snapshot_digest(snapshot: DataSnapshot) -> str:
    body = snapshot.model_dump(mode="json", exclude={"snapshot_id"})
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
