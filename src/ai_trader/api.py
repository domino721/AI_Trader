from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ai_trader import __version__
from ai_trader.data.archive import Archive
from ai_trader.data.models import DataSnapshot
from ai_trader.domain import DemoRun
from ai_trader.service import run_demo
from ai_trader.settings import Settings
from ai_trader.store import RunStore


class DemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    app = FastAPI(title="AI Trader Research", version=__version__)

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

    @app.post("/demo/runs", response_model=DemoRun)
    def demo(request: DemoRequest) -> DemoRun:
        return run_demo(request.request_id, config)

    @app.get("/demo/runs/{request_id}", response_model=DemoRun)
    def get_run(request_id: str) -> DemoRun:
        run = RunStore(config.state_dir).get(request_id)
        if run is None:
            raise HTTPException(status_code=404, detail="demo run not found")
        return run

    @app.get("/data/snapshots/{snapshot_id}", response_model=DataSnapshot)
    def get_snapshot(snapshot_id: str) -> DataSnapshot:
        try:
            return Archive(config.state_dir).load_snapshot(snapshot_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="snapshot not found") from None
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid or corrupt snapshot") from None

    return app
