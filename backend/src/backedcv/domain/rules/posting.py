"""R3: tool sprawl, a posting-level banner that never touches the score."""

from backedcv.config import load
from backedcv.domain.keywords import contains_term
from backedcv.domain.models import JobPosting, PostingBanner, Requirement

MORE_THAN_HARD_SKILLS = 10  # R3 needs more hard skills than this...
MIN_DOMAINS = 4  # ...spread over at least this many domains.


def _domains_of(req: Requirement, domains: dict[str, dict]) -> set[str]:
    text = " ".join([req.label, *req.terms])
    return {
        key
        for key, domain in domains.items()
        if any(contains_term(text, term) for term in domain["terms"])
    }


def tool_sprawl_banner(job: JobPosting) -> PostingBanner | None:
    """Banner for postings that ask for many hard skills across many domains."""
    skills = [r for r in job.requirements if r.category == "hard_skill"]
    if len(skills) <= MORE_THAN_HARD_SKILLS:
        return None
    domains = load("skill_domains")["domains"]
    touched: set[str] = set()
    for req in skills:
        touched |= _domains_of(req, domains)
    if len(touched) < MIN_DOMAINS:
        return None
    names = ", ".join(d["name"] for key, d in domains.items() if key in touched)
    return PostingBanner(
        rule_id="R3",
        requirement_ids=[r.id for r in skills],
        severity="info",
        explanation=(
            f"This posting lists {len(skills)} hard skills across {len(touched)} areas "
            f"({names}). It may be a wish list; the role's real core is probably narrower."
        ),
    )
