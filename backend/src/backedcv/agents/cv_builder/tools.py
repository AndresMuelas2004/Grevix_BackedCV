"""Tools for the order agent. They change only the order of sections and items, and they report
problems as text so that the agent can read them and try again."""

from dataclasses import dataclass, field

from langchain_core.tools import BaseTool, tool

from backedcv.domain import document_diff
from backedcv.domain.models import CVDocument, ParsedCV, Suggestion


@dataclass
class Workspace:
    """Everything one ordering run needs. Only the tools change `document`, and only its order."""

    document: CVDocument  # the built document; each move replaces it with a reordered copy
    cv: ParsedCV
    applied: list[Suggestion]  # the accepted, verified suggestions already in `document`
    accepted_ids: set[str]
    approved: bool = False  # True when the last finalize returned "ok"
    usage: list[dict] = field(default_factory=list)  # one usage record per model call
    error: Exception | None = None  # why the run failed, if it did


def make_tools(ws: Workspace) -> list[BaseTool]:
    """The three tools of the order agent, bound to one workspace."""

    @tool
    def move_section(section_id: str, position: int) -> str:
        """Move one section so that it sits at this position. Position 0 is the first section."""
        try:
            ws.document = document_diff.move_section(ws.document, section_id, position)
        except ValueError as error:
            return f"Error: {error}"
        return f"Section order: {_section_order(ws)}"

    @tool
    def reorder_items(section_id: str, ordered_ids: list[str]) -> str:
        """Set the order of the items inside one section. Pass every item ID of that section
        exactly once, in the new order."""
        try:
            ws.document = document_diff.reorder_items(ws.document, section_id, ordered_ids)
        except ValueError as error:
            return f"Error: {error}"
        section = next(s for s in ws.document.sections if s.id == section_id)
        return f"Item order in {section_id}: {', '.join(item.id for item in section.items)}"

    @tool
    def finalize() -> str:
        """Check the new order. Call it when the order is final. Returns "ok" or the errors."""
        errors = document_diff.validate_document(ws.document, ws.cv, ws.applied, ws.accepted_ids)
        ws.approved = not errors
        return "ok" if not errors else "Errors: " + "; ".join(errors)

    return [move_section, reorder_items, finalize]


def _section_order(ws: Workspace) -> str:
    return ", ".join(section.id for section in ws.document.sections)
