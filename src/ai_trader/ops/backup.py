import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from ai_trader.ops.locking import HostLock
from ai_trader.ops.store import OpsStore, timestamp
from ai_trader.settings import Settings


def backup(settings: Settings, target: Path):
    root = settings.prepare_state()
    target = target.resolve()
    if target.is_relative_to(root) or root.is_relative_to(target) or target.exists():
        raise ValueError("backup_requires_new_directory_outside_state")
    with HostLock(root):
        store = OpsStore(root)
        with store.connect() as db:
            if db.execute("SELECT 1 FROM runs WHERE status='running'").fetchone():
                raise ValueError("interrupted_runs_must_be_recovered_before_backup")
        target.mkdir(parents=True, mode=0o700)
        files = {}
        for source in sorted(root.rglob("*")):
            if source.is_symlink():
                raise ValueError("backup_does_not_follow_symlinks")
            if not source.is_file() or source.name == ".operator.lock":
                continue
            if (
                source.name.endswith(("-wal", "-shm", "-journal"))
                or source.name.startswith(".env")
                and source.name != ".environment.db"
            ):
                continue
            relative = source.relative_to(root)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with source.open("rb") as stream:
                is_sqlite = stream.read(16) == b"SQLite format 3\x00"
            if is_sqlite:
                with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
                    with closing(sqlite3.connect(destination)) as dst:
                        src.backup(dst)
            else:
                shutil.copyfile(source, destination)
            destination.chmod(0o600)
            files[relative.as_posix()] = hashlib.sha256(destination.read_bytes()).hexdigest()
        manifest = {
            "schema_version": "1.0",
            "environment": settings.environment,
            "created_at": timestamp(),
            "files": files,
        }
        path = target / "backup-manifest.json"
        path.write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
        path.chmod(0o600)
        return {"status": "completed", "files": len(files), "environment": settings.environment}


def restore(settings: Settings, source: Path):
    target = settings.state_dir.resolve()
    if source.is_symlink():
        raise ValueError("restore_source_must_not_be_symlink")
    source = source.resolve()
    if target.exists():
        raise ValueError("restore_requires_new_state_directory")
    manifest = json.loads((source / "backup-manifest.json").read_bytes())
    if (
        manifest.get("schema_version") != "1.0"
        or manifest.get("environment") != settings.environment
    ):
        raise ValueError("backup_environment_or_version_mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict) or ".environment.db" not in files:
        raise ValueError("backup_manifest_incomplete")
    for name, digest in files.items():
        path = Path(name)
        actual = (source / path).resolve()
        if path.is_absolute() or ".." in path.parts or not actual.is_relative_to(source):
            raise ValueError("backup_path_escape")
        if hashlib.sha256(actual.read_bytes()).hexdigest() != digest:
            raise ValueError("backup_checksum_mismatch")
    target.mkdir(parents=True, mode=0o700)
    try:
        for name in files:
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(source / name, destination)
            destination.chmod(0o600)
        settings.prepare_state()
        for path in target.rglob("*"):
            if path.is_file():
                with path.open("rb") as stream:
                    is_sqlite = stream.read(16) == b"SQLite format 3\x00"
                if is_sqlite:
                    with closing(sqlite3.connect(path)) as db:
                        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                            raise ValueError("restored_database_integrity_failed")
    except Exception:
        shutil.rmtree(target)
        raise
    return {"status": "completed", "files": len(files), "environment": settings.environment}
