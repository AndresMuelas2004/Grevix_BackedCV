"""Knockout requirements: the screening question they likely become, and how facts answer it."""

from backedcv.domain.models import (
    CandidateFacts,
    JobPosting,
    Requirement,
    RequirementAssessment,
)
from backedcv.domain.text import fold_lower


def is_knockout(requirement: Requirement) -> bool:
    return requirement.importance == "required" and requirement.knockout_type is not None


def likely_question(requirement: Requirement, job: JobPosting) -> str:
    """The screening question this requirement usually becomes, phrased as a likely question."""
    where = job.location or "this job's location"
    match requirement.knockout_type:
        case "work_authorization":
            return f"Are you legally authorized to work in {where} without visa sponsorship?"
        case "location":
            return f"Are you able to work from {where} (or willing to relocate)?"
        case "language":
            return f"Do you meet this language requirement: {requirement.label}?"
        case "certification_license":
            return f"Do you hold this credential: {requirement.label}?"
        case "experience_years":
            years = f"{requirement.min_years:g}+ years" if requirement.min_years else "the required"
            return f"Do you have {years} of experience as asked ({requirement.label})?"
        case "education":
            return f"Do you meet this education requirement: {requirement.label}?"
        case "clearance":
            return f"Do you hold or can you obtain this clearance: {requirement.label}?"
        case "availability":
            return f"Can you meet this availability requirement: {requirement.label}?"
    return f"Do you meet this requirement: {requirement.label}?"


def apply_facts(
    requirement: Requirement,
    assessment: RequirementAssessment,
    facts: CandidateFacts,
    job: JobPosting,
) -> RequirementAssessment:
    """Resolve an unknown knockout from the user's answers. Never guesses from names or places."""
    if assessment.status != "unknown" or not is_knockout(requirement):
        return assessment

    answer = facts.answers.get(requirement.id)
    if answer is not None:  # a direct yes/no answer beats the typed facts
        return assessment.model_copy(
            update={
                "status": "met" if answer else "missing",
                "source": "user_answer",
                "rationale": "You answered yes." if answer else "You answered no.",
            }
        )

    status = None
    if requirement.knockout_type == "work_authorization":
        if facts.needs_sponsorship is True and _mentions_sponsorship(requirement):
            status = "missing"
        elif facts.work_authorization and job.location:
            covered = any(
                fold_lower(country) in fold_lower(job.location)
                for country in facts.work_authorization
            )
            status = "met" if covered else None
    elif requirement.knockout_type == "location" and facts.willing_to_relocate is not None:
        status = "met" if facts.willing_to_relocate else "missing"
    elif requirement.knockout_type == "language" and facts.languages is not None:
        wanted = fold_lower(requirement.label + " " + requirement.quote)
        status = "met" if any(fold_lower(lang) in wanted for lang in facts.languages) else None
    elif requirement.knockout_type == "certification_license" and facts.licenses is not None:
        wanted = fold_lower(requirement.label + " " + requirement.quote)
        status = "met" if any(fold_lower(lic) in wanted for lic in facts.licenses) else None

    if status is None:
        return assessment
    return assessment.model_copy(
        update={"status": status, "source": "user_answer", "rationale": "From your answers."}
    )


def _mentions_sponsorship(requirement: Requirement) -> bool:
    text = fold_lower(requirement.quote + " " + requirement.label)
    return "sponsor" in text or "visa" in text or "patrocin" in text
