from fastapi import APIRouter

from backedcv import __version__
from backedcv.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str | bool]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "llm_configured": settings.anthropic_api_key is not None,
    }
