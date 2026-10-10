"""Read uploaded CVs into numbered lines. Runs in the API handler, before the graph."""

from backedcv.ingestion.errors import IngestionError
from backedcv.ingestion.reader import read_cv, read_cv_text

__all__ = ["IngestionError", "read_cv", "read_cv_text"]
