# Decision log

What I decided, what I rejected and why. Times are Madrid time (CEST). The Challenge Card sections are added when each card arrives.

## 2026-10-11, Ignition phase

### Product

- **I build a CV vs job posting checker**, framed as "is this job worth applying to?" rather than "beat the ATS robot". Most ATS do not auto-reject on keywords; what does reject automatically is knockout questions (work authorization, licenses, minimum years, location).
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

## 2026-10-11, Challenge Card 1: hidden screening barriers, recency and the corroboration gate

The card asks BackedCV to catch what a keyword match hides: disqualifiers buried in the posting (a work permit nobody lists as a requirement, a multi-year recency rule), experience that is too old to count, and risks that only disqualify in combination. It must refuse an edit that is backed by a real CV line but not viable, while extraction and line-backed suggestions keep working. Details and the demo are in [challenge-cards.md](challenge-cards.md).

- **I kept everything that already worked.** Reading, Fit and keyword coverage, knockout questions, the guards and the verifier, the review and the rebuilt CV are unchanged; every existing test and the three end-to-end pairs still pass.
- **Recency is computed in code from the CV's own dates.** Each line inherits the dates of the job it belongs to, so I know when a skill was last used: recent (up to 3 years), aging (3 to 6), stale (over 6). A model never guesses a date.
- **Old evidence loses credit only when the posting states a window** ("within the last 5 years"), always quoted word for word from the posting. Without a stated window, old evidence is a warning and costs no points. This is my balance between strictness and over-conservatism: a 2017 job is real experience, unless the employer says it is too old.
- **Hidden barriers come from a separate model call that reads the whole posting**, because buried disqualifiers often sit outside the requirement list, in a closing note or a perks paragraph. A barrier whose quote is not found in the posting is dropped. The most common one (no visa sponsorship, right to work in a country) is also found by code patterns, so it never depends on the model alone.
- **Code, not the model, sets the risk level**, by checking each barrier against the CV and the candidate's answers: "you must already have the right to work in the United States" with a CV located in Spain is high risk; a yes answer resolves it and a no confirms it. I rejected asking the model for a rejection probability: three levels with a reason are honest, a percentage would be false precision.
- **Two medium risks combine into one high "composite" risk.** A language level and three office days a week abroad are each tolerable; together they make a silent rejection likely.
- **"Looks met, but..."** marks a requirement whose keyword is in the CV but whose evidence is too old or blocked. That is exactly where a keyword score misleads.
- **Every edit goes through a three-pass corroboration gate**, each pass a node of the graph: backed by a real CV line (the existing guards and verifier), recent enough for the posting's window, and not blocked by a hidden barrier. An edit that fails the second or third pass gets a new status, "refused: not viable", with the reason, and cannot be accepted.
- **Not-viable requirements are refused before any edit is generated**, so the model is never asked to make old experience look current. The refusal is still listed with its reason: a silent omission would look like a missed opportunity.
- **A CV edit can never fix an eligibility barrier**, so edits aimed at one are refused and the candidate answers the yes/no question instead. An unanswered high risk counts as one more question before the verdict; a no acts like a failed knockout. A barrier that the posting already lists as a knockout requirement is not asked twice.
- **Measured on a new demo sample and a fourth end-to-end pair:** a platform engineering posting with a buried no-sponsorship sentence and a 5-year Kubernetes window, and a CV in Valencia whose only Kubernetes evidence is a 2015-2017 job.
- **A risk tied to a knockout keeps its real level.** The first live run showed the extraction also turning the buried sponsorship sentence into a knockout requirement, and my rule capped such risks at medium, hiding a CV in Spain against "the right to work in the United States". Now only the question and the verdict defer to the knockout; the level comes from the CV. The next live run passed 19 of 19 checks.
- **A posting's own window can make the verdict "Likely screened out".** "3+ years of Kubernetes within the last 5 years" is a minimum-years knockout; when the only Kubernetes experience ended in 2017, the CV itself shows it is not met. That is the honest answer, and the report says exactly which sentence causes it.

## 2026-10-11, Challenge Card 2: real-world feedback

The card asks me to share BackedCV, collect genuine feedback with screenshots, ship at least one improvement based on it, and document everything in the repository. The feedback, the changes and the proof are in [feedback/README.md](../feedback/README.md).

- **I share the demo, the screenshots and the repository** on LinkedIn (mentioning GREVIX), X, Reddit and the participants' WhatsApp group. Every post ends with the same three questions (would you trust the verdict and score; which part helps and which is noise; what would stop you using it on a real application), so the answers point at something I can change.
- **Feedback stays authentic.** I only use what people actually wrote, always with a screenshot. Names and profile photos are blurred unless the person agreed to be named: a public repository is not the place for other people's data.
- **A public feedback form in the repository** (a GitHub issue form) gives a timestamped record anyone can check, and it asks people not to paste a real CV.
- **I change only what a specific comment points at**, and I link each change to its comment. Feedback I chose not to act on is listed with the reason.
- **A temporary public demo after all: [backedcv.onrender.com](https://backedcv.onrender.com).** Feedback on something people can try is worth more than feedback on a video, and the other teams shared live links. I changed my earlier "no deployment" decision with limits: Render's free plan from a Blueprint in the repository, the cheap model for every call, 20 model runs per person per hour and 150 per day, contact details never sent to the model, everything deleted after 24 hours, a privacy note on the first screen asking for the samples or fictional details, and Render's GitHub access limited to this repository.
- **Where I post follows each community's rules.** Before posting on Reddit I checked the rules of nineteen subreddits: the job-search ones forbid promoting tools, so I posted in r/LangChain (the app is built with LangGraph and LangChain) and r/hackathon, with a different text for each. Reddit's filters removed both because the account is new, so I asked the moderators to review them instead of posting again.
- **I gave feedback before asking for it.** I tried five other participants' projects, as a user and by reading their code, and left honest notes where each author asked for them (LinkedIn comments, GitHub issues, a feedback form). Security problems went only to private channels, never into public comments.

### What the feedback made me see, and what I decided (17:40-18:40)

- **Three participants answered, and two said the same thing: too much.** One found the output "way too overwhelming", another "a bit too lengthy". A third asked for the posting's sentence next to the CV line, hard deal-breakers kept apart from soft preferences, and a preview of how the CV's dates were read. I took the first two as the problem and the third as the shape of the fix. Their words and screenshots are in [feedback/README.md](../feedback/README.md).
- **I rebuilt the report from simple to complex instead of trimming it.** The verdict in one sentence and one number at the top, the open yes/no questions right under it, "Improve my CV" locked until they are answered, then a numbered list of what to fix, most damaging first. Three tiers with text labels, not just colours: could rule you out, serious gap, worth improving. Each item shows the posting's sentence next to the CV line and one thing to do. What already works comes after, then how the dates were read, and everything else (all requirements, keyword coverage, the score breakdown, the CV as parsed) is folded into details. Nothing was deleted: it moved down. I approved a clickable mockup before any of it was built.
- **Short texts everywhere.** Every explanation the app writes is one plain sentence of about 20 words, without internal IDs.
- **Only legal bans rule you out on their own.** A missing work permit, security clearance or professional license gives "Likely screened out". A missing language or degree caps the verdict at "Long shot" and goes to the top of the list, because many employers are flexible there. Location and availability become yes/no questions. Answering "No" to any of them still rules you out. This replaces my Card 1 rule that a posting's own window could make the verdict "Likely screened out" on its own: Kubernetes experience that ended in 2017 against "within the last 5 years" now caps the verdict at "Long shot" and leads the list, which is what a candidate needs to hear.
- **Dates are shown, never guessed.** The report lists each job's dates as read and the time counted. A missing month says "month unknown" and counts as the shortest period it allows, so the total says "at least".
- **The landing page shows the result first.** A short example of the report plays before anyone uploads anything, because "paste, upload, press the button" says nothing about what you get.
- **Extra testing, kept apart from the feedback.** I also ran extra tests on the app. They are not real-world feedback and I don't count them for the card, but they found real bugs, so I fixed them: a blank line in the posting could move the score from 55 to 72, a missing "2+ years" counted as a small partial, the same question was asked twice, a 2023 degree was marked "aging", a date glued to a city ("SpainApr 2026") was read as January, and some suggestions only stuffed posting words into a line. Same CV and same posting must now give the same verdict and score.
