"""Application settings, read from environment variables and the repository's `.env` file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

# LangChain and LangSmith read their settings straight from os.environ,
# so the .env file is loaded into the process environment (real env vars win).
load_dotenv(REPO_ROOT / ".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BACKEDCV_", extra="ignore")

    env: Literal["dev", "prod"] = "dev"

    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY")
    )
    model_fast: str = "claude-haiku-5-5"
    model_strong: str = "claude-haiku-5-5"
    llm_cache: bool = True  # an identical model call gets the stored answer again, for free

    # Abuse and budget limits on the routes that call the model.
    rate_limit_per_hour: int = Field(default=30, ge=1)  # per client address, rolling hour
    daily_model_runs: int = Field(default=300, ge=1)  # all clients together, per UTC day

    data_dir: Path = REPO_ROOT / "data"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    samples_dir: Path = REPO_ROOT / "backend" / "samples"


@lru_cache
def get_settings() -> Settings:
    return Settings()
