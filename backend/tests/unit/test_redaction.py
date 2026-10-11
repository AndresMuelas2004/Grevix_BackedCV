"""Contact details never reach a model: redaction rules, graph prompts, order agent outline."""

import asyncio
import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backedcv.agents.cv_builder import Workspace
from backedcv.agents.cv_builder.agent import _outline
from backedcv.domain.document_diff import document_from_cv
from backedcv.domain.models import CVLine, ParsedCV
from backedcv.domain.redaction import numbered_rows, redact_contact
from backedcv.graph.builder import build_graph, run_config
from backedcv.ingestion import read_cv_text
from tests.fakes import CV_TEXT, JOB_TEXT, FakeLLM
from tests.fakes_optimize import FakeOptimizeLLM

# The sample CV of tests/fakes.CV_TEXT with the contact links a CV usually has (same lines and IDs).
CV_WITH_LINKS = CV_TEXT.replace(
    "+34 600 123 456\n", "+34 600 123 456 · linkedin.com/in/janedoe\n"
).replace(
    "Built a support bot with LangGraph\n",
    "Built a support bot with LangGraph · github.com/janedoe · janedoe.dev\n",
)
# The contact values of CV_WITH_LINKS. None of them may appear in a prompt.
CONTACT = [
    "jane@example.com",
    "600 123 456",
    "linkedin.com/in/janedoe",
    "github.com/janedoe",
    "janedoe.dev",
]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("jane@example.com", "[email]"),
        ("Contact: jane.doe+cv@mail.example.co.uk.", "Contact: [email]."),
        ("JANE@EXAMPLE.COM", "[email]"),
        ("+34 600 000 142", "[phone]"),
        ("Tel. +34 600 123 456, Madrid", "Tel. [phone], Madrid"),
        ("(212) 555-0100", "[phone]"),
        ("+1 (212) 555-0100", "[phone]"),
        ("(+34) 600 123 456", "[phone]"),
        ("612345678", "[phone]"),
        ("+33 6 12 34 56 78", "[phone]"),
        ("06.12.34.56.78", "[phone]"),
        ("600  123 456", "[phone]"),
        ("600 123 456 (Madrid)", "[phone] (Madrid)"),
        ("https://janedoe.dev/work", "[link]"),
        ("www.janedoe.com", "[link]"),
        ("janedoe.dev", "[link]"),
        ("janedoe.co.uk", "[link]"),
        ("jane-doe.github.io", "[link]"),
        ("linkedin.com/in/janedoe", "[link]"),
        ("https://www.linkedin.com/in/jane-doe-123/", "[link]"),
        ("github.com/janedoe", "[link]"),
        ("See https://janedoe.dev.", "See [link]."),
        ("(github.com/janedoe)", "([link])"),
        (
            "Madrid, Spain · jane@example.com · +34 600 123 456 · linkedin.com/in/janedoe",
            "Madrid, Spain · [email] · [phone] · [link]",
        ),
    ],
)
def test_contact_details_are_replaced(text, expected):
    assert redact_contact(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Jan 2021 - Present",
        "2019 - 2023",
        "03/2019 - 2021",
        "2019 2020 2021",
        "2019-2023 (4 years)",
        "Certified in 2020, renewed 2023",
        "Grew revenue 2 million EUR",
        "Cut costs by 71%",
        "Salary 40,000 - 50,000 EUR",
        "Revenue 120 000 000 EUR",
        "Processed 1 000 000 rows",
        "Built a service in C++ and C#",
        "Python 3.12.1 and Node.js 20.11",
        "v2.10.4",
        "Python 3.10.12 3.11.4 3.12.1",
        "ASP.NET Core, Vue.js, Next.js",
        "Team of 12 engineers across 3 countries",
        "Total professional experience: 3.2 years (computed from the dates of 3 jobs)",
    ],
)
def test_dates_numbers_and_versions_are_kept(text):
    assert redact_contact(text) == text


def test_numbered_rows_redact_each_text_and_keep_the_ids():
    rows = numbered_rows(
        [("L001", "Jane Doe"), ("L002", "Madrid · jane@example.com · +34 600 123 456")]
    )

    assert rows == "L001 | Jane Doe\nL002 | Madrid · [email] · [phone]"


def test_the_cv_numbered_block_is_redacted():
    cv = ParsedCV(lines=[CVLine(id="L002", text="Madrid · jane@example.com")])

    assert cv.numbered() == "L002 | Madrid · [email]"


def _assert_no_contact(data: str) -> None:
    for value in CONTACT:
        assert value not in data, value


def _start(llm):
    graph = build_graph(llm, checkpointer=InMemorySaver())
    analysis_id = str(uuid.uuid4())
    initial = {
        "analysis_id": analysis_id,
        "cv_lines": [line.model_dump() for line in read_cv_text(CV_WITH_LINKS).lines],
        "job_text": JOB_TEXT,
    }
    return graph, run_config(analysis_id), initial


def test_the_analysis_prompts_hold_no_contact_details():
    llm = FakeLLM()
    graph, config, initial = _start(llm)

    asyncio.run(graph.ainvoke(initial, config))

    assert sorted(set(llm.calls)) == [
        "match_chunk",
        "prepare_cv",
        "prepare_job",
        "review_posting",
        "screen_barriers",
    ]
    for _, data in llm.received:
        _assert_no_contact(data)
    assert "L002 | Madrid, Spain · [email] · [phone] · [link]" in dict(llm.received)["prepare_cv"]

    # The app keeps the original details: contact detection reads the unredacted lines.
    contact = asyncio.run(graph.aget_state(config)).values["cv"]["contact"]
    assert contact["email"]["value"] == "jane@example.com"
    assert contact["phone"]["value"] == "+34 600 123 456"
    assert [link["value"] for link in contact["links"]] == [
        "linkedin.com/in/janedoe",
        "github.com/janedoe",
    ]


def test_the_suggest_and_verify_prompts_hold_no_contact_details():
    llm = FakeOptimizeLLM()
    graph, config, initial = _start(llm)

    asyncio.run(graph.ainvoke(initial, config))  # pauses before optimizing
    asyncio.run(graph.ainvoke(Command(resume=True), config))  # suggest, verify, then the review

    assert asyncio.run(graph.aget_state(config)).next == ("await_review",)
    assert {"suggest", "verify_batch"} <= set(llm.calls)
    for _, data in llm.received:
        _assert_no_contact(data)
    for node, data in llm.received:
        if node in ("suggest", "verify_batch"):  # both read the CV, with the links redacted
            assert "L007 | Built a support bot with LangGraph · [link] · [link]" in data


def test_the_order_agent_outline_holds_no_contact_details():
    # L001 is the headline, so the first body line (the one the outline shows) is L002.
    cv = ParsedCV(
        lines=[
            CVLine(id="L001", text="Jane Doe"),
            CVLine(
                id="L002",
                text="Built ETL · github.com/janedoe · +34 600 123 456 · jane@example.com",
            ),
        ]
    )
    ws = Workspace(document=document_from_cv(cv), cv=cv, applied=[], accepted_ids=set())

    outline = _outline(ws)

    assert "Built ETL · [link] · [phone] · [email]" in outline
    _assert_no_contact(outline)
