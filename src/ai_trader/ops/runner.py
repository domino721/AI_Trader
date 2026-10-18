import hashlib
import json
import re
import threading
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import AwareDatetime, TypeAdapter

from ai_trader.knowledge.catalog import check_catalog, load_catalog
from ai_trader.knowledge.index import (
    build_knowledge_snapshot,
    evaluate_knowledge_benchmark,
    load_evaluation_benchmark,
)
from ai_trader.llm.fixture import fixture_request
from ai_trader.llm.models import InvocationPolicy
from ai_trader.llm.provider import FixtureProvider
from ai_trader.llm.runtime import invoke
from ai_trader.ops.locking import HostLock
from ai_trader.ops.store import OpsStore
from ai_trader.settings import Settings

PIPELINE = "offline-research-v2"
GRAPH = (
    ("verify_sources", ()),
    ("build_index", ("verify_sources",)),
    ("evaluate_retrieval", ("build_index",)),
    ("offline_model", ("evaluate_retrieval",)),
)


class Operator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = OpsStore(settings.prepare_state())
        self.stop = threading.Event()
        self.worker_alive = False
        self.last_slot = None

    def submit(self, run_id: str, decision_time: datetime | None = None):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", run_id):
            raise ValueError("invalid_run_id")
        if decision_time is not None:
            decision_time = TypeAdapter(AwareDatetime).validate_python(decision_time)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "pipeline": PIPELINE,
                    "environment": self.settings.environment,
                    "decision_time": decision_time.isoformat() if decision_time else None,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        self.store.create(
            run_id,
            fingerprint,
            PIPELINE,
            decision_time.isoformat() if decision_time else None,
            GRAPH,
        )
        return self.store.get(run_id)

    def _tasks(self, run_id, decision_time):
        root, state = self.settings.knowledge_root.resolve(), self.settings.state_dir
        shared = {}

        def verify():
            catalog = load_catalog(root / "docs/knowledge/catalog.json")
            report = check_catalog(catalog, root, decision_time, "model_context")
            if report["status"] != "passed":
                raise ValueError("source_gate_failed")
            shared["catalog"] = catalog
            return {"documents": len(catalog.documents), "status": "passed"}

        def index():
            snap = build_knowledge_snapshot(shared["catalog"], root, state)
            shared["snapshot"] = snap
            return {"snapshot_id": snap.snapshot_id, "chunks": len(snap.chunks)}

        def evaluate():
            bench = load_evaluation_benchmark(root / "docs/knowledge/eval-benchmark.json")
            report = evaluate_knowledge_benchmark(bench, shared["snapshot"])
            if report.status != "passed":
                raise ValueError("retrieval_gate_failed")
            return {
                "status": report.status,
                "passed_cases": report.passed_cases,
                "total_cases": report.total_cases,
                "scope": "fixed_fixture_evaluation",
            }

        def model():
            # Explicit synthetic context; do not claim real RAG/analyst integration.
            result = invoke(
                fixture_request("ops-" + run_id),
                InvocationPolicy(enabled=True, monthly_call_limit=1000),
                FixtureProvider(),
                state,
            )
            if result.status != "completed":
                raise ValueError("offline_model_blocked")
            return result.summary()

        return {
            "verify_sources": verify,
            "build_index": index,
            "evaluate_retrieval": evaluate,
            "offline_model": model,
        }

    def execute(self, run_id, *, _host_owned=False):
        if not _host_owned:
            with HostLock(self.settings.prepare_state()):
                return self.execute(run_id, _host_owned=True)
        owner = uuid4().hex
        if not self.store.claim(run_id, owner):
            return self.store.get(run_id)
        run = self.store.get(run_id)
        if run["pipeline"] != PIPELINE:
            self.store.finish(run_id, owner, "failed", "unsupported_pipeline_version")
            return self.store.get(run_id)
        done = threading.Event()

        def heartbeat():
            while not done.wait(self.settings.ops_lease_seconds / 3):
                if self.stop.is_set() or not self.store.heartbeat(run_id, owner):
                    break

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            tasks = self._tasks(run_id, datetime.fromisoformat(run["decision_time"]))
            for name, _ in GRAPH:
                if self.stop.is_set():
                    self.store.finish(run_id, owner, "interrupted", "worker_stopped")
                    break
                self.store.transition(run_id, owner, name, "running")
                try:
                    summary = tasks[name]()
                except Exception as error:
                    code = (
                        "input_missing"
                        if isinstance(error, FileNotFoundError)
                        else "validation_failed"
                        if isinstance(error, ValueError)
                        else "io_failed"
                        if isinstance(error, OSError)
                        else "step_failed"
                    )
                    self.store.transition(run_id, owner, name, "failed", error_code=code)
                    self.store.finish(run_id, owner, "failed", code)
                    break
                self.store.transition(run_id, owner, name, "succeeded", summary)
            else:
                self.store.finish(run_id, owner, "succeeded")
        finally:
            done.set()
            thread.join(timeout=1)
        return self.store.get(run_id)

    def serve(self):
        with HostLock(self.settings.prepare_state()):
            self._serve()

    def _serve(self):
        self.worker_alive = True
        try:
            while not self.stop.is_set():
                self.store.recover_stale(self.settings.ops_lease_seconds)
                self.schedule()
                if queued := self.store.next_queued():
                    self.execute(queued, _host_owned=True)
                self.stop.wait(0.5)
        finally:
            self.worker_alive = False

    def schedule(self, now=None):
        interval = self.settings.ops_schedule_seconds
        if not interval:
            return
        slot = int((now or datetime.now(UTC)).timestamp()) // interval
        if slot == self.last_slot:
            return
        rid = f"scheduled-{interval}-{slot}"
        self.submit(rid)
        self.store.record_schedule_slot(interval, slot, rid)
        self.last_slot = slot
