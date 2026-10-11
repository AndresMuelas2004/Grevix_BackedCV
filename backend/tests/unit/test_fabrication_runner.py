import asyncio
import socket
from collections import Counter
from types import SimpleNamespace

import pytest

from backedcv.graph.optimize_nodes import make_optimize_nodes
from backedcv.llm.drafts_optimize import VerificationBatchDraft
from evals import run_fabrication
from evals.run_fabrication import (
    SPLITS,
    load_cases,
    load_cv,
    load_job,
    main,
    outcome_of,
    run_checks,
)
from tests.fakes_optimize import FakeOptimizeLLM


def _refuse(*_args, **_kwargs):
    raise AssertionError("the run tried to open a network connection")


@pytest.fixture
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)


class _BrokenVerifier(FakeOptimizeLLM):
    """Answers suggest, but every verify call fails."""

    async def run(self, prompt, data, schema, *, node):
        if schema is VerificationBatchDraft:
            raise RuntimeError("no answer")
        return await super().run(prompt, data, schema, node=node)


class _LoopBoundLLM(FakeOptimizeLLM):
    """Works only in the event loop of its first call, as the real async client does."""

    def __init__(self):
        super().__init__()
        self.loop = None

    async def run(self, prompt, data, schema, *, node):
        loop = asyncio.get_running_loop()
        if self.loop is None:
            self.loop = loop
        elif loop is not self.loop:
            raise RuntimeError("Event loop is closed")
        return await super().run(prompt, data, schema, node=node)


class _FakeLangSmithClient:
    """Stands in for langsmith.Client: keeps the uploaded examples and runs the evaluators."""

    def __init__(self):
        self.examples = []
        self.scores = []

    def has_dataset(self, dataset_name):
        return False

    def create_dataset(self, dataset_name, description=None):
        return SimpleNamespace(id="dataset-id")

    def create_examples(self, dataset_id, examples):
        self.examples = examples

    def evaluate(self, target, /, data=None, evaluators=(), experiment_prefix=None, metadata=None):
        for example in self.examples:
            outputs = target(example["inputs"])
            for evaluator in evaluators:
                result = evaluator(outputs=outputs, reference_outputs=example["outputs"])
                self.scores.append(result["score"])


def _outcomes(run) -> Counter:
    return Counter(outcome_of(r.case, r.verdict) for r in run.results)


def test_offline_counts_add_up_to_the_whole_set(no_network):
    run = run_checks(load_cases(), load_cv(), load_job(), live=False)

    assert len(run.results) == 40
    for split in SPLITS:
        rows = [r for r in run.results if r.case.split == split]
        counts = Counter(outcome_of(r.case, r.verdict) for r in rows)
        assert len(rows) == 20
        assert sum(counts.values()) == 20
        # Without the verifier, a case either fails a guard or is not checked.
        assert set(counts) <= {"caught by guards", "wrongly blocked by guards", "not checked"}


def test_offline_run_writes_the_report_without_network(tmp_path, no_network, capsys):
    assert main(["--results-dir", str(tmp_path)]) == 0

    [report] = tmp_path.glob("fabrication-offline-*.md")
    text = report.read_text(encoding="utf-8")
    assert "## all (40 cases)" in text
    assert "### Fabricated (20)" in text
    assert str(report) in capsys.readouterr().out


def test_langsmith_needs_the_live_run(tmp_path):
    with pytest.raises(SystemExit):
        main(["--langsmith", "--results-dir", str(tmp_path)])
    assert list(tmp_path.iterdir()) == []


def test_each_split_is_balanced():
    cases = load_cases()
    for split in SPLITS:
        labels = Counter(case.expected for case in cases if case.split == split)
        assert labels == {"verified": 10, "unsupported": 10}


def test_live_path_runs_every_batch_in_one_event_loop(monkeypatch):
    # _LoopBoundLLM verifies whatever it gets, so the cases the guards let through come out as
    # passed (faithful) or missed (fabricated). Batches from both splits must share one loop.
    nodes = make_optimize_nodes(_LoopBoundLLM())
    monkeypatch.setattr(run_fabrication, "live_nodes", lambda: nodes)

    run = run_checks(load_cases(), load_cv(), load_job(), live=True)

    assert run.failures == []
    assert len(run.usage) > 2  # several batches
    assert _outcomes(run) == Counter({"caught by guards": 8, "missed": 12, "passed": 20})


def test_failed_verifier_calls_leave_their_cases_not_checked(monkeypatch):
    nodes = make_optimize_nodes(_BrokenVerifier())
    monkeypatch.setattr(run_fabrication, "live_nodes", lambda: nodes)

    run = run_checks(load_cases(), load_cv(), load_job(), live=True)

    assert run.failures
    assert _outcomes(run) == Counter({"caught by guards": 8, "not checked": 32})


def test_langsmith_scores_every_example_even_when_the_verifier_failed(monkeypatch):
    import langsmith  # imported here only: the offline path never loads it

    client = _FakeLangSmithClient()
    monkeypatch.setattr(langsmith, "Client", lambda: client)
    nodes = make_optimize_nodes(_BrokenVerifier())
    monkeypatch.setattr(run_fabrication, "live_nodes", lambda: nodes)
    run = run_checks(load_cases(), load_cv(), load_job(), live=True)

    run_fabrication._record_in_langsmith(run)

    assert len(client.scores) == 40
    assert sum(client.scores) == 8  # only the cases the guards blocked are scored right
