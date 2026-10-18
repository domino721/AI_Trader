import hashlib
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from ai_trader.domain import Record
from ai_trader.knowledge.models import Identifier, SearchReport, Text

Money = Annotated[Decimal, Field(ge=0, max_digits=16, decimal_places=8)]


class InvocationPolicy(Record):
    # This literal deliberately prevents configuring a paid provider at this stage.
    provider_id: Literal["offline_fixture"] = "offline_fixture"
    model_id: Literal["fixture-v1"] = "fixture-v1"
    enabled: bool = False
    monthly_call_limit: int = Field(default=0, ge=0, le=10000)
    monthly_reservation_limit_usd: Money = Decimal("0")
    attempt_reservation_usd: Money = Decimal("0")
    max_attempts: int = Field(default=1, ge=1, le=3)
    timeout_seconds: float = Field(default=10, gt=0, le=60)


class ModelRequest(Record):
    request_id: Identifier
    decision_time: AwareDatetime
    prompt_version: Identifier
    task: Text = Field(max_length=4000)
    context: SearchReport

    @model_validator(mode="after")
    def validate_context(self) -> "ModelRequest":
        if self.context.purpose != "model_context":
            raise ValueError("model context permission is required")
        if self.context.decision_time != self.decision_time:
            raise ValueError("context and request decision times differ")
        for hit in self.context.hits:
            if hit.available_at > self.decision_time:
                raise ValueError("future model evidence")
            if hashlib.sha256(hit.text.encode()).hexdigest() != hit.text_sha256:
                raise ValueError("model context checksum mismatch")
        if len(self.model_dump_json().encode()) > 65536:
            raise ValueError("model request exceeds offline input limit")
        return self

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class ProviderReply(Record):
    model_id: Text
    raw_text: str
    input_tokens: int = Field(ge=0, strict=True)
    output_tokens: int = Field(ge=0, strict=True)

    @field_validator("raw_text")
    @classmethod
    def valid_utf8(cls, value: str) -> str:
        value.encode("utf-8")
        return value


class InvocationResult(Record):
    request_id: Identifier
    status: Literal["completed", "abstained"]
    reason: Identifier
    attempts: int = Field(ge=0)
    reserved_usd: Money
    provider_id: Literal["offline_fixture"] = "offline_fixture"
    model_id: Literal["fixture-v1"] = "fixture-v1"
    response: dict[str, Any] | None = None
    offline_only: Literal[True] = True
    cost_basis: Literal["synthetic_reservation_not_billing"] = "synthetic_reservation_not_billing"
    untrusted_proposal_only: Literal[True] = True
    historical_backtest_approved: Literal[False] = False
    trading_approved: Literal[False] = False

    def summary(self) -> dict:
        # CLI output contains no prompts, source text, provider payload or exceptions.
        return self.model_dump(mode="json", exclude={"response"})
