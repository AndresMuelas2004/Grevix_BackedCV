import io

import docx
import pytest
import typst
from docx.oxml import parse_xml

from backedcv.ingestion import IngestionError, read_cv, read_cv_text

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _pdf(tmp_path, markup: str) -> bytes:
    source = tmp_path / "cv.typ"
    source.write_text(markup, encoding="utf-8")
    return typst.compile(str(source))


def test_pasted_text_gets_numbered_lines_without_bullets():
    result = read_cv_text("Jane Doe\n\n• Built APIs with FastAPI\n- Led a team of 4\n")

    assert [(line.id, line.text) for line in result.lines] == [
        ("L001", "Jane Doe"),
        ("L002", "Built APIs with FastAPI"),
        ("L003", "Led a team of 4"),
    ]


def test_pdf_lines_in_reading_order_with_bold_headings(tmp_path):
    data = _pdf(
        tmp_path,
        "#set page(width: 210mm, height: 297mm)\n"
        "*Jane Doe*\n\n"
        "jane\\@example.com\n\n"
        "*Experience*\n\n"
        "Data Engineer, Acme Corp, Jan 2020 - Present\n\n"
        "- Built ETL pipelines in Python and SQL\n",
    )

    result = read_cv(data, "cv.pdf")
    texts = [line.text for line in result.lines]

    assert result.kind == "pdf"
    assert texts[0] == "Jane Doe"
    assert "Data Engineer, Acme Corp, Jan 2020 - Present" in texts
    assert texts[-1] == "Built ETL pipelines in Python and SQL"
    assert next(line for line in result.lines if line.text == "Experience").bold


def _docx_bytes(document) -> bytes:
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_docx_reads_tables_headers_and_content_controls():
    document = docx.Document()
    document.sections[0].header.paragraphs[0].text = "Jane Doe | jane@example.com"
    document.add_heading("Experience", level=1)
    document.add_paragraph("Data Engineer, Acme Corp")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Python"
    table.cell(0, 1).text = "SQL"
    sdt = parse_xml(
        f"<w:sdt {W_NS}><w:sdtContent><w:p><w:r><w:t>Skills inside a content control"
        "</w:t></w:r></w:p></w:sdtContent></w:sdt>"
    )
    document.element.body.insert(len(document.element.body) - 1, sdt)

    result = read_cv(_docx_bytes(document), "cv.docx")
    by_text = {line.text: line for line in result.lines}

    assert by_text["Jane Doe | jane@example.com"].source == "header"
    assert by_text["Experience"].bold
    assert by_text["Python"].source == "table"
    assert "Skills inside a content control" in by_text


def test_rejects_unsupported_files():
    with pytest.raises(IngestionError) as error:
        read_cv(b"just some bytes", "cv.txt")
    assert error.value.code == "cv_unsupported_type"


def test_image_only_pdf_asks_for_pasted_text(tmp_path):
    data = _pdf(tmp_path, "#rect(width: 4cm, height: 2cm, fill: gray)")

    with pytest.raises(IngestionError) as error:
        read_cv(data, "scan.pdf")
    assert error.value.code == "cv_image_only"
