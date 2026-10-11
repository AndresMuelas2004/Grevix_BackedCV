"""DOCX CVs: walk the XML in document order, including content controls and text boxes.

Word's own resume templates wrap whole sections in content controls (`w:sdt`), which
python-docx's paragraph iterators skip, so the body is walked with lxml instead.
"""

import io
import zipfile

import docx

from backedcv.domain.models.cv import LineSource
from backedcv.ingestion.errors import IngestionError
from backedcv.ingestion.lines import RawLine

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_MAX_UNCOMPRESSED = 50 * 1024 * 1024


def _q(tag: str) -> str:
    prefix, name = tag.split(":")
    return f"{{{W if prefix == 'w' else MC}}}{name}"


def read_docx(data: bytes) -> list[RawLine]:
    _check_zip(data)
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise IngestionError("cv_unreadable", "This Word file could not be opened.") from exc
    body = document.element.find(_q("w:body"))
    if body is None:
        raise IngestionError("cv_unreadable", "This Word file is damaged or incomplete.")

    rows: list[RawLine] = []
    seen_margins: set[str] = set()
    for section in document.sections:
        for part, source in ((section.header, "header"), (section.first_page_header, "header")):
            _walk_margin(part, source, rows, seen_margins)

    _walk(body, "body", rows)

    for section in document.sections:
        for part in (section.footer, section.first_page_footer):
            _walk_margin(part, "footer", rows, seen_margins)

    if not any(r.text.strip() for r in rows):
        raise IngestionError("cv_empty", "This Word file has no readable text.")
    return rows


def _check_zip(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if "word/document.xml" not in names:
                raise IngestionError("cv_unsupported_type", "This file is not a Word document.")
            if sum(i.file_size for i in archive.infolist()) > _MAX_UNCOMPRESSED:
                raise IngestionError("cv_too_large", "This Word file is too large to read.")
    except zipfile.BadZipFile as exc:
        raise IngestionError("cv_unreadable", "This Word file is damaged.") from exc


def _walk_margin(part, source: LineSource, rows: list[RawLine], seen: set[str]) -> None:
    try:
        if part.is_linked_to_previous:
            return
        element = part._element
    except Exception:  # absent first-page headers raise on some documents
        return
    margin_rows: list[RawLine] = []
    _walk(element, source, margin_rows)
    for row in margin_rows:
        key = row.text.strip()
        if key and key not in seen:
            seen.add(key)
            rows.append(row)


def _walk(element, source: LineSource, rows: list[RawLine]) -> None:
    for child in element:
        tag = child.tag
        if tag == _q("w:p"):
            _paragraph(child, source, rows)
        elif tag == _q("w:tbl"):
            for cell_p in child.iter(_q("w:p")):
                _paragraph(cell_p, "table" if source == "body" else source, rows)
        elif tag == _q("w:sdt"):
            content = child.find(_q("w:sdtContent"))
            if content is not None:
                _walk(content, source, rows)
        elif tag == _q("mc:AlternateContent"):
            choice = child.find(_q("mc:Choice"))
            if choice is not None:
                _walk(choice, source, rows)


def _paragraph(p, source: LineSource, rows: list[RawLine]) -> None:
    texts: list[str] = []
    bold_runs: list[bool] = []
    sizes: list[float] = []
    for node in p.iter():
        if node.tag == _q("mc:Fallback"):
            # Text boxes appear twice (modern and legacy markup); keep the modern copy only.
            for sub in node.iter():
                sub.set("{urn:backedcv}skip", "1")
        if node.get("{urn:backedcv}skip"):
            continue
        if node.tag == _q("w:txbxContent"):
            _walk(node, "textbox", rows)
            for sub in node.iter():
                sub.set("{urn:backedcv}skip", "1")
            continue
        if node.tag == _q("w:t"):
            texts.append(node.text or "")
            run = node.getparent()
            bold_runs.append(_run_bold(run))
            size = _run_size(run)
            if size:
                sizes.append(size)
        elif node.tag in (_q("w:tab"),):
            texts.append(" ")
        elif node.tag in (_q("w:br"), _q("w:cr")):
            texts.append("\n")

    style = p.find(f"{_q('w:pPr')}/{_q('w:pStyle')}")
    is_heading = style is not None and str(style.get(_q("w:val"), "")).lower().startswith(
        ("heading", "title")
    )
    joined = "".join(texts)
    for piece in joined.split("\n"):
        if piece.strip():
            rows.append(
                RawLine(
                    text=piece,
                    source=source,
                    bold=is_heading or (bool(bold_runs) and all(bold_runs)),
                    size=max(sizes) if sizes else None,
                )
            )


def _run_bold(run) -> bool:
    if run is None:
        return False
    b = run.find(f"{_q('w:rPr')}/{_q('w:b')}")
    return b is not None and b.get(_q("w:val"), "true") not in ("0", "false")


def _run_size(run) -> float | None:
    if run is None:
        return None
    sz = run.find(f"{_q('w:rPr')}/{_q('w:sz')}")
    try:
        return int(sz.get(_q("w:val"))) / 2 if sz is not None else None
    except (TypeError, ValueError):
        return None
