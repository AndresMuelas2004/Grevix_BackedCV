"""Keyword coverage of the new CV: the formula of domain/scoring.py, with keyword presence checked
on the new document instead of the original CV."""

from collections.abc import Iterable, Mapping, Sequence

from backedcv.domain.keywords import keyword_present
from backedcv.domain.models import CVDocument, CVLine, Requirement, RequirementAssessment
from backedcv.domain.scoring import compute_score


def coverage_after(
    requirements: Sequence[Requirement],
    assessments: Mapping[str, RequirementAssessment],
    doc: CVDocument,
    *,
    excluded_ids: Iterable[str] = (),
    flagged: Mapping[str, str] | None = None,
    included_flagged_ids: Iterable[str] = (),
) -> float | None:
    """Keyword coverage (0 to 100) of the new document, with the same inputs as compute_score.
    None when no requirement counts toward coverage."""
    lines = _shown_lines(doc)
    rechecked: dict[str, RequirementAssessment] = {}
    for req in requirements:
        base = assessments.get(req.id) or RequirementAssessment(
            requirement_id=req.id, status="unknown"
        )
        rechecked[req.id] = base.model_copy(update={"keyword_present": keyword_present(req, lines)})
    score = compute_score(
        list(requirements),
        rechecked,
        excluded_ids=excluded_ids,
        flagged=dict(flagged or {}),
        included_flagged_ids=included_flagged_ids,
    )
    return score.coverage


def _shown_lines(doc: CVDocument) -> list[CVLine]:
    """Every line the new CV shows: contact details, the headline, headings and body lines."""
    contact = [doc.contact.name, doc.contact.headline, *doc.contact.details]
    lines = [CVLine(id="contact", text=text) for text in contact if text]
    for section in doc.sections:
        lines.append(CVLine(id=section.heading_origin or section.id, text=section.heading))
        for item in section.items:
            lines.extend(CVLine(id=line.origin, text=line.text) for line in item.lines)
    return lines
