from datetime import date

from backedcv.domain.corroboration import (
    apply_pass,
    backed_pass,
    barrier_pass,
    not_viable_targets,
    recency_pass,
    refusals_from,
    requirement_risk,
)
from backedcv.domain.models import (
    GatePass,
    HiddenRisk,
    JobPosting,
    RecencyCheck,
    RecencyRule,
    Refusal,
    Requirement,
    RequirementAssessment,
    Suggestion,
    Verification,
)

TODAY = date(2026, 10, 11)
FIVE_YEARS = RecencyRule(quote="in the last 5 years", window_years=5, requirement_ids=["R03"])


def req(rid, label):
    return Requirement(
        id=rid, label=label, quote=label, category="hard_skill", importance="required"
    )


def met(rid, status="met"):
    return RequirementAssessment(requirement_id=rid, status=status)


def risk(kind="location", level="high", reqs=("R03",), rid="H01", **kw):
    kw.setdefault("explanation", "A screener may reject this silently.")
    return HiddenRisk(id=rid, kind=kind, risk=level, requirement_ids=list(reqs), **kw)


def check(rule=None, *, effect="none", last_used=None, evidence=("L010",)):
    return RecencyCheck(
        requirement_id="R03",
        original_status="met",
        last_used=last_used,
        band="stale" if effect == "downgraded" else "recent",
        evidence_refs=list(evidence),
        rule=rule,
        effect=effect,
        explanation="Kubernetes is only shown by old experience.",
    )


def suggestion(
    sid="S01",
    *,
    status="verified",
    target="L010",
    reqs=("R03",),
    covers=(),
    cited=("L010",),
    passes=(),
    reason=None,
):
    return Suggestion(
        id=sid,
        kind="align_wording",
        target=target,
        before="Old wording",
        after="New wording",
        requirement_ids=list(reqs),
        covers_requirement_ids=list(covers),
        cited_refs=list(cited),
        verification=Verification(status=status, reason=reason, passes=list(passes)),
    )


def test_requirement_risk_takes_the_highest_unresolved_level():
    assert requirement_risk("R03", []) is None
    assert requirement_risk("R03", [risk(level="low")]) == "low"
    assert requirement_risk("R03", [risk(level="medium")]) == "medium"
    two_mediums = [risk(level="medium"), risk(level="medium", rid="H02")]
    assert requirement_risk("R03", two_mediums) == "high"
    assert requirement_risk("R03", [risk(level="low"), risk(level="high", rid="H02")]) == "high"
    assert requirement_risk("R03", [risk(resolved=True)]) is None
    assert requirement_risk("R03", [risk(reqs=("R04",))]) is None


def test_a_stale_requirement_is_refused_before_any_edit_is_generated():
    job = JobPosting(requirements=[req("R03", "Kubernetes")])
    recency = {
        "R03": check(FIVE_YEARS, effect="downgraded", last_used="2015-06"),
    }
    assessments = {"R03": met("R03", "missing")}

    refusals = not_viable_targets(job, assessments, recency, [], excluded=[])

    assert refusals == [
        Refusal(
            requirement_id="R03",
            gate="recent_enough",
            reason="Not viable: Kubernetes was last used in 2015, outside the last 5 years.",
            refs=["L010"],
        )
    ]
    assert not_viable_targets(job, assessments, recency, [], excluded=["R03"]) == []


def test_a_met_requirement_under_an_eligibility_barrier_is_refused():
    job = JobPosting(
        requirements=[req("R03", "Kubernetes"), req("R04", "Python"), req("R05", "Docker")]
    )
    assessments = {"R03": met("R03"), "R04": met("R04"), "R05": met("R05")}
    permit = risk("work_authorization", reqs=("R03",), rid="H01", confirmed=True, cv_refs=["L001"])
    other_kind = risk("other", reqs=("R04",), rid="H02")

    refusals = not_viable_targets(job, assessments, {}, [permit, other_kind], excluded=[])

    assert [(r.requirement_id, r.gate, r.refs) for r in refusals] == [
        ("R03", "not_blocked", ["L001"])
    ]
    assert refusals[0].reason == (
        "Not viable: A screener may reject this silently. A CV edit cannot fix this."
    )


def test_composites_and_two_medium_eligibility_risks_block_their_requirements():
    job = JobPosting(requirements=[req("R03", "Kubernetes"), req("R04", "Python")])
    assessments = {"R03": met("R03"), "R04": met("R04")}
    composite = [risk(kind="composite", rid="HC1", reqs=("R03", "R04"))]
    two_mediums = [
        risk("location", level="medium", rid="H01"),
        risk("language", level="medium", rid="H02"),
    ]
    mixed_kinds = [
        risk("location", level="medium", rid="H01"),
        risk("other", level="medium", rid="H02"),
    ]

    def refused(risks):
        return [r.requirement_id for r in not_viable_targets(job, assessments, {}, risks, [])]

    assert refused(composite) == ["R03", "R04"]
    assert refused(two_mediums) == ["R03"]
    assert refused(mixed_kinds) == []


def test_pass_one_follows_the_verifier():
    assert backed_pass(suggestion()).ok
    assert backed_pass(suggestion(status="refused")).ok
    failed = backed_pass(suggestion(status="unsupported", reason="numbers not in the lines"))
    assert (failed.ok, failed.detail) == (False, "numbers not in the lines")


def test_a_recency_rule_needs_a_cited_line_inside_its_window():
    rules = {"R03": check(FIVE_YEARS)}

    old = recency_pass(suggestion(), rules, {"L010": "2015-06"}, TODAY)
    assert (old.ok, old.hard) == (False, True)
    assert old.detail == "Not viable: none of the cited lines shows use within the last 5 years."
    assert recency_pass(suggestion(), rules, {"L010": "2024-03"}, TODAY).ok
    target_line = suggestion(target="L011", cited=("L010",))
    assert recency_pass(target_line, rules, {"L010": "2015-06", "L011": "2025-01"}, TODAY).ok
    assert not recency_pass(suggestion(), rules, {}, TODAY).ok  # undated evidence does not count
    covered = suggestion(reqs=("R01",), covers=("R03",))
    assert not recency_pass(covered, rules, {"L010": "2015-06"}, TODAY).ok


def test_without_a_rule_only_fully_stale_evidence_gets_a_note():
    stale = recency_pass(suggestion(), {}, {"L010": "2015-06"}, TODAY)
    assert (stale.ok, stale.hard) == (True, False)
    assert stale.detail == "All cited lines were last used more than 6 years ago."

    mixed = suggestion(cited=("L010", "L002"))
    fresh_too = recency_pass(mixed, {}, {"L010": "2015-06", "L002": "2024-03"}, TODAY)
    assert (fresh_too.ok, fresh_too.detail) == (True, None)
    assert recency_pass(suggestion(), {}, {}, TODAY).detail is None


def test_pass_three_refuses_a_target_under_an_eligibility_barrier():
    blocked = barrier_pass(suggestion(), [risk("location")])
    assert (blocked.ok, blocked.hard) == (False, True)
    assert blocked.detail == (
        "Not viable: A screener may reject this silently. A CV edit cannot fix this."
    )

    assert barrier_pass(suggestion(), [risk("other")]).ok
    assert barrier_pass(suggestion(), [risk("location", resolved=True)]).ok
    composite = [risk(kind="composite", rid="HC1", reqs=("R04",))]
    assert not barrier_pass(suggestion(covers=("R04",)), composite).ok


def test_an_open_question_turns_the_advice_into_an_instruction():
    asked = risk("location", question="Can you work on site in Madrid?")
    job = JobPosting(requirements=[req("R03", "Kubernetes")])
    reason = (
        "Not viable: A screener may reject this silently. "
        "A CV edit cannot fix this; answer the question instead."
    )

    assert barrier_pass(suggestion(), [asked]).detail == reason
    refusals = not_viable_targets(job, {"R03": met("R03")}, {}, [asked], excluded=[])
    assert [r.reason for r in refusals] == [reason]


def test_a_barrier_refusal_is_written_from_the_risk_and_never_from_an_id():
    named = barrier_pass(suggestion(), [risk("location", explanation="Only US applicants.")])
    assert named.detail == "Not viable: Only US applicants. A CV edit cannot fix this."

    blank = barrier_pass(suggestion(), [risk("location", explanation="")])
    assert blank.detail == (
        "Not viable: a hidden barrier in the posting rules this out. A CV edit cannot fix this."
    )


def test_a_hard_failure_refuses_a_verified_edit_and_keeps_the_pass_trail():
    original = suggestion()
    stale = GatePass(name="recent_enough", ok=False, detail="Not viable: old.")

    refused = apply_pass(original, stale)

    assert (refused.verification.status, refused.verification.reason) == (
        "refused",
        "Not viable: old.",
    )
    assert refused.verification.passes == [stale]
    assert (original.verification.status, original.verification.passes) == ("verified", [])

    after = apply_pass(refused, GatePass(name="not_blocked", ok=True))
    assert [p.name for p in after.verification.passes] == ["recent_enough", "not_blocked"]
    assert after.verification.status == "refused"


def test_soft_notes_and_unverified_edits_are_never_refused():
    note = GatePass(name="recent_enough", ok=True, hard=False, detail="Old.")
    assert apply_pass(suggestion(), note).verification.status == "verified"

    failed = GatePass(name="not_blocked", ok=False, detail="Not viable: blocked.")
    unsupported = apply_pass(suggestion(status="unsupported"), failed)
    assert unsupported.verification.status == "unsupported"


def test_rerunning_a_pass_replaces_its_earlier_result():
    stale = GatePass(name="recent_enough", ok=False, detail="Not viable: old.")
    once = apply_pass(suggestion(), stale)
    assert apply_pass(once, stale) == once

    newer = GatePass(name="recent_enough", ok=False, detail="Not viable: new.")
    rerun = apply_pass(once, newer)
    assert [p.name for p in rerun.verification.passes] == ["recent_enough"]
    assert (rerun.verification.status, rerun.verification.reason) == ("refused", "Not viable: new.")


def test_a_rerun_pass_that_now_succeeds_restores_a_refused_edit():
    refused = apply_pass(
        suggestion(), GatePass(name="recent_enough", ok=False, detail="Not viable: old.")
    )

    restored = apply_pass(refused, GatePass(name="recent_enough", ok=True))

    assert (restored.verification.status, restored.verification.reason) == ("verified", None)
    assert [p.name for p in restored.verification.passes] == ["recent_enough"]


def test_a_refusal_by_another_pass_survives_a_rerun_that_now_succeeds():
    refused = apply_pass(
        suggestion(), GatePass(name="recent_enough", ok=False, detail="Not viable: old.")
    )
    refused = apply_pass(
        refused, GatePass(name="not_blocked", ok=False, detail="Not viable: blocked.")
    )

    rerun = apply_pass(refused, GatePass(name="recent_enough", ok=True))

    assert (rerun.verification.status, rerun.verification.reason) == (
        "refused",
        "Not viable: blocked.",
    )


def test_passes_keep_their_order_whatever_order_they_ran_in():
    backed = GatePass(name="backed", ok=True)
    recent = GatePass(name="recent_enough", ok=False, detail="Not viable: old.")
    blocked = GatePass(name="not_blocked", ok=False, detail="Not viable: blocked.")

    forward = suggestion()
    for p in (backed, recent, blocked):
        forward = apply_pass(forward, p)
    backward = suggestion()
    for p in (blocked, recent, backed):
        backward = apply_pass(backward, p)

    names = [p.name for p in backward.verification.passes]
    assert names == ["backed", "recent_enough", "not_blocked"]
    assert backward.verification == forward.verification
    assert backward.verification.reason == "Not viable: old."


def test_an_unverified_edit_only_records_its_passes_once():
    failed = GatePass(name="not_blocked", ok=False, detail="Not viable: blocked.")
    unsupported = suggestion(status="unsupported", reason="numbers not in the lines")

    once = apply_pass(unsupported, failed)
    twice = apply_pass(once, failed)

    assert twice == once
    assert (twice.verification.status, twice.verification.reason) == (
        "unsupported",
        "numbers not in the lines",
    )
    assert len(twice.verification.passes) == 1


def test_refusals_come_only_from_refused_suggestions():
    stale = apply_pass(
        suggestion(sid="S01", cited=("L010",)),
        GatePass(name="recent_enough", ok=False, detail="Not viable: old."),
    )
    blocked = apply_pass(
        suggestion(sid="S02", reqs=("R04",), cited=("L011",)),
        GatePass(name="not_blocked", ok=False, detail="Not viable: blocked."),
    )

    assert refusals_from([stale, suggestion(sid="S03"), blocked]) == [
        Refusal(
            requirement_id="R03",
            gate="recent_enough",
            reason="Not viable: old.",
            refs=["L010"],
            suggestion_id="S01",
        ),
        Refusal(
            requirement_id="R04",
            gate="not_blocked",
            reason="Not viable: blocked.",
            refs=["L011"],
            suggestion_id="S02",
        ),
    ]
