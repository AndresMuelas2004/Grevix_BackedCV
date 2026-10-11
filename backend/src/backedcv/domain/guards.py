"""Deterministic checks on suggested CV rewrites. A hard failure makes one unsupported."""

import re
from collections import Counter
from difflib import SequenceMatcher

from backedcv.domain.keywords import contains_term
from backedcv.domain.models import GuardResult, JobPosting, ParsedCV, Suggestion
from backedcv.domain.numbers import extract_numbers
from backedcv.domain.redaction import PLACEHOLDERS
from backedcv.domain.text import fold_lower

NEW_SUMMARY = "new-summary"  # tailor_summary target for a CV that has no summary section yet
NEW_SKILLS = "new-skills"  # add_skill target for a CV that has no skills section yet
# A number, or a word that may have dotted parts ("Node.js"). Commas and hyphens split words.
_TOKEN = re.compile(r"[0-9]+(?:[.,][0-9]+)*|\w[\w+#&]*(?:\.\w[\w+#&]*)*")
_CAMEL = re.compile(r"[a-z][A-Z]|[A-Z]{2}[a-z]")
_BULLETS = " \t•*-–—"
# A capitalized word that starts a sentence is exempt only if it is listed here, or if it ends
# in -ed, -ing or -s and is not in _TECH_LOOKALIKES.
_SENTENCE_STARTERS = frozenset({
    "the", "a", "an", "i", "my", "our", "we", "with", "for", "in", "on", "at", "by", "and",
    "over", "using", "through", "led", "built", "designed", "managed", "developed", "created",
    "improved", "reduced", "increased", "implemented", "worked", "helped", "collaborated",
    "delivered",
})  # fmt: skip
# Technical names ending in -s, -ed or -ing, which the suffix rule would otherwise exempt.
_TECH_LOOKALIKES = frozenset({
    "atlas", "cypress", "databricks", "jenkins", "keras", "kubernetes", "pandas", "postgres",
    "prometheus", "rails", "redis", "spring",
})  # fmt: skip


def _starts_sentence(text: str, index: int) -> bool:
    before = text[:index].rstrip(_BULLETS)
    return not before or before[-1] in ".!?\n"


def _looks_ordinary(token: str) -> bool:
    """An everyday word at the start of a sentence, so it is not checked."""
    word = fold_lower(token)
    if word in _SENTENCE_STARTERS:
        return True
    return word.endswith(("ed", "ing", "s")) and word not in _TECH_LOOKALIKES


def _is_flagged(token: str, starts_sentence: bool) -> bool:
    """Technical-looking tokens always count. Capitalized words count unless they are ordinary."""
    letters = sum(c.isalpha() for c in token)
    if any(c.isdigit() or c in "+#." for c in token) or _CAMEL.search(token):
        return True
    if token.isupper() and letters >= 2:
        return True
    if letters < 2 or not token[0].isupper():
        return False
    return not (starts_sentence and _looks_ordinary(token))


def introduced_terms(after: str, cv: ParsedCV) -> list[str]:
    """Capitalized or technical words in `after` that appear nowhere in the CV. A soft flag."""
    cv_text = "\n".join([line.text for line in cv.lines] + [fact.text for fact in cv.facts])
    first_seen: dict[str, str] = {}  # folded word -> its first spelling in `after`
    for match in _TOKEN.finditer(after):
        token = match.group()
        key = fold_lower(token)
        if key not in first_seen and _is_flagged(token, _starts_sentence(after, match.start())):
            first_seen[key] = token
    return [term for term in first_seen.values() if not contains_term(cv_text, term)]


def covered_requirements(after: str, job: JobPosting) -> list[str]:
    """IDs of the requirements whose posting terms or aliases appear literally in `after`."""
    return [
        req.id
        for req in job.requirements
        if any(contains_term(after, term) for term in [*req.terms, *req.aliases])
    ]


def _target_exists(s: Suggestion, cv: ParsedCV) -> bool:
    if s.kind == "align_wording":
        return s.target in {line.id for line in cv.lines}
    if s.kind == "add_skill":
        return s.target in {section.id for section in cv.sections} | {NEW_SKILLS}
    summaries = {section.id for section in cv.sections if section.type == "summary"}
    return s.target in summaries | {NEW_SUMMARY}


def _ids_exist(s: Suggestion, cv: ParsedCV, job: JobPosting) -> GuardResult:
    refs = cv.texts_by_ref()
    requirements = {req.id for req in job.requirements}
    problems: list[str] = []
    if not _target_exists(s, cv):
        problems.append(f"target {s.target} does not exist")
    unknown_refs = [ref for ref in s.cited_refs if ref not in refs]
    if unknown_refs:
        problems.append(f"unknown cited refs: {', '.join(unknown_refs)}")
    unknown_reqs = [req for req in s.requirement_ids if req not in requirements]
    if unknown_reqs:
        problems.append(f"unknown requirement IDs: {', '.join(unknown_reqs)}")
    return GuardResult(name="ids_exist", ok=not problems, detail="; ".join(problems) or None)


def _cites_evidence(s: Suggestion) -> GuardResult:
    if s.cited_refs:
        return GuardResult(name="cites_evidence", ok=True)
    return GuardResult(name="cites_evidence", ok=False, detail="no L or F line is cited")


def _numbers_backed(s: Suggestion, cv: ParsedCV) -> GuardResult:
    refs = cv.texts_by_ref()
    backed: set[str] = set()
    for ref in s.cited_refs:
        if ref in refs:
            backed |= extract_numbers(refs[ref])
    if s.before:
        backed |= extract_numbers(s.before)
    missing = sorted(extract_numbers(s.after) - backed)
    if not missing:
        return GuardResult(name="numbers_backed", ok=True)
    detail = f"not in the cited lines or the original: {', '.join(missing)}"
    return GuardResult(name="numbers_backed", ok=False, detail=detail)


# What may follow a total's number: its own scope, then the clause must end. Any other word
# ("years of experience building X", "years as a data engineer") ties the total to one role,
# skill or employer, which a total over the whole CV cannot support.
_TOTAL_SCOPE = re.compile(
    r"\+?\s*(?:years?(?:\s+of)?(?:\s+(?:total|professional))*\s+experience"
    r"|years?['’]s?\s+experience)"
    r"(?=\s*(?:[.,;:!?)]|$|overall\b|in\s+total\b))",
    re.IGNORECASE,
)
_TOTAL_MISPLACED = (
    "A computed total ({fact}) covers the whole CV; "
    "it cannot be attached to one role, skill or employer."
)


def _fact_scope(s: Suggestion, cv: ParsedCV) -> GuardResult:
    """Numbers that only computed facts back must keep the facts' scope. Every fact is a total."""
    refs = cv.texts_by_ref()
    fact_ids = {fact.id for fact in cv.facts}
    stated = extract_numbers(s.before) if s.before else set()  # what the original already states
    fact_of: dict[str, str] = {}  # number -> the first cited fact that states it
    for ref in s.cited_refs:
        if ref not in refs:
            continue
        if ref in fact_ids:
            for number in extract_numbers(refs[ref]):
                fact_of.setdefault(number, ref)
        else:
            stated |= extract_numbers(refs[ref])
    misplaced: list[str] = []  # facts whose number is followed by words outside their scope
    for match in _TOKEN.finditer(s.after):
        only_facts = [
            fact_of[n] for n in extract_numbers(match.group()) if n in fact_of and n not in stated
        ]
        if only_facts and _TOTAL_SCOPE.match(s.after, match.end()) is None:
            misplaced += only_facts
    if not misplaced:
        return GuardResult(name="fact_scope", ok=True)
    details = [_TOTAL_MISPLACED.format(fact=fact) for fact in dict.fromkeys(misplaced)]
    return GuardResult(name="fact_scope", ok=False, detail=" ".join(details))


def _no_posting_entities(s: Suggestion, cv: ParsedCV, job: JobPosting) -> GuardResult:
    if s.kind == "tailor_summary":
        return GuardResult(name="no_posting_entities", ok=True)
    entry_texts = [
        text for entry in cv.entries for text in (entry.title, entry.organization) if text
    ]
    leaks: list[str] = []
    for label, name in (("job title", job.title), ("company", job.company)):
        if not name or not contains_term(s.after, name):
            continue
        if not any(contains_term(text, name) for text in entry_texts):
            leaks.append(f"{label} '{name}'")
    if not leaks:
        return GuardResult(name="no_posting_entities", ok=True)
    detail = f"names the posting's {' and '.join(leaks)} outside the CV entries"
    return GuardResult(name="no_posting_entities", ok=False, detail=detail)


def _length(s: Suggestion) -> GuardResult:
    before_words = len(s.before.split()) if s.before else 0
    new_summary = s.kind == "tailor_summary" and s.target == NEW_SUMMARY
    limit = 2 * before_words + (60 if new_summary else 30)
    words = len(s.after.split())
    if words <= limit:
        return GuardResult(name="length", ok=True)
    return GuardResult(name="length", ok=False, detail=f"{words} words, limit is {limit}")


def _no_placeholders(s: Suggestion) -> GuardResult:
    """The model only sees placeholders for contact details, so none may reach the CV."""
    found = [p for p in PLACEHOLDERS if p in s.after.lower()]
    if not found:
        return GuardResult(name="no_placeholders", ok=True)
    detail = f"contains a placeholder that must not reach the CV: {', '.join(found)}"
    return GuardResult(name="no_placeholders", ok=False, detail=detail)


def run_guards(s: Suggestion, cv: ParsedCV, job: JobPosting) -> list[GuardResult]:
    """Every deterministic check on one suggestion, in a fixed order. The last one is soft."""
    terms = introduced_terms(s.after, cv)
    return [
        _ids_exist(s, cv, job),
        _cites_evidence(s),
        _numbers_backed(s, cv),
        _fact_scope(s, cv),
        _no_posting_entities(s, cv, job),
        _length(s),
        _no_placeholders(s),
        GuardResult(name="introduced_terms", ok=True, hard=False, detail=", ".join(terms) or None),
    ]


def _original(s: Suggestion, cv: ParsedCV) -> str | None:
    """The text a suggestion replaces, read from the CV so that a generator cannot fake it."""
    if s.kind == "align_wording":
        return next((line.text for line in cv.lines if line.id == s.target), s.before)
    if s.kind == "add_skill" or s.target == NEW_SUMMARY:
        return None  # an added line, or a new summary, replaces nothing
    summary = next(
        (sec for sec in cv.sections if sec.id == s.target and sec.type == "summary"), None
    )
    if summary is None:
        return s.before
    return " ".join(line.text for line in cv.lines if line.id in summary.line_ids)


# Words that show nothing on their own: function words (English and Spanish), the adjectives and
# umbrella nouns a rewrite adds to sound closer to a posting, and generic action verbs whose swap
# does not change what a line shows. Hyphenated words split, so "cutting-edge" is two words.
_FILLER = frozenset({
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "with", "by", "from",
    "as", "into", "across", "via", "using", "through", "including", "include", "includes",
    "such", "like", "e.g", "i.e", "etc", "also", "both", "plus", "while", "within", "per", "its",
    "their", "our", "my", "this", "that", "these", "those", "which", "who", "other", "related",
    "based", "around", "various", "multiple", "several", "key", "core", "wide", "range",
    "de", "del", "la", "el", "los", "las", "y", "e", "o", "u", "en", "con", "para", "por", "al",
    "un", "una", "como", "incluyendo", "entre", "mediante", "su", "sus",
    "strong", "solid", "proven", "extensive", "deep", "hands", "robust", "scalable", "reliable",
    "efficient", "effective", "successful", "successfully", "seamless", "seamlessly",
    "innovative", "cutting", "edge", "modern", "advanced", "comprehensive", "complex", "dynamic",
    "diverse", "high", "quality", "impactful", "strategic", "best", "leading", "powered",
    "driven", "native", "enabled", "focused", "oriented", "centric", "critical", "cross",
    "functional", "end", "large", "scale", "production", "grade", "ready", "enterprise",
    "solution", "solutions", "system", "systems", "application", "applications", "technology",
    "technologies", "tool", "tools", "tooling", "capability", "capabilities", "initiative",
    "initiatives", "platform", "platforms", "soluciones", "solución", "sistemas", "herramientas",
    "built", "build", "builds", "building", "developed", "develop", "develops", "developing",
    "created", "create", "creates", "creating", "implemented", "implement", "implements",
    "implementing", "wrote", "write", "writes", "writing", "written", "made", "make", "makes",
    "making", "worked", "work", "works", "working", "used", "use", "uses", "leveraged",
    "leverage", "leverages", "leveraging", "utilized", "utilize", "utilizes", "utilizing", "set",
    "sets", "setting", "up", "engineered",
})  # fmt: skip


def _words(text: str) -> list[tuple[str, str]]:
    """The words of a text in order, as (folded, as written) pairs."""
    return [(fold_lower(m.group()), m.group()) for m in _TOKEN.finditer(text)]


def _posting_words(job: JobPosting) -> set[str]:
    """Every word of the posting's terms, aliases and job title."""
    names = [name for req in job.requirements for name in (*req.terms, *req.aliases)]
    return {key for name in [*names, job.title or ""] for key, _ in _words(name)}


def _names_what_the_line_has(before: str, after: str, job: JobPosting) -> bool:
    """True when the rewrite adds a requirement's name next to another of its names that the line
    already has: "K8s" becoming "Kubernetes (K8s)" names the tool, it does not pad the line."""
    for req in job.requirements:
        names = [*req.terms, *req.aliases]
        if any(contains_term(before, name) for name in names) and any(
            contains_term(after, name) and not contains_term(before, name) for name in names
        ):
            return True
    return False


def _content(words: list[str]) -> Counter[str]:
    return Counter(word for word in words if word not in _FILLER)


def keyword_only(s: Suggestion, job: JobPosting) -> str | None:
    """Why a rewrite of an existing line or summary only pads it, or None when it changes it.

    Padding keeps every word of the original, apart from filler, and adds only posting words or
    filler: "observability" becoming "AI observability". A real change removes or replaces a word,
    adds a number or any other word, or reorders the line (three or more words, or a number, move);
    moving one or two words to make room for a posting term is still padding. `before` must
    already hold the original (apply_guards fills it).
    """
    if s.kind == "add_skill" or not s.before:
        return None
    before, after = _words(s.before), _words(s.after)
    matcher = SequenceMatcher(None, [k for k, _ in before], [k for k, _ in after], autojunk=False)
    removed: list[str] = []
    added: list[str] = []
    spans: list[str] = []  # the added text as written, for the reason
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            removed += [key for key, _ in before[i1:i2]]
            added += [key for key, _ in after[j1:j2]]
            spans.append(" ".join(word for _, word in after[j1:j2]))
    moved = _content(removed) & _content(added)
    if _content(removed) - moved:
        return None  # a word of the original is gone or replaced
    if moved.total() >= 3 or any(extract_numbers(word) for word in moved):
        return None  # the line is reordered, not padded
    posting = _posting_words(job)
    for key in (_content(added) - moved).elements():
        if extract_numbers(key) or key not in posting:
            return None
    if _names_what_the_line_has(s.before, s.after, job):
        return None
    shown = ", ".join(dict.fromkeys(span for span in spans if span))
    if not shown:
        return "Changes nothing that matters in the line."
    return f"Only adds the posting's words or filler ({shown}); nothing else changes."


def apply_guards(s: Suggestion, cv: ParsedCV, job: JobPosting) -> Suggestion:
    """A copy of the suggestion with the original text, soft flags and guard results filled in."""
    filled = s.model_copy(update={"before": _original(s, cv)})
    guards = run_guards(filled, cv, job)
    failed = next((g for g in guards if g.hard and not g.ok), None)
    verification = s.verification.model_copy(
        update={
            "status": "unsupported" if failed else "pending",
            "reason": failed.detail if failed else None,
            "guards": guards,
        }
    )
    return filled.model_copy(
        update={
            "introduced_terms": introduced_terms(s.after, cv),
            "covers_requirement_ids": covered_requirements(s.after, job),
            "verification": verification,
        }
    )
