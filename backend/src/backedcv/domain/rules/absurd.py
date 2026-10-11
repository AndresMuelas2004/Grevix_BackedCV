"""R1/R2: absurd requirements that leave Fit (the user can include them back)."""

import re
from datetime import date

from backedcv.config import load
from backedcv.domain.keywords import contains_term
from backedcv.domain.models import JobPosting, RequirementFlag
from backedcv.domain.scoring import ScoringConfig
from backedcv.domain.text import fold_lower


def is_entry_level(job: JobPosting, config: ScoringConfig) -> bool:
    text = fold_lower(" ".join(filter(None, [job.seniority, job.seniority_quote, job.title])))
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in config.r1_seniority_words)


def flag_requirements(
    job: JobPosting, *, today: date | None = None, config: ScoringConfig | None = None
) -> list[RequirementFlag]:
    config = config or ScoringConfig.default()
    today = today or date.today()
    flags: list[RequirementFlag] = []

    if is_entry_level(job, config):
        for req in job.requirements:
            if req.min_years is not None and req.min_years >= config.r1_min_years:
                flags.append(
                    RequirementFlag(
                        rule_id="R1",
                        requirement_ids=[req.id],
                        explanation=(
                            f"An entry-level role asking for {req.min_years:g}+ years often "
                            "accepts less, so apply if you meet the rest."
                        ),
                    )
                )

    releases = load("tech_release_years").get("technologies", {})
    for req in job.requirements:  # also when R1 already flags it: both flags can apply
        if req.min_years is None:
            continue
        text = " ".join([req.quote, req.label, *req.terms])
        for tech, year in releases.items():
            age = today.year - int(year)
            if contains_term(text, tech) and req.min_years > age:
                flags.append(
                    RequirementFlag(
                        rule_id="R2",
                        requirement_ids=[req.id],
                        explanation=(
                            f"Asks for {req.min_years:g} years of {tech}, first released in "
                            f"{year}, so nobody can meet it literally."
                        ),
                    )
                )
                break
    return flags


def flags_by_requirement(flags: list[RequirementFlag]) -> dict[str, str]:
    """Requirement ID -> its rule IDs joined with "+" (e.g. "R1+R2" when both flag it)."""
    rules: dict[str, set[str]] = {}
    for flag in flags:
        for rid in flag.requirement_ids:
            rules.setdefault(rid, set()).add(flag.rule_id)
    return {rid: "+".join(sorted(ids)) for rid, ids in rules.items()}
