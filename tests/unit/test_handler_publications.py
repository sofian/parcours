import json

from parcours.core.schema import CategorySchema
from parcours.core.handlers.base import HandlerContext
from parcours.core.handlers.publications import PublicationsHandler


def _write_csl_json(tmp_path, records):
    zotero_dir = tmp_path / "zotero"
    zotero_dir.mkdir()
    path = zotero_dir / "library.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return "zotero/library.json"


def _schema(json_rel_path):
    return CategorySchema(
        name="publications",
        handler="publications",
        options={"json": json_rel_path},
    )


def test_resolve_finds_a_known_citekey(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "audry2024plaquette", "title": "Plaquette", "DOI": "10.1/plaquette",
         "issued": {"date-parts": [[2024]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    record = handler.resolve("audry2024plaquette")

    assert record is not None
    assert record["title"] == "Plaquette"


def test_resolve_returns_none_for_unknown_citekey(tmp_path):
    json_path = _write_csl_json(tmp_path, [])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))
    assert handler.resolve("nonexistent") is None


def test_validate_flags_unresolved_citekey(tmp_path):
    json_path = _write_csl_json(tmp_path, [])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    issues = handler.validate({"id": "pub-1", "citekey": "nonexistent"})

    assert len(issues) == 1
    assert issues[0].field == "citekey"


def test_validate_passes_a_resolvable_citekey(tmp_path):
    json_path = _write_csl_json(tmp_path, [{"id": "audry2024plaquette", "title": "Plaquette"}])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    assert handler.validate({"id": "pub-1", "citekey": "audry2024plaquette"}) == []


def test_find_matches_same_citekey_is_duplicate(tmp_path):
    json_path = _write_csl_json(tmp_path, [])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))
    entry = {"id": "new", "citekey": "same-key"}
    existing = [{"id": "old", "citekey": "same-key"}]

    matches = handler.find_matches(entry, existing)

    assert len(matches) == 1
    assert matches[0].kind == "duplicate"
    assert matches[0].existing_row_id == "old"


def test_find_matches_same_doi_is_duplicate(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "key-a", "title": "Title A", "DOI": "10.1/shared"},
        {"id": "key-b", "title": "Different Title", "DOI": "10.1/shared"},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))
    entry = {"id": "new", "citekey": "key-a"}
    existing = [{"id": "old", "citekey": "key-b"}]

    matches = handler.find_matches(entry, existing)

    assert len(matches) == 1
    assert matches[0].kind == "duplicate"


def test_find_matches_fuzzy_title_and_same_year_is_duplicate(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "key-a", "title": "Machine Learning Art", "issued": {"date-parts": [[2024]]}},
        {"id": "key-b", "title": "Machine Learning  Art", "issued": {"date-parts": [[2024]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))
    entry = {"id": "new", "citekey": "key-a"}
    existing = [{"id": "old", "citekey": "key-b"}]

    matches = handler.find_matches(entry, existing)

    assert len(matches) == 1


def test_find_matches_fuzzy_title_and_same_year_with_mixed_year_types_is_duplicate(tmp_path):
    # Same real-world quirk as above, exercised through the dedup path:
    # one record's year stored as an int, the other as a string, same
    # actual year — must still be recognized as the same year.
    json_path = _write_csl_json(tmp_path, [
        {"id": "key-a", "title": "Machine Learning Art", "issued": {"date-parts": [[2024]]}},
        {"id": "key-b", "title": "Machine Learning  Art", "issued": {"date-parts": [["2024"]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))
    entry = {"id": "new", "citekey": "key-a"}
    existing = [{"id": "old", "citekey": "key-b"}]

    matches = handler.find_matches(entry, existing)

    assert len(matches) == 1


def test_find_matches_no_false_positive_for_unrelated_publications(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "key-a", "title": "Machine Learning Art", "DOI": "10.1/a",
         "issued": {"date-parts": [[2024]]}},
        {"id": "key-b", "title": "Completely Unrelated Topic", "DOI": "10.1/b",
         "issued": {"date-parts": [[2019]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))
    entry = {"id": "new", "citekey": "key-a"}
    existing = [{"id": "old", "citekey": "key-b"}]

    assert handler.find_matches(entry, existing) == []


def test_match_citekey_by_title_returns_confident_match(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "smith2020widget", "title": "A Widget Study", "issued": {"date-parts": [[2020]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    citekey = handler.match_citekey_by_title("A Widget Study", 2020)

    assert citekey == "smith2020widget"


def test_match_citekey_by_title_returns_none_when_no_match(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "smith2020widget", "title": "A Widget Study", "issued": {"date-parts": [[2020]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    citekey = handler.match_citekey_by_title("Completely Unrelated Title", 2020)

    assert citekey is None


def test_match_citekey_by_title_tolerates_a_one_year_difference(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "smith2020widget", "title": "A Widget Study", "issued": {"date-parts": [[2020]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    citekey = handler.match_citekey_by_title("A Widget Study", 2019)

    assert citekey == "smith2020widget"


def test_match_citekey_by_title_rejects_a_year_mismatch_beyond_one_year(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "smith2020widget", "title": "A Widget Study", "issued": {"date-parts": [[2020]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    citekey = handler.match_citekey_by_title("A Widget Study", 2015)

    assert citekey is None


def test_match_citekey_by_title_handles_a_string_typed_year_in_csl_json(tmp_path):
    # Real-world Better BibTeX CSL-JSON exports don't reliably agree on
    # whether issued.date-parts' year is an int or a numeric string —
    # confirmed against a real ~1800-item export mixing both. A naive
    # `record_year != year` comparison would silently reject this match
    # forever, since `2020 == "2020"` is always False in Python.
    json_path = _write_csl_json(tmp_path, [
        {"id": "smith2020widget", "title": "A Widget Study", "issued": {"date-parts": [["2020"]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    citekey = handler.match_citekey_by_title("A Widget Study", 2020)

    assert citekey == "smith2020widget"


def test_match_citekey_by_title_returns_none_when_ambiguous(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "smith2020widget", "title": "A Widget Study", "issued": {"date-parts": [[2020]]}},
        {"id": "jones2020widget", "title": "A Widget Study II", "issued": {"date-parts": [[2020]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    citekey = handler.match_citekey_by_title("A Widget Study", 2020)

    assert citekey is None
