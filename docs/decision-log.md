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
