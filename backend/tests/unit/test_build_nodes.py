import asyncio

from backedcv.domain.builders import build_assessments
from backedcv.domain.document_diff import move_section
from backedcv.domain.models import (
    BuildReport,
    Contact,
    ContactField,
    CVDocument,
    CVEntry,
    CVLine,
    CVSection,
    JobPosting,
    ParsedCV,
    Requirement,
    Suggestion,
    Verification,
)
from backedcv.domain.scoring import compute_score
from backedcv.graph import build_nodes
from backedcv.graph.build_nodes import make_build_nodes


def _state() -> dict:
    """One CV, one posting, one accepted verified suggestion (FastAPI into Skills) and one
    accepted suggestion the verifier rejected (it must not reach the CV)."""
    cv = ParsedCV(
        lines=[
            CVLine(id="L001", text="Jane Doe"),
            CVLine(id="L002", text="Summary"),
            CVLine(id="L003", text="Backend engineer focused on APIs."),
            CVLine(id="L004", text="Experience"),
            CVLine(id="L005", text="Senior Engineer"),
            CVLine(id="L006", text="Acme Corp, 2021-03 - Present"),
            CVLine(id="L007", text="Built the billing API in Python"),
            CVLine(id="L008", text="Skills"),
            CVLine(id="L009", text="Python, SQL, Docker"),
        ],
        contact=Contact(name=ContactField(value="Jane Doe", line_id="L001")),
        sections=[
            CVSection(id="S00", heading_line_id=None, type="contact", line_ids=["L001"]),
            CVSection(id="S01", heading_line_id="L002", type="summary", line_ids=["L002", "L003"]),
            CVSection(
                id="S02",
                heading_line_id="L004",
                type="experience",
                line_ids=["L004", "L005", "L006", "L007"],
            ),
            CVSection(id="S03", heading_line_id="L008", type="skills", line_ids=["L008", "L009"]),
        ],
        entries=[
            CVEntry(
                id="E01",
                section_id="S02",
                kind="job",
                title="Senior Engineer",
                organization="Acme Corp",
                start="2021-03",
                end="present",
                line_ids=["L005", "L006", "L007"],
            )
        ],
    )
    job = JobPosting(
        title="Backend Engineer",
        requirements=[
            Requirement(
                id="R01",
                label="Python",
                quote="Python",
                terms=["Python"],
                category="hard_skill",
                importance="required",
            ),
            Requirement(
                id="R02",
                label="FastAPI",
                quote="FastAPI",
                terms=["FastAPI"],
                category="hard_skill",
                importance="required",
            ),
        ],
    )
    assessments = build_assessments(job, cv, {})
    suggestions = [
        Suggestion(
            id="S01",
            kind="add_skill",
            target="S03",
            after="FastAPI",
            requirement_ids=["R02"],
            verification=Verification(status="verified"),
        ),
        Suggestion(
            id="S02",
            kind="align_wording",
            target="L007",
            before="Built the billing API in Python",
            after="Built the billing API in Python with Kubernetes",
            verification=Verification(status="unsupported", reason="The CV shows no Kubernetes."),
        ),
    ]
    return {
        "cv": cv.model_dump(),
        "job": job.model_dump(),
        "assessments": {rid: a.model_dump() for rid, a in assessments.items()},
        "score": compute_score(job.requirements, assessments).model_dump(),
        "suggestions": [s.model_dump() for s in suggestions],
        "decisions": {"accepted": ["S01", "S02"], "rejected": []},
        "flags": [],
        "excluded_ids": [],
        "included_flagged_ids": [],
    }


def _built(state: dict) -> dict:
    return asyncio.run(make_build_nodes()["build_cv"](state))


def _checked(state: dict) -> BuildReport:
    update = asyncio.run(make_build_nodes()["final_checks"](state))
    return BuildReport.model_validate(update["build_report"])


def test_build_cv_applies_the_accepted_verified_suggestion_and_not_the_unsupported_one():
    update = _built(_state())

    doc = CVDocument.model_validate(update["document"])
    texts = [line.text for section in doc.sections for item in section.items for line in item.lines]
    assert "FastAPI" in texts
    assert "Built the billing API in Python" in texts
    assert "Built the billing API in Python with Kubernetes" not in texts
    assert update["built_by"] == "fallback"


def test_final_checks_on_the_built_cv_round_trip_and_raise_coverage():
    state = _state()
    state = {**state, **_built(state)}

    report = _checked(state)

    assert report.roundtrip_ok is True
    assert report.roundtrip_issues == []
    assert report.validation_errors == []
    assert report.built_by == "fallback"
    assert report.fit == state["score"]["fit"]
    assert (report.coverage_before, report.coverage_after) == (50.0, 100.0)
    changed = [(d.status, d.origin) for d in report.diff if d.status != "unchanged"]
    assert changed == [("added", "S01")]


def test_a_render_failure_is_reported_in_the_build_report(monkeypatch):
    def broken_render(doc):
        raise RuntimeError("typst crashed")

    monkeypatch.setattr(build_nodes, "render_pdf", broken_render)
    state = _state()
    state = {**state, **_built(state)}

    report = _checked(state)

    assert report.roundtrip_ok is False
    assert report.roundtrip_issues == ["The PDF could not be rendered: RuntimeError: typst crashed"]
    assert report.coverage_after == 100.0


def test_build_cv_keeps_the_agent_order_and_its_usage(monkeypatch):
    async def reorder(ws, job_summary, model):
        ws.usage.append(
            {"node": "build_cv", "model": "stub", "input_tokens": 1, "output_tokens": 1}
        )
        return move_section(ws.document, "S03", 0), "agent"

    monkeypatch.setattr(build_nodes, "run_order_agent", reorder)
    update = asyncio.run(make_build_nodes(order_model=object())["build_cv"](_state()))

    assert update["built_by"] == "agent"
    assert [s["id"] for s in update["document"]["sections"]] == ["S03", "S01", "S02"]
    assert update["usage"][0]["model"] == "stub"
    assert update["errors"] == []


def test_a_failed_order_agent_is_recorded_as_an_error(monkeypatch):
    async def failing(ws, job_summary, model):
        ws.error = TimeoutError("slow")
        return ws.document, "fallback"

    monkeypatch.setattr(build_nodes, "run_order_agent", failing)
    update = asyncio.run(make_build_nodes(order_model=object())["build_cv"](_state()))

    assert update["built_by"] == "fallback"
    assert update["errors"] == [{"node": "build_cv", "error": "TimeoutError", "detail": "slow"}]
