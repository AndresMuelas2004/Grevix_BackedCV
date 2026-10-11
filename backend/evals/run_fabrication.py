"""Measures the fabrication set: how many invented CV rewrites the checks block, and how many
faithful rewrites they block by mistake.

Offline (default): the deterministic guards only, no network.
Live (--live): the guards, then the app's real verifier on the suggestions the guards let through.
Run from backend/: uv run python -m evals.run_fabrication --help
"""

import argparse
import asyncio
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from backedcv.domain.guards import apply_guards
from backedcv.domain.models import JobPosting, ParsedCV, Requirement, Suggestion

EVALS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = EVALS_DIR / "fabrication"
RESULTS_DIR = EVALS_DIR / "results"
SPLITS = ("dev", "heldout")
LANGSMITH_DATASET = "backedcv-fabrication"

# What the checks did with one case. "not_checked" means the verifier gave no verdict.
Verdict = Literal["blocked_by_guards", "blocked_by_verifier", "passed", "not_checked"]
BLOCKED = ("blocked_by_guards", "blocked_by_verifier")
FABRICATED_OUTCOMES = ("caught by guards", "caught by verifier", "missed", "not checked")
FAITHFUL_OUTCOMES = (
    "wrongly blocked by guards",
    "wrongly blocked by verifier",
    "passed",
    "not checked",
)
NOTES = {
    "offline": (
        "Guards only, no network. The verifier did not run, so a case that passes the guards is "
        "`not checked`, not `passed`."
    ),
    "live": (
        "Guards, then the app's real verifier on the suggestions the guards let through, one call "
        "per CV section. A failed verifier call leaves its suggestions `not checked`."
    ),
}


@dataclass(frozen=True)
class Case:
    id: str
    split: str
    expected: str  # "verified" or "unsupported"
    fabrication_type: str | None
    suggestion: Suggestion


@dataclass(frozen=True)
class Result:
    case: Case
    verdict: Verdict
    reason: str | None = None


@dataclass
class VerifierRun:
    """What the verifier answered for every pending suggestion of the run."""

    checked: dict[str, Suggestion] = field(default_factory=dict)  # by suggestion ID
    failed: dict[str, str] = field(default_factory=dict)  # by suggestion ID: why the call failed
    errors: list[str] = field(default_factory=list)  # one line per failed call
    usage: list[dict] = field(default_factory=list)  # one usage record per call that answered


@dataclass
class Run:
    mode: str  # "offline" or "live"
    results: list[Result] = field(default_factory=list)
    usage: list[dict] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)  # one line per failed verifier call


def load_cases(path: Path = FIXTURES_DIR / "cases.jsonl") -> list[Case]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["split"] not in SPLITS:
            raise ValueError(f"{row['id']}: unknown split {row['split']!r}")
        cases.append(
            Case(
                id=row["id"],
                split=row["split"],
                expected=row["expected"],
                fabrication_type=row["fabrication_type"],
                suggestion=Suggestion.model_validate(row["suggestion"]),
            )
        )
    suggestion_ids = [case.suggestion.id for case in cases]
    if len(set(suggestion_ids)) != len(suggestion_ids):
        raise ValueError("suggestion IDs must be unique: the verifier's answers are keyed by them")
    return cases


def load_cv(path: Path = FIXTURES_DIR / "cv.json") -> ParsedCV:
    return ParsedCV.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_job(path: Path = FIXTURES_DIR / "job.json") -> JobPosting:
    raw = json.loads(path.read_text(encoding="utf-8"))
    # The set gives only IDs, labels and terms. The guards read the terms and aliases and nothing
    # else, so the other fields are placeholders.
    requirements = [
        Requirement(
            id=row["id"],
            label=row["label"],
            quote="",
            category="other",
            importance="required",
            terms=row["terms"],
        )
        for row in raw["requirements"]
    ]
    return JobPosting(title=raw["title"], company=raw["company"], requirements=requirements)


def outcome_of(case: Case, verdict: Verdict) -> str:
    """The label a case gets in the tables, given what the checks did with it."""
    if verdict == "not_checked":
        return "not checked"
    fabricated = case.expected == "unsupported"
    if verdict == "passed":
        return "missed" if fabricated else "passed"
    blocker = "guards" if verdict == "blocked_by_guards" else "verifier"
    return f"caught by {blocker}" if fabricated else f"wrongly blocked by {blocker}"


def run_guards(cases: list[Case], cv: ParsedCV, job: JobPosting) -> dict[str, Suggestion]:
    """Each case's suggestion after the guards, keyed by suggestion ID."""
    return {case.suggestion.id: apply_guards(case.suggestion, cv, job) for case in cases}


def live_nodes() -> dict[str, Any]:
    """The app's optimize nodes, backed by the model from settings. Imported only for --live."""
    from backedcv.graph.optimize_nodes import make_optimize_nodes
    from backedcv.llm.structured import OpenAIStructuredLLM
    from backedcv.settings import get_settings

    settings = get_settings()
    if settings.openai_api_key is None:
        raise SystemExit("OPENAI_API_KEY is not set (add it to the repository's .env)")
    return make_optimize_nodes(OpenAIStructuredLLM(settings, cache=False))  # measure, never replay


async def _verify_all(verify_batch: Any, tasks: list[dict]) -> list[dict]:
    return await asyncio.gather(*(verify_batch(task) for task in tasks))


def run_verifier(
    guarded: dict[str, dict[str, Suggestion]], cv: ParsedCV, nodes: dict[str, Any]
) -> VerifierRun:
    """The app's verifier on every pending suggestion, one call per CV section and split.

    All calls run in one event loop. The async model client binds to the loop of its first call,
    so a second asyncio.run would fail with "Event loop is closed".
    """
    tasks: list[dict] = []
    for split_guarded in guarded.values():
        pending = {sid: s for sid, s in split_guarded.items() if s.verification.status == "pending"}
        if pending:  # route_verification returns a string, not a list, when nothing is pending
            state = {
                "cv": cv.model_dump(),
                "suggestions": [s.model_dump() for s in pending.values()],
            }
            tasks += [send.arg for send in nodes["route_verification"](state)]
    run = VerifierRun()
    if not tasks:
        return run
    for update in asyncio.run(_verify_all(nodes["verify_batch"], tasks)):
        if update.get("errors"):  # the app marks a failed call's suggestions unsupported
            why = "; ".join(f"{e['error']}: {e['detail']}" for e in update["errors"])
            run.errors.append(why)
            run.failed.update({raw["id"]: why for raw in update["suggestions"]})
            continue
        run.usage += update["usage"]
        run.checked.update(
            {raw["id"]: Suggestion.model_validate(raw) for raw in update["suggestions"]}
        )
    return run


def classify(
    cases: list[Case], guarded: dict[str, Suggestion], verifier: VerifierRun | None
) -> list[Result]:
    """One result per case: the first check that stopped it, or none."""
    results = []
    for case in cases:
        sid = case.suggestion.id
        suggestion = guarded[sid]
        if suggestion.verification.status == "unsupported":
            guard = next(g for g in suggestion.verification.guards if g.hard and not g.ok)
            results.append(Result(case, "blocked_by_guards", f"{guard.name}: {guard.detail}"))
        elif verifier is None:
            results.append(Result(case, "not_checked", "verifier not run (offline)"))
        elif sid in verifier.failed:
            why = verifier.failed[sid]
            results.append(Result(case, "not_checked", f"verifier call failed: {why}"))
        elif verifier.checked[sid].verification.status == "unsupported":
            reason = verifier.checked[sid].verification.reason
            results.append(Result(case, "blocked_by_verifier", reason))
        else:
            results.append(Result(case, "passed"))
    return results


def run_checks(cases: list[Case], cv: ParsedCV, job: JobPosting, live: bool) -> Run:
    guarded = {
        split: run_guards([case for case in cases if case.split == split], cv, job)
        for split in SPLITS
    }
    verifier = run_verifier(guarded, cv, live_nodes()) if live else None
    run = Run(mode="live" if live else "offline")
    if verifier is not None:
        run.usage = verifier.usage
        run.failures = verifier.errors
    for split in SPLITS:
        split_cases = [case for case in cases if case.split == split]
        run.results += classify(split_cases, guarded[split], verifier)
    return run


def _cost_totals(usage: list[dict]) -> tuple[int, int, float]:
    return (
        sum(u["input_tokens"] for u in usage),
        sum(u["output_tokens"] for u in usage),
        round(sum(u["cost_usd"] for u in usage), 6),
    )


def _one_line(text: str | None) -> str:
    return " ".join((text or "-").split())


def _cell(text: str | None) -> str:
    return _one_line(text).replace("|", "\\|")


def _tally(rows: list[Result], outcomes: tuple[str, ...]) -> str:
    counts = Counter(outcome_of(r.case, r.verdict) for r in rows)
    return ", ".join(f"{outcome} {counts[outcome]}" for outcome in outcomes)


def sections_of(results: list[Result]) -> list[tuple[str, list[Result]]]:
    """One section per split that ran, plus an "all" section when more than one split ran."""
    sections = [(split, [r for r in results if r.case.split == split]) for split in SPLITS]
    sections = [(name, rows) for name, rows in sections if rows]
    if len(sections) > 1:
        sections.append(("all", results))
    return sections


def _outcome_table(title: str, outcomes: tuple[str, ...], rows: list[Result]) -> list[str]:
    ids: dict[str, list[str]] = {outcome: [] for outcome in outcomes}
    for r in rows:
        ids[outcome_of(r.case, r.verdict)].append(r.case.id)
    lines = [f"### {title}", "", "| Outcome | Count | Cases |", "|---|---:|---|"]
    lines += [f"| {o} | {len(ids[o])} | {', '.join(ids[o]) or '-'} |" for o in outcomes]
    return [*lines, ""]


def _by_type_table(fabricated: list[Result]) -> list[str]:
    lines = [
        "| Type | Cases | Caught by guards | Caught by verifier | Missed | Not checked |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for kind in sorted({r.case.fabrication_type for r in fabricated}):
        rows = [r for r in fabricated if r.case.fabrication_type == kind]
        counts = Counter(outcome_of(r.case, r.verdict) for r in rows)
        lines.append(
            f"| {kind} | {len(rows)} | {counts['caught by guards']} "
            f"| {counts['caught by verifier']} | {counts['missed']} | {counts['not checked']} |"
        )
    return [*lines, ""]


def _split_section(name: str, rows: list[Result]) -> list[str]:
    fabricated = [r for r in rows if r.case.expected == "unsupported"]
    faithful = [r for r in rows if r.case.expected == "verified"]
    wrong = [r for r in faithful if r.verdict in BLOCKED]
    lines = [f"## {name} ({len(rows)} cases)", ""]
    lines += _outcome_table(f"Fabricated ({len(fabricated)})", FABRICATED_OUTCOMES, fabricated)
    lines += _outcome_table(f"Faithful ({len(faithful)})", FAITHFUL_OUTCOMES, faithful)
    lines += ["### Faithful cases wrongly blocked", ""]
    lines += [f"- {r.case.id}: {_one_line(r.reason)}" for r in wrong] or ["None."]
    lines += ["", "### By fabrication type", ""]
    lines += _by_type_table(fabricated)
    return lines


def _cost_section(run: Run) -> list[str]:
    tokens_in, tokens_out, cost = _cost_totals(run.usage)
    return [
        "## Verifier cost",
        "",
        "| Calls | Input tokens | Output tokens | Cost (USD) | Failed calls |",
        "|---:|---:|---:|---:|---:|",
        f"| {len(run.usage)} | {tokens_in} | {tokens_out} | {cost:.4f} | {len(run.failures)} |",
        "",
    ]


def _cases_section(results: list[Result]) -> list[str]:
    lines = [
        "## All cases",
        "",
        "| Case | Split | Expected | Fabrication type | Outcome | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.case.id} | {r.case.split} | {r.case.expected} | "
            f"{r.case.fabrication_type or '-'} | {outcome_of(r.case, r.verdict)} | "
            f"{_cell(r.reason)} |"
        )
    return lines


def render_report(run: Run, started: datetime) -> str:
    title = f"# Fabrication set: {run.mode} run, {started:%Y-%m-%d %H:%M}"
    lines = [title, "", NOTES[run.mode], ""]
    for name, rows in sections_of(run.results):
        lines += _split_section(name, rows)
    if run.mode == "live":
        lines += _cost_section(run)
    lines += _cases_section(run.results)
    return "\n".join(lines) + "\n"


def summary_lines(run: Run, report: Path) -> list[str]:
    lines = [f"Fabrication set, {run.mode} run: {len(run.results)} cases"]
    for name, rows in sections_of(run.results):
        fabricated = [r for r in rows if r.case.expected == "unsupported"]
        faithful = [r for r in rows if r.case.expected == "verified"]
        fab_tally = _tally(fabricated, FABRICATED_OUTCOMES)
        lines.append(f"{name}: fabricated {len(fabricated)}: {fab_tally}")
        lines.append(f"  faithful {len(faithful)}: {_tally(faithful, FAITHFUL_OUTCOMES)}")
        missed = [r.case.id for r in fabricated if r.verdict == "passed"]
        if missed:
            lines.append(f"  missed: {', '.join(missed)}")
        for r in faithful:
            if r.verdict in BLOCKED:
                lines.append(f"  wrongly blocked: {r.case.id} ({_one_line(r.reason)})")
    lines.append(f"Report: {report}")
    if run.mode == "live":
        tokens_in, tokens_out, cost = _cost_totals(run.usage)
        lines.append(
            f"Verifier: {len(run.usage)} calls, {tokens_in} input and {tokens_out} output tokens, "
            f"${cost:.4f}"
        )
    for why in run.failures:
        lines.append(f"WARNING: verifier call failed, its cases are not checked: {why}")
    return lines


def _record_in_langsmith(run: Run) -> None:
    """Uploads the set and records the live run in LangSmith. Only for --langsmith."""
    from langsmith import Client

    client = Client()
    if client.has_dataset(dataset_name=LANGSMITH_DATASET):
        print(f"LangSmith: dataset '{LANGSMITH_DATASET}' exists, reusing its examples")
    else:
        dataset = client.create_dataset(
            LANGSMITH_DATASET,
            description="Suggested CV rewrites, each labelled verified or unsupported.",
        )
        client.create_examples(
            dataset_id=dataset.id,
            examples=[
                {
                    "inputs": r.case.suggestion.model_dump(
                        include={"id", "kind", "target", "after", "cited_refs", "requirement_ids"}
                    ),
                    "outputs": {"expected": r.case.expected},
                    "metadata": {
                        "case_id": r.case.id,
                        "split": r.case.split,
                        "fabrication_type": r.case.fabrication_type,
                    },
                }
                for r in run.results
            ],
        )
    by_suggestion = {r.case.suggestion.id: r for r in run.results}

    def target(inputs: dict) -> dict:
        # Replays the verdict of the live pass above, so the verifier is not paid for twice.
        # It always returns a status, so every example gets a score.
        result = by_suggestion.get(inputs.get("id"))
        if result is None:
            return {"status": "not_checked", "reason": "no live verdict for this example"}
        if result.verdict == "passed":
            status = "verified"
        elif result.verdict == "not_checked":
            status = "not_checked"
        else:
            status = "unsupported"
        return {"status": status, "reason": result.reason}

    def label_correct(outputs: dict | None, reference_outputs: dict | None) -> dict:
        # Defensive: if the target ever fails on an example, LangSmith passes no outputs for it.
        # That example counts as wrong (score 0), not as a crash.
        status = (outputs or {}).get("status")
        expected = (reference_outputs or {}).get("expected")
        if status is None or expected is None:
            return {"key": "label_correct", "score": 0}
        return {"key": "label_correct", "score": int(status == expected)}

    client.evaluate(
        target,
        data=LANGSMITH_DATASET,
        evaluators=[label_correct],
        experiment_prefix="backedcv-fabrication",
        metadata={"verifier_calls": len(run.usage), "cost_usd": _cost_totals(run.usage)[2]},
    )
    print(f"LangSmith: recorded the run on dataset '{LANGSMITH_DATASET}'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the fabrication set (see README.md).")
    parser.add_argument(
        "--live", action="store_true", help="also run the real verifier (calls the model)"
    )
    parser.add_argument(
        "--split", choices=[*SPLITS, "all"], default="all", help="which split to run"
    )
    parser.add_argument(
        "--langsmith",
        action="store_true",
        help="record the live run in LangSmith (needs --live and --split all)",
    )
    parser.add_argument(
        "--results-dir", type=Path, default=RESULTS_DIR, help="where the report is written"
    )
    args = parser.parse_args(argv)
    if args.langsmith and (not args.live or args.split != "all"):
        parser.error("--langsmith needs --live and --split all (it records the whole set)")

    sys.stdout.reconfigure(errors="replace")  # a model's text must not crash the summary
    started = datetime.now()
    cases = [case for case in load_cases() if args.split in ("all", case.split)]
    run = run_checks(cases, load_cv(), load_job(), live=args.live)
    args.results_dir.mkdir(parents=True, exist_ok=True)
    report = args.results_dir / f"fabrication-{run.mode}-{started:%Y%m%d-%H%M}.md"
    report.write_text(render_report(run, started), encoding="utf-8")
    print("\n".join(summary_lines(run, report)))
    if args.langsmith:
        _record_in_langsmith(run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
