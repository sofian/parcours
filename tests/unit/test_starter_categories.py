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


def test_degree_type_and_degree_status_are_shared_between_students_and_education():
    students = load_category_schema(_CATEGORIES_DIR / "students.yaml")
    education = load_category_schema(_CATEGORIES_DIR / "education.yaml")
    assert students.get_field("degree_type").vocab == education.get_field("degree_type").vocab
    assert students.get_field("degree_status").vocab == education.get_field("degree_status").vocab


def test_starter_translations_has_exactly_the_18_non_skills_section_rows():
    table = load_translations(_STARTER_DIR / "translations.csv")
    entries = table.all()
    assert len(entries) == 18
    assert {e.id for e in entries} == _EXPECTED_CATEGORIES - {"skills"}
    assert all(e.category == "section" for e in entries)


def test_starter_translations_has_no_missing_translations():
    table = load_translations(_STARTER_DIR / "translations.csv")
    assert table.missing_translations() == []


def test_starter_translations_grants_row_matches_the_agreed_wording():
    table = load_translations(_STARTER_DIR / "translations.csv")
    assert table.lookup("section", "grants", "en") == "Grants"
    assert table.lookup("section", "grants", "fr") == "Subventions"
