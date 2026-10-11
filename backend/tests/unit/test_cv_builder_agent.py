import asyncio

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.errors import GraphRecursionError
from pydantic import Field

from backedcv.agents.cv_builder import Workspace, make_tools, run_order_agent
from backedcv.domain.document_diff import document_from_cv
from backedcv.domain.models import (
    Contact,
    ContactField,
    CVDocument,
    CVEntry,
    CVLine,
    CVSection,
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
