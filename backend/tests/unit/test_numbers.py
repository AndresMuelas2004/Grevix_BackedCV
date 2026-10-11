import pytest

from backedcv.domain.numbers import extract_numbers


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Cut costs by 40%", {"40"}),
        ("Cut costs by 40 percent", {"40"}),
        ("Cut costs by 40 por ciento", {"40"}),
        ("Saved 1,200 hours", {"1200"}),
        ("Atendí 1.200 clientes", {"1200"}),
        ("Shipped 1,000,000 rows", {"1000000"}),
        ("Revenue 1.200,50 EUR", {"1200.5"}),
        ("GPA 1.5", {"1.5"}),
        ("GPA 1,5", {"1.5"}),
        ("Ratio 1.25", {"1.25"}),
        ("GPA 3.0", {"3"}),
        ("Led five engineers", {"5"}),
        ("Lideré cinco equipos", {"5"}),
        ("Mentored twenty interns", {"20"}),
        ("Gestioné veinte proyectos", {"20"}),
        ("Hablo dos idiomas", {"2"}),
        ("Reduced incidents to zero", {"0"}),
        ("Cero incidencias", {"0"}),
        ("Worked since 2019", {"2019"}),
        ("Built S3 and EC2 pipelines", set()),
        ("Python3 scripts", set()),
        ("someone, often, stone", set()),
        ("One of the teams", set()),  # "one" is a pronoun here, not a quantity
        ("Lideré una migración", set()),  # "una" is an article here
        ("Un equipo", set()),
    ],
)
def test_extract_numbers(text, expected):
    assert extract_numbers(text) == expected


def test_separators_do_not_change_the_number():
    assert extract_numbers("1,200") == extract_numbers("1.200") == {"1200"}
