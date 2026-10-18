from typing import Protocol

from ai_trader.llm.models import ModelRequest, ProviderReply


class RetryableBeforeDispatch(Exception):
    """Adapter guarantees no request was dispatched; a new reserved attempt is safe."""


class ProviderTimeout(Exception):
    """Completion is uncertain. Do not automatically retry or release the reservation."""


class Provider(Protocol):
    provider_id: str
    model_id: str

    def generate(self, request: ModelRequest, *, timeout_seconds: float) -> ProviderReply:
        """Adapters must honor transport timeouts; no tools/order authority is supplied."""
        ...


class FixtureProvider:
    """In-memory responses only: no SDK, URL, credential lookup or network access."""

    provider_id = "offline_fixture"
    model_id = "fixture-v1"

    def __init__(self, events: tuple[str | Exception, ...] | None = None):
        self.events = events or ('{"status":"abstain","reason":"offline_fixture"}',)
        self.calls = 0
        self.timeouts: list[float] = []

    def generate(self, request: ModelRequest, *, timeout_seconds: float) -> ProviderReply:
        self.timeouts.append(timeout_seconds)
        index = self.calls
        self.calls += 1
        event = self.events[min(index, len(self.events) - 1)]
        if isinstance(event, Exception):
            raise event
        return ProviderReply(
            model_id=self.model_id, raw_text=event, input_tokens=0, output_tokens=0
        )
