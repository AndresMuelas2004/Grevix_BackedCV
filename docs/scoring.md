# Scoring and verdict

BackedCV gives each job posting two scores and one verdict. This page explains how each one is computed.

The numbers and labels come from `backend/src/backedcv/config/scoring.toml` and `backend/src/backedcv/config/tech_release_years.toml`. The rules come from the code in `backend/src/backedcv/domain/`.

## Two scores

**Fit (0 to 100)** asks whether you meet the requirements. It is judged by meaning: the model links each requirement to CV lines, and the code checks those links.

**Keyword coverage (0 to 100)** asks whether an exact-term search would find you. It checks whether the posting's terms, or their aliases (up to three abbreviations or expansions per requirement), appear in your CV as whole words. Matching ignores case. Plain words of four or more letters also match with the endings -s, -es, -d, -ed and -ing. C++, C#, .NET and Node.js match as written.

Coverage counts only hard skills, job titles, education, certifications and licenses, and languages. Years of experience, soft skills and other items are left out. Soft skills are left out on purpose: counting them word for word would reward keyword stuffing.

Rewording the CV can raise coverage but not Fit. Coverage only checks that a term appears, so adding a posting's exact term raises it. Fit asks what the CV proves, and an extra word proves nothing new. The one exception is described under Evidence rules.

## Weights and points

A requirement's base weight is its category weight times its importance multiplier. The multiplier is 2 for required and 1 for preferred. Importance comes from the posting's wording, or from its section when the wording is silent (see Same input, same score).

**Units.** Each requirement belongs to the posting bullet or sentence its quote sits in: its unit. A unit weighs as its heaviest counted requirement, and the counted requirements of one unit share that weight equally. "Strong Python and SQL skills." weighs 6 whether it is read as one requirement (6) or as Python and SQL (3 each), so how finely a bullet is split cannot move Fit. A requirement with no unit (its quote is not in the posting, or an analysis made before units) is a unit of its own. Below, "weight" means this shared weight.

| Category | Category weight | Required (x2) | Preferred (x1) | Counts for coverage |
|---|---|---|---|---|
| hard_skill | 3 | 6 | 3 | yes |
| experience_years | 3 | 6 | 3 | no |
| job_title | 2 | 4 | 2 | yes |
| education | 2 | 4 | 2 | yes |
| certification_license | 2 | 4 | 2 | yes |
| language | 2 | 4 | 2 | yes |
| soft_skill | 1 | 2 | 1 | no |
| other | 1 | 2 | 1 | no |
| work_authorization, location, clearance, availability (gates) | 0 | not scored | not scored | no |

Credit per status: met 1.0, partial 0.5, missing 0, unknown 0.

- **Denominator:** the total weight of the counted requirements (the ones not excluded, see below).
- **Fit** = 100 × (sum of weight × credit) ÷ denominator.
- **Keyword coverage** = 100 × (weight of coverage-category requirements whose term or alias is in the CV) ÷ (weight of all counted coverage-category requirements). Empty if there are none.
- **Share:** a requirement's weight ÷ denominator × 100. It earns share × credit and loses the rest.
- **Pending points:** the share of counted requirements still unknown. They earn nothing until you answer, so answers can only raise Fit.

Scores are rounded to one decimal place.

Excluded requirements do not count. They leave both the numerator and the denominator, so the rest is re-scaled:
- Marked not relevant by you.
- Flagged R1 or R2, unless you include them (see Flags).
- Gates (work authorization, location, clearance, availability). They never score. A required gate still acts as a knockout in the verdict.
- Requirements whose quote is not in the posting. They are dropped, unless the model gave them a knockout type or they are a gate.

Each excluded requirement records why: `not_relevant`, `flagged_R1`, `flagged_R2`, `flagged_R1+R2` (both rules flag it) or `gate`. An excluded requirement also leaves its unit: the counted requirements left in that unit keep the unit's weight.

## Same input, same score

The same CV and the same posting always get the same requirements, score and verdict:
- **Canonical text.** Both texts are normalized once, where they enter the app, before anything reads them: Unicode NFC; CRLF and CR become LF; zero-width characters, BOM, soft hyphens and other invisible format characters are dropped; tabs, NBSP and other Unicode spaces become one plain space; runs of spaces collapse; spaces at line ends go; three or more line breaks become two; blank lines at both ends go. Whitespace and invisible characters never change anything after that.
- **Cache.** Model answers are cached by model, reasoning effort, prompt (ID, version and text), schema and the canonical input, so a re-run of the same pair gets the stored answers.
- **Posting order and duplicates.** Code ties each requirement to its unit, sorts the requirements by where they sit in the posting and numbers them R01, R02... in that order. Two requirements of the same kind (a skill and the years asked of it count as one kind) with the same label or the same terms are merged into one, keeping the strictest importance and the most years asked.
- **Importance from the posting.** Wording in the bullet decides first ("must", "required" make it required; "nice to have", "a plus", "bonus", "preferred", "ideally" make it preferred). Otherwise the section heading above it does (Requirements, Must have, Qualifications... make it required; Nice to have, Preferred, Bonus, Plus... make it preferred). A bullet with both kinds of wording, or no clear section, keeps the model's reading.
- **Units** keep the split of a bullet from moving Fit (see Weights and points).

The model itself cannot be pinned: Claude Haiku 5.5 accepts no temperature, and the API takes no seed. A fresh extraction can still read a posting differently; the rules above limit what that can change.

## Evidence rules

Each requirement gets one status:
- **met**: the CV proves it. Full credit.
- **partial**: some proof, or an inferred match. Half credit.
- **missing**: the CV does not show it. No credit.
- **unknown**: not decided yet. No credit. Only gates and knockouts can stay unknown.

A knockout is a required requirement that employers usually ask as a yes/no screening question. The model sets the knockout type (work authorization, location, language, certification or license, years of experience, education, clearance or availability), and gate categories always get one.

The code applies these rules in order:
1. The model cites evidence only by ID: CV lines (such as `L012`) or computed facts (`F…`, such as total experience). The code fills in each quote from the CV and drops IDs that do not exist.
2. Met or partial with no valid citation becomes missing. For gates and knockouts, it becomes unknown.
3. An inferred match is never more than partial.
4. A gate is missing only with cited evidence or your answer. Otherwise it stays unknown.
5. A claim of enough years, backed only by the computed total, is checked against that total. If the total falls short, the claim becomes partial when the CV has at least half the years asked, and missing otherwise.
6. Any other unknown becomes missing. A skill the CV never shows is missing, not a question.
7. Your answers can settle an unknown knockout. Every required knockout can be answered yes or no, keyed by requirement ID. Answers apply only while the knockout is still unknown, so CV evidence always wins. Typed facts (work authorization, relocation, languages, licenses) can settle some unknowns too, but a direct answer comes first.
8. If the model's answer skips a requirement, or its call fails, the code falls back to literal matches. A posting term or alias found in the CV (same matching as Keyword coverage) counts as met, with up to three lines as evidence. This is the one exception to "Fit asks what the CV proves": for a requirement without a model answer, a literal match alone can raise Fit. Gates and knockouts never get this shortcut: they stay unknown. Anything else is missing.
9. A recency downgrade turns met or partial into missing. See Recency and hidden screening risks.

## Recency and hidden screening risks

Recency asks when the CV last showed each requirement. Hidden risks ask whether the posting holds a buried disqualifier that the CV does not settle. Both measure time from the analysis's creation date.

**Bands.** Each CV line takes the dates of the entry it belongs to: the end date, or the start date when there is no end. A current job counts as ending on the analysis date. A line in several entries keeps the latest date. A line outside any dated entry is undated.

For each met or partial requirement with CV-line evidence, the most recent dated line gives its last use. Years since then (whole months divided by 12, rounded to one decimal) set the band:

| Band | Years since last use |
|---|---|
| `recent` | up to 3.0 |
| `aging` | over 3.0, up to 6.0 |
| `stale` | over 6.0 |
| `undated` | no dated line |

The thresholds are the constants `RECENT_MAX_YEARS` and `AGING_MAX_YEARS` in `domain/recency.py`. Facts such as total years are not checked this way.

**Windows.** Only a window stated in the posting removes credit. Code patterns find windows such as "within the last 5 years" or "5+ years in the last 7 years" (the window is the 7). Numbers can be digits or the words one to ten. "Recent experience" with no number is not a window. Each window keeps the posting's exact sentence.

A window applies to the requirements its sentence mentions. A window that names none applies to every required hard skill and experience-years requirement. If several apply, the smallest counts.

**Effect.** With a window:
- Dated evidence inside it: no effect.
- Dated evidence only outside it: downgraded. The status becomes missing, so the requirement earns no credit. Keyword coverage does not change, because the keyword is still in the CV.
- No dated evidence: warning.

Without a window, a stale last use is a warning. A warning never changes the score.

**Risk levels.** A hidden barrier is a disqualifier that the posting states in a buried or unclear way. Its kind is work authorization, location, recency, graduation window, language, clearance, availability or other. Work authorization, location, graduation window, language, clearance and availability are eligibility barriers: a CV edit cannot fix them, so you answer them.

Code sets the risk levels, from the CV, your answers and the dates. The model never sets a level. "Explicit" means the posting states the barrier plainly; "implied" means it only suggests it. "Resolved" means the barrier no longer counts. "Confirmed" means it applies to you.

| Case | Risk |
|---|---|
| Tied to a knockout requirement, and every such requirement is met | low, resolved |
| Tied to a knockout requirement, and you answered one of them no | high, confirmed |
| Tied to a knockout requirement, otherwise | medium if explicit, low if implied |
| You answered yes | low, resolved |
| You answered no | high, confirmed |
| Work authorization, and you said you need sponsorship | high, confirmed |
| Work authorization or location, and the place it names is your location or a country you are authorized in | low, resolved |
| Location, and you are willing to relocate | low, resolved |
| Work authorization or location, and your known location does not match the place it names | high, with your location line as evidence |
| Recency | high if downgraded, medium if warning, low otherwise; resolved when the evidence is inside a stated window |
| Any other barrier | medium if explicit, low if implied |

- A barrier tied to a knockout requirement never asks a question of its own. The knockout's question covers it.
- Other eligibility barriers ask a yes or no question: the model's wording, or a default for the kind. Recency and other barriers ask none.
- Two or more open medium risks that are not tied to a knockout make one composite risk, `HC1`, at high level. It lists those risks as components and the requirements they touch.

**Looks met, but...** A requirement gets this badge when it looks met and carries a recency warning or downgrade, or an unresolved medium or high barrier risk that names it. It looks met when its status before the recency check was met or partial, or its exact keyword is in the CV. The badge gives plain reasons and the barrier IDs behind it (for example `H01`). It is separate from the R1 and R2 flags (see Flags).

**Effect on the verdict.** Hidden risks feed the rules in Verdict as if they were knockouts:
- A confirmed eligibility risk (a no answer, or a sponsorship need you gave) acts like a missing knockout: Likely screened out, with the barrier's quote.
- An unanswered high risk with a question acts like an unanswered knockout: it counts in "Answer N question(s) first" and is listed as an open question.
- A barrier tied to a knockout requirement never changes the verdict. The knockout's own question covers it.
- Other high risks and composite risks add a reason to the verdict, without changing its label.

Only a recency downgrade changes Fit. Hidden risks never do.

## Verdict

The rules run top to bottom, and the first match wins. Knockouts come first. Hidden risks join the first two rules (see Recency and hidden screening risks).

An **active** knockout is required, not marked not relevant, and not flagged (unless you included it).

| Label | Title shown | When |
|---|---|---|
| `likely_screened_out` | Likely screened out | An active knockout is missing: the employer's screening question would likely reject you. Each one is listed with its quote. |
| `answer_questions` | Answer N question(s) first | An active knockout is unknown. Each open question is listed. Provisional. |
| `apply` | Apply | Fit is 75 or more, and there is no blocking item. |
| `stretch` | Stretch: apply if you can explain the gaps | Fit is 55 or more, and the verdict is not Apply. |
| `long_shot` | Long shot | Fit is below 55. |

- A **blocking item** is a counted, required requirement that is missing and sits in a category with weight 2 or more (hard skill, years of experience, job title, education, license, language). So a Fit of 80 with a missing required skill is Stretch.
- Thresholds use the rounded Fit.
- If no requirement can be scored, the band is Stretch and the verdict says "No scorable requirements were found."
- Only `answer_questions` is provisional. Answering the questions can change the verdict.

Each verdict shows reasons under its title:

- **Fit against the thresholds** (first reason of every score band): "Your Fit is 65 out of 100; 55 is needed for a stretch and 75 to apply with confidence."
- **Strongest matches** (Apply, when there are any): up to 3 met requirements, heaviest first.
- **Missing required** (Stretch and Long shot, when there are any): up to 3 counted required requirements that are missing, heaviest first.
- **Likely screened out:** one reason per missing active knockout, with its quote.
- **Answer N questions:** one reason per open knockout, then the score band's reasons.

Badges can appear with any verdict:

| Badge | Appears when |
|---|---|
| `tailor_first` | Fit minus Keyword coverage is 15 or more. Fit is well ahead of coverage: the CV may match by meaning but not by wording. |
| `screening_risk` | A flagged knockout (left out by default) is missing. It warns without changing the verdict. |
| `posting_red_flags` | The posting has a banner from R3 or R4 (see Banners). Banners never change the score or the verdict. |

## Flags

Flags are set when a posting is analysed. A flagged requirement leaves the score by default.

- **R1, entry level asking for years.** The posting's seniority, the quote that states it, or its title contains an entry-level word as a whole word: entry, junior, graduate, intern, trainee, jr, becario or prácticas (the last two are Spanish for intern). And a requirement asks for 3 or more years.
- **R2, years beyond a technology's age.** A requirement with a years minimum names a technology from the table below and asks for more years than that technology's age. Age is the current year minus its first public release year. Example: in 2026, asking for 3 years of LangGraph is flagged, because LangGraph (2024) is 2 years old.

R1 and R2 are checked separately, so one requirement can carry both. Its excluded reason then reads `flagged_R1+R2`.

"First public release" means the first public version, beta or open-source release, not 1.0. The years were checked on 2026-10-11 against official release notes, repositories, blogs or package indexes.

| Technology | First public release |
|---|---|
| Docker | 2013 |
| Kubernetes | 2014 |
| React | 2013 |
| TypeScript | 2012 |
| Swift | 2014 |
| Rust | 2012 |
| Kotlin | 2011 |
| FastAPI | 2018 |
| LangChain | 2022 |
| LangGraph | 2024 |
| TensorFlow | 2015 |
| PyTorch | 2016 |
| Terraform | 2014 |
| Flutter | 2017 |
| Next.js | 2016 |
| GitHub Actions | 2018 |
| Model Context Protocol | 2024 |
| MCP | 2024 |
| LlamaIndex | 2022 |
| GPT-4 | 2023 |

What a flag does:
- **Left out (default):** the requirement leaves Fit and coverage. It cannot make the verdict "Likely screened out" or ask a question. If it is missing, the `screening_risk` badge can show.
- **Included (you count it again):** it scores like any other requirement. If it is a required knockout, it can now trigger a screening-out verdict or a question.
- **Marked not relevant:** it leaves everything, flagged or not.

## Banners

Banners are notes about the posting as a whole. They never change the score or the verdict. They only add the `posting_red_flags` badge.

- **R3, tool sprawl (computed in code):** more than 10 hard skills spread over at least 4 skill areas (the areas come from `skill_domains.toml`). The posting may be a wish list.
- **R4, posting review (model, cautious):** two sentences in the posting that seem not to fit together, or a certificate, license or degree that seems not to exist as named. Each finding needs a quote or a name. If the review call fails, there are no R4 banners.

## Worked example

Four counted requirements from four different bullets (so four units), total weight 20:

| Requirement | Type | Weight | Status | Share | Points won | Keyword match |
|---|---|---|---|---|---|---|
| Python | hard skill, required | 6 | met | 30 | 30 | yes |
| Kubernetes | hard skill, required | 6 | partial | 30 | 15 | no |
| Backend engineer | job title, required | 4 | missing | 20 | 0 | no |
| Bachelor's degree | education, required | 4 | met | 20 | 20 | yes |

- Fit = 30 + 15 + 0 + 20 = **65.0**, the same as 100 × 13 ÷ 20.
- Keyword coverage = 100 × (6 + 4) ÷ 20 = **50.0**. All four are coverage categories.
- Fit minus coverage is 15.0, so `tailor_first` shows.
- Backend engineer is a missing required job title (category weight 2), so it blocks Apply.
- Fit is 65.0, which is 55 or more, so the verdict is **Stretch**.

The reasons shown: "Your Fit is 65 out of 100; 55 is needed for a stretch and 75 to apply with confidence." and "Missing required: Backend engineer."

## Limits

- The scores are indicative. They show how your CV lines up with a posting under these published rules. Nobody can compute the real score a specific company's system gives you.
- Most applicant tracking systems (ATS) do not auto-reject on keywords. Knockout questions usually do, which is why knockouts come first in the verdict.
- Matches by meaning come from a language model. The code checks citations, quotes and years, not the model's judgment.
- The weights are this project's choices, not an industry standard.
