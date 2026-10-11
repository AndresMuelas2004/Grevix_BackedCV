# Decision log

What I decided, what I rejected and why. Times are Madrid time (CEST). The Challenge Card sections are added when each card arrives.

## 2026-10-11, Ignition phase

### Product

- **I build a CV vs job posting checker inspired by Jobscan**, framed as "is this job worth applying to?" rather than "beat the ATS robot". Most ATS do not auto-reject on keywords; what does reject automatically is knockout questions (work authorization, licenses, minimum years, location).
- **Name: BackedCV.** The `.com` was unregistered and I found no product, package or trademark with that name. I rejected Proofline (domain, PyPI name and a near-identical repository already taken), FitReceipt and WorthApplying.
- **The posting is pasted as text.** I rejected fetching job URLs: job boards' terms and fragile scraping.
- **No accounts and no signup** for the first analysis.

### Scoring and verdict

- **Two scores instead of one opaque match rate:** *Fit* (do I meet the requirements, by meaning) and *Keyword coverage* (would an exact-term search find me). Optimizing the CV can raise coverage, never Fit.
- **The score is computed in code from published weights**, never by the model, so every point can be explained and tested.
- **Knockouts are verdict blockers, not points.** Screening questions are yes/no; mixing them into a percentage hides them.
- **A knockout is only "missing" when the user says so or the CV says so explicitly.** I never guess eligibility from location or names.

### No invented experience

- **The model cites CV line IDs; code fills in the quotes.** This removes invented quotes.
- **General evidence never becomes a specific tool** (a direction rule), and inferred matches count as partial at most.
- **Every suggested edit goes through deterministic guards and an independent verifier.** Unsupported edits cannot be accepted; edited suggestions are verified again.
- **No generated bullets for missing skills.** That is exactly where these tools invent experience.

### Architecture

- **One LangGraph graph per analysis** with two human-in-the-loop pauses (before optimizing, and the review of suggestions) and parallel fan-out for matching and verification.
- **Files are read in the API, before the graph**, so no file bytes end up in checkpoints.
- **Code applies the accepted changes; a small tool-calling agent only orders the final CV**, with a deterministic fallback. I rejected an agent that writes free text.
- **No RAG, vector database or embeddings for now:** one CV and one posting fit in the model's context. Embeddings come in only if meaning-based matching through the model proves unreliable.
- **Two OpenAI models:** a cheap one for bulk extraction, a stronger one for rewriting and verification. Strict structured outputs everywhere.
- **Production traces hide inputs and outputs**, so real CVs never reach a third-party trace store. Only synthetic data lives in this repository.

### Stack

- **Backend:** Python 3.12, FastAPI with server-sent events, LangGraph and LangChain, OpenAI, LangSmith.
- **Frontend:** React with TypeScript, built to static files served by FastAPI. I rejected HTMX (clumsy for highlights, diffs and live scores) and Streamlit (looks like a demo).
- **Reading CVs:** pdfplumber and python-docx. I rejected PyMuPDF because of its AGPL license.
- **Writing CVs:** python-docx for DOCX and Typst for PDF. I rejected WeasyPrint (system packages in Docker).
- **Tooling:** uv, ruff, pytest, SQLite checkpoints. **License:** MIT.
- **Measurement:** a small fabrication set (suggestions with invented facts, to count how many get blocked) and three end-to-end CV and posting pairs, in LangSmith. I rejected a formal eval suite.

### Delivery

- **No cloud deployment during the event.** The rules accept a working demo instead of a live link, so I deliver a demo recording and this repository, runnable with Docker Compose. AWS Lightsail stays as plan B. I rejected ECS Express Mode as too expensive for a provisional demo.

## 2026-10-11, building the first version (night)

- **Frontend build: Vite with plain CSS.** The interface is a handful of components, so I rejected Tailwind and component libraries: fewer dependencies and nothing to learn for a reviewer.
- **The technology-age rule (R2) uses a short list** of 20 technologies whose release years I checked on official sources. I rejected a long list I could not verify one by one.
- **For ordinary requirements, "unknown" becomes "missing".** In the first real run the model answered "unknown" for skills the CV never mentions. The CV is the only evidence a recruiter sees, so silence means missing. Knockouts are the exception: they stay "unknown" until the user answers the question.
- **The cheapest model for every call while building**, to keep the whole event inside a small API budget. One full analysis costs a fraction of a cent.
- **Contracts first:** I defined the suggestion and document models before writing the guards, the document assembly and the renderers, so those pieces share one contract.
- **Every knockout question can be answered yes or no.** Some knockout types (degree, clearance, availability) had no way to be resolved, so the verdict could stay "answer the questions first" forever. A per-requirement answer fixes that; CV evidence still wins over an answer.
- **R2 can flag a requirement that R1 already flags.** "5+ years of LangGraph" in a junior role is both too senior for the level and older than the technology; showing both reasons is more useful than hiding one.
- **The posting review runs beside the matching, not before it.** The R4 review needs the extracted requirements but not the matching, so it runs in parallel and adds no waiting time.

## 2026-10-11, testing the full flow with real runs (night)

- **I read PDFs as logical lines, not physical ones.** A real run on a two-column CV showed wrapped bullets turning into fragments, and a rewrite of the first fragment left the rest behind as a duplicate bullet. Bullets and paragraphs are now rebuilt before anything else sees them; short list items stay separate.
- **I measured the no-invention promise and fixed what the measurement found.** On 40 synthetic cases the verifier sometimes let through a rewrite that attached the total years of experience to one role. A language model is not reliable at that arithmetic, so I added a deterministic guard: a computed total can only be used as a total. Latest run: 20 of 20 fabricated rewrites blocked, 19 of 20 faithful ones accepted. The verifier is not deterministic, so I keep every run's report.
- **Identical model calls are replayed from a local cache.** Re-running the sample gives the same numbers at no cost, which matters for a demo and for anyone trying the repository.
- **Limits before launch:** per-IP and daily caps on model-using requests, and production traces hide inputs and outputs.
- **Every verdict explains itself:** the Fit against the band's threshold and the top missing required items, in whole numbers that match the screen.
- **Compound requirements are split** ("PostgreSQL and Snowflake" becomes two), so one matching word cannot inflate keyword coverage.
- **A broader category counts as partial evidence, never as missing.** "Agent frameworks" in a CV is real evidence for LangChain, but not proof of it, so it scores partial. End-to-end checks on three CV and posting pairs (one of them a nursing job) now cover this.
- **Runs live on the server, not in the browser tab.** A code review showed that closing or reloading the tab mid-analysis left it stuck. Each step now runs as a server task; a reload picks it up again and a failed step can be retried.
- **The model never sees contact details.** Email addresses, phone numbers and links are replaced with placeholders before every model call; the app keeps the original text for the report and the new CV. Matching does not need them, and a CV is personal data.
- **When the ordering agent is unavailable, the new CV uses a standard section order.** Keeping the original order would put a two-column CV's sidebar (education, skills) before the summary.
