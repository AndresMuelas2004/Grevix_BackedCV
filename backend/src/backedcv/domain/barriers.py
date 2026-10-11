"""Hidden screening barriers: buried disqualifiers, checked against the CV and the answers.

Code finds the work-authorization sentences a model can miss, keeps only the model's quotes that
really appear in the posting, merges both with the recency rules, and assesses each barrier against
the CV and the candidate's answers. Pure functions: no I/O and no LLM calls.
"""

import re

from backedcv.domain.keywords import contains_term
from backedcv.domain.models import (
    ELIGIBILITY_KINDS,
    BarrierItem,
    BarrierKind,
    CandidateFacts,
    HiddenRisk,
    JobPosting,
    ParsedCV,
    RecencyCheck,
    RecencyRule,
    Requirement,
    RequirementAssessment,
    RiskLevel,
    ScreeningFlag,
)
from backedcv.domain.models.screening import clean_prose, short_sentence
from backedcv.domain.text import fold, fold_lower, locate_quote
from backedcv.llm.drafts_screening import HiddenBarriersDraft

MAX_ITEMS = 8
MIN_WINDOW_YEARS, MAX_WINDOW_YEARS = 1, 20
PLACE_KINDS = frozenset({"work_authorization", "location"})
LEVEL_RANK: dict[str, int] = {"high": 0, "medium": 1, "low": 2}
EFFECT_RANK: dict[str, int] = {"none": 0, "warning": 1, "downgraded": 2}
EFFECT_LEVEL: dict[str, RiskLevel] = {"none": "low", "warning": "medium", "downgraded": "high"}

DEFAULT_ACTION = "Ask the employer about this point before you apply, and say how you meet it."
ACTIONS: dict[str, str] = {
    "work_authorization": (
        "State in your application and CV whether you already have the right to work there."
    ),
    "location": "State where you live and whether you can work from the required place.",
    "recency": "Show when you last used each skill in your CV, with dates, or explain any gap.",
    "graduation_window": "Put your graduation date at the top of your education section.",
    "language": "State your language level and any certificate in your CV.",
    "clearance": "Say in your application whether you hold the clearance or could get it.",
    "availability": (
        "State your start date and any limits on shifts or travel in your application."
    ),
}

_UNITED_STATES = ("united states", "united states of america", "usa", "us", "u.s.", "u.s.a.")
_UNITED_KINGDOM = ("united kingdom", "great britain", "uk", "u.k.")
_EUROPEAN_UNION = ("european union", "eu", "e.u.")
_EU_MEMBERS = (
    "austria",
    "belgium",
    "bulgaria",
    "croatia",
    "cyprus",
    "czechia",
    "czech republic",
    "denmark",
    "estonia",
    "finland",
    "france",
    "germany",
    "greece",
    "hungary",
    "ireland",
    "italy",
    "latvia",
    "lithuania",
    "luxembourg",
    "malta",
    "netherlands",
    "poland",
    "portugal",
    "romania",
    "slovakia",
    "slovenia",
    "spain",
    "sweden",
)
_ALIAS_GROUPS = {name: group for group in (_UNITED_STATES, _UNITED_KINGDOM) for name in group}
_THE_PLACES = frozenset(
    {*_UNITED_STATES, "united kingdom", "uk", "u.k.", *_EUROPEAN_UNION, "netherlands"}
)

# Sentences end at a full stop, "!" or "?" and at line breaks; a semicolon keeps a clause together.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
_BULLET = re.compile(r"^\s*[-*]\s+")
# A proper name after "in" or "of": "the United States", "Spain", "U.S.", "New York City".
_PLACE = r"[A-Z][\w'-]*(?:\.[A-Z]\.?)*(?:\s+(?:of\s+)?[A-Z][\w'-]*(?:\.[A-Z]\.?)*){0,3}"
_NEGATION = (
    r"(?i:\b(?:no|not|unable|cannot|can't|won't|don't|doesn't|do\s+not|does\s+not"
    r"|will\s+not)\b)"
)
_NO_SPONSOR = re.compile(_NEGATION + r"[^.;]{0,60}?\bsponsor(?:ship|ing|s)?\b")
_VISA_WORDS = re.compile(r"(?i:\bvisas?\b|\bimmigration\b|\bwork\s+permits?\b)")
_NO_VISA_SPONSORSHIP = re.compile(
    r"(?i:\b(?:visa|immigration)\s+sponsor(?:ship|ing)\b)"
    r"[^.;]{0,30}?(?i:\b(?:not|unavailable)\b)"
)
_RIGHT_TO_WORK = re.compile(
    r"(?i:\b(?:right|authori[sz]ed|authori[sz]ation|eligible|eligibility|entitled|permission)\b"
    r"[^.;]{0,30}?\bto\s+work\s+in\b)"
    rf"(?:\s+(?i:the\s+)?(?P<place>{_PLACE}))?"
)
_CITIZEN_OF = re.compile(rf"(?i:\b(?:citizens?|nationals?)\s+of\s+)(?i:the\s+)?(?P<place>{_PLACE})")
_CITIZENS_ONLY = re.compile(
    r"(?i:\b(?:citizens?|nationals?)\s+only\b|\bonly\s+(?:citizens?|nationals?)\b)"
)


# 1. Model items: keep only what the posting really says -----------------------------------


def barriers_from_draft(
    draft: HiddenBarriersDraft, job_text: str, job: JobPosting
) -> list[BarrierItem]:
    """Model barriers that hold up: the quote is in the posting (its span is kept), and only
    known requirement IDs stay. At most MAX_ITEMS items are kept."""
    known = {req.id for req in job.requirements}
    labels = {req.id: req.label for req in job.requirements}
    items: list[BarrierItem] = []
    for row in draft.items:
        quote = locate_quote(_BULLET.sub("", row.quote), job_text)
        if quote is None:
            continue
        window = row.window_years if row.kind == "recency" else None
        if window is not None and not MIN_WINDOW_YEARS <= window <= MAX_WINDOW_YEARS:
            window = None
        ids = _union([rid for rid in row.requirement_ids if rid in known])
        items.append(
            _complete(
                BarrierItem(
                    id=_barrier_id(len(items)),
                    kind=row.kind,
                    quote=quote,
                    explicit=row.explicit,
                    place=_place_in_text(row.place, job_text),
                    window_years=window,
                    requirement_ids=ids,
                    # The model's sentences: no IDs (labels replace requirement IDs), one short
                    # sentence each.
                    explanation=short_sentence(clean_prose(row.explanation, labels)),
                    action=short_sentence(clean_prose(row.action, labels)),
                    question=_clean(short_sentence(clean_prose(row.question, labels))),
                    source="model",
                )
            )
        )
        if len(items) == MAX_ITEMS:
            break
    return items


# 2. Rule items: work-authorization wording that code can see -----------------------------


def find_rule_barriers(job_text: str) -> list[BarrierItem]:
    """Work-authorization sentences that code patterns find, one item per distinct sentence."""
    items: list[BarrierItem] = []
    seen: set[str] = set()
    for piece in _SENTENCE_BREAK.split(job_text):
        sentence = _BULLET.sub("", fold(piece))
        found, place = _work_rule(sentence)
        quote = locate_quote(sentence, job_text) if found else None
        if quote is None or fold_lower(quote) in seen:
            continue
        seen.add(fold_lower(quote))
        items.append(
            _complete(
                BarrierItem(
                    id=_barrier_id(len(items)),
                    kind="work_authorization",
                    quote=quote,
                    explicit=True,
                    place=place,
                    source="rule",
                )
            )
        )
    return items


def _work_rule(sentence: str) -> tuple[bool, str | None]:
    """Whether the sentence states a work-authorization barrier, and the place it names, if any."""
    place: str | None = None
    found = False
    for pattern in (_RIGHT_TO_WORK, _CITIZEN_OF):
        match = pattern.search(sentence)
        if match:
            found = True
            place = place or match.group("place")
    if _NO_SPONSOR.search(sentence) and _VISA_WORDS.search(sentence):
        found = True
    if _NO_VISA_SPONSORSHIP.search(sentence) or _CITIZENS_ONLY.search(sentence):
        found = True
    return found, place


# 3. Merge: model first, then rules they do not repeat, then recency rules -----------------


def merge_barriers(
    model_items: list[BarrierItem],
    rule_items: list[BarrierItem],
    recency_rules: list[RecencyRule],
    job: JobPosting,
) -> list[BarrierItem]:
    """Model items first, then the code rules they do not repeat, then the recency rules. A rule
    joins an item of its kind whose quote overlaps it. An eligibility item that asks the question
    an earlier one asks joins it too: one question per fact. Every item lists each requirement
    whose quote overlaps its own. IDs run H01... in that order."""
    merged = [item.model_copy() for item in model_items]
    for rule in rule_items:
        if not any(item.kind == rule.kind and _overlaps(item.quote, rule.quote) for item in merged):
            merged.append(rule.model_copy())
    for recency_rule in recency_rules:
        twin = next(
            (
                item
                for item in merged
                if item.kind == "recency" and _overlaps(item.quote, recency_rule.quote)
            ),
            None,
        )
        if twin is None:
            merged.append(_recency_item(recency_rule))
        else:
            twin.window_years = recency_rule.window_years
            twin.requirement_ids = _union(twin.requirement_ids, recency_rule.requirement_ids)
    kept: list[BarrierItem] = []
    asking: dict[str, BarrierItem] = {}  # question key -> the item that asks it
    for item in merged:
        key = _question_key(item, job.location)
        first = asking.setdefault(key, item) if key else item
        if first is item:
            kept.append(item)
        else:
            first.requirement_ids = _union(
                first.requirement_ids, item.requirement_ids, _overlapping(item.quote, job)
            )
    return [
        _linked(item, job).model_copy(update={"id": _barrier_id(index)})
        for index, item in enumerate(kept)
    ]


def _recency_item(rule: RecencyRule) -> BarrierItem:
    return _complete(
        BarrierItem(
            id="",  # renumbered by merge_barriers
            kind="recency",
            quote=rule.quote,
            explicit=True,
            window_years=rule.window_years,
            requirement_ids=list(rule.requirement_ids),
            source="rule" if rule.source == "rule" else "model",
        )
    )


def _linked(item: BarrierItem, job: JobPosting) -> BarrierItem:
    """The item lists every requirement whose quote overlaps its own, and the gate requirement
    that asks about the same fact (see _same_fact). Its sentences carry no raw IDs."""
    ids = _union(item.requirement_ids, _overlapping(item.quote, job))
    twin = _same_fact(item, ids, job)
    labels = {req.id: req.label for req in job.requirements}
    return item.model_copy(
        update={
            "requirement_ids": _union(ids, [twin] if twin else []),
            "explanation": clean_prose(item.explanation, labels),
            "action": clean_prose(item.action, labels),
            "question": _clean(clean_prose(item.question, labels)),
        }
    )


def _overlapping(quote: str, job: JobPosting) -> list[str]:
    return [req.id for req in job.requirements if _overlaps(quote, req.quote)]


def _same_fact(item: BarrierItem, ids: list[str], job: JobPosting) -> str | None:
    """The gate requirement (one with a knockout type) that asks the same question as an
    eligibility barrier, so one answer settles both: same kind, and the place the barrier names
    is in that requirement's words or is the job's location. A barrier without a place matches
    the only gate requirement of its kind. None when the barrier already lists a gate."""
    gates = [req for req in job.requirements if req.knockout_type is not None]
    if item.kind not in ELIGIBILITY_KINDS or any(req.id in ids for req in gates):
        return None
    same_kind = [req for req in gates if req.knockout_type == item.kind]
    if not item.place:
        return same_kind[0].id if len(same_kind) == 1 else None
    for req in same_kind:
        if _covers(item.place, f"{req.label} {req.quote}"):
            return req.id
    if len(same_kind) == 1 and job.location and _covers(item.place, job.location):
        return same_kind[0].id
    return None


# 4. Risks: each barrier against the CV and the answers ------------------------------------


def assess_risks(
    barriers: list[BarrierItem],
    job: JobPosting,
    cv: ParsedCV,
    assessments: dict[str, RequirementAssessment],
    facts: CandidateFacts,
    recency: dict[str, RecencyCheck],
) -> list[HiddenRisk]:
    """One risk per barrier, plus a composite HC1 when two or more open medium risks remain.
    A barrier tied to a knockout asks no question of its own; see _knockout_risk. Tied barriers
    never join the composite. Order: the composite first, then high, medium and low, barrier
    order within each level."""
    knockouts = {req.id: req for req in job.requirements if req.knockout_type}
    risks: list[HiddenRisk] = []
    tied: set[str] = set()
    for barrier in barriers:
        tied_to = [knockouts[rid] for rid in barrier.requirement_ids if rid in knockouts]
        if tied_to:
            tied.add(barrier.id)
            risks.append(_knockout_risk(barrier, tied_to, assessments, cv, facts, recency))
        else:
            risks.append(_own_risk(barrier, job, cv, facts, recency))
    composite = _composite(risks, tied)
    if composite is not None:
        risks.append(composite)
    return sorted(risks, key=lambda risk: (risk.kind != "composite", LEVEL_RANK[risk.risk]))


def _knockout_risk(
    barrier: BarrierItem,
    knockouts: list[Requirement],
    assessments: dict[str, RequirementAssessment],
    cv: ParsedCV,
    facts: CandidateFacts,
    recency: dict[str, RecencyCheck],
) -> HiddenRisk:
    """A barrier tied to a knockout. Only three rules are special: it asks no question of its own
    (the knockout asks); a met knockout resolves it (low); a no from the candidate confirms it
    (high). Otherwise the barrier's own kind decides, exactly as for any other barrier."""
    states = [_knockout_state(assessments.get(req.id)) for req in knockouts]
    if "answered_no" in states:
        return _risk(barrier, "high", confirmed=True)
    if all(state == "met" for state in states):
        return _risk(barrier, "low", resolved=True)
    return _by_kind(barrier, cv, facts, recency, question=None)


def _knockout_state(assessment: RequirementAssessment | None) -> str:
    if assessment is None:
        return "open"
    if assessment.status == "met":
        return "met"
    if assessment.status == "missing" and assessment.source == "user_answer":
        return "answered_no"
    return "open"


def _own_risk(
    barrier: BarrierItem,
    job: JobPosting,
    cv: ParsedCV,
    facts: CandidateFacts,
    recency: dict[str, RecencyCheck],
) -> HiddenRisk:
    """A barrier with a question of its own: the candidate's yes or no settles it first."""
    question = _question(barrier, job.location)
    answer = facts.answers.get(barrier.id)
    if answer is not None:
        return _risk(
            barrier,
            "low" if answer else "high",
            question=question,
            resolved=answer,
            confirmed=not answer,
        )
    return _by_kind(barrier, cv, facts, recency, question)


def _by_kind(
    barrier: BarrierItem,
    cv: ParsedCV,
    facts: CandidateFacts,
    recency: dict[str, RecencyCheck],
    question: str | None,
) -> HiddenRisk:
    """The level from the barrier's own kind: needs_sponsorship, the place against the CV, the
    recency checks, or medium or low when the posting alone decides."""
    if barrier.kind == "work_authorization" and facts.needs_sponsorship is True:
        return _risk(barrier, "high", question=question, confirmed=True)
    if barrier.kind == "recency":
        return _recency_risk(barrier, recency)
    if barrier.kind in PLACE_KINDS:
        return _place_risk(barrier, cv, facts, question)
    return _risk(barrier, "medium" if barrier.explicit else "low", question=question)


def _place_risk(
    barrier: BarrierItem, cv: ParsedCV, facts: CandidateFacts, question: str | None
) -> HiddenRisk:
    """The place a barrier names, against the candidate's countries and location line."""
    if barrier.kind == "location" and facts.willing_to_relocate is True:
        return _risk(barrier, "low", question=question, resolved=True)
    line = cv.contact.location
    here = line.value if line else facts.location
    if barrier.place:
        countries: list[str] = []
        if barrier.kind == "work_authorization":
            countries = facts.work_authorization or []
        if any(_covers(barrier.place, c) for c in countries) or (
            here and _covers(barrier.place, here)
        ):
            return _risk(barrier, "low", question=question, resolved=True)
        if here:
            refs = [line.line_id] if line else []
            return _risk(barrier, "high", question=question, cv_refs=refs)
    return _risk(barrier, "medium" if barrier.explicit else "low", question=question)


def _recency_risk(barrier: BarrierItem, recency: dict[str, RecencyCheck]) -> HiddenRisk:
    checks = _checks_for(barrier, recency)
    if not checks:
        return _risk(barrier, "low")
    effect = max((check.effect for check in checks), key=EFFECT_RANK.__getitem__)
    if effect == "none":
        return _risk(barrier, "low", resolved=any(check.within_rule for check in checks))
    worst = [check for check in checks if check.effect == effect]
    why = next((check.explanation for check in worst if check.explanation), "")
    refs = _union(*(check.evidence_refs for check in worst))
    # One short sentence: the check's own, which names the year and the window.
    return _risk(
        barrier, EFFECT_LEVEL[effect], explanation=why or barrier.explanation, cv_refs=refs
    )


def _checks_for(barrier: BarrierItem, recency: dict[str, RecencyCheck]) -> list[RecencyCheck]:
    """The checks of the requirements the barrier names. A general rule has none, so it takes the
    checks that applied its own window."""
    if barrier.requirement_ids:
        return [recency[rid] for rid in barrier.requirement_ids if rid in recency]
    return [
        check
        for check in recency.values()
        if check.rule is not None and check.rule.window_years == barrier.window_years
    ]


def _composite(risks: list[HiddenRisk], tied: set[str]) -> HiddenRisk | None:
    """Two or more open medium risks, none tied to a knockout, make one high composite."""
    open_mediums = [
        risk
        for risk in risks
        if risk.id not in tied and risk.risk == "medium" and not (risk.resolved or risk.confirmed)
    ]
    if len(open_mediums) < 2:
        return None
    return HiddenRisk(
        id="HC1",
        kind="composite",
        risk="high",
        explanation=(
            "Several open barriers here may add up to a silent rejection, even if none rules "
            "you out alone."
        ),
        action="Answer the yes/no questions; this risk goes away when fewer than two stay open.",
        requirement_ids=_union(*(risk.requirement_ids for risk in open_mediums)),
        component_ids=[risk.id for risk in open_mediums],
    )


def _risk(
    barrier: BarrierItem,
    level: RiskLevel,
    *,
    explanation: str | None = None,
    question: str | None = None,
    resolved: bool = False,
    confirmed: bool = False,
    cv_refs: list[str] | None = None,
) -> HiddenRisk:
    return HiddenRisk(
        id=barrier.id,
        kind=barrier.kind,
        quote=barrier.quote,
        explanation=barrier.explanation if explanation is None else explanation,
        action=barrier.action,
        risk=level,
        requirement_ids=list(barrier.requirement_ids),
        question=question,
        resolved=resolved,
        confirmed=confirmed,
        cv_refs=list(cv_refs or []),
    )


def _question(barrier: BarrierItem, job_location: str | None) -> str | None:
    """The barrier's own question, or the default one. Only the eligibility kinds ask."""
    if barrier.kind not in ELIGIBILITY_KINDS:
        return None
    return barrier.question or _default_question(barrier.kind, barrier.place, job_location)


def _question_key(barrier: BarrierItem, job_location: str | None) -> str | None:
    """What a barrier's question is about: its kind and place when it names one, else the
    question's own words. Two barriers with the same key ask one question."""
    question = _question(barrier, job_location)
    if question is None:
        return None
    if barrier.place:
        return f"{barrier.kind}|{_names_for(barrier.place)[0]}"
    return f"{barrier.kind}|{' '.join(re.findall(r'\w+', fold_lower(question)))}"


# 5. Flags: looks met, but... ---------------------------------------------------------------


def screening_flags(
    job: JobPosting,
    original_assessments: dict[str, RequirementAssessment],
    recency: dict[str, RecencyCheck],
    risks: list[HiddenRisk],
) -> list[ScreeningFlag]:
    """Requirements that look met in the CV (original status met or partial, or the keyword is
    there) but carry a recency warning or an open medium or high risk. Each sentence is listed
    once. A recency risk adds no sentence once the requirement's own recency check has spoken;
    every linked risk still counts toward the level and the risk IDs."""
    flags: list[ScreeningFlag] = []
    for req in job.requirements:
        before = original_assessments.get(req.id)
        if before is None or not _looks_met(before):
            continue
        reasons: list[str] = []
        levels: list[RiskLevel] = []
        recency_spoke = False
        check = recency.get(req.id)
        if check is not None and check.effect != "none":
            _add_reason(reasons, check.explanation or "Its dates do not show recent use.")
            levels.append(EFFECT_LEVEL[check.effect])
            recency_spoke = True
        linked = [
            risk
            for risk in risks
            if risk.kind != "composite"
            and req.id in risk.requirement_ids
            and not risk.resolved
            and risk.risk != "low"
        ]
        for risk in linked:
            levels.append(risk.risk)
            if not (risk.kind == "recency" and recency_spoke):
                _add_reason(reasons, risk.explanation)
        if reasons:
            flags.append(
                ScreeningFlag(
                    requirement_id=req.id,
                    risk=min(levels, key=LEVEL_RANK.__getitem__),
                    reasons=reasons,
                    risk_ids=[risk.id for risk in linked],
                )
            )
    return flags


def _looks_met(assessment: RequirementAssessment) -> bool:
    """Met or partial, its keyword is in the CV, or CV lines show it while incomplete dates turned
    its minimum years into a question."""
    if assessment.status in ("met", "partial") or assessment.keyword_present:
        return True
    return (
        assessment.status == "unknown"
        and assessment.years_check is not None
        and any(e.ref.startswith("L") for e in assessment.evidence)
    )


# Shared helpers ----------------------------------------------------------------------------


def _barrier_id(index: int) -> str:
    return f"H{index + 1:02d}"


def _clean(text: str | None) -> str | None:
    value = (text or "").strip()
    return value or None


def _union(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(rid for group in groups for rid in group))


def _overlaps(a: str, b: str) -> bool:
    """Containment either way, after folding and ignoring case. Empty text overlaps nothing."""
    x, y = fold_lower(a), fold_lower(b)
    return bool(x and y) and (x in y or y in x)


def _add_reason(reasons: list[str], sentence: str) -> None:
    """Appends a reason unless it is empty or says a point already listed: a sentence that holds a
    listed reason, or sits inside one, repeats it. Compared folded and ignoring case."""
    new = fold_lower(sentence)
    if not new or any(new in fold_lower(old) or fold_lower(old) in new for old in reasons):
        return
    reasons.append(sentence)


def _names_for(place: str) -> tuple[str, ...]:
    """The names a place goes by: EU covers its member countries; US and UK have short names."""
    key = fold_lower(place).removeprefix("the ")
    if key in _EUROPEAN_UNION:
        return (*_EUROPEAN_UNION, *_EU_MEMBERS)
    return _ALIAS_GROUPS.get(key, (key,))


def _covers(place: str, text: str) -> bool:
    """True when the text names the place or one of its usual names, as a whole word."""
    folded = fold_lower(text)
    return any(contains_term(folded, name) for name in _names_for(place))


def _place_in_text(place: str | None, text: str) -> str | None:
    """The place the model names, kept only when the posting really names it."""
    value = _clean(place)
    return value if value and _covers(value, text) else None


def _the(place: str) -> str:
    """Puts 'the' before the few places that take one: 'the United States', 'the EU'."""
    return f"the {place}" if fold_lower(place) in _THE_PLACES else place


def _complete(item: BarrierItem) -> BarrierItem:
    """Fills an empty explanation or action with the plain default for the item's kind."""
    return item.model_copy(
        update={
            "explanation": item.explanation
            or _default_explanation(item.kind, item.place, item.window_years),
            "action": item.action or ACTIONS.get(item.kind, DEFAULT_ACTION),
        }
    )


def _default_explanation(kind: BarrierKind, place: str | None, window: float | None) -> str:
    """Why a screener may silently reject the candidate, in plain words."""
    match kind:
        case "work_authorization":
            where = f"in {_the(place)}" if place else "here"
            return f"You may be dropped without a reply if you lack the right to work {where}."
        case "location":
            near = f"near {_the(place)}" if place else "where this job is"
            return f"You may be dropped without a reply if you cannot live or work {near}."
        case "recency":
            span = f"the last {window:g} years" if window else "the period it asks for"
            return f"You may be dropped without a reply if your experience is older than {span}."
        case "graduation_window":
            return "You may be dropped without a reply if you graduated outside the asked period."
        case "language":
            return "You may be dropped without a reply if your language level is too low."
        case "clearance":
            return "You may be dropped without a reply if you lack the clearance this job needs."
        case "availability":
            return "You may be dropped without a reply if you cannot meet its schedule or travel."
    return "You may be dropped without a reply on this point, even when your CV matches."


def _default_question(kind: BarrierKind, place: str | None, job_location: str | None) -> str:
    """A yes/no question the candidate can answer, for the eligibility kinds."""
    match kind:
        case "work_authorization":
            where = _the(place) if place else (job_location or "this country")
            return f"Do you already have the right to work in {where} without visa sponsorship?"
        case "location" if place:
            return f"Are you able to work from {_the(place)}, or willing to move there?"
        case "location":
            return "Can you meet this location requirement, or are you willing to relocate?"
        case "graduation_window":
            return "Did you graduate within the period this job asks for?"
        case "language":
            return "Do you meet the language level this job asks for?"
        case "clearance":
            return "Do you hold, or can you get, the clearance this job asks for?"
        case "availability":
            return "Can you meet the start date, shifts or travel this job asks for?"
    return "Do you meet this requirement?"
