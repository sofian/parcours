from pathlib import Path

from parcours.core.schema import load_category_schema
from parcours.core.translations import load_translations
from parcours.core.vocab import load_vocab

_STARTER_DIR = Path(__file__).parent.parent.parent / "parcours" / "starter_config"
_CATEGORIES_DIR = _STARTER_DIR / "categories"

_EXPECTED_CATEGORIES = {
    "publications", "review", "catalog", "grants", "artworks", "students",
    "teaching", "service", "outreach", "presentations", "press", "education",
    "positions", "recognitions", "exhibitions", "curatorship", "residencies",
    "software", "skills",
}


def test_starter_categories_directory_has_exactly_the_19_expected_files():
    names = {p.stem for p in _CATEGORIES_DIR.glob("*.yaml")}
    assert names == _EXPECTED_CATEGORIES


def test_every_starter_category_loads_and_matches_its_filename():
    for path in _CATEGORIES_DIR.glob("*.yaml"):
        schema = load_category_schema(path)
        assert schema.name == path.stem


def test_every_vocab_reference_across_starter_categories_exists_in_starter_vocab():
    vocab = load_vocab(_STARTER_DIR / "vocab.yaml")
    for path in _CATEGORIES_DIR.glob("*.yaml"):
        schema = load_category_schema(path)
        for field in schema.fields:
            if field.vocab:
                assert field.vocab in vocab, (
                    f"{schema.name}.{field.name} references vocab '{field.vocab}', "
                    f"not found in starter vocab.yaml"
                )


def test_starter_vocab_has_the_expected_lists():
    vocab = load_vocab(_STARTER_DIR / "vocab.yaml")
    assert vocab["publication_status"] == ["submitted", "under-review", "accepted", "in-press", "published"]
    assert vocab["degree_type"] == ["bachelors", "bachelors-honours", "masters", "doctorate", "postdoc"]
    assert vocab["degree_status"] == ["completed", "in-progress", "withdrawn", "all-but-degree"]
    assert vocab["skill_category"] == [
        "expertise", "programming", "framework", "platform", "software", "spoken-language", "other",
    ]
    assert vocab["presentation_format"] == [
        "talk", "panel", "round-table", "workshop", "poster", "special-session",
    ]


def test_degree_type_and_degree_status_are_shared_between_students_and_education():
    students = load_category_schema(_CATEGORIES_DIR / "students.yaml")
    education = load_category_schema(_CATEGORIES_DIR / "education.yaml")
    assert students.get_field("degree_type").vocab == education.get_field("degree_type").vocab
    assert students.get_field("degree_status").vocab == education.get_field("degree_status").vocab


def test_starter_translations_has_exactly_the_18_non_skills_section_rows():
    table = load_translations(_STARTER_DIR / "translations.csv")
    entries = [e for e in table.all() if e.category == "section"]
    assert len(entries) == 18
    assert {e.id for e in entries} == _EXPECTED_CATEGORIES - {"skills"}


def test_starter_translations_has_195_pre_populated_country_rows_plus_official_aliases():
    table = load_translations(_STARTER_DIR / "translations.csv")
    entries = [e for e in table.all() if e.category == "country"]
    assert len(entries) == 209
    assert table.lookup("country", "France", "fr") == "France"
    assert table.lookup("country", "Canada", "fr") == "Canada"
    # Official ISO long-form names some data sources (e.g. CCV) use in place
    # of the common short form we key most rows on.
    assert table.lookup("country", "United States of America", "en") == "United States"
    assert table.lookup("country", "South Africa, Republic of", "en") == "South Africa"
    # Common acronyms people actually type.
    assert table.lookup("country", "USA", "fr") == "États-Unis"
    assert table.lookup("country", "UK", "en") == "United Kingdom"
    assert table.lookup("country", "UAE", "en") == "United Arab Emirates"


def test_starter_translations_has_no_missing_translations():
    table = load_translations(_STARTER_DIR / "translations.csv")
    assert table.missing_translations() == []


def test_starter_translations_grants_row_matches_the_agreed_wording():
    table = load_translations(_STARTER_DIR / "translations.csv")
    assert table.lookup("section", "grants", "en") == "Grants"
    assert table.lookup("section", "grants", "fr") == "Subventions"


def test_artwork_status_values_have_en_fr_labels_and_waive_the_date():
    vocab = load_vocab(_STARTER_DIR / "vocab.yaml")
    table = load_translations(_STARTER_DIR / "translations.csv")
    for value in vocab["artwork_status"]:
        assert table.lookup("artwork_status", value, "en")
        assert table.lookup("artwork_status", value, "fr")
    assert table.lookup("artwork_status", "in-progress", "fr") == "en cours"

    date_field = load_category_schema(_CATEGORIES_DIR / "artworks.yaml").get_field("date")
    assert date_field.is_required({"status": "in-progress"}) is False
    assert date_field.is_required({"status": ""}) is True


def test_grants_title_is_optional_and_dates_accept_a_bare_year():
    # Some grants (travel or operating support) have no title of their own,
    # and older ones are only known to the year.
    schema = load_category_schema(_CATEGORIES_DIR / "grants.yaml")
    assert not any("title_en" in group for group in schema.require_one_of)
    by_name = {f.name: f for f in schema.fields}
    assert by_name["start_date"].precision == "year"
    assert by_name["end_date"].precision == "year"


def test_grant_role_has_co_applicant_and_every_value_is_translated():
    # Art grants often have equal co-applicants rather than a PI.
    vocab = load_vocab(_STARTER_DIR / "vocab.yaml")
    table = load_translations(_STARTER_DIR / "translations.csv")
    assert "co-applicant" in vocab["grant_role"]
    for value in vocab["grant_role"]:
        assert table.lookup("grant_role", value, "en")
        assert table.lookup("grant_role", value, "fr")
    assert table.lookup("grant_role", "co-applicant", "fr") == "Cocandidat.e"

    role_field = load_category_schema(_CATEGORIES_DIR / "grants.yaml").get_field("role")
    assert role_field.glossary == "grant_role"
