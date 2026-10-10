"""Run one real analysis on the bundled synthetic sample and print the result.

Usage (from backend/): uv run python scripts/smoke_run.py
Uses the real OpenAI API (a few cents at most) and an in-memory checkpointer.
"""

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backedcv.main import create_app

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def main() -> int:
    cv = (SAMPLES / "sample_cv.txt").read_text(encoding="utf-8")
    job = (SAMPLES / "sample_job.txt").read_text(encoding="utf-8")
    with TestClient(create_app(checkpointer=InMemorySaver())) as client:
        response = client.post("/api/analyses", data={"cv_text": cv, "job_text": job})
    if response.status_code != 200:
        print(response.status_code, response.text)
        return 1

    report = None
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if lines.get("event") == "error":
            print("ERROR", lines.get("data"))
            return 1
        if lines.get("event") == "report":
            report = json.loads(lines["data"])
    if report is None:
        print("No report event")
        return 1

    reqs = {r["id"]: r for r in report["job"]["requirements"]}
    print("Verdict:", report["verdict"]["title"], report["verdict"]["badges"])
    print("Score:", report["score"]["summary"])
    print("Coverage:", report["score"]["coverage"])
    print("Flags:", [(f["rule_id"], f["requirement_ids"]) for f in report["flags"]])
    for rid, a in report["assessments"].items():
        r = reqs[rid]
        refs = [e["ref"] for e in a["evidence"]]
        print(
            f"  {rid} [{r['importance'][:3]} {r['category']}] {r['label']}: {a['status']} "
            f"{refs} kw={a['keyword_present']}"
        )
    print("Errors:", report["errors"])
    print("Usage:", report["usage"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
