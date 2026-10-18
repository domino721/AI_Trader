import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_TRADER_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    environment: Literal["dev", "test", "prod"] = "dev"
    execution_mode: Literal["simulation"] = "simulation"
    state_dir: Path = Path(".local/dev")
    kill_switch: bool = False
    sec_user_agent: str | None = None
    api_token: SecretStr | None = None
    knowledge_root: Path = Path(".")
    ops_lease_seconds: int = Field(default=30, ge=5, le=300)
    ops_schedule_seconds: int = Field(default=0, ge=0, le=86400)
    capital_usd: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    max_daily_loss_usd: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    max_drawdown_fraction: Decimal | None = Field(default=None, gt=0, lt=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def deployment_boundary(self) -> "Settings":
        if 0 < self.ops_schedule_seconds < 60:
            raise ValueError("schedule interval must be zero or at least 60 seconds")
        if self.environment == "prod":
            if not self.state_dir.is_absolute():
                raise ValueError("prod requires an explicit absolute state directory")
            if self.api_token is None or len(self.api_token.get_secret_value()) < 32:
                raise ValueError("prod requires a protected API token of at least 32 characters")
        if self.capital_usd and self.max_daily_loss_usd:
            if self.max_daily_loss_usd > self.capital_usd:
                raise ValueError("daily loss limit cannot exceed capital")
        return self

    def prepare_state(self) -> Path:
        root = self.state_dir.resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = root / ".environment.db"
        path.touch(mode=0o600, exist_ok=True)
        path.chmod(0o600)
        with closing(sqlite3.connect(path, timeout=5)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS identity (id INTEGER PRIMARY KEY, env TEXT)")
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT env FROM identity WHERE id=1").fetchone()
            if row and row[0] != self.environment:
                raise ValueError("state directory belongs to another environment")
            db.execute("INSERT OR IGNORE INTO identity VALUES (1,?)", (self.environment,))
        return root
