"""Run the smoke pairs through the real analysis graph and check what each report shows.

Every pair calls the model, so the run needs --live and costs money.
Run from backend/: uv run python -m evals.run_smoke --help
"""

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

from backedcv.api.projection import REPORT_STAGE, project
from backedcv.api.routes.analyses import JOB_MAX_CHARS, JOB_MIN_CHARS
from backedcv.domain.models import (
    BarrierKind,
    CandidateFacts,
    Importance,
    KnockoutType,
    RiskLevel,
    Status,
)
from backedcv.domain.models.score import VerdictLabel
from backedcv.domain.text import fold_lower
from backedcv.graph.builder import build_graph, run_config
from backedcv.ingestion import read_cv, read_cv_text
from backedcv.ingestion.reader import ReadResult

EVALS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVALS_DIR.parent  # the pair files are referenced from here
PAIRS_PATH = EVALS_DIR / "smoke" / "pairs.json"
RESULTS_DIR = EVALS_DIR / "results"
LANGSMITH_DATASET = "backedcv-smoke"
BINARY_SUFFIXES = (".pdf", ".docx")  # read like uploads; any other file is read as pasted text
EXPECT_KEYS = {
    "requirements",
    "flags",
    "banners",
    "parse_warnings",
    "verdict_not",
    "hidden_risks",
    "recency",
    "screening_flags",
    "refusals",
}
SELECTOR_KEYS = {"contains", "importance", "knockout_type", "status", "screening_question"}
SELECTOR_VALUES = {
    "importance": get_args(Importance),
    "knockout_type": get_args(KnockoutType),
    "status": get_args(Status),
}
FLAG_KEYS = {"rule", "contains"}
FLAG_RULES = ("R1", "R2")
BANNER_RULES = ("R3", "R4")
VERDICT_LABELS = get_args(VerdictLabel)
HIDDEN_RISK_VALUES = {"kind": get_args(BarrierKind), "risk": get_args(RiskLevel)}
RECENCY_EFFECTS = ("none", "warning", "downgraded")
REFUSAL_GATES = ("recent_enough", "not_blocked")
ANALYSIS_HEADER = (
    "Pair",
    "Verdict",
    "Fit",
    "Requirements",
    "Flags",
    "Banners",
    "Parse warnings",
    "Node errors",
    "Calls",
    "Cost (USD)",
)
NOTE = (
    "Each pair runs the real analysis up to the report pause (no optimize, no build). Checks test "
    "properties of the report, not exact scores. Costs use the list prices in the models config."
)


@dataclass(frozen=True)
class Pair:
    id: str
    description: str
    cv: str  # a path relative to backend/, or the CV text itself (inline text has line breaks)
    job: str  # the same, for the posting
    expect: dict[str, Any]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    reason: str


@dataclass
class PairRun:
    pair: Pair
    analysis_id: str
    state: dict  # the first graph state, built the way the API builds it
    cv_text: str  # the CV as the app read it: one line per CV line
    job_text: str
    projection: dict | None = None  # what the report shows once the analysis has paused
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.ok for check in self.checks)

    @property
    def usage(self) -> dict:
        return (self.projection or {}).get("usage") or {}


def load_pairs(path: Path = PAIRS_PATH) -> list[Pair]:
    pairs = [Pair(**row) for row in json.loads(path.read_text(encoding="utf-8"))]
    ids = [pair.id for pair in pairs]
    if len(set(ids)) != len(ids):
        raise ValueError("pair IDs must be unique: the LangSmith examples are keyed by them")
    for pair in pairs:
        validate_expect(pair.expect)
    return pairs


def _options(want) -> list:
    """One value, or a list: the requirement may match any of them."""
    return want if isinstance(want, list) else [want]


def _valid_options(want, allowed: tuple) -> bool:
    options = _options(want)
    return bool(options) and all(option in allowed for option in options)


def validate_expect(expect: dict[str, Any]) -> None:
    """Rejects a misspelled key or value up front, so it cannot quietly check nothing."""
    unknown = set(expect) - EXPECT_KEYS
    if unknown:
        raise ValueError(f"unknown expectation keys: {sorted(unknown)}")
    for selector in expect.get("requirements", []):
        if not selector or set(selector) - SELECTOR_KEYS:
            raise ValueError(f"bad requirement {selector}: use keys from {sorted(SELECTOR_KEYS)}")
        for key, allowed in SELECTOR_VALUES.items():
            if key in selector and not _valid_options(selector[key], allowed):
                raise ValueError(
                    f"{key} must be one of {allowed} (or a list of them), got {selector[key]!r}"
                )
        if "screening_question" in selector and not isinstance(
            selector["screening_question"], bool
        ):
            raise ValueError("screening_question must be true or false")
    for flag in expect.get("flags", []):
        if flag.get("rule") not in FLAG_RULES or set(flag) - FLAG_KEYS:
            raise ValueError(f"bad flag {flag}: rule must be one of {FLAG_RULES}")
    for rule in expect.get("banners", []):
        if rule not in BANNER_RULES:
            raise ValueError(f"banner must be one of {BANNER_RULES}, got {rule!r}")
    for label in expect.get("verdict_not", []):
        if label not in VERDICT_LABELS:
            raise ValueError(f"verdict must be one of {VERDICT_LABELS}, got {label!r}")
    for risk in expect.get("hidden_risks", []):
        if not risk or set(risk) - set(HIDDEN_RISK_VALUES):
            raise ValueError(f"bad hidden risk {risk}: use the keys kind and risk")
        for key, allowed in HIDDEN_RISK_VALUES.items():
            if key in risk and risk[key] not in allowed:
                raise ValueError(f"{key} must be one of {allowed}, got {risk[key]!r}")
    for recency in expect.get("recency", []):
        if set(recency) != {"contains", "effect"}:
            raise ValueError(f"bad recency {recency}: use the keys contains and effect")
        if recency["effect"] not in RECENCY_EFFECTS:
            raise ValueError(f"effect must be one of {RECENCY_EFFECTS}, got {recency['effect']!r}")
    for flag in expect.get("screening_flags", []):
        if set(flag) != {"contains"}:
            raise ValueError(f"bad screening flag {flag}: use the key contains")
    for refusal in expect.get("refusals", []):
        if set(refusal) != {"gate", "contains"}:
            raise ValueError(f"bad refusal {refusal}: use the keys gate and contains")
        if refusal["gate"] not in REFUSAL_GATES:
            raise ValueError(f"gate must be one of {REFUSAL_GATES}, got {refusal['gate']!r}")


def is_inline(value: str) -> bool:
    return "\n" in value  # a path never has a line break


def read_text(value: str) -> str:
    return value if is_inline(value) else (BACKEND_DIR / value).read_text(encoding="utf-8")


def read_cv_source(value: str) -> ReadResult:
    if not is_inline(value) and Path(value).suffix.lower() in BINARY_SUFFIXES:
        path = BACKEND_DIR / value
        return read_cv(path.read_bytes(), path.name)
    return read_cv_text(read_text(value))


def prepare(pair: Pair) -> PairRun:
    """Reads a pair the way the API reads an upload and pasted posting text. No model call."""
    cv = read_cv_source(pair.cv)
    job_text = read_text(pair.job).strip()
    if not JOB_MIN_CHARS <= len(job_text) <= JOB_MAX_CHARS:
        raise ValueError(
            f"the posting has {len(job_text)} characters, not {JOB_MIN_CHARS} to {JOB_MAX_CHARS}"
        )
    analysis_id = str(uuid.uuid4())
    state = {
        "analysis_id": analysis_id,
        "created_at": datetime.now(UTC).isoformat(),
        "cv_meta": {
            "kind": cv.kind,
            "filename": cv.filename,
            "size": cv.size,
            "lines": len(cv.lines),
            "multi_column": cv.multi_column,
        },
        "cv_lines": [line.model_dump() for line in cv.lines],
        "job_text": job_text,
        "facts": CandidateFacts().model_dump(),
        "excluded_ids": [],
        "included_flagged_ids": [],
    }
    cv_text = "\n".join(line.text for line in cv.lines)
    return PairRun(pair, analysis_id, state, cv_text, job_text)


def check_expectations(expect: dict[str, Any], projection: dict) -> list[Check]:
    checks = [_reaches_report(projection)]
    checks += [_requirement_check(s, projection) for s in expect.get("requirements", [])]
    checks += [_flag_check(f, projection) for f in expect.get("flags", [])]
    checks += [_banner_check(rule, projection) for rule in expect.get("banners", [])]
    checks += [_warning_check(code, projection) for code in expect.get("parse_warnings", [])]
    checks += [_verdict_check(label, projection) for label in expect.get("verdict_not", [])]
    checks += [_hidden_risk_check(risk, projection) for risk in expect.get("hidden_risks", [])]
    checks += [_recency_check(recency, projection) for recency in expect.get("recency", [])]
    checks += [
        _screening_flag_check(flag, projection) for flag in expect.get("screening_flags", [])
    ]
    checks += [_refusal_check(refusal, projection) for refusal in expect.get("refusals", [])]
    return checks


def _reaches_report(projection: dict) -> Check:
    if projection.get("stage") == REPORT_STAGE:
        return Check("reaches the report", True, "paused at the report")
    stage = projection.get("stage") or "none"
    return Check("reaches the report", False, f"status {projection.get('status')}, stage {stage}")


def _requirements(projection: dict) -> list[dict]:
    return (projection.get("job") or {}).get("requirements", [])


def _text(req: dict) -> str:
    """What a phrase is matched against: the label, the posting quote and the terms."""
    parts = [req.get("label") or "", req.get("quote") or "", *req.get("terms", [])]
    return fold_lower(" ".join(parts))


def _brief(req: dict, assessment: dict | None) -> str:
    status = assessment["status"] if assessment else "unknown"
    asked = "yes" if assessment and assessment.get("question") else "no"
    return f"{req['id']} '{req['label']}' (status {status}, screening question {asked})"


def _describe(selector: dict) -> str:
    return ", ".join(f"{key}={_shown(want)}" for key, want in selector.items())


def _shown(want) -> str:
    if isinstance(want, list):
        return " or ".join(want)
    return str(want).lower() if isinstance(want, bool) else str(want)


def _matches(selector: dict, req: dict, assessment: dict | None) -> bool:
    status = assessment["status"] if assessment else "unknown"
    asked = bool(assessment and assessment.get("question"))
    tests = {
        "contains": lambda want: fold_lower(want) in _text(req),
        "importance": lambda want: req.get("importance") in _options(want),
        "knockout_type": lambda want: req.get("knockout_type") in _options(want),
        "status": lambda want: status in _options(want),
        "screening_question": lambda want: asked == want,
    }
    return all(tests[key](want) for key, want in selector.items())


def _requirement_check(selector: dict, projection: dict) -> Check:
    name = f"requirement {_describe(selector)}"
    assessments = projection.get("assessments") or {}
    reqs = _requirements(projection)
    matches = [r for r in reqs if _matches(selector, r, assessments.get(r["id"]))]
    if matches:
        return Check(name, True, _brief(matches[0], assessments.get(matches[0]["id"])))
    if "contains" not in selector:
        return Check(name, False, f"no requirement has all of these ({len(reqs)} in the posting)")
    near = [r for r in reqs if fold_lower(selector["contains"]) in _text(r)]
    if not near:
        return Check(name, False, f"no requirement contains {selector['contains']!r}")
    found = "; ".join(_brief(r, assessments.get(r["id"])) for r in near)
    return Check(name, False, f"no requirement has all of these. Phrase found in: {found}")


def _flag_check(expect: dict, projection: dict) -> Check:
    rule, phrase = expect["rule"], expect.get("contains")
    name = f"flag {rule}" + (f" about {phrase}" if phrase else "")
    flags = [f for f in projection.get("flags") or [] if f["rule_id"] == rule]
    if not flags:
        found = _ids(projection.get("flags"), "rule_id")
        return Check(name, False, f"no {rule} flag (flags: {found})")
    ids = sorted({i for f in flags for i in f["requirement_ids"]})
    if phrase is None:
        return Check(name, True, f"{rule} on {', '.join(ids)}")
    by_id = {r["id"]: r for r in _requirements(projection)}
    hit = [i for i in ids if i in by_id and fold_lower(phrase) in _text(by_id[i])]
    if hit:
        return Check(name, True, f"{rule} on {', '.join(hit)}")
    return Check(name, False, f"{rule} is on {', '.join(ids)}, none about {phrase!r}")


def _banner_check(rule: str, projection: dict) -> Check:
    banners = projection.get("banners")
    name = f"banner {rule}"
    if any(b["rule_id"] == rule for b in banners or []):
        return Check(name, True, f"{rule} shown")
    return Check(name, False, f"no {rule} banner (banners: {_ids(banners, 'rule_id')})")


def _warning_check(code: str, projection: dict) -> Check:
    warnings = projection.get("parse_warnings")
    name = f"parse warning {code}"
    if any(w["code"] == code for w in warnings or []):
        return Check(name, True, f"{code} shown")
    return Check(name, False, f"no {code} warning (warnings: {_ids(warnings, 'code')})")


def _verdict_check(label: str, projection: dict) -> Check:
    name = f"verdict not {label}"
    actual = (projection.get("verdict") or {}).get("label")
    if actual is None:
        return Check(name, False, "the report has no verdict")
    return Check(name, actual != label, f"verdict is {actual}")


def _named(phrase: str, projection: dict) -> list[dict]:
    return [r for r in _requirements(projection) if fold_lower(phrase) in _text(r)]


def _hidden_risk_check(expect: dict, projection: dict) -> Check:
    name = f"hidden risk {_describe(expect)}"
    risks = projection.get("hidden_risks") or []
    hit = next((r for r in risks if all(r.get(k) == v for k, v in expect.items())), None)
    if hit:
        return Check(name, True, f"{hit['id']} shown")
    found = ", ".join(sorted({f"{r['kind']} at {r['risk']}" for r in risks})) or "none"
    return Check(name, False, f"no such risk (risks: {found})")


def _recency_check(expect: dict, projection: dict) -> Check:
    name = f"recency {_describe(expect)}"
    recency = projection.get("recency") or {}
    named = _named(expect["contains"], projection)
    if not named:
        return Check(name, False, f"no requirement contains {expect['contains']!r}")
    effects = {r["id"]: (recency.get(r["id"]) or {}).get("effect") for r in named}
    if expect["effect"] in effects.values():
        hit = next(rid for rid, effect in effects.items() if effect == expect["effect"])
        return Check(name, True, f"{hit} effect is {expect['effect']}")
    found = ", ".join(f"{rid} {effect or 'unchecked'}" for rid, effect in effects.items())
    return Check(name, False, f"no matching requirement has effect {expect['effect']} ({found})")


def _screening_flag_check(expect: dict, projection: dict) -> Check:
    name = f"screening flag {_describe(expect)}"
    flags = projection.get("screening_flags") or []
    named = _named(expect["contains"], projection)
    if not named:
        return Check(name, False, f"no requirement contains {expect['contains']!r}")
    flagged = {f["requirement_id"] for f in flags}
    hits = [r["id"] for r in named if r["id"] in flagged]
    if hits:
        return Check(name, True, f"flagged: {', '.join(hits)}")
    return Check(name, False, f"not flagged (flags: {_ids(flags, 'requirement_id')})")


def _refusal_check(expect: dict, projection: dict) -> Check:
    name = f"refusal {_describe(expect)}"
    refusals = projection.get("refusals") or []
    named = {r["id"] for r in _named(expect["contains"], projection)}
    if not named:
        return Check(name, False, f"no requirement contains {expect['contains']!r}")
    hits = [f for f in refusals if f["gate"] == expect["gate"] and f["requirement_id"] in named]
    if hits:
        return Check(name, True, f"{hits[0]['requirement_id']}: {hits[0]['reason']}")
    found = ", ".join(f"{f['requirement_id']} {f['gate']}" for f in refusals) or "none"
    return Check(name, False, f"no matching refusal (refusals: {found})")


def _ids(items: list[dict] | None, key: str) -> str:
    return ", ".join(sorted({item[key] for item in items or []})) or "none"


def make_graph():
    """The analysis graph backed by the model from settings. Imported only for --live."""
    from langgraph.checkpoint.memory import InMemorySaver

    from backedcv.llm.structured import AnthropicStructuredLLM
    from backedcv.settings import get_settings

    settings = get_settings()
    if settings.anthropic_api_key is None:
        raise SystemExit("ANTHROPIC_API_KEY is not set (add it to the repository's .env)")
    llm = AnthropicStructuredLLM(settings, cache=False)  # measure, never replay
    return build_graph(llm, checkpointer=InMemorySaver())


async def run_all(runs: list[PairRun], graph) -> None:
    """One pair after another, all in one event loop: the async model client binds to it."""
    for run in runs:
        config = run_config(run.analysis_id)
        failure = None
        try:
            await graph.ainvoke(run.state, config)
        except Exception as exc:  # the other pairs still run; the cost so far still counts
            failure = f"{type(exc).__name__}: {exc}"[:300]
        snapshot = await graph.aget_state(config)
        run.projection = project(run.analysis_id, snapshot)
        if failure:
            run.checks = [Check("reaches the report", False, failure)]
        else:
            run.checks = check_expectations(run.pair.expect, run.projection)


def _one_line(text: str | None) -> str:
    return " ".join((text or "-").split())


def _cell(text: str | None) -> str:
    return _one_line(text).replace("|", "\\|")


def _md_table(header: tuple[str, ...], rows: list[list[str]]) -> list[str]:
    def row(cells: list[str] | tuple[str, ...]) -> str:
        return "| " + " | ".join(_cell(c) for c in cells) + " |"

    return [row(header), "|" + "---|" * len(header), *(row(r) for r in rows)]


def _check_rows(runs: list[PairRun]) -> list[list[str]]:
    return [
        [run.pair.id, c.name, "PASS" if c.ok else "FAIL", c.reason]
        for run in runs
        for c in run.checks
    ]


def _analysis_row(run: PairRun) -> list[str]:
    p = run.projection or {}
    if not p:
        return [run.pair.id, *["-"] * 9]
    fit = (p.get("score") or {}).get("fit")
    return [
        run.pair.id,
        (p.get("verdict") or {}).get("label", "-"),
        "-" if fit is None else f"{fit:g}",
        str(len(_requirements(p))),
        _ids(p.get("flags"), "rule_id"),
        _ids(p.get("banners"), "rule_id"),
        _ids(p.get("parse_warnings"), "code"),
        str(len(p.get("errors") or [])),
        str(run.usage.get("calls", 0)),
        f"{run.usage.get('cost_usd', 0.0):.4f}",
    ]


def render_report(runs: list[PairRun], started: datetime) -> str:
    calls = sum(run.usage.get("calls", 0) for run in runs)
    cost = sum(run.usage.get("cost_usd", 0.0) for run in runs)
    lines = [
        f"# Smoke pairs: live run, {started:%Y-%m-%d %H:%M}",
        "",
        NOTE,
        "",
        "## Checks",
        "",
        *_md_table(("Pair", "Check", "Result", "Reason"), _check_rows(runs)),
        "",
        "## Analysis per pair",
        "",
        *_md_table(ANALYSIS_HEADER, [_analysis_row(run) for run in runs]),
        "",
        "## Cost",
        "",
        f"{calls} model calls, USD {cost:.4f} in total.",
    ]
    return "\n".join(lines) + "\n"


def _console_table(runs: list[PairRun]) -> list[str]:
    rows = [["PAIR", "CHECK", "RESULT", "REASON"], *_check_rows(runs)]
    widths = [max(len(row[i]) for row in rows) for i in range(3)]
    lines = [
        f"{a:<{widths[0]}}  {b:<{widths[1]}}  {c:<{widths[2]}}  {_one_line(d)}"
        for a, b, c, d in rows
    ]
    return [lines[0], "-" * len(lines[0]), *lines[1:]]


def summary_lines(runs: list[PairRun], report: Path) -> list[str]:
    checks = [c for run in runs for c in run.checks]
    calls = sum(run.usage.get("calls", 0) for run in runs)
    cost = sum(run.usage.get("cost_usd", 0.0) for run in runs)
    return [
        *_console_table(runs),
        "",
        f"Smoke pairs: {sum(run.passed for run in runs)} of {len(runs)} passed, "
        f"{sum(c.ok for c in checks)} of {len(checks)} checks",
        f"Cost: USD {cost:.4f} over {calls} model calls",
        f"Report: {report}",
    ]


def _record_in_langsmith(runs: list[PairRun]) -> None:
    from langsmith import Client

    client = Client()
    if client.has_dataset(dataset_name=LANGSMITH_DATASET):
        print(f"LangSmith: dataset '{LANGSMITH_DATASET}' exists, reusing its examples")
    else:
        dataset = client.create_dataset(
            LANGSMITH_DATASET, description="Synthetic CV and posting pairs with their expectations."
        )
        client.create_examples(
            dataset_id=dataset.id,
            examples=[
                {
                    "inputs": {"id": r.pair.id, "cv_text": r.cv_text, "job_text": r.job_text},
                    "outputs": {"expect": r.pair.expect},
                    "metadata": {"description": r.pair.description},
                }
                for r in runs
            ],
        )
    by_id = {r.pair.id: r for r in runs}

    def target(inputs: dict) -> dict:
        # Replays the checks of the live pass above, so the model is not paid for twice.
        run = by_id.get(inputs.get("id"))
        if run is None:
            return {"met": False, "checks": []}  # no live result: scores 0, never a crash
        return {"met": run.passed, "checks": [asdict(c) for c in run.checks]}

    def all_expectations_met(outputs: dict | None, reference_outputs: dict | None) -> dict:
        return {"key": "all_expectations_met", "score": int((outputs or {}).get("met") is True)}

    client.evaluate(
        target,
        data=LANGSMITH_DATASET,
        evaluators=[all_expectations_met],
        experiment_prefix="backedcv-smoke",
        metadata={"pairs": len(runs), "cost_usd": sum(r.usage.get("cost_usd", 0.0) for r in runs)},
    )
    print(f"LangSmith: recorded the run on dataset '{LANGSMITH_DATASET}'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the smoke pairs (see README.md).")
    parser.add_argument("--live", action="store_true", help="required: the pairs call the model")
    parser.add_argument("--langsmith", action="store_true", help="also record the run in LangSmith")
    parser.add_argument(
        "--results-dir", type=Path, default=RESULTS_DIR, help="where the report is written"
    )
    args = parser.parse_args(argv)
    if not args.live:
        parser.error("the smoke pairs call the model: pass --live to run them (it costs money)")

    sys.stdout.reconfigure(errors="replace")  # a model's text must not crash the summary
    started = datetime.now()
    runs = []
    for pair in load_pairs():
        try:
            runs.append(prepare(pair))
        except Exception as exc:  # name the pair and stop before the first model call
            raise SystemExit(f"{pair.id}: {type(exc).__name__}: {exc}") from exc
    graph = make_graph()
    asyncio.run(run_all(runs, graph))
    args.results_dir.mkdir(parents=True, exist_ok=True)
    report = args.results_dir / f"smoke-{started:%Y%m%d-%H%M}.md"
    report.write_text(render_report(runs, started), encoding="utf-8", newline="\n")
    print("\n".join(summary_lines(runs, report)))
    if args.langsmith:
        _record_in_langsmith(runs)
    return 0 if all(run.passed for run in runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
