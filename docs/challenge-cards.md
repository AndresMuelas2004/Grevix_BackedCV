# Challenge cards

How BackedCV adapted to each Challenge Card of Grevix AfterCode. The reasoning behind every decision is in the [decision log](decision-log.md).

## Card 1: hidden screening barriers, recency decay and composite disqualifiers

Received 2026-10-11, about 10:40 (Madrid). Built on the `card-1` branch and merged into `main`.

### What the card asks

- **Recency and composite validation:** a multi-pass corroboration gate in the LangGraph workflow that checks not only that an edit is backed by a real CV line, but that the line meets the posting's recency and hidden hiring thresholds.
- **Hidden screening risk flagging:** actionable warnings when a requirement looks met but is likely to be silently rejected, balancing strictness against over-conservatism.
- **Keep working:** requirement extraction and line-backed edit suggestions must continue to operate smoothly.
- **The goal:** analyze a posting with buried or ambiguous disqualifiers (an unstated work permit barrier, a multi-year recency rule), flag the hidden risk, and refuse an unviable edit even when the keyword appears in older CV history.

### What stays, changes and is new

| | What | Why |
|---|---|---|
| Stays | Reading CVs, requirement extraction, Fit and keyword coverage, knockout questions, guards and verifier, review, rebuilt DOCX and PDF | The card requires them to keep working; all earlier tests and end-to-end pairs still pass |
| Changes | A requirement backed only by evidence outside the posting's stated window no longer counts as met | Old experience is not what the employer asked for |
| Changes | The verdict counts unanswered high hidden risks like knockout questions | A buried work permit rule is a knockout the posting did not list |
| Changes | Suggestions skip requirements that are not viable | The model is never asked to make old experience look current |
| New | Recency per CV line (recent, aging, stale) computed from the CV's own dates | Code knows when each skill was last used |
| New | A model call that reads the whole posting for buried barriers, with every quote checked in code, plus code patterns for visa sponsorship | Buried barriers often sit outside the requirement list |
| New | Risk levels set in code against the CV and the candidate's answers; two medium risks make a high composite | Repeatable and testable, no invented probabilities |
| New | Three-pass corroboration gate (backed, recent enough, not blocked), each pass a graph node; new status "refused: not viable" | The card's gate, visible in the architecture |
| New | "Hidden screening risks" panel, "Looks met, but..." badge, "Refused as not viable" group in the review | Actionable warnings, never hidden refusals |
| New | Demo sample "posting with hidden barriers" and a fourth end-to-end pair | Shows and measures the card's goal |
| Removed | Nothing | |

### How it works

1. **Recency.** Every CV line inherits the dates of the job it belongs to. For each requirement, code finds the most recent dated evidence and its band: recent (up to 3 years since last use), aging (3 to 6) or stale (over 6).
2. **Explicit windows.** Code patterns find stated windows ("within the last 5 years", "5+ years in the last 7 years"); the barrier call can find more. A window always comes with the posting's exact sentence. Only a stated window removes credit; without one, stale evidence is a warning.
3. **Hidden barriers.** One model call reads the whole posting and returns buried or ambiguous disqualifiers: work permit, location and on-site days, recency rules, graduation windows, language level, clearance, availability. A quote that is not in the posting is dropped.
4. **Risk levels in code.** Each barrier is checked against the CV and the answers: for example the right to work in the United States against a CV located in Spain is high. A yes answer resolves a risk, a no confirms it. Two unresolved medium risks combine into one high composite risk.
5. **Corroboration gate.** Pass 1, *backed*: the existing guards and the independent verifier. Pass 2, *recent enough*: the cited lines fall inside the posting's window. Pass 3, *not blocked*: the target requirement carries no high eligibility or composite risk. A failure in pass 2 or 3 sets the status "refused: not viable" with the reason; such an edit cannot be accepted.

```
verify_batch (pass 1: backed) -> gate_recency (pass 2) -> gate_barriers (pass 3) -> await_review
```

### Demo

Press **Try a posting with hidden barriers** on the first screen. The posting is for a platform engineer in Austin and hides "we are unable to sponsor work visas, so you must already have the right to work in the United States" in its closing notes; it asks for Kubernetes "within the last 5 years". The CV belongs to an engineer in Valencia whose only Kubernetes evidence is "Deployed and operated microservices on K8s clusters" in a 2015-2017 job.

BackedCV flags the work permit as a high hidden risk and asks the yes/no question, marks Kubernetes "Looks met, but..." (the keyword is there, the experience is nine years old), and in the review lists the Kubernetes edit under "Refused as not viable" instead of rewording the old line.
