import asyncio

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.errors import GraphRecursionError
from pydantic import Field

from backedcv.agents.cv_builder import Workspace, make_tools, run_order_agent
from backedcv.domain.document_diff import document_from_cv, standard_order
from backedcv.domain.models import (
    Contact,
    ContactField,
    CVDocument,
    CVEntry,
    CVLine,
    CVSection,
    DocItem,
    DocSection,
    ParsedCV,
)
from backedcv.llm.prompt_loader import load_prompt

USAGE = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
JOB = "Title: Backend Engineer\n- Python (required)\n- FastAPI (preferred)"


class ScriptedChatModel(BaseChatModel):
    """Answers with one scripted message per call and records what it was sent. No network."""

    script: list[AIMessage] = Field(default_factory=list)
    fail: bool = False
    model_name: str = "scripted-order-model"
    turns: int = 0
    seen: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if self.fail:
            raise RuntimeError("model unavailable")
        self.seen.append(list(messages))
        message = self.script[self.turns] if self.turns < len(self.script) else AIMessage("Done.")
        self.turns += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


def _call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id}],
        usage_metadata=USAGE,
    )


def _cv() -> ParsedCV:
    """Contact, summary, two jobs and skills."""
    return ParsedCV(
        lines=[
            CVLine(id="L001", text="Jane Doe"),
            CVLine(id="L002", text="Summary"),
            CVLine(id="L003", text="Backend engineer focused on APIs."),
            CVLine(id="L004", text="Experience"),
            CVLine(id="L005", text="Senior Engineer"),
            CVLine(id="L006", text="Acme Corp, 2021-03 - Present"),
            CVLine(id="L007", text="Built the billing API in Python"),
            CVLine(id="L008", text="Junior Developer"),
            CVLine(id="L009", text="Beta Labs, 2018-06 - 2020-12"),
            CVLine(id="L010", text="Wrote the first ETL pipeline"),
            CVLine(id="L011", text="Skills"),
            CVLine(id="L012", text="Python, SQL, Docker"),
        ],
        contact=Contact(name=ContactField(value="Jane Doe", line_id="L001")),
        sections=[
            CVSection(id="S00", heading_line_id=None, type="contact", line_ids=["L001"]),
            CVSection(id="S01", heading_line_id="L002", type="summary", line_ids=["L002", "L003"]),
            CVSection(
                id="S02",
                heading_line_id="L004",
                type="experience",
                line_ids=["L004", "L005", "L006", "L007", "L008", "L009", "L010"],
            ),
            CVSection(id="S03", heading_line_id="L011", type="skills", line_ids=["L011", "L012"]),
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
            ),
            CVEntry(
                id="E02",
                section_id="S02",
                kind="job",
                title="Junior Developer",
                organization="Beta Labs",
                start="2018-06",
                end="2020-12",
                line_ids=["L008", "L009", "L010"],
            ),
        ],
    )


def _workspace() -> Workspace:
    cv = _cv()
    return Workspace(document=document_from_cv(cv), cv=cv, applied=[], accepted_ids=set())


def _order(doc: CVDocument) -> list[str]:
    return [section.id for section in doc.sections]


def _reading_order_cv() -> ParsedCV:
    """The sections in reading order, as a two-column CV gives them: education, skills and
    languages come before the summary and the experience."""
    return ParsedCV(
        lines=[
            CVLine(id="L001", text="Jane Doe"),
            CVLine(id="L002", text="Education"),
            CVLine(id="L003", text="MSc Computer Science, 2016-2018"),
            CVLine(id="L004", text="Skills"),
            CVLine(id="L005", text="Python, SQL, Docker"),
            CVLine(id="L006", text="Languages"),
            CVLine(id="L007", text="English, Spanish"),
            CVLine(id="L008", text="Summary"),
            CVLine(id="L009", text="Backend engineer focused on APIs."),
            CVLine(id="L010", text="Experience"),
            CVLine(id="L011", text="Built the billing API in Python"),
        ],
        contact=Contact(name=ContactField(value="Jane Doe", line_id="L001")),
        sections=[
            CVSection(id="S00", heading_line_id=None, type="contact", line_ids=["L001"]),
            CVSection(
                id="S01", heading_line_id="L002", type="education", line_ids=["L002", "L003"]
            ),
            CVSection(id="S02", heading_line_id="L004", type="skills", line_ids=["L004", "L005"]),
            CVSection(
                id="S03", heading_line_id="L006", type="languages", line_ids=["L006", "L007"]
            ),
            CVSection(id="S04", heading_line_id="L008", type="summary", line_ids=["L008", "L009"]),
            CVSection(
                id="S05", heading_line_id="L010", type="experience", line_ids=["L010", "L011"]
            ),
        ],
    )


def _reading_order_workspace() -> Workspace:
    cv = _reading_order_cv()
    return Workspace(document=document_from_cv(cv), cv=cv, applied=[], accepted_ids=set())


def _section(section_id: str, section_type: str, item_ids: list[str] | None = None) -> DocSection:
    items = [DocItem(id=item_id) for item_id in item_ids or []]
    return DocSection(id=section_id, type=section_type, heading=section_id, items=items)


def test_agent_moves_a_section_and_finalizes_so_the_new_order_is_kept():
    ws = _workspace()
    model = ScriptedChatModel(
        script=[
            _call("move_section", {"section_id": "S03", "position": 0}, "c1"),
            _call("finalize", {}, "c2"),
        ]
    )

    doc, built_by = asyncio.run(run_order_agent(ws, JOB, model))

    assert built_by == "agent"
    assert _order(doc) == ["S03", "S01", "S02"]
    assert ws.error is None
    assert len(ws.usage) == 3  # the move, the finalize and the closing reply
    assert ws.usage[0]["node"] == "build_cv"
    assert ws.usage[0]["input_tokens"] == 100
    system, human = model.seen[0]
    assert system.content == load_prompt("build_cv").text
    assert "S03 | skills | Skills" in human.content
    assert "E02 | Junior Developer | 2018-06 to 2020-12" in human.content


def test_invalid_reorder_without_finalize_keeps_the_original_order():
    ws = _workspace()
    original = ws.document
    model = ScriptedChatModel(
        script=[_call("reorder_items", {"section_id": "S02", "ordered_ids": ["E01"]}, "c1")]
    )

    doc, built_by = asyncio.run(run_order_agent(ws, JOB, model))

    assert built_by == "fallback"
    assert doc == original
    assert ws.approved is False
    results = [m.content for m in model.seen[1] if isinstance(m, ToolMessage)]
    assert results[0].startswith("Error: ordered_ids must name")


def test_a_model_that_raises_keeps_the_original_order():
    ws = _workspace()
    original = ws.document

    doc, built_by = asyncio.run(run_order_agent(ws, JOB, ScriptedChatModel(fail=True)))

    assert built_by == "fallback"
    assert doc == original
    assert isinstance(ws.error, RuntimeError)


def test_hitting_the_recursion_limit_keeps_the_original_order():
    ws = _workspace()
    original = ws.document
    script = [
        _call("move_section", {"section_id": "S03", "position": 0}, f"c{n}") for n in range(40)
    ]

    doc, built_by = asyncio.run(run_order_agent(ws, JOB, ScriptedChatModel(script=script)))

    assert built_by == "fallback"
    assert doc == original
    assert isinstance(ws.error, GraphRecursionError)


def test_tools_report_problems_as_text_and_finalize_approves_a_valid_order():
    ws = _workspace()
    tools = {tool.name: tool for tool in make_tools(ws)}

    assert tools["move_section"].invoke({"section_id": "S99", "position": 0}).startswith("Error:")
    assert tools["move_section"].invoke({"section_id": "S01", "position": 9}).startswith("Error:")
    duplicate = {"section_id": "S02", "ordered_ids": ["E01", "E01"]}
    assert tools["reorder_items"].invoke(duplicate).startswith("Error:")
    assert tools["finalize"].invoke({}) == "ok"
    assert ws.approved is True


def test_a_failed_order_agent_gives_the_standard_section_order():
    ws = _reading_order_workspace()
    assert _order(ws.document) == ["S01", "S02", "S03", "S04", "S05"]

    doc, built_by = asyncio.run(run_order_agent(ws, JOB, ScriptedChatModel(fail=True)))

    assert built_by == "fallback"
    assert _order(doc) == ["S04", "S05", "S01", "S02", "S03"]
    assert isinstance(ws.error, RuntimeError)


def test_an_order_that_is_never_finalized_gives_the_standard_section_order():
    ws = _reading_order_workspace()
    model = ScriptedChatModel(
        script=[_call("move_section", {"section_id": "S02", "position": 0}, "c1")]
    )

    doc, built_by = asyncio.run(run_order_agent(ws, JOB, model))

    assert built_by == "fallback"
    assert ws.approved is False
    assert _order(doc) == ["S04", "S05", "S01", "S02", "S03"]


def test_a_finalized_agent_order_is_kept_even_when_it_differs_from_the_standard_order():
    ws = _reading_order_workspace()
    model = ScriptedChatModel(
        script=[
            _call("move_section", {"section_id": "S02", "position": 0}, "c1"),
            _call("finalize", {}, "c2"),
        ]
    )

    doc, built_by = asyncio.run(run_order_agent(ws, JOB, model))

    assert built_by == "agent"
    assert _order(doc) == ["S02", "S01", "S03", "S04", "S05"]


def test_standard_order_keeps_the_items_and_the_order_of_sections_of_one_type():
    doc = CVDocument(
        sections=[
            _section("S01", "other"),
            _section("S02", "skills", ["S02-i2", "S02-i1"]),
            _section("S03", "languages"),
            _section("S04", "skills"),
            _section("S05", "summary"),
        ]
    )

    result = standard_order(doc)

    assert _order(result) == ["S05", "S02", "S04", "S03", "S01"]
    assert [item.id for item in result.sections[1].items] == ["S02-i2", "S02-i1"]
    assert _order(doc) == ["S01", "S02", "S03", "S04", "S05"]  # the input is not changed


def test_standard_order_puts_an_unknown_section_type_just_before_other():
    # The section type field allows only known types, so this section skips validation.
    hobbies = DocSection.model_construct(id="S02", type="hobbies", heading="Hobbies", items=[])
    doc = CVDocument.model_construct(
        sections=[_section("S01", "other"), hobbies, _section("S03", "languages")]
    )

    assert _order(standard_order(doc)) == ["S03", "S02", "S01"]
