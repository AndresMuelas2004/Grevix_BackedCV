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

    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("OPENAI_API_KEY")
    )
    model_fast: str = "gpt-6-luna"
    model_strong: str = "gpt-6.1-sol"

    data_dir: Path = REPO_ROOT / "data"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
