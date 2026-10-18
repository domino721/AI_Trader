import os
from pathlib import Path


class HostLock:
    """OS releases the single-host operator lock even after an abrupt process exit."""

    def __init__(self, root: Path):
        self.path = root / ".operator.lock"
        self.stream = None

    def __enter__(self):
        self.stream = self.path.open("a+b")
        self.path.chmod(0o600)
        self.stream.seek(0)
        if self.path.stat().st_size == 0:
            self.stream.write(b"0")
            self.stream.flush()
        try:
            if os.name == "nt":
                import msvcrt

                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            self.stream = None
            raise ValueError("operator_or_backup_already_active") from None
        return self

    def __exit__(self, *args):
        if self.stream:
            if os.name == "nt":
                import msvcrt

                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close()
