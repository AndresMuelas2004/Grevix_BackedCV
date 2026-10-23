"""Reorders one built CV for one job. Any failure falls back to the standard section order."""

import logging
from typing import Literal

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage

from backedcv.agents.cv_builder.tools import Workspace, make_tools
from backedcv.config import load
from backedcv.domain.document_diff import standard_order
from backedcv.domain.models import CVDocument, CVEntry, DocItem
from backedcv.domain.redaction import redact_contact
from backedcv.llm.prompt_loader import load_prompt
from backedcv.llm.structured import MAX_TOKENS, usage_record
from backedcv.settings import Settings

log = logging.getLogger(__name__)
RECURSION_LIMIT = 25


async def run_order_agent(
    ws: Workspace, job_summary: str, model: BaseChatModel
) -> tuple[CVDocument, Literal["agent", "fallback"]]:
    """The agent's order if it finalized one, else the standard order. Never raises: a failure is
    kept on `ws.error`."""
    original = ws.document
    prompt = load_prompt("build_cv")
    message = (
        f"<outline>\n{_outline(ws)}\n</outline>\n\n"
        f"<job_requirements>\n{job_summary}\n</job_requirements>"
    )
    try:
        agent = create_agent(model, make_tools(ws), system_prompt=prompt.text)
        result = await agent.ainvoke(
            {"messages": [HumanMessage(message)]},
            config={
                "recursion_limit": RECURSION_LIMIT,
                "run_name": "build_cv",
                "metadata": prompt.metadata,
                "tags": [prompt.id],
            },
        )
    except Exception as exc:  # the order agent is optional: the standard order is used instead
        log.warning("build agent failed: %s", exc)
        ws.error = exc
        return standard_order(original), "fallback"

    # ChatAnthropic names its model in `model`; other chat models (the tests' fake) in `model_name`.
    name = getattr(model, "model", None) or getattr(model, "model_name", "unknown")
    ws.usage.extend(
        usage_record("build_cv", name, m) for m in result["messages"] if isinstance(m, AIMessage)
    )
    if not ws.approved:
        return standard_order(original), "fallback"
    return ws.document, "agent"


def _outline(ws: Workspace) -> str:
    """One row per section and per item, with contact details redacted."""
    entries = {entry.id: entry for entry in ws.cv.entries}
    rows: list[str] = []
    for section in ws.document.sections:
        rows.append(f"{section.id} | {section.type} | {redact_contact(section.heading)}")
        rows.extend(_item_row(item, entries.get(item.id)) for item in section.items)
    return "\n".join(rows)


def _item_row(item: DocItem, entry: CVEntry | None) -> str:
    first = redact_contact(item.lines[0].text) if item.lines else ""
    dates = ""
    if entry is not None and entry.start:
        dates = f" | {entry.start} to {entry.end or 'unknown'}"
    return f"  {item.id} | {first}{dates}"


def default_order_model(settings: Settings) -> ChatAnthropic:
    effort = load("models").get("effort", {}).get("build_cv", "low")
    return ChatAnthropic(
        model=settings.model_fast,
        max_tokens=MAX_TOKENS,
        max_retries=1,
        effort=effort,
    )
