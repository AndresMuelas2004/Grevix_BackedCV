"""Facts the frontend shows about this server: version, models and input limits."""

from fastapi import APIRouter

from backedcv import __version__
from backedcv.api.routes.analyses import JOB_MAX_CHARS, JOB_MIN_CHARS
from backedcv.ingestion.reader import MAX_BYTES, MAX_CV_CHARS, MAX_PAGES
from backedcv.settings import get_settings

router = APIRouter(tags=["meta"])


@router.get("/meta")
def get_meta() -> dict:
    settings = get_settings()
    return {
        "version": __version__,
        "llm_configured": settings.anthropic_api_key is not None,
        "models": {"fast": settings.model_fast, "strong": settings.model_strong},
        "limits": {
            "cv_max_bytes": MAX_BYTES,
            "cv_max_pages": MAX_PAGES,
            "cv_max_chars": MAX_CV_CHARS,
            "job_min_chars": JOB_MIN_CHARS,
            "job_max_chars": JOB_MAX_CHARS,
        },
    }
