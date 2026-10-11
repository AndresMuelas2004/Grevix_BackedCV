"""Canned LLM answers for tests: no network, no cost."""

from backedcv.llm.drafts import (
    AssessmentDraft,
    CVStructureDraft,
    EntryDraft,
    JobExtractionDraft,
    MatchChunkDraft,
    RequirementDraft,
    SectionDraft,
)
from backedcv.llm.drafts_optimize import ContradictionDraft, PostingReviewDraft

CV_TEXT = """Jane Doe
Madrid, Spain · jane@example.com · +34 600 123 456
EXPERIENCE
Data Engineer, Acme Corp
Jan 2021 - Present
Built ETL pipelines in Python and SQL on AWS
Built a support bot with LangGraph
EDUCATION
BSc Computer Science, Universidad Example, 2020
"""

JOB_TEXT = """Junior Data Engineer at Example Analytics (New York, NY, onsite).
Requirements:
- Strong Python and SQL skills.
- Experience with agent frameworks.
- Must have 5+ years of experience with Kubernetes.
- Must be authorized to work in the United States without sponsorship.
Nice to have: experience with dbt.
"""


def structure_draft() -> CVStructureDraft:
    return CVStructureDraft(
        name_line_id="L001",
        location_line_id="L002",
        sections=[
            SectionDraft(
                type="contact", heading_line_id=None, first_line_id="L001", last_line_id="L002"
            ),
            SectionDraft(
                type="experience", heading_line_id="L003", first_line_id="L003", last_line_id="L007"
            ),
            SectionDraft(
                type="education", heading_line_id="L008", first_line_id="L008", last_line_id="L009"
            ),
        ],
        entries=[
            EntryDraft(
                kind="job",
                title="Data Engineer",
                organization="Acme Corp",
                location=None,
                first_line_id="L004",
                last_line_id="L007",
                date_line_id="L005",
            ),
            EntryDraft(
                kind="education",
                title="BSc Computer Science",
                organization="Universidad Example",
                location=None,
                first_line_id="L009",
                last_line_id="L009",
                date_line_id="L009",
            ),
        ],
    )


def _req(quote, terms, label, category, importance="required", **kw):
    return RequirementDraft(
        quote=quote,
        terms=terms,
        label=label,
        category=category,
        importance=importance,
        cue=kw.get("cue"),
        knockout_type=kw.get("knockout_type"),
        min_years=kw.get("min_years"),
        aliases=kw.get("aliases", []),
    )


def job_draft() -> JobExtractionDraft:
    return JobExtractionDraft(
        title="Junior Data Engineer",
        company="Example Analytics",
        seniority="junior",
        seniority_quote="Junior",
        location="New York, NY",
        remote_policy="onsite",
        employment_type=None,
        salary_present=False,
        requirements=[
            _req("Strong Python and SQL skills.", ["Python"], "Python", "hard_skill"),
            _req("Strong Python and SQL skills.", ["SQL"], "SQL", "hard_skill"),
            _req(
                "Experience with agent frameworks.",
                ["agent frameworks"],
                "Agent frameworks",
                "hard_skill",
            ),
            _req(
                "Must have 5+ years of experience with Kubernetes.",
                ["Kubernetes"],
                "5+ years of Kubernetes",
                "experience_years",
                cue="Must",
                knockout_type="experience_years",
                min_years=5,
            ),
            _req(
                "Must be authorized to work in the United States without sponsorship.",
                [],
                "US work authorization",
                "work_authorization",
                cue="Must",
                knockout_type="work_authorization",
            ),
            _req(
                "experience with dbt",
                ["dbt"],
                "dbt",
                "hard_skill",
                importance="preferred",
                cue="Nice to have",
            ),
            _req("This line is not in the posting", ["Rust"], "Rust", "hard_skill"),
        ],
    )


def match_draft(requirement_ids: list[str]) -> MatchChunkDraft:
    canned = {
        "R01": AssessmentDraft(
            requirement_id="R01",
            status="met",
            line_ids=["L006"],
            match_type="exact",
            rationale="Python appears in L006.",
        ),
        "R02": AssessmentDraft(
            requirement_id="R02",
            status="met",
            line_ids=["L006"],
            match_type="exact",
            rationale="SQL appears in L006.",
        ),
        "R03": AssessmentDraft(
            requirement_id="R03",
            status="met",
            line_ids=["L007"],
            match_type="semantic",
            rationale="LangGraph is one.",
        ),
        "R04": AssessmentDraft(
            requirement_id="R04",
            status="missing",
            line_ids=[],
            match_type=None,
            rationale="No Kubernetes.",
        ),
        "R05": AssessmentDraft(
            requirement_id="R05",
            status="missing",
            line_ids=[],
            match_type=None,
            rationale="Not stated.",
        ),
        "R06": AssessmentDraft(
            requirement_id="R06",
            status="met",
            line_ids=["L999"],
            match_type="exact",
            rationale="Invented line ID.",
        ),
    }
    return MatchChunkDraft(assessments=[canned[r] for r in requirement_ids if r in canned])


def review_draft() -> PostingReviewDraft:
    """One contradiction (the example from the prompt), so the posting_red_flags badge shows."""
    return PostingReviewDraft(
        contradictions=[
            ContradictionDraft(
                explanation="Fully remote work and five on-site days a week do not seem to fit.",
                quotes=[
                    "Work fully remote from anywhere",
                    "Work on-site in our Madrid office five days a week",
                ],
            )
        ],
        doubtful_credentials=[],
    )


class FakeLLM:
    def __init__(self):
        self.calls: list[str] = []
        self.received: list[tuple[str, str]] = []  # (node, data) of every call: what the model got

    async def run(self, prompt, data, schema, *, node):
        self.calls.append(node)
        self.received.append((node, data))
        usage = {
            "node": node,
            "model": "fake",
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_usd": 0.0,
        }
        if schema is CVStructureDraft:
            return structure_draft(), usage
        if schema is JobExtractionDraft:
            return job_draft(), usage
        if schema is MatchChunkDraft:
            ids = [
                row.split(" | ")[0]
                for row in data.split("<requirements>\n")[1]
                .split("\n</requirements>")[0]
                .splitlines()
            ]
            return match_draft(ids), usage
        if schema is PostingReviewDraft:
            return review_draft(), usage
        raise AssertionError(f"unexpected schema {schema}")
