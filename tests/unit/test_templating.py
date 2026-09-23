from parcours.core.templating import resolve_field, resolve_template


def test_resolve_field_prefers_the_requested_language():
    row = {"title_en": "English Title", "title_fr": "Titre français"}
    assert resolve_field(row, "title", "en") == "English Title"
    assert resolve_field(row, "title", "fr") == "Titre français"


def test_resolve_field_falls_back_to_the_other_language_when_blank():
    row = {"title_en": "", "title_fr": "Titre français"}
    assert resolve_field(row, "title", "en") == "Titre français"


def test_resolve_field_falls_back_to_a_plain_field_with_no_bilingual_pair():
    row = {"organization": "Acme"}
    assert resolve_field(row, "organization", "en") == "Acme"


def test_resolve_field_returns_none_when_nothing_matches():
    row = {}
    assert resolve_field(row, "title", "en") is None


def test_resolve_template_with_no_braces_is_a_direct_field_copy():
    row = {"start_date": "2020-01", "weight": "5"}
    assert resolve_template("start_date", row, "en") == "2020-01"


def test_resolve_template_direct_copy_of_a_missing_field_is_none():
    assert resolve_template("start_date", {}, "en") is None


def test_resolve_template_bare_placeholder_resolves_bilingual():
    row = {"title_en": "English", "title_fr": "Français"}
    assert resolve_template("{title}", row, "fr") == "Français"


def test_resolve_template_bare_placeholder_passes_through_a_list_unchanged():
    row = {"zotero_authors": ["Jane Doe", "John Smith"]}
    assert resolve_template("{zotero_authors}", row, "en") == ["Jane Doe", "John Smith"]


def test_resolve_template_compound_string_substitutes_each_placeholder():
    row = {"funder": "FRQSC", "role": "PI"}
    assert resolve_template("{funder} — {role}", row, "en") == "FRQSC — PI"


def test_resolve_template_compound_string_treats_blank_fields_as_empty():
    row = {"funder": "FRQSC", "role": ""}
    assert resolve_template("{funder} — {role}", row, "en") == "FRQSC — "


def test_resolve_template_list_resolves_each_item_and_drops_blanks():
    row = {"funder": "FRQSC", "role": "PI", "co_investigators": ""}
    result = resolve_template(
        ["{funder} — {role}", "{co_investigators}", "amount"], row, "en"
    )
    assert result == ["FRQSC — PI"]


def test_resolve_template_non_string_non_list_passes_through():
    assert resolve_template(None, {"x": "y"}, "en") is None
