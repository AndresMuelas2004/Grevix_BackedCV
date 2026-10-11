from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backedcv.main import create_app
from backedcv.settings import get_settings
from tests.fakes import FakeLLM

HIDDEN_RISK_DIR = Path(__file__).resolve().parents[2] / "samples" / "hidden_risk"


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    with TestClient(create_app(llm=FakeLLM(), checkpointer=InMemorySaver())) as c:
        yield c


def _write_hidden_risk_texts(folder: Path) -> None:
    """Make a samples folder with the two hidden-risk texts."""
    hidden = folder / "hidden_risk"
    hidden.mkdir()
    (hidden / "cv.txt").write_text("CV - Platform Engineer\n", encoding="utf-8")
    (hidden / "job.txt").write_text("Job posting\n", encoding="utf-8")


def test_hidden_risk_sample_returns_the_cv_and_the_posting(client, monkeypatch):
    monkeypatch.delenv("BACKEDCV_SAMPLES_DIR", raising=False)
    get_settings.cache_clear()

    response = client.get("/api/samples/hidden-risk")

    assert response.status_code == 200
    assert response.json() == {
        "cv_text": (HIDDEN_RISK_DIR / "cv.txt").read_text(encoding="utf-8"),
        "job_text": (HIDDEN_RISK_DIR / "job.txt").read_text(encoding="utf-8"),
    }


def test_hidden_risk_sample_follows_the_samples_dir_setting(client, monkeypatch, tmp_path):
    _write_hidden_risk_texts(tmp_path)
    monkeypatch.setenv("BACKEDCV_SAMPLES_DIR", str(tmp_path))
    get_settings.cache_clear()

    response = client.get("/api/samples/hidden-risk")

    assert response.status_code == 200
    assert response.json() == {"cv_text": "CV - Platform Engineer\n", "job_text": "Job posting\n"}


@pytest.mark.parametrize("missing", ["cv.txt", "job.txt"])
def test_missing_hidden_risk_text_is_404(client, monkeypatch, tmp_path, missing):
    _write_hidden_risk_texts(tmp_path)
    (tmp_path / "hidden_risk" / missing).unlink()
    monkeypatch.setenv("BACKEDCV_SAMPLES_DIR", str(tmp_path))
    get_settings.cache_clear()

    response = client.get("/api/samples/hidden-risk")

    assert response.status_code == 404
    assert response.json()["code"] == "samples_missing"
