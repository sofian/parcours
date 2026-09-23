# tests/unit/test_starter_views.py
from pathlib import Path

from parcours.core.views import load_views

_STARTER_VIEWS_PATH = Path(__file__).parent.parent.parent / "starter_config" / "views.yaml"

_EXPECTED_ENTRY_TYPES = {
    "publications": "PublicationEntry",
    "review": "PublicationEntry",
    "catalog": "PublicationEntry",
    "grants": "NormalEntry",
    "artworks": "NormalEntry",
    "students": "NormalEntry",
    "teaching": "ExperienceEntry",
    "service": "ExperienceEntry",
    "outreach": "ExperienceEntry",
    "presentations": "NormalEntry",
    "press": "NormalEntry",
    "education": "EducationEntry",
    "positions": "ExperienceEntry",
    "recognitions": "NormalEntry",
    "exhibitions": "NormalEntry",
    "curatorship": "NormalEntry",
    "residencies": "NormalEntry",
    "software": "NormalEntry",
}


def test_starter_views_covers_every_non_skills_category():
    views = load_views(_STARTER_VIEWS_PATH)
    assert set(views.keys()) == set(_EXPECTED_ENTRY_TYPES.keys())


def test_starter_views_use_the_documented_entry_type_per_category():
    views = load_views(_STARTER_VIEWS_PATH)
    for category_name, expected_entry_type in _EXPECTED_ENTRY_TYPES.items():
        assert views[category_name].entry_type == expected_entry_type, category_name


def test_starter_views_source_matches_the_view_name_for_every_category():
    views = load_views(_STARTER_VIEWS_PATH)
    for category_name, view in views.items():
        assert view.source == category_name


def test_zotero_backed_views_reference_only_zotero_fields():
    views = load_views(_STARTER_VIEWS_PATH)
    for category_name in ("publications", "review", "catalog"):
        view = views[category_name]
        for field_value in view.fields.values():
            assert "zotero_" in field_value, (category_name, field_value)


def test_authors_field_is_a_bare_placeholder_not_a_compound_template():
    # Required so the templating engine's list-passthrough rule applies
    # (see Global Constraints) — "authors" must map PublicationEntry's
    # list[str] field directly, not stringify it.
    views = load_views(_STARTER_VIEWS_PATH)
    for category_name in ("publications", "review", "catalog"):
        assert views[category_name].fields["authors"] == "{zotero_authors}"
