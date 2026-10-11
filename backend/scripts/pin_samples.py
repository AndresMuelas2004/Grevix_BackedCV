"""Pin the model answers of the built-in samples, so the demo gives the same report on every visit.

The answer cache lives 24 hours, and on the live demo the disk is wiped on every restart; a fresh
model call can then move the fit by a few points. This script runs the two samples the UI offers,
sent exactly as the UI sends them ("Try the sample": the PDF from GET /api/samples as an upload;
"hidden barriers": the CV from GET /api/samples/hidden-risk as pasted text), each through the
analysis and the optimize step, against the real model and an empty cache. It writes every answer
the model gave to samples/pinned_answers.json, which the app loads at startup (llm/cache.py). Each
pinned answer is the model's own answer from that run; nothing is written by hand.

Usage (from backend/):
    uv run python scripts/pin_samples.py           # real model calls (2 analyses), writes the file
    uv run python scripts/pin_samples.py --check   # both samples, twice, empty cache, no model

Run it again after a change to a prompt, a model, or the code that builds the model's input, and
when a month starts (the CV's computed total experience counts months up to today and is part of
the matching input). Until then the entries that no longer match are skipped, and the samples are
answered live. `--check` shows whether the file still covers every call.
"""

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from backedcv.domain.text import normalize_text
from backedcv.llm import structured
from backedcv.llm.cache import PINNED_FILE, PINNED_FORMAT, answer_key, pinned_entry
from backedcv.llm.prompt_loader import Prompt
from backedcv.llm.structured import OpenAIStructuredLLM
from backedcv.main import create_app
from backedcv.settings import Settings, get_settings

ABOUT = (
    "Model answers recorded from one real run of the built-in samples (scripts/pin_samples.py). "
    "The app replays them so the demo is reproducible; any other CV is cached for 24 hours."
)


class RecordingLLM(OpenAIStructuredLLM):
    """The real model behind the usual cache. Every answer is recorded under its cache key, and
    the calls that reached the model are counted with their cost."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings, cache=True)
        self.cache.pinned = {}  # real runs: the answers already pinned are not replayed
        self.entries: dict[str, dict] = {}
        self.live_calls = 0
        self.cost_usd = 0.0

    async def run(
        self, prompt: Prompt, data: str, schema: type[BaseModel], *, node: str
    ) -> tuple[BaseModel, dict]:
        parsed, usage = await super().run(prompt, data, schema, node=node)
        model, effort = self._model_name(prompt.tier), self._effort(prompt.id)
        key = answer_key(model, effort, prompt, schema, normalize_text(data))
        self.entries[key] = pinned_entry(
            key,
            model=model,
            effort=effort,
            prompt=prompt,
            schema=schema,
            answer=parsed.model_dump(mode="json"),
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
        )
        if not usage["cached"]:
            self.live_calls += 1
            self.cost_usd += usage["cost_usd"]
        return parsed, usage


def run_samples(client: TestClient) -> dict[str, dict]:
    """Both samples as the UI sends them (frontend/src/components/InputForm.tsx and
    lib/draft.ts: the posting is trimmed, the CV text is not), each through the analysis and the
    optimize step. Raises RuntimeError when a run fails or reports an error."""
    curated = _ok(client.get("/api/samples")).json()
    pdf = _ok(client.get(curated["cv_pdf_url"])).content
    hidden = _ok(client.get("/api/samples/hidden-risk")).json()
    sends = {
        "curated": {
            "data": {"job_text": curated["job_text"].strip()},
            "files": {"cv_file": (curated["cv_filename"], pdf, "application/pdf")},
        },
        "hidden_risk": {
            "data": {"cv_text": hidden["cv_text"], "job_text": hidden["job_text"].strip()},
            "files": None,
        },
    }
    return {name: _run_one(client, name, **send) for name, send in sends.items()}


def _run_one(client: TestClient, name: str, data: dict, files: dict | None) -> dict:
    event, report = _last_event(client.post("/api/analyses", data=data, files=files))
    _require(event == "report" and not report.get("errors"), f"{name} analysis", event, report)
    path = f"/api/analyses/{report['analysis_id']}/optimize"
    event, result = _last_event(client.post(path))
    _require(event == "suggestions" and not result.get("errors"), f"{name} optimize", event, result)
    score, verdict = result.get("score") or {}, result.get("verdict") or {}
    suggestions = result.get("suggestions") or []
    summary = {
        "fit": score.get("fit"),
        "coverage": score.get("coverage"),
        "verdict": verdict.get("label"),
        "verdict_title": verdict.get("title"),
        "requirements": len((result.get("job") or {}).get("requirements") or []),
        "suggestions": len(suggestions),
        "verified": sum(1 for s in suggestions if s["verification"]["status"] == "verified"),
    }
    return {"summary": summary, "usage": result["usage"]}


def _ok(response):
    if response.status_code != 200:
        raise RuntimeError(f"{response.request.url}: HTTP {response.status_code}")
    return response


def _last_event(response) -> tuple[str, dict]:
    """The last named event of a server-sent event stream, with its JSON data."""
    _ok(response)
    event, data = "", {}
    for block in response.text.replace("\r\n", "\n").strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if fields.get("event"):
            event, data = fields["event"], json.loads(fields.get("data") or "{}")
    return event, data


def _require(ok: bool, step: str, event: str, body: dict) -> None:
    if not ok:
        detail = body.get("errors") or body.get("error") or body
        raise RuntimeError(f"{step} ended with {event!r}: {str(detail)[:500]}")


def generate(path: Path) -> int:
    """Real runs of both samples on an empty cache; writes the pinned answers file."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        settings = Settings(data_dir=Path(tmp))  # an empty cache; models and key from the env
        print(f"Models: fast={settings.model_fast}, strong={settings.model_strong}")
        llm = RecordingLLM(settings)
        with TestClient(create_app(llm=llm, checkpointer=InMemorySaver())) as client:
            results = run_samples(client)
        with closing(sqlite3.connect(Path(tmp) / "llm_cache.sqlite")) as db:
            stored = {key for (key,) in db.execute("SELECT key FROM answers")}
    if stored != set(llm.entries):
        print("The recorded keys differ from the cache's own keys: check answer_key in structured.")
        return 1
    payload = {
        "format": PINNED_FORMAT,
        "about": ABOUT,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "samples": {name: result["summary"] for name, result in results.items()},
        "entries": sorted(llm.entries.values(), key=lambda e: (e["prompt_id"], e["key"])),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, result in results.items():
        print(name, result["summary"])
    print(
        f"Wrote {len(llm.entries)} entries to {path} ({path.stat().st_size:,} bytes). "
        f"Live calls: {llm.live_calls}, cost ${llm.cost_usd:.4f}."
    )
    return 0


def _offline(**_options):
    """Stands in for ChatOpenAI during --check: a call that is not pinned fails the check instead
    of reaching (and paying for) the model."""
    raise RuntimeError("this call is not pinned, so it would have reached the model")


def check(path: Path, rounds: int = 2) -> int:
    """Runs both samples `rounds` times through the app as it starts in production, each time on
    an empty cache and with the model unreachable. Passes when every round gives the same report
    from pinned answers alone. A report that differs from the pinned run's numbers means the code
    after the model changed since the file was written: it is still reproducible, but run the
    script again so the recorded numbers match."""
    expected = json.loads(path.read_text(encoding="utf-8")).get("samples", {})
    structured.ChatOpenAI = _offline
    seen = []
    for round_no in range(1, rounds + 1):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            os.environ["BACKEDCV_DATA_DIR"] = tmp  # a fresh, empty cache location
            get_settings.cache_clear()
            try:
                with TestClient(create_app(checkpointer=InMemorySaver())) as client:
                    results = run_samples(client)
            except RuntimeError as exc:
                print(f"round {round_no}: {exc}\nFAIL")
                return 1
        summaries = {name: result["summary"] for name, result in results.items()}
        seen.append(summaries)
        for name, result in results.items():
            usage, same = result["usage"], summaries[name] == expected.get(name)
            print(
                f"round {round_no} {name}: {summaries[name]} | calls {usage['calls']}, "
                f"cached {usage['cached_calls']} | "
                f"{'as pinned' if same else 'differs from the pinned run numbers'}"
            )
    passed = all(summaries == seen[0] for summaries in seen)
    print("PASS" if passed else "FAIL: the rounds differ")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="replay the samples on empty caches, no writing"
    )
    args = parser.parse_args()
    path = get_settings().samples_dir / PINNED_FILE
    return check(path) if args.check else generate(path)


if __name__ == "__main__":
    sys.exit(main())
