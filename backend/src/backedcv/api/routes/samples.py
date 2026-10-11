"""Serve the curated sample CV (text, PDF, DOCX) and job posting for the one-click demo."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from backedcv.api.errors import ApiError
from backedcv.settings import get_settings

router = APIRouter(tags=["samples"])

PDF_TYPE = "application/pdf"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/samples")
def get_samples() -> dict[str, str]:
    folder = _curated_dir()
    return {
        "cv_text": _read(folder / "cv.txt"),
        "job_text": _read(folder / "job.txt"),
        "cv_pdf_url": "/api/samples/cv.pdf",
        "cv_docx_url": "/api/samples/cv.docx",
        "cv_filename": "sample-cv.pdf",
    }


@router.get("/samples/cv.pdf")
def get_sample_pdf() -> FileResponse:
    return _file(_curated_dir() / "cv.pdf", PDF_TYPE)


@router.get("/samples/cv.docx")
def get_sample_docx() -> FileResponse:
    return _file(_curated_dir() / "cv.docx", DOCX_TYPE)


def _curated_dir() -> Path:
    return get_settings().samples_dir / "curated"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise _missing(path) from exc


def _file(path: Path, media_type: str) -> FileResponse:
    if not path.is_file():
        raise _missing(path)
    return FileResponse(path, media_type=media_type)


def _missing(path: Path) -> ApiError:
    return ApiError(404, "samples_missing", "The sample files are missing.", path.name)
