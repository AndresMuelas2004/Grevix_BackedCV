"""Render the rebuilt CV to PDF with Typst, using the bundled ATS-safe template."""

import json
from pathlib import Path

import typst

from backedcv.domain.models import CVDocument

TEMPLATE = Path(__file__).parent / "templates" / "cv.typ"


def render_pdf(doc: CVDocument) -> bytes:
    """Pass the document to the template as JSON in sys.inputs."""
    payload = json.dumps(doc.model_dump(mode="json"), ensure_ascii=False)
    return typst.compile(
        TEMPLATE,
        format="pdf",
        ignore_system_fonts=True,  # embedded fonts only, so the PDF looks the same on every machine
        sys_inputs={"data": payload},
    )
