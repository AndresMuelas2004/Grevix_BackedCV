from types import SimpleNamespace

import pytest

from backedcv.api.projection import project
from backedcv.domain.models import (
    ParseWarning,
    PostingBanner,
    Requirement,
    RequirementAssessment,
    RequirementFlag,
    ScoreBreakdown,
    Verdict,
)
from evals import run_smoke
from evals.run_smoke import (
    BACKEND_DIR,
    Check,
    Pair,
    PairRun,
    check_expectations,
    load_pairs,
    main,
    read_cv_source,
)

LICENSE = "Active, unencumbered state Registered Nurse (RN) license in Ohio."
SPANISH = "Spanish is preferred: many of our patients and their families speak Spanish at home."
LANGGRAPH = "5+ years of hands-on experience with LangGraph"
LANGCHAIN = "Hands-on experience with LangChain."
AUTHORIZATION = "Must be authorized to work in the United States without visa sponsorship."


def _expect(pair_id: str) -> dict:
    return next(pair.expect for pair in load_pairs() if pair.id == pair_id)


def _req(req_id: str, label: str, quote: str, *, category="other", importance="required", **kw):
    fields = {"category": category, "importance": importance, **kw}
    return Requirement(id=req_id, label=label, quote=quote, **fields).model_dump()


def _assessment(req_id: str, status="met", question=None) -> dict:
    return RequirementAssessment(
        requirement_id=req_id, status=status, question=question
    ).model_dump()


def _report(
    requirements, *, assessments=(), flags=(), banners=(), warnings=(), verdict="apply", paused=True
):
    """The projection that project() builds from a snapshot shaped like LangGraph's."""
    values = {
        "job": {"title": "Test role", "requirements": requirements},
        "assessments": {a["requirement_id"]: a for a in assessments},
        "flags": [f.model_dump() for f in flags],
        "banners": [b.model_dump() for b in banners],
        "parse_warnings": [w.model_dump() for w in warnings],
        "verdict": Verdict(label=verdict, title=verdict).model_dump(),
        "score": ScoreBreakdown(
            fit=80, coverage=60, coverage_numerator=1, coverage_denominator=2, pending_points=0
        ).model_dump(),
    }
    interrupts = [SimpleNamespace(value={"stage": "report_ready"})] if paused else []
    next_node = ("await_optimize",) if paused else ("prepare_job",)
    snapshot = SimpleNamespace(values=values, next=next_node, interrupts=interrupts)
    return project("analysis-test", snapshot)


def _curated(
    *, r1=True, r2=True, banner=True, warning=True, question=True, tools="partial"
) -> dict:
    flags = []
    if r1:
        flags.append(RequirementFlag(rule_id="R1", requirement_ids=["R01"], explanation="Entry."))
    if r2:
        flags.append(RequirementFlag(rule_id="R2", requirement_ids=["R01"], explanation="Newer."))
    asked = "Are you legally authorized to work in New York, NY without visa sponsorship?"
    auth = _assessment("R02", "unknown", asked) if question else _assessment("R02")
    return _report(
        [
            _req("R01", LANGGRAPH, LANGGRAPH, category="hard_skill", min_years=5),
            _req(
                "R02",
                "Work authorization",
                AUTHORIZATION,
                category="work_authorization",
                knockout_type="work_authorization",
            ),
            _req("R03", LANGCHAIN, LANGCHAIN, category="hard_skill"),
        ],
        assessments=[_assessment("R01", tools), auth, _assessment("R03", tools)],
        flags=flags,
        banners=[PostingBanner(rule_id="R3", explanation="Many hard skills.")] if banner else [],
        warnings=[ParseWarning(code="multi_column", severity="warning", message="Two columns.")]
        if warning
        else [],
    )


def _nurse(*, license_asked=False, spanish="preferred", verdict="answer_questions") -> dict:
    requirements = [
        _req(
            "R01",
            "Active state RN license",
            LICENSE,
            category="certification_license",
            knockout_type="certification_license",
        ),
        _req("R02", "Spanish", SPANISH, category="language", importance=spanish),
    ]
    license_check = (
        _assessment("R01", "unknown", "Do you hold this credential: Active state RN license?")
        if license_asked
        else _assessment("R01")
    )
    return _report(requirements, assessments=[license_check, _assessment("R02")], verdict=verdict)


def _failed(checks: list[Check]) -> list[str]:
    return [check.name for check in checks if not check.ok]


def _pair_run(pair_id: str, checks: list[Check]) -> PairRun:
    pair = Pair(id=pair_id, description="test", cv="cv.txt", job="job.txt", expect={})
    return PairRun(pair, "analysis-test", {}, "CV text", "Job text", checks=checks)


# The expectation checker, on hand-built reports (no model) --------------------------------


def test_curated_expectations_pass_on_a_report_that_shows_them():
    checks = check_expectations(_expect("curated-two-column"), _curated())

    assert _failed(checks) == []
    assert "parse warning multi_column" in [check.name for check in checks]


@pytest.mark.parametrize(
    ("missing", "failed"),
    [
        ({"r1": False}, "flag R1"),
        ({"r2": False}, "flag R2"),
        ({"banner": False}, "banner R3"),
        ({"warning": False}, "parse warning multi_column"),
        (
            {"question": False},
            "requirement knockout_type=work_authorization, screening_question=true",
        ),
    ],
)
def test_each_missing_piece_fails_only_its_own_check(missing, failed):
    checks = check_expectations(_expect("curated-two-column"), _curated(**missing))

    assert _failed(checks) == [failed]


def test_a_failed_flag_names_the_flags_it_did_find():
    [failed] = [
        c for c in check_expectations(_expect("curated-two-column"), _curated(r2=False)) if not c.ok
    ]

    assert failed.reason == "no R2 flag (flags: R1)"


@pytest.mark.parametrize("tools", ["partial", "met"])
def test_langchain_and_langgraph_pass_when_partial_or_met(tools):
    checks = check_expectations(_expect("curated-two-column"), _curated(tools=tools))

    assert _failed(checks) == []


def test_langchain_and_langgraph_fail_when_the_cv_shows_them_missing():
    checks = check_expectations(_expect("curated-two-column"), _curated(tools="missing"))

    assert _failed(checks) == [
        "requirement contains=LangChain, status=partial or met",
        "requirement contains=LangGraph, status=partial or met",
    ]


def test_simple_sample_needs_the_r1_flag_on_langgraph():
    requirements = [_req("R01", "Strong Python", "Strong Python skills.", category="hard_skill")]
    flags = [RequirementFlag(rule_id="R1", requirement_ids=["R01"], explanation="Entry.")]

    failed = _failed(
        check_expectations(_expect("simple-sample"), _report(requirements, flags=flags))
    )

    assert "flag R1 about LangGraph" in failed


def test_nurse_pair_passes_when_the_license_is_held_and_spanish_is_preferred():
    checks = check_expectations(_expect("nurse-rn"), _nurse())

    assert _failed(checks) == []


def test_a_license_question_fails_the_nurse_pair():
    checks = check_expectations(_expect("nurse-rn"), _nurse(license_asked=True))

    assert _failed(checks) == ["requirement contains=license, status=met, screening_question=false"]


def test_spanish_must_be_preferred_not_required():
    checks = check_expectations(_expect("nurse-rn"), _nurse(spanish="required"))

    assert _failed(checks) == ["requirement contains=Spanish, importance=preferred"]


def test_a_likely_screened_out_verdict_fails_the_nurse_pair():
    checks = check_expectations(_expect("nurse-rn"), _nurse(verdict="likely_screened_out"))

    assert _failed(checks) == ["verdict not likely_screened_out"]


def test_an_analysis_that_has_not_paused_fails_first():
    checks = check_expectations(_expect("nurse-rn"), _report([], paused=False))

    assert (checks[0].name, checks[0].ok) == ("reaches the report", False)
    assert checks[0].reason == "status stalled, stage none"


@pytest.mark.parametrize(
    "expect",
    [
        {"flagz": []},
        {"requirements": [{"containz": "license"}]},
        {"requirements": [{"status": "maybe"}]},
        {"requirements": [{"status": ["partial", "maybe"]}]},
        {"requirements": [{"status": []}]},
        {"requirements": [{"screening_question": "yes"}]},
        {"flags": [{"rule": "R9"}]},
        {"banners": ["R1"]},
        {"verdict_not": ["maybe"]},
    ],
)
def test_misspelled_expectations_are_rejected(expect):
    with pytest.raises(ValueError):
        run_smoke.validate_expect(expect)


# The pairs file and the inputs it points to (no model) -------------------------------------


def test_pairs_load_and_every_file_they_reference_exists():
    pairs = load_pairs()

    assert [pair.id for pair in pairs] == [
        "curated-two-column",
        "simple-sample",
        "nurse-rn",
        "hidden-risk",
    ]
    for pair in pairs:
        for value in (pair.cv, pair.job):
            if not run_smoke.is_inline(value):
                assert (BACKEND_DIR / value).is_file(), value


def test_every_pair_reads_and_fits_the_api_limits():
    runs = [run_smoke.prepare(pair) for pair in load_pairs()]

    assert all(run.state["cv_lines"] and run.job_text for run in runs)


def test_the_curated_pdf_reads_as_two_columns():
    cv = read_cv_source("samples/curated/cv.pdf")

    assert (cv.kind, cv.multi_column) == ("pdf", True)


def test_inline_text_is_read_as_pasted_text():
    cv = read_cv_source("Jane Doe\nSUMMARY\nBackend engineer.")

    assert cv.kind == "text"
    assert [line.text for line in cv.lines] == ["Jane Doe", "SUMMARY", "Backend engineer."]


def test_the_runner_refuses_to_run_without_live(tmp_path):
    with pytest.raises(SystemExit):
        main(["--results-dir", str(tmp_path)])

    assert list(tmp_path.iterdir()) == []


# LangSmith scoring, with a fake client ----------------------------------------------------


class _FakeLangSmithClient:
    """Stands in for langsmith.Client: keeps the uploaded examples and runs the evaluators."""

    def __init__(self):
        self.examples = []
        self.scores = []

    def has_dataset(self, dataset_name):
        return False

    def create_dataset(self, dataset_name, description=None):
        return SimpleNamespace(id="dataset-id")

    def create_examples(self, dataset_id, examples):
        self.examples = examples

    def evaluate(self, target, /, data=None, evaluators=(), experiment_prefix=None, metadata=None):
        for example in self.examples:
            outputs = target(example["inputs"])
            for evaluator in evaluators:
                result = evaluator(outputs=outputs, reference_outputs=example["outputs"])
                self.scores.append(result["score"])


def test_langsmith_scores_each_pair_on_whether_all_its_expectations_hold(monkeypatch):
    import langsmith  # imported here only: the checks above never load it

    client = _FakeLangSmithClient()
    monkeypatch.setattr(langsmith, "Client", lambda: client)
    met = _pair_run("nurse-rn", [Check("reaches the report", True, "ok")])
    unmet = _pair_run(
        "simple-sample",
        [Check("reaches the report", True, "ok"), Check("flag R1 about LangGraph", False, "no")],
    )

    run_smoke._record_in_langsmith([met, unmet])

    assert [example["inputs"]["id"] for example in client.examples] == ["nurse-rn", "simple-sample"]
    assert client.scores == [1, 0]
