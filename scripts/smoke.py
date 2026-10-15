"""Validate a running loopback API with a fresh synthetic decision and audit replay."""

import json
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4


def main() -> None:
    opener = build_opener(ProxyHandler({}))
    base = "http://127.0.0.1:8000"

    def request(path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        message = Request(base + path, data=data, headers={"Content-Type": "application/json"})
        with opener.open(message, timeout=10) as response:
            return json.load(response)

    health = request("/health")
    assert health["status"] == "ok"
    assert health["execution_mode"] == "simulation"
    assert health["live_execution_available"] is False
    request_id = "smoke-" + uuid4().hex
    payload = {"request_id": request_id}
    first = request("/demo/runs", payload)
    assert first["data_kind"] == "synthetic"
    assert first["deliberation"]["engine"] == "deterministic_demo"
    assert len(first["deliberation"]["opinions"]) == 6
    if health["kill_switch"]:
        assert first["risk"]["approved"] is False
        assert first["simulation"] is None
    else:
        assert first["risk"]["approved"] is True
        assert len(first["simulation"]["fills"]) == 1
        assert first["simulation"]["remaining_cash"] == "9190.79"
    assert request("/demo/runs/" + request_id) == first
    assert request("/demo/runs", payload) == first
    print(
        json.dumps(
            {
                "status": "passed",
                "request_id": request_id,
                "checks": [
                    "health",
                    "six_rule_based_opinions",
                    "risk_gate",
                    "simulation_or_kill_switch",
                    "audit_readback",
                    "idempotent_replay",
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
