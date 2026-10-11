"""LLM-facing output schemas for the optimize step: suggestions, verification, posting review.

Same strict-mode rules as drafts.py.
"""

from typing import Literal

from pydantic import BaseModel, Field

SuggestionKind = Literal["align_wording", "add_skill", "tailor_summary"]
TermVerdict = Literal["faithful_name", "adds_claim"]


class SuggestionDraft(BaseModel):
    kind: SuggestionKind = Field(
        description="align_wording: rewrite one CV line so its evidence for a requirement is "
        "clearer and stronger. add_skill: add one posting term to the Skills section. "
        "tailor_summary: rewrite the summary from the strongest evidence."
    )
    target: str = Field(
        description="A CV line ID (e.g. 'L012'): the line to reword for align_wording, the "
        "Skills heading for add_skill, the Summary heading (or the first CV line) for "
        "tailor_summary."
    )
    after: str = Field(
        description="The new text, in the CV's language. For add_skill, only the skill name. "
        "Every number, title, employer, degree and certificate must be in the cited lines. "
        "Never the original line plus posting words or adjectives only."
    )
    cited_refs: list[str] = Field(
        description="IDs of the CV lines (L...) and facts (F...) that show everything in "
        "`after`, including every line a detail comes from. At least one."
    )
    requirement_ids: list[str] = Field(
        description="IDs of the requirements (R...) this change addresses. At least one."
    )
    rationale: str = Field(
        description="For the user, in English: one plain sentence of at most 20 words on what "
        "the edit makes clearer. No IDs."
    )


class SuggestionsDraft(BaseModel):
    suggestions: list[SuggestionDraft] = Field(
        description="At most 6, strongest first. Empty when no edit would really help without "
        "inventing or only adding posting words."
    )


class ClaimDraft(BaseModel):
    text: str = Field(
        description="One atomic claim from `after`: a single skill, role, number, date, scope "
        "or outcome, as a short span of `after`."
    )
    supported_by: list[str] = Field(
        description="IDs (L... or F...) that prove the whole claim as written. Empty when "
        "unsupported."
    )
    unsupported_reason: str | None = Field(
        description="Null when supported. Otherwise, for the user: one plain sentence of at most "
        "20 words on what the CV does not show. No IDs."
    )


class TermJudgementDraft(BaseModel):
    term: str = Field(
        description="A new name from `after` that the CV does not contain, copied as written."
    )
    verdict: TermVerdict = Field(
        description="faithful_name: a fair name for what a CV line describes, adding no detail. "
        "adds_claim: adds a skill, tool, level, scope or experience the CV does not show."
    )
    line_id: str | None = Field(
        description="For faithful_name, the L... line it names. Null for adds_claim."
    )


class VerificationDraft(BaseModel):
    suggestion_id: str = Field(description="The suggestion's ID exactly as given, e.g. 'S01'.")
    claims: list[ClaimDraft] = Field(
        description="Every atomic claim of `after`, in order. Never empty."
    )
    term_judgements: list[TermJudgementDraft] = Field(
        description="One per introduced term, plus any other new name in `after`. Empty when "
        "there are none."
    )
    uncertain: bool = Field(
        description="True whenever you are in doubt about any claim or term. False only when "
        "every claim is clearly supported and every term clearly faithful."
    )


class VerificationBatchDraft(BaseModel):
    verifications: list[VerificationDraft] = Field(
        description="One verification per suggestion given, in the same order."
    )


# The posting review is shown as a banner and never scored.
class ContradictionDraft(BaseModel):
    explanation: str = Field(
        description="One short sentence on what clashes. Low confidence: use 'seems' or 'may'."
    )
    quotes: list[str] = Field(
        description="The clashing sentences or values, copied verbatim from the posting data."
    )


class DoubtfulCredentialDraft(BaseModel):
    credential: str = Field(
        description="The certificate, license or degree name, copied verbatim from the posting."
    )
    explanation: str = Field(
        description="One short sentence on why the name seems not to exist as written."
    )


class PostingReviewDraft(BaseModel):
    contradictions: list[ContradictionDraft] = Field(
        description="Clear clashes inside the posting. Empty when nothing is clearly wrong."
    )
    doubtful_credentials: list[DoubtfulCredentialDraft] = Field(
        description="Credentials that seem not to exist as named. Empty when none."
    )
