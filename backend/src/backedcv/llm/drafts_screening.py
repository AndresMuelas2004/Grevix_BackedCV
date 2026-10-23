"""LLM-facing output schema for the hidden-barrier screen (Claude structured outputs).

Same schema rules as drafts.py. Domain models are built from these drafts in
domain/barriers.py.
"""

from pydantic import BaseModel, Field

from backedcv.domain.models.screening import BarrierKind


class BarrierDraft(BaseModel):
    kind: BarrierKind = Field(
        description="The kind of barrier, as listed in the prompt. Use other when none fits."
    )
    quote: str = Field(
        description="The exact sentence of the posting that holds the barrier, copied verbatim."
    )
    explicit: bool = Field(
        description="True when the posting states the barrier plainly. False when only implied."
    )
    place: str | None = Field(
        description="The country, region or city the barrier names, copied as written. "
        "Null if none."
    )
    window_years: float | None = Field(
        description="Recency only: the number of years in the window, e.g. 5. Null for other kinds."
    )
    requirement_ids: list[str] = Field(
        description="IDs of the requirements (R...) from <requirements> that the quote comes from "
        "or affects. Empty when none."
    )
    explanation: str = Field(
        description="One plain sentence, 20 words at most, no IDs: why a screener may silently "
        "reject the candidate."
    )
    action: str = Field(
        description="One plain sentence, 20 words at most, no IDs: what the candidate can do."
    )
    question: str | None = Field(
        description="A short yes/no question without IDs, for work_authorization, location, "
        "graduation_window, language, clearance and availability. Null for recency and other."
    )


class HiddenBarriersDraft(BaseModel):
    items: list[BarrierDraft] = Field(
        description="At most 8, strongest first. Empty when the posting hides no barrier."
    )
