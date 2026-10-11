# Evals

Scripts that measure BackedCV's claims. Nothing in the app imports them. Run them from `backend/`.

## Fabrication set

Measures the no-invention promise. `fabrication/` holds 40 synthetic cases (see its README): half faithful CV rewrites, half invented ones, in two splits, `dev` and `heldout`. The runner counts:

- invented rewrites caught by the guards, caught by the verifier, or missed;
- faithful rewrites blocked by mistake.

### Modes

| Command | What runs | Cost |
|---|---|---|
| `uv run python -m evals.run_fabrication` | The guards only. No network, no API key. | Free |
| `uv run python -m evals.run_fabrication --live` | The guards, then the app's real verifier on what the guards let through (one call per CV section). Needs `OPENAI_API_KEY` in `.env`. | Model calls |
| `uv run python -m evals.run_fabrication --live --langsmith` | The same, plus a LangSmith dataset and one recorded experiment. Needs `LANGSMITH_API_KEY` in `.env`. | Model calls |

Options:

- `--split dev|heldout|all` (default `all`). `--langsmith` needs `--live` and `--split all`.
- `--results-dir PATH` (default `evals/results/`).

Notes:

- Offline, a case that passes the guards shows as `not checked`, because the verifier did not run.
- A failed verifier call is printed as a warning. Its cases are `not checked`, not blocked, so a broken key does not look like a result.
- `--langsmith` creates the dataset `backedcv-fabrication` if it is missing. If it exists, it is reused as it is; delete it in LangSmith to upload changed cases.
- The LangSmith target replays the verdicts of the live pass, so the verifier is paid once. A case with no verdict is uploaded with status `not_checked` and scores 0.

### Reading the report

Each run writes `evals/results/fabrication-<offline|live>-<YYYYMMDD-HHMM>.md`. There is one section per split, plus `all` when both run.

- **Fabricated** (should be blocked): *caught by guards* and *caught by verifier* say which check blocked it. *Missed* means it passed everything. Watch this one. *Not checked* means no verdict.
- **Faithful** (should pass): *wrongly blocked by guards* or *by verifier* are false alarms, each with its reason. Then *passed* and *not checked*.
- **By fabrication type**: the fabricated counts per kind of invention.
- **Verifier cost** (live only): calls, tokens, USD and failed calls.
- **All cases**: one row per case, with its reason.

For the headline number, use the `heldout` section and report guards and verifier counts separately.

### Latest results

The newest live run is `evals/results/fabrication-live-20261011-0257.md`. On the `heldout` split, the guards caught 3 of the 10 invented rewrites and the verifier 7, with none missed. The verifier blocked 1 of the 10 faithful rewrites by mistake (C29), and the guards none. The verifier took 10 calls and cost USD 0.0067, with no failed calls. Earlier runs stay in the same folder to show the variation between runs: C13 was blocked by mistake in two earlier live runs, and C09 was missed in two.

## Tests

```
uv run pytest -q tests/unit/test_fabrication_runner.py
```

These check the offline counts on the real set, that the offline run makes no network calls, that each split is balanced, the live path with a fake model (all batches share one event loop, failed calls stay `not checked`), and the LangSmith scoring with a fake client.
