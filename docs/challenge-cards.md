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

BackedCV flags the work permit and the Austin office days as high hidden risks (the CV is located in Spain) and points to the matching deal-breaker questions, marks Kubernetes "Looks met, but..." (the keyword is there, but the experience ended in 2017), and in the review lists the Kubernetes edit under "Refused as not viable" instead of rewording the old line. Because the posting states the 5-year window, the Kubernetes requirement no longer counts as met, so the verdict is "Likely screened out" until the candidate's situation changes. (Card 2 later narrowed this: the old Kubernetes evidence now caps the verdict at "Long shot", and only a "No" to the work permit question screens the candidate out.)

Screenshots: [hidden risks](screenshots/08-hidden-risks.png), [Looks met, but...](screenshots/09-looks-met.png), [Refused as not viable](screenshots/10-refused.png).

### Measured

- **Everything that existed still works:** 625 backend tests pass (505 before the card), the full click-through of the original flow (sample, answers, optimize, review, build, downloads) passes every step, the Docker image builds and serves, and an axe-core audit of the new screens finds 0 accessibility violations.
- **End-to-end pairs, live with the model:** 4 of 4 pairs and 20 of 20 checks, for $0.0119. The fourth pair checks the card's goal: a high work permit risk, Kubernetes downgraded by recency, flagged "Looks met, but..." and its edit refused as not viable.
- **The first live run caught a miss:** the posting's extraction also turned the buried work permit sentence into a knockout requirement, and my first rule capped such risks at medium. Now a risk tied to a knockout keeps its real level and only leaves the question and the verdict to the knockout. Both run reports are kept in `backend/evals/results/`.

## Card 2: real-world feedback

Received 2026-10-11, about 13:35 (Madrid). Built on the `card-2` branch and merged into `main`.

### What the card asks

Share the project on LinkedIn or Reddit mentioning GREVIX (or in community groups), collect screenshots of genuine feedback, implement at least one improvement based on it, and upload the proof, the screenshots and a short note to the repository. Fake reviews are not accepted.

### How BackedCV adapts

| | What | Why |
|---|---|---|
| New | Posts on LinkedIn (mentioning GREVIX), X (mentioning @Grevixofficial), r/LangChain, r/hackathon and the participants' WhatsApp group, all ending with the same three questions | Answers that point at something specific to change |
| New | A public feedback form in the repository (GitHub issue form) | A timestamped, checkable record; it asks people not to paste personal data |
| New | A temporary live demo, [backedcv.onrender.com](https://backedcv.onrender.com) (Render free plan, cheap model, hourly and daily limits, privacy note on the first screen) | People can try it instead of only watching a video |
| New | [feedback/](../feedback/README.md): where it was shared, what people said (screenshots, names blurred unless agreed), what changed and what did not | The card's proof, kept honest |
| Changes | Only what a specific comment points at, each change linked to its comment | Feedback drives the change, not the other way round |
| Stays | Everything from the build and Card 1 | Nothing in the card asks to remove anything |

### What the feedback changed

Three participants answered (their words and screenshots: [feedback/README.md](../feedback/README.md)). Two found the report overwhelming and too long; one asked for side-by-side quotes, hard deal-breakers apart from soft preferences, and a preview of the parsed dates.

| | What | Comment it answers |
|---|---|---|
| Rebuilt | The report, from simple to complex: the verdict in one sentence and one number; the open yes/no questions right under it, with "Improve my CV" locked until they are answered; a numbered "What to fix, most important first" list in three tiers (could rule you out, serious gap, worth improving), each item with the posting's sentence next to the CV line and one thing to do; "Already strong"; everything else folded into details | "way too overwhelming", "a bit too lengthy", side-by-side quotes |
| Changes | Only legal bans (work permit, clearance, license) give "Likely screened out" on their own; a missing language or degree caps the verdict at "Long shot"; location and availability are asked | Deal-breakers apart from preferences |
| New | "How we read your dates": each entry's dates as read and the time counted; a missing month says "month unknown" and is never guessed | A preview of the parsed timelines |
| Changes | Every explanation is one short sentence, without internal IDs | "a bit too lengthy" |
| New | The first screen plays an example of the report before anyone uploads anything | "improve the landing page ui" |
| Fixed | From extra testing (not counted as feedback): whitespace no longer changes the report, the built-in samples always give the same result, missing minimum years is a serious gap, one question per fact, no "aging" for degrees, dates glued to a city, keyword-stuffing suggestions filtered out | Determinism and correctness |
