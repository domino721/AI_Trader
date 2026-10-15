from concurrent.futures import ThreadPoolExecutor

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from ai_trader.api import create_app
from ai_trader.service import run_demo
from ai_trader.settings import Settings


@pytest.fixture
def anyio_backend():
    return "asyncio"


def client_for(settings):
    return AsyncClient(transport=ASGITransport(app=create_app(settings)), base_url="http://test")


@pytest.mark.anyio
async def test_api_records_and_replays_a_demo_after_app_restart(tmp_path):
    settings = Settings(state_dir=tmp_path, _env_file=None)
    async with client_for(settings) as client:
        health = (await client.get("/health")).json()
        assert health["live_execution_available"] is False
        first = await client.post("/demo/runs", json={"request_id": "api-test-001"})
        assert first.status_code == 200
        payload = first.json()
        assert payload["data_kind"] == "synthetic"
        assert payload["deliberation"]["engine"] == "deterministic_demo"
        assert payload["risk"]["approved"] is True
        assert len(payload["simulation"]["fills"]) == 1
    async with client_for(settings) as restarted:
        assert (await restarted.get("/demo/runs/api-test-001")).json() == payload
        assert (
            await restarted.post("/demo/runs", json={"request_id": "api-test-001"})
        ).json() == payload


def test_kill_switch_blocks_new_fills_and_audits_the_rejection(tmp_path):
    settings = Settings(state_dir=tmp_path, kill_switch=True, _env_file=None)
    result = run_demo("blocked-request", settings)
    assert not result.risk.approved
    assert result.risk.reasons == ("kill switch enabled",)
    assert result.simulation is None
    assert run_demo("blocked-request", settings) == result


def test_concurrent_retries_produce_one_audit_result(tmp_path):
    settings = Settings(state_dir=tmp_path, _env_file=None)
    with ThreadPoolExecutor(max_workers=4) as executor:
        runs = list(executor.map(lambda _: run_demo("same-request", settings), range(4)))
    assert len({run.run_id for run in runs}) == 1


@pytest.mark.anyio
async def test_unknown_run_and_malformed_request(tmp_path):
    async with client_for(Settings(state_dir=tmp_path, _env_file=None)) as client:
        assert (await client.get("/demo/runs/does-not-exist")).status_code == 404
        assert (await client.post("/demo/runs", json={"request_id": "short"})).status_code == 422
        assert (
            await client.post("/demo/runs", json={"request_id": "test-request", "live": True})
        ).status_code == 422


def test_live_mode_cannot_be_enabled_by_configuration():
    with pytest.raises(ValidationError):
        Settings(execution_mode="live", _env_file=None)
