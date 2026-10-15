from datetime import timedelta
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)


class Observation(Record):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,19}$")
    available_at: AwareDatetime
    source_id: str
    close: Decimal = Field(gt=0)
    book_value_per_share: Decimal = Field(gt=0)
    return_on_equity: float
    momentum_12m: float
    annualized_volatility: float = Field(gt=0)


class Snapshot(Record):
    as_of: AwareDatetime
    observations: tuple[Observation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_availability(self) -> "Snapshot":
        symbols = [row.symbol for row in self.observations]
        if len(symbols) != len(set(symbols)):
            raise ValueError("duplicate symbols")
        for row in self.observations:
            if row.available_at > self.as_of:
                raise ValueError("future evidence is unavailable at the decision time")
            if self.as_of - row.available_at > timedelta(days=7):
                raise ValueError("stale demo snapshot")
        return self


class Opinion(Record):
    role: Literal["value", "momentum", "quant"]
    symbol: str
    target_weight: Decimal = Field(ge=0, le=1)
    rationale: str
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class Deliberation(Record):
    engine: Literal["deterministic_demo"] = "deterministic_demo"
    opinions: tuple[Opinion, ...]
    objections: tuple[str, ...]
    target_weights: dict[str, Decimal]
    aggregation_policy: str = "equal-weight mean of three rule-based opinions"


class RiskPolicy(Record):
    max_position_weight: Decimal = Field(default=Decimal("0.10"), gt=0, le=1)
    max_gross_weight: Decimal = Field(default=Decimal("0.80"), gt=0, le=1)
    min_cash_weight: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)
    max_turnover_weight: Decimal = Field(default=Decimal("0.20"), gt=0, le=2)


class RiskCheck(Record):
    approved: bool
    reasons: tuple[str, ...]


class ExecutionBar(Record):
    symbol: str
    timestamp: AwareDatetime
    open: Decimal = Field(gt=0)


class Fill(Record):
    symbol: str
    timestamp: AwareDatetime
    quantity: int = Field(gt=0)
    price: Decimal = Field(gt=0)
    fee: Decimal = Field(ge=0)


class Simulation(Record):
    initial_cash: Decimal
    remaining_cash: Decimal
    fills: tuple[Fill, ...]
    fee_bps: Decimal
    slippage_bps: Decimal


class DemoRun(Record):
    run_id: str
    request_id: str
    as_of: AwareDatetime
    data_kind: Literal["synthetic"] = "synthetic"
    execution_mode: Literal["simulation"] = "simulation"
    deliberation: Deliberation
    risk: RiskCheck
    simulation: Simulation | None
