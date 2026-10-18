import secrets
import sqlite3
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ai_trader import __version__
from ai_trader.data.archive import Archive
from ai_trader.data.models import DataSnapshot
from ai_trader.domain import DemoRun
from ai_trader.ops.readiness import readiness
from ai_trader.ops.runner import GRAPH, PIPELINE, Operator
from ai_trader.service import run_demo
from ai_trader.settings import Settings
from ai_trader.store import RunStore


class DemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class OpsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    decision_time: AwareDatetime | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    operator = Operator(config)

    @asynccontextmanager
    async def lifespan(app):
        worker = threading.Thread(target=operator.serve, daemon=True)
        worker.start()
        yield
        operator.stop.set()
        worker.join(timeout=5)

    app = FastAPI(
        title="AI Trader Research",
        version=__version__,
        lifespan=lifespan,
        docs_url=None if config.environment == "prod" else "/docs",
        redoc_url=None if config.environment == "prod" else "/redoc",
        openapi_url=None if config.environment == "prod" else "/openapi.json",
    )
    app.state.operator = operator

    def authorize(request: Request):
        if config.api_token is not None:
            expected = "Bearer " + config.api_token.get_secret_value()
            supplied = request.headers.get("authorization", "")
            if not secrets.compare_digest(supplied.encode(), expected.encode()):
                raise HTTPException(status_code=401, detail="authentication required")

    protected = [Depends(authorize)]

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        return response

    static = Path(__file__).parent / "ops/static"

    @app.get("/ops", include_in_schema=False)
    def dashboard():
        return FileResponse(static / "index.html", media_type="text/html")

    @app.get("/ops/app.js", include_in_schema=False)
    def dashboard_script():
        return FileResponse(static / "app.js", media_type="application/javascript")

    @app.get("/ops/style.css", include_in_schema=False)
    def dashboard_styles():
        return FileResponse(static / "style.css", media_type="text/css")

    @app.get("/ops/readiness", dependencies=protected)
    def operational_readiness():
        return readiness(operator)

    @app.get("/ready", dependencies=protected)
    def ready():
        report = readiness(operator)
        return JSONResponse(report, status_code=200 if report["runtime_ready"] else 503)

    @app.get("/ops/graph", dependencies=protected)
    def graph():
        return {
            "pipeline": PIPELINE,
            "steps": [{"name": name, "dependencies": deps} for name, deps in GRAPH],
            "external_model_calls": False,
            "trading_approved": False,
        }

    @app.get("/ops/runs", dependencies=protected)
    def operations_runs():
        return operator.store.list_runs()

    @app.get("/ops/alerts", dependencies=protected)
    def operations_alerts():
        return operator.store.alerts()

    @app.post("/ops/runs", dependencies=protected, status_code=202)
    def start_operations(request: OpsRequest):
        try:
            return operator.submit(request.run_id, request.decision_time)
        except ValueError:
            raise HTTPException(
                status_code=409, detail="run identity or request conflict"
            ) from None

    @app.get("/ops/runs/{run_id}", dependencies=protected)
    def operations_run(run_id: str):
        result = operator.store.get(run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="run not found")
        return result

    @app.exception_handler(sqlite3.Error)
    async def storage_error(request, error):
        return JSONResponse({"detail": "state storage unavailable"}, status_code=503)

    @app.get("/health")
    def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "version": __version__,
            "execution_mode": config.execution_mode,
            "analyst_engine": "deterministic_demo",
            "live_execution_available": False,
            "kill_switch": config.kill_switch,
        }

    @app.post("/demo/runs", response_model=DemoRun, dependencies=protected)
    def demo(request: DemoRequest) -> DemoRun:
        return run_demo(request.request_id, config)

    @app.get("/demo/runs/{request_id}", response_model=DemoRun, dependencies=protected)
    def get_run(request_id: str) -> DemoRun:
        run = RunStore(config.state_dir).get(request_id)
        if run is None:
            raise HTTPException(status_code=404, detail="demo run not found")
        return run

    @app.get("/data/snapshots/{snapshot_id}", response_model=DataSnapshot, dependencies=protected)
    def get_snapshot(snapshot_id: str) -> DataSnapshot:
        try:
            return Archive(config.state_dir).load_snapshot(snapshot_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="snapshot not found") from None
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid or corrupt snapshot") from None

    return app
