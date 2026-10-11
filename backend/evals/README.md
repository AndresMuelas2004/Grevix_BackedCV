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

## Smoke pairs

Four synthetic CV and posting pairs run through the real analysis, up to the report. Each pair lists what its report must show: a screening question, a flag, a banner, a parse warning, a verdict, a hidden risk, a recency result, a screening flag or a refusal. The checks test those properties, not exact scores. `smoke/pairs.json` holds the pairs:

- `cv` and `job` are paths from `backend/`, or the text itself when it has line breaks. A PDF or DOCX is read like an upload; any other file as pasted text.
- `expect` keys: `requirements` (a requirement with these properties exists: `contains`, `importance`, `knockout_type`, `status`, `screening_question`), `flags` (`rule`, and optionally `contains`, a phrase the flagged requirement must have), `banners` and `parse_warnings` (rule IDs and codes), `verdict_not` (verdict labels it must not have), `hidden_risks` (`kind` and `risk`, e.g. `work_authorization` at `high`), `recency` (`contains` and `effect`: `none`, `warning` or `downgraded`), `screening_flags` (`contains`: the requirement with that phrase must be flagged), `refusals` (`gate` and `contains`: a refusal with that gate on a requirement with that phrase).
- `hidden-risk` (pair 4) tests buried rules: a work-permit sentence in the posting's last paragraph, and a 5-year Kubernetes window that the CV's only Kubernetes evidence (2015-2017) falls outside of. The report must refuse that requirement as not viable.

| Command | What runs | Cost |
|---|---|---|
| `uv run python -m evals.run_smoke --live` | The four pairs, with the model. Needs `OPENAI_API_KEY` in `.env`. | Model calls |
| `uv run python -m evals.run_smoke --live --langsmith` | The same, plus one experiment on the LangSmith dataset `backedcv-smoke`. Needs `LANGSMITH_API_KEY` in `.env`. | Model calls |

Notes:

- `--live` is required: there is no offline mode.
- Each run writes `evals/results/smoke-<YYYYMMDD-HHMM>.md` (checks, analysis per pair, cost) and exits with 1 when a check fails.
- `--langsmith` reuses the dataset if it exists; delete it in LangSmith to upload changed pairs. The experiment replays the live checks, so the model is paid once.
- The checker's tests make no model call: `uv run pytest -q tests/unit/test_smoke_runner.py`.

## Tests

```
uv run pytest -q tests/unit/test_fabrication_runner.py
```

These check the offline counts on the real set, that the offline run makes no network calls, that each split is balanced, the live path with a fake model (all batches share one event loop, failed calls stay `not checked`), and the LangSmith scoring with a fake client.
