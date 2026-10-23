"""Same CV and posting, same verdict and score, whatever the whitespace or requirement split."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backedcv.domain.builders import build_job
from backedcv.domain.dedupe import canonical_requirements
from backedcv.domain.models import RequirementAssessment
from backedcv.domain.scoring import compute_score
from backedcv.domain.text import normalize_text
from backedcv.llm.cache import answer_key
from backedcv.llm.drafts import (
    AssessmentDraft,
    JobExtractionDraft,
    MatchChunkDraft,
    RequirementDraft,
)
from backedcv.llm.prompt_loader import load_prompt
from backedcv.main import create_app
from tests.fakes import FakeLLM

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "curated"
JOB = (SAMPLES / "job.txt").read_text(encoding="utf-8")
CV = (SAMPLES / "cv.txt").read_text(encoding="utf-8")


def messy(text: str) -> str:
    """Messy variant of a text: BOM, leading newline, CRLF, NBSP, a zero-width space, tabs,
    trailing spaces and a longer gap between sections."""
    text = "\U0000feff\n" + text.replace("About the role\n", "About the role \n", 1)
    text = text.replace("Python and SQL", "Python\xa0and SQL\U0000200b", 1)
    text = text.replace("Requirements\n", "Requirements \t \n", 1)
    text = text.replace("\n\nWhat you will do", "\n \n\t\n\nWhat you will do", 1)
    return "\r\n".join(line + "  " for line in text.split("\n"))


def _draft(quote, terms, label, category="hard_skill", importance="required", **kw):
    return RequirementDraft(
        quote=quote,
        terms=terms,
        label=label,
        category=category,
        importance=importance,
        cue=kw.get("cue"),
        knockout_type=kw.get("knockout_type"),
        min_years=kw.get("min_years"),
        aliases=[],
    )


def _job(requirements: list[RequirementDraft]) -> JobExtractionDraft:
    return JobExtractionDraft(
        title="Junior AI Engineer",
        company="Lanternfield Analytics",
        seniority="entry level",
        seniority_quote="entry-level",
        location="New York, NY",
        remote_policy="onsite",
        employment_type=None,
        salary_present=False,
        requirements=requirements,
    )


DEGREE = "Bachelor's degree in Computer Science or a related field."
PY_SQL = "Strong Python and SQL skills."
LANGGRAPH = "5+ years of hands-on experience with LangGraph."
DOCKER = "Working knowledge of Docker and FastAPI."
DATA = "Familiarity with Spark, Airflow, dbt and Kafka."
COMMON = [
    _draft(DEGREE, ["Bachelor's degree"], "CS degree", "education", knockout_type="education"),
    _draft("Hands-on experience with LangChain.", ["LangChain"], "LangChain"),
    _draft("Excellent communication skills.", [], "Communication", "soft_skill"),
    _draft(
        "Must be authorized to work in the United States without visa sponsorship.",
        [],
        "US work authorization",
        "work_authorization",
        knockout_type="work_authorization",
    ),
    _draft("Experience with AWS.", ["AWS"], "AWS", importance="preferred"),
]
# The model's answer, split finely: every listed tool on its own and LangGraph twice.
FINE = _job(
    [
        *COMMON,
        _draft(PY_SQL, ["Python"], "Python"),
        _draft(PY_SQL, ["SQL"], "SQL"),
        _draft(LANGGRAPH, ["LangGraph"], "LangGraph"),
        _draft(
            LANGGRAPH,
            ["LangGraph"],
            "5+ years of LangGraph",
            "experience_years",
            knockout_type="experience_years",
            min_years=5,
        ),
        _draft(DOCKER, ["Docker"], "Docker", importance="required"),  # the section says preferred
        _draft(DOCKER, ["FastAPI"], "FastAPI", importance="preferred"),
        *(_draft(DATA, [tool], tool, importance="preferred") for tool in ("Spark", "Airflow")),
        *(_draft(DATA, [tool], tool, importance="preferred") for tool in ("dbt", "Kafka")),
    ]
)
# The same posting, split coarsely: one requirement per bullet.
COARSE = _job(
    [
        *reversed(COMMON),  # and listed in another order
        _draft(PY_SQL, ["Python", "SQL"], "Python and SQL"),
        _draft(
            LANGGRAPH,
            ["LangGraph"],
            "LangGraph experience",
            "experience_years",
            knockout_type="experience_years",
            min_years=5,
        ),
        _draft(DOCKER, ["Docker", "FastAPI"], "Docker and FastAPI", importance="preferred"),
        _draft(DATA, ["Spark", "Airflow", "dbt"], "Data tools", importance="preferred"),
    ]
)


class CuratedLLM(FakeLLM):
    """The fake model, answering for the curated posting: matching marks met exactly the
    requirements whose terms the CV shows (the exact_hits the code gives it)."""

    def __init__(self, extraction: JobExtractionDraft = FINE):
        super().__init__()
        self.extraction = extraction

    async def run(self, prompt, data, schema, *, node):
        if schema is JobExtractionDraft:
            self.calls.append(node)
            self.received.append((node, data))
            return self.extraction, {
                "node": node,
                "model": "fake",
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": 0.0,
            }
        if schema is MatchChunkDraft:
            self.calls.append(node)
            self.received.append((node, data))
            rows = data.split("<requirements>\n")[1].split("\n</requirements>")[0].splitlines()
            assessments = []
            for row in rows:
                rid, hits = row.split(" | ")[0], row.rsplit("exact_hits: ", 1)[1].split(", ")
                met = hits != ["none"]
                assessments.append(
                    AssessmentDraft(
                        requirement_id=rid,
                        status="met" if met else "missing",
                        line_ids=hits if met else [],
                        match_type="exact" if met else None,
                        rationale="Shown in the CV." if met else "Not in the CV.",
                    )
                )
            return MatchChunkDraft(assessments=assessments), {
                "node": node,
                "model": "fake",
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": 0.0,
            }
        return await super().run(prompt, data, schema, node=node)


def _events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def _analyse(job_text: str, cv_text: str) -> tuple[dict, CuratedLLM]:
    llm = CuratedLLM()
    with TestClient(create_app(llm=llm, checkpointer=InMemorySaver())) as client:
        response = client.post("/api/analyses", data={"job_text": job_text, "cv_text": cv_text})
    assert response.status_code == 200
    name, report = _events(response.text)[-1]
    assert name == "report"
    return report, llm


def test_the_messy_variants_normalize_to_the_original():
    assert normalize_text(messy(JOB)) == normalize_text(JOB)
    assert normalize_text(messy(CV)) == normalize_text(CV)
    assert normalize_text(
        "\n" + JOB.replace("About the role", "About the role ")
    ) == normalize_text(JOB)


def test_the_messy_posting_gets_the_same_cache_key():
    prompt = load_prompt("extract_job")

    def key(data: str) -> str:
        return answer_key("claude-haiku-5-5", "low", prompt, JobExtractionDraft, data)

    def as_sent(posting: str) -> str:  # the extraction input, as prepare_job builds it
        return f"<job_posting>\n{normalize_text(posting)}\n</job_posting>"

    assert key(as_sent(messy(JOB))) == key(as_sent(JOB))
    # The key itself ignores whitespace and invisible characters inside the input too.
    raw = as_sent(JOB).replace("\n", "  \r\n").replace(" and ", "\xa0and\U0000200b ")
    assert key(raw) == key(as_sent(JOB))
    assert key(as_sent(JOB + " more")) != key(as_sent(JOB))  # a real change is another key


@pytest.mark.parametrize("variant", [messy, lambda t: "\n" + t.replace("role\n", "role \n", 1)])
def test_same_pair_with_other_whitespace_gives_the_same_report(variant):
    original, llm_a = _analyse(JOB, CV)
    changed, llm_b = _analyse(variant(JOB), variant(CV))

    assert sorted(llm_a.received) == sorted(llm_b.received)  # the model got the same input
    for key in ("job", "assessments", "score", "verdict", "flags", "hidden_risks"):
        assert key in original
        assert changed[key] == original[key], key
    labels = [r["label"] for r in original["job"]["requirements"]]
    assert labels.count("5+ years of LangGraph") == 1 and "LangGraph" not in labels


def test_a_fine_and_a_coarse_split_of_the_posting_give_nearly_the_same_fit():
    posting = normalize_text(JOB)
    cv = normalize_text(CV).casefold()

    def fit(extraction: JobExtractionDraft) -> float:
        job, _ = build_job(posting, extraction)
        job = canonical_requirements(job, posting)
        assessments = {
            r.id: RequirementAssessment(
                requirement_id=r.id,
                status="met" if any(t.casefold() in cv for t in r.terms) else "missing",
            )
            for r in job.requirements
        }
        return compute_score(job.requirements, assessments).fit

    fine, coarse = fit(FINE), fit(COARSE)
    assert abs(fine - coarse) <= 2.0, (fine, coarse)
