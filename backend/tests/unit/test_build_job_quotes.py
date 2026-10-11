from backedcv.domain.builders import build_job
from tests.fakes import _req, job_draft


def test_a_quote_copied_with_its_bullet_keeps_only_the_sentence():
    posting = (
        "Requirements\n- 3+ years of hands-on Kubernetes experience within the last 5 years.\n"
    )
    draft = job_draft().model_copy(
        update={
            "requirements": [
                _req(
                    "- 3+ years of hands-on Kubernetes experience within the last 5 years.",
                    ["Kubernetes"],
                    "Kubernetes experience",
                    "experience_years",
                    knockout_type="experience_years",
                    min_years=3,
                )
            ]
        }
    )

    job, _ = build_job(posting, draft)

    assert job.requirements[0].quote == (
        "3+ years of hands-on Kubernetes experience within the last 5 years."
    )
    assert job.requirements[0].quote_located
