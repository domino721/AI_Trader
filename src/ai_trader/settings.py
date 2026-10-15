from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_TRADER_", env_file=".env", extra="ignore")

    execution_mode: Literal["simulation"] = "simulation"
    state_dir: Path = Path(".local")
    kill_switch: bool = False
