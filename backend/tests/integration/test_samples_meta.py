from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backedcv import __version__
from backedcv.api.routes.analyses import JOB_MAX_CHARS, JOB_MIN_CHARS
from backedcv.ingestion.reader import MAX_BYTES, MAX_CV_CHARS, MAX_PAGES
from backedcv.main import create_app
from backedcv.settings import get_settings
from tests.fakes import FakeLLM

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    with TestClient(create_app(llm=FakeLLM(), checkpointer=InMemorySaver())) as c:
        yield c


def _set_env(monkeypatch, **values: str | None) -> None:
    """Set each variable, or unset it when the value is None, then reload the settings."""
    for name, value in values.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    get_settings.cache_clear()


def test_samples_returns_the_bundled_texts(client, monkeypatch):
    _set_env(monkeypatch, BACKEDCV_SAMPLES_DIR=None)

    response = client.get("/api/samples")

    assert response.status_code == 200
    assert response.json() == {
        "cv_text": (SAMPLES_DIR / "sample_cv.txt").read_text(encoding="utf-8"),
        "job_text": (SAMPLES_DIR / "sample_job.txt").read_text(encoding="utf-8"),
    }


def test_samples_follow_the_samples_dir_setting(client, monkeypatch, tmp_path):
    (tmp_path / "sample_cv.txt").write_text("CV · Data Engineer\n", encoding="utf-8")
    (tmp_path / "sample_job.txt").write_text("Job posting\n", encoding="utf-8")
    _set_env(monkeypatch, BACKEDCV_SAMPLES_DIR=str(tmp_path))

    response = client.get("/api/samples")

    assert response.status_code == 200
    assert response.json() == {"cv_text": "CV · Data Engineer\n", "job_text": "Job posting\n"}


@pytest.mark.parametrize("missing", ["sample_cv.txt", "sample_job.txt"])
def test_missing_sample_file_is_404(client, monkeypatch, tmp_path, missing):
    (tmp_path / "sample_cv.txt").write_text("CV\n", encoding="utf-8")
    (tmp_path / "sample_job.txt").write_text("Job posting\n", encoding="utf-8")
    (tmp_path / missing).unlink()
    _set_env(monkeypatch, BACKEDCV_SAMPLES_DIR=str(tmp_path))

    response = client.get("/api/samples")

    assert response.status_code == 404
    assert response.json()["code"] == "samples_missing"


def test_meta_reports_version_models_and_limits(client):
    response = client.get("/api/meta")
    settings = get_settings()

    assert response.status_code == 200
    assert response.json() == {
        "version": __version__,
        "llm_configured": settings.openai_api_key is not None,
        "models": {"fast": settings.model_fast, "strong": settings.model_strong},
        "limits": {
            "cv_max_bytes": MAX_BYTES,
            "cv_max_pages": MAX_PAGES,
            "cv_max_chars": MAX_CV_CHARS,
            "job_min_chars": JOB_MIN_CHARS,
            "job_max_chars": JOB_MAX_CHARS,
        },
    }


@pytest.mark.parametrize(("api_key", "configured"), [(None, False), ("test-key", True)])
def test_meta_reports_whether_an_llm_key_is_set(client, monkeypatch, api_key, configured):
    _set_env(monkeypatch, OPENAI_API_KEY=api_key)

    assert client.get("/api/meta").json()["llm_configured"] is configured
