"""The Fit score does not change when one posting bullet is split into several requirements."""

from backedcv.domain.models import Requirement, RequirementAssessment
from backedcv.domain.scoring import compute_score


def _req(rid, unit, category="hard_skill", importance="required", label=None):
    return Requirement(
        id=rid,
        label=label or rid,
        quote=f"quote of {unit}",
        terms=[label or rid],
        category=category,
        importance=importance,
        source_unit=unit,
    )


def _status(*pairs):
    return {
        rid: RequirementAssessment(
            requirement_id=rid, status=status, keyword_present=status == "met"
        )
        for rid, status in pairs
    }


BASE = [
    _req("R10", "U02", "education"),
    _req("R11", "U03", "soft_skill"),
    _req("R12", "U04", importance="preferred"),
]
BASE_STATUS = [("R10", "met"), ("R11", "missing"), ("R12", "partial")]


def test_one_bullet_split_into_three_met_requirements_gives_the_same_fit():
    whole = compute_score([_req("R01", "U01"), *BASE], _status(("R01", "met"), *BASE_STATUS))
    split = compute_score(
        [_req("R01", "U01"), _req("R02", "U01"), _req("R03", "U01"), *BASE],
        _status(("R01", "met"), ("R02", "met"), ("R03", "met"), *BASE_STATUS),
    )
    assert split.fit == whole.fit
    assert split.coverage == whole.coverage


def test_a_split_with_mixed_statuses_scores_like_the_bullet_half_met():
    whole = compute_score([_req("R01", "U01"), *BASE], _status(("R01", "partial"), *BASE_STATUS))
    split = compute_score(
        [_req("R01", "U01"), _req("R02", "U01"), *BASE],
        _status(("R01", "met"), ("R02", "missing"), *BASE_STATUS),
    )
    assert split.fit == whole.fit


def test_without_shared_units_a_split_used_to_move_the_score():
    """Requirements with no unit each weigh on their own."""
    reqs = [_req(rid, None) for rid in ("R01", "R02", "R03")] + [_req("R10", None, "education")]
    score = compute_score(reqs, _status(("R01", "met"), ("R02", "met"), ("R03", "met")))
    assert score.fit == round(100 * 18 / 22, 1)


def test_a_unit_weighs_as_its_heaviest_counted_requirement():
    reqs = [_req("R01", "U01", "soft_skill"), _req("R02", "U01"), _req("R03", "U02", "education")]
    score = compute_score(reqs, _status(("R01", "met"), ("R02", "met"), ("R03", "missing")))
    weights = {c.requirement_id: c.weight for c in score.contributions}
    assert weights == {"R01": 3.0, "R02": 3.0, "R03": 4.0}  # the unit weighs 6 (hard skill)
    assert score.fit == 60.0


def test_an_excluded_requirement_leaves_its_unit_to_the_others():
    reqs = [_req("R01", "U01"), _req("R02", "U01"), _req("R03", "U02", "education")]
    statuses = _status(("R01", "met"), ("R02", "missing"), ("R03", "missing"))
    score = compute_score(reqs, statuses, excluded_ids={"R02"})
    weights = {c.requirement_id: c.weight for c in score.contributions}
    assert weights["R01"] == 6.0
    assert score.fit == 60.0


def test_points_still_add_up_to_the_fit():
    reqs = [_req("R01", "U01"), _req("R02", "U01"), _req("R03", "U01"), *BASE]
    score = compute_score(reqs, _status(("R01", "met"), ("R02", "partial"), *BASE_STATUS))
    assert abs(sum(c.points_won for c in score.contributions) - score.fit) <= 0.2
    assert abs(sum(c.points_won + c.points_lost for c in score.contributions) - 100) <= 0.2
