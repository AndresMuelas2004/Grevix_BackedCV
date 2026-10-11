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

CURATED_DIR = Path(__file__).resolve().parents[2] / "samples" / "curated"
PDF_TYPE = "application/pdf"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SAMPLE_LINKS = {
    "cv_pdf_url": "/api/samples/cv.pdf",
    "cv_docx_url": "/api/samples/cv.docx",
    "cv_filename": "sample-cv.pdf",
}


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


def _write_texts(folder: Path) -> None:
    """Make a samples folder with the two curated texts and no PDF or DOCX."""
    curated = folder / "curated"
    curated.mkdir()
    (curated / "cv.txt").write_text("CV · Data Engineer\n", encoding="utf-8")
    (curated / "job.txt").write_text("Job posting\n", encoding="utf-8")


def test_samples_returns_the_curated_sample(client, monkeypatch):
    _set_env(monkeypatch, BACKEDCV_SAMPLES_DIR=None)

    response = client.get("/api/samples")

    assert response.status_code == 200
    assert response.json() == {
        "cv_text": (CURATED_DIR / "cv.txt").read_text(encoding="utf-8"),
        "job_text": (CURATED_DIR / "job.txt").read_text(encoding="utf-8"),
        **SAMPLE_LINKS,
    }


def test_samples_follow_the_samples_dir_setting(client, monkeypatch, tmp_path):
    _write_texts(tmp_path)
    _set_env(monkeypatch, BACKEDCV_SAMPLES_DIR=str(tmp_path))

    response = client.get("/api/samples")

    assert response.status_code == 200
    assert response.json() == {
        "cv_text": "CV · Data Engineer\n",
        "job_text": "Job posting\n",
        **SAMPLE_LINKS,
    }


@pytest.mark.parametrize("missing", ["cv.txt", "job.txt"])
def test_missing_sample_text_is_404(client, monkeypatch, tmp_path, missing):
    _write_texts(tmp_path)
    (tmp_path / "curated" / missing).unlink()
    _set_env(monkeypatch, BACKEDCV_SAMPLES_DIR=str(tmp_path))

    response = client.get("/api/samples")

    assert response.status_code == 404
    assert response.json()["code"] == "samples_missing"


@pytest.mark.parametrize(
    ("route", "filename", "media_type"),
    [
        ("/api/samples/cv.pdf", "cv.pdf", PDF_TYPE),
        ("/api/samples/cv.docx", "cv.docx", DOCX_TYPE),
    ],
)
def test_sample_files_are_served_with_their_content_type(
    client, monkeypatch, route, filename, media_type
):
    _set_env(monkeypatch, BACKEDCV_SAMPLES_DIR=None)

    response = client.get(route)

    assert response.status_code == 200
    assert response.headers["content-type"] == media_type
    assert response.content == (CURATED_DIR / filename).read_bytes()


@pytest.mark.parametrize("route", ["/api/samples/cv.pdf", "/api/samples/cv.docx"])
def test_missing_sample_file_is_404_and_the_texts_still_load(client, monkeypatch, tmp_path, route):
    _write_texts(tmp_path)
    _set_env(monkeypatch, BACKEDCV_SAMPLES_DIR=str(tmp_path))

    response = client.get(route)

    assert response.status_code == 404
    assert response.json()["code"] == "samples_missing"
    # The frontend falls back to the sample text when the PDF is missing, so the text must load.
    assert client.get("/api/samples").status_code == 200


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
