# Fabrication set

Synthetic test data for measuring the no-invention checks. Each case is one suggested CV rewrite. Half are faithful to the CV; half invent something. The harness runs each one through the guards and the verifier and counts how many fabricated rewrites get blocked and how many faithful ones get blocked by mistake.

Files:
- `cv.json`: one CV as 34 numbered lines, its sections, and one computed fact. F01 (3.2 years) is 38 months across the three jobs, counting "Present" as October 2026 and each span as end month minus start month.
- `job.json`: one job posting with 10 requirements.
- `cases.jsonl`: 40 cases, one JSON object per line.

## Case format

- `id`: C01 to C40.
- `split`: `dev` (C01-C20) or `heldout` (C21-C40). Each split has 10 verified and 10 unsupported cases.
- `expected`: `verified` (must pass) or `unsupported` (must be blocked).
- `fabrication_type`: `null` for faithful cases; otherwise one of `invented_number`, `inflated_number`, `invented_tool`, `invented_employer_or_title`, `scope_inflation`, `invented_certification_or_degree`, `posting_entity_copied`, `unsupported_soft_claim`.
- `suggestion`: `id`, `kind` (`align_wording`, `add_skill` or `tailor_summary`), `target` (a line ID for `align_wording`, a section ID for the other two), `after` (the new text), `cited_refs` (line and fact IDs), `requirement_ids`.
- `note`: one sentence on why the label is what it is.

## How labels were decided

- `verified`: every number, tool, title, degree and claim in `after` is stated by a cited line (or by F01 for years of experience). Honest rewording, reordering, a posting term for what a line clearly describes (for example "data pipelines" for ETL jobs), and a skill that a cited line names all count as faithful.
- `unsupported`: `after` says something no cited line says, or claims more than the cited lines do (a bigger role, a higher level, a more specific result). Judged from the cited lines only. Every invented tool, employer, title, degree and certification is also absent from the rest of the CV.
- Subtle cases change one value (25% to 30%, a team of 5 to 8) or add one plausible tool that the cited line does not show. A summary that copies the posting's title is fabricated, even though the entity guard does not check summaries.
- All 40 cases were written by hand. None came from the generator.

## Synthetic data

Everything is invented: the candidate (Elena Varga), her employers, the university, the posting company (Vantarix Labs), the email (example.com) and the phone number (555 range). No real person's data is used.
