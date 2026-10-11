"""Render the rebuilt CV to DOCX and PDF, and check that the PDF reads back."""

from backedcv.rendering.docx_writer import render_docx
from backedcv.rendering.pdf_writer import render_pdf
from backedcv.rendering.roundtrip import roundtrip_check

__all__ = ["render_docx", "render_pdf", "roundtrip_check"]
