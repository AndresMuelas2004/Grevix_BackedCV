"""Graph runs as background tasks. A run starts with its request and goes on until it ends, even if
the browser that started it has gone. A stream only adds a listener to the run: when the listener
leaves, the run keeps going.

A run holds the analysis lock from start to end and gives it back before its final event is sent,
so a client that reacts to that event finds the analysis free. Every event is kept in a buffer, so
a listener that starts late still gets all of them; each listener also has its own queue for the
events that come after."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi.sse import ServerSentEvent

from backedcv.api.errors import stream_error
from backedcv.api.locks import RunLocks

log = logging.getLogger(__name__)

# The work of one run. It returns the payload of the run's final event.
Work = Callable[["Run"], Awaitable[dict]]
FAILURES_KEPT = 1000  # failed runs whose error the projection can still show
_END = object()  # tells a listener that the run has ended


class Run:
    """One run: its events so far, and the listeners that wait for the rest."""

    def __init__(self, analysis_id: str) -> None:
        self.analysis_id = analysis_id
        self.task: asyncio.Task | None = None
        self._events: list[ServerSentEvent] = []
        self._listeners: set[asyncio.Queue] = set()
        self._ended = False

    def emit(self, event: ServerSentEvent) -> None:
        self._events.append(event)
        for queue in self._listeners:
            queue.put_nowait(event)

    def close(self, final: ServerSentEvent | None) -> None:
        if final is not None:
            self.emit(final)
        self._ended = True
        for queue in self._listeners:
            queue.put_nowait(_END)
        self._listeners.clear()

    async def listen(self) -> AsyncIterator[ServerSentEvent]:
        """Yields every event so far, then the new ones, until the run ends. Leaving early only
        stops this listener."""
        # The buffer and the queue are taken in one step, so no event is missed or repeated.
        replay = list(self._events)
        queue: asyncio.Queue | None = None
        if not self._ended:
            queue = asyncio.Queue()
            self._listeners.add(queue)
        try:
            for event in replay:
                yield event
            if queue is None:
                return
            while True:
                event = await queue.get()
                if event is _END:
                    return
                yield event
        finally:
            if queue is not None:
                self._listeners.discard(queue)


class RunManager:
    """Starts the runs and keeps track of the ones going. It also keeps the error of a run that
    failed, so the projection can show it until the analysis runs again."""

    def __init__(self, locks: RunLocks) -> None:
        self.locks = locks
        self._active: dict[str, Run] = {}
        self._failures: dict[str, dict] = {}

    def is_running(self, analysis_id: str) -> bool:
        return self.locks.is_running(analysis_id)

    def failure(self, analysis_id: str) -> dict | None:
        return self._failures.get(analysis_id)

    def launch(self, analysis_id: str, work: Work, *, done: str, failed: tuple[str, str]) -> Run:
        """Starts `work` as its own task and returns at once. The caller must already hold the run
        lock (`locks.acquire`): the task gives it back when the run ends, however it ends. `done`
        names the final event of a successful run; `failed` is the (code, title) of the error."""
        run = Run(analysis_id)
        self._failures.pop(analysis_id, None)
        self._active[analysis_id] = run
        run.task = asyncio.create_task(self._execute(run, work, done, failed))
        return run

    async def shutdown(self) -> None:
        """Cancels the runs still going, and waits until they have given their locks back."""
        runs = list(self._active.values())
        for run in runs:
            if run.task is not None:
                run.task.cancel()
        await asyncio.gather(*(run.task for run in runs if run.task), return_exceptions=True)
        for run in runs:  # a task cancelled before it first ran never reaches its own cleanup
            if self._active.get(run.analysis_id) is run:
                self._end(run, None)

    async def _execute(self, run: Run, work: Work, done: str, failed: tuple[str, str]) -> None:
        # Stays None when the run is cancelled: its listeners then just see the stream end.
        final: ServerSentEvent | None = None
        try:
            payload = await work(run)
            final = ServerSentEvent(event=done, data=payload)
        except Exception as exc:
            log.exception("run of analysis %s failed", run.analysis_id)
            final = stream_error(*failed, exc)
            self._remember_failure(run.analysis_id, final.data)
        finally:
            self._end(run, final)

    def _remember_failure(self, analysis_id: str, body: dict) -> None:
        self._failures[analysis_id] = body
        while len(self._failures) > FAILURES_KEPT:
            del self._failures[next(iter(self._failures))]

    def _end(self, run: Run, final: ServerSentEvent | None) -> None:
        self.locks.release(run.analysis_id)  # first: a client that reacts to `final` finds it free
        self._active.pop(run.analysis_id, None)
        run.close(final)


async def stream_graph(graph: Any, graph_input: Any, config: dict, run: Run) -> None:
    """Runs one graph step and passes its progress on to the run's listeners."""
    async for mode, chunk in graph.astream(graph_input, config, stream_mode=["custom", "updates"]):
        if mode == "custom":
            run.emit(ServerSentEvent(event="progress", data=chunk))


def emit_progress(run: Run, step: str, status: str, **extra: Any) -> None:
    """A progress event shaped like the ones the nodes write (see graph/nodes.py `_progress`), for
    steps that run outside the graph, where the nodes cannot write them."""
    data = {"type": "progress", "step": step, "status": status, **extra}
    run.emit(ServerSentEvent(event="progress", data=data))
