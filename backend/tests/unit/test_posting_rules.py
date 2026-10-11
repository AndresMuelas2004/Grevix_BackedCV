from backedcv.domain.models import JobPosting, Requirement
from backedcv.domain.rules.posting import tool_sprawl_banner


def req(rid, label, category="hard_skill"):
    return Requirement(
        id=rid,
        label=label,
        quote=f"Experience with {label}",
        terms=[label],
        category=category,
        importance="required",
    )


def job(*labels):
    return JobPosting(requirements=[req(f"R{i:02d}", label) for i, label in enumerate(labels, 1)])


def test_sprawling_posting_gets_an_r3_banner():
    posting = job(
        "React",
        "TypeScript",
        "Django",
        "PostgreSQL",
        "Redis",
        "Docker",
        "Kubernetes",
        "AWS",
        "Terraform",
        "Selenium",
        "Figma",
        "Salesforce",
        "Kafka",
    )

    banner = tool_sprawl_banner(posting)

    assert banner is not None
    assert banner.rule_id == "R3"
    assert banner.severity == "info"
    assert banner.requirement_ids == [r.id for r in posting.requirements]
    assert "13 hard skills across 8 areas" in banner.explanation


def test_focused_posting_in_two_domains_gets_no_banner():
    posting = job(
        "React",
        "TypeScript",
        "Next.js",
        "Tailwind CSS",
        "Redux",
        "CSS",
        "Node.js",
        "Express.js",
        "Django",
        "Java",
        "Spring Boot",
        "REST API",
    )

    assert tool_sprawl_banner(posting) is None


def test_ten_or_fewer_hard_skills_never_trigger():
    posting = job(
        "React",
        "TypeScript",
        "Django",
        "PostgreSQL",
        "Redis",
        "Docker",
        "Kubernetes",
        "AWS",
        "Terraform",
        "Selenium",
    )
    posting.requirements.append(req("R11", "Teamwork", category="soft_skill"))

    assert tool_sprawl_banner(posting) is None


def test_eleven_hard_skills_across_four_domains_is_enough():
    posting = job(
        "React",
        "TypeScript",
        "Redux",
        "Django",
        "Flask",
        "PostgreSQL",
        "Redis",
        "Docker",
        "Kubernetes",
        "AWS",
        "Terraform",
    )

    assert tool_sprawl_banner(posting) is not None
