"""Versioned configuration files (TOML, read with the standard library)."""

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).parent


@lru_cache
def load(name: str) -> dict[str, Any]:
    with (CONFIG_DIR / f"{name}.toml").open("rb") as f:
        return tomllib.load(f)
