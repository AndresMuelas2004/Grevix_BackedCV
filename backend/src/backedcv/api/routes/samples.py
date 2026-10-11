"""Serve the sample CV and job posting that the frontend can load with one click."""

from pathlib import Path

from fastapi import APIRouter

from backedcv.api.errors import ApiError
from backedcv.settings import get_settings

router = APIRouter(tags=["samples"])


@router.get("/samples")
def get_samples() -> dict[str, str]:
    folder = get_settings().samples_dir
    return {
        "cv_text": _read(folder / "sample_cv.txt"),
        "job_text": _read(folder / "sample_job.txt"),
    }


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ApiError(404, "samples_missing", "The sample files are missing.", path.name) from exc
