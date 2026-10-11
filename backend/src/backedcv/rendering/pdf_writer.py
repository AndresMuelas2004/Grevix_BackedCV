"""Render the rebuilt CV to PDF with Typst, using the bundled ATS-safe template."""

import json
from pathlib import Path

import typst

from backedcv.domain.models import CVDocument

TEMPLATE = Path(__file__).parent / "templates" / "cv.typ"


def render_pdf(doc: CVDocument) -> bytes:
    """Pass the document as JSON through sys.inputs; the template reads it back as plain text.

    ignore_system_fonts keeps the output on Typst's embedded fonts, so it looks the same
    on every machine.
    """
    payload = json.dumps(doc.model_dump(mode="json"), ensure_ascii=False)
    return typst.compile(
        TEMPLATE,
        format="pdf",
        ignore_system_fonts=True,
        sys_inputs={"data": payload},
    )
