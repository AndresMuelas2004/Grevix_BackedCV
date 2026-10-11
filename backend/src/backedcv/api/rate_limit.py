"""Abuse and budget limits for the routes that call the model: a rolling hour per client address,
and a daily total shared by everyone. A request is counted only when it is accepted to run."""

import math
from collections import deque
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

from fastapi import Request

from backedcv.api.errors import ApiError
from backedcv.api.retention import utc_now

HOUR = timedelta(hours=1)


class RunLimiter:
    """Counts the model runs in memory, so the counts start again with the process."""

    def __init__(
        self, per_hour: int, per_day: int, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self.per_hour, self.per_day = per_hour, per_day
        self._clock = clock
        self._by_client: dict[str, deque[datetime]] = {}
        self._day: date | None = None
        self._day_runs = 0

    def check(self, client: str) -> None:
        """Counts one model run for `client`, or raises the 429 that says when to try again."""
        now = self._clock()
        if now.date() != self._day:
            self._day, self._day_runs = now.date(), 0
        if self._day_runs >= self.per_day:
            midnight = datetime.combine(now.date() + timedelta(days=1), time.min, UTC)
            raise ApiError(
                429,
                "daily_limit_reached",
                "The daily limit of analyses has been reached.",
                f"The limit resets at midnight UTC, in {_wait(midnight - now)}.",
            )
        runs = self._by_client.setdefault(client, deque())
        while runs and now - runs[0] >= HOUR:
            runs.popleft()
        if len(runs) >= self.per_hour:
            wait = _wait(runs[0] + HOUR - now)
            raise ApiError(
                429,
                "rate_limited",
                "Too many requests from this network.",
                f"At most {self.per_hour} requests an hour are allowed. Try again in {wait}.",
            )
        runs.append(now)
        self._day_runs += 1


def _wait(delta: timedelta) -> str:
    """A short, readable wait: whole minutes, or whole hours when it is more than two hours."""
    minutes = max(1, math.ceil(delta.total_seconds() / 60))
    if minutes > 120:
        return f"{math.ceil(minutes / 60)} hours"
    return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"


def count_model_run(request: Request) -> None:
    """Counts one model run for the client, or raises the 429. Call it only after the request has
    passed its validation and its stage checks, so a refused request uses no quota. It has no
    await, so the check and the count cannot interleave with another request."""
    client = request.client.host if request.client else "unknown"
    request.app.state.limiter.check(client)
