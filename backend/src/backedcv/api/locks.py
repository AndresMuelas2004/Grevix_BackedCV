"""One run at a time per analysis (in memory: valid with a single instance)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from backedcv.api.errors import ApiError


class RunLocks:
    def __init__(self) -> None:
        self._running: set[str] = set()

    def is_running(self, analysis_id: str) -> bool:
        return analysis_id in self._running

    def acquire(self, analysis_id: str) -> None:
        """Called before the response starts, so a double click gets a clean 409."""
        if analysis_id in self._running:
            raise ApiError(409, "run_in_progress", "This analysis is already running.")
        self._running.add(analysis_id)

    def release(self, analysis_id: str) -> None:
        self._running.discard(analysis_id)

    @asynccontextmanager
    async def held(self, analysis_id: str) -> AsyncIterator[None]:
        """Releases a lock taken with `acquire` when the stream ends, however it ends."""
        try:
            yield
        finally:
            self.release(analysis_id)
