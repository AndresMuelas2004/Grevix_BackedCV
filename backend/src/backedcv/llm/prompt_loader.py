"""Prompts live as versioned Markdown files with a small front matter (id, version, tier)."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class Prompt:
    id: str
    version: str
    tier: str
    text: str

    @property
    def metadata(self) -> dict[str, str]:
        return {"prompt_id": self.id, "prompt_version": self.version}


@lru_cache
def load_prompt(name: str) -> Prompt:
    raw = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    _, header, body = raw.split("---", 2)
    meta = dict(
        (key.strip(), value.strip())
        for key, value in (line.split(":", 1) for line in header.strip().splitlines())
    )
    return Prompt(meta["id"], meta["version"], meta["tier"], body.strip())
