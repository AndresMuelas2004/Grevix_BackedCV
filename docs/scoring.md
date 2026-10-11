# Scoring and verdict

BackedCV gives each job posting two scores and one verdict. This page explains how each one is computed.

The numbers and labels come from `backend/src/backedcv/config/scoring.toml` and `backend/src/backedcv/config/tech_release_years.toml`. The rules come from the code in `backend/src/backedcv/domain/`.

## Two scores

**Fit (0 to 100)** asks whether you meet the requirements. It is judged by meaning: the model links each requirement to CV lines, and the code checks those links.

**Keyword coverage (0 to 100)** asks whether an exact-term search would find you. It checks whether the posting's terms, or their aliases (up to three abbreviations or expansions per requirement), appear in your CV as whole words. Matching ignores case. Plain words of four or more letters also match with the endings -s, -es, -d, -ed and -ing. C++, C#, .NET and Node.js match as written.

Coverage counts only hard skills, job titles, education, certifications and licenses, and languages. Years of experience, soft skills and other items are left out. Soft skills are left out on purpose: counting them word for word would reward keyword stuffing.

Rewording the CV can raise coverage but not Fit. Coverage only checks that a term appears, so adding a posting's exact term raises it. Fit asks what the CV proves, and an extra word proves nothing new. The one exception is described under Evidence rules.

## Weights and points

A requirement's weight is its category weight times its importance multiplier. The multiplier is 2 for required and 1 for preferred. Importance comes from the posting's wording, or from its section when the wording is silent.

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

Each excluded requirement records why: `not_relevant`, `flagged_R1`, `flagged_R2`, `flagged_R1+R2` (both rules flag it) or `gate`.

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

## Verdict

The rules run top to bottom, and the first match wins. Knockouts come first.

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

Four counted requirements, total weight 20:

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
