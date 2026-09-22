import pytest

from parcours.core.translations import (
    TranslationExists,
    TranslationNotFound,
    add_translation,
    delete_translation,
    edit_translation,
    load_translations,
)


def _no_commit(monkeypatch):
    calls = []

    def fake_commit(data_dir, filename, message):
        calls.append((data_dir, filename, message))

    monkeypatch.setattr("parcours.core.translations.git_commit", fake_commit)
    return calls


def _write_translations(tmp_path, rows):
    import csv
    from io import StringIO
    path = tmp_path / "translations.csv"
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "category", "en", "fr"])
    for row in rows:
        writer.writerow(row)
    path.write_text(output.getvalue(), encoding="utf-8")
    return path


def test_lookup_by_category_and_id(tmp_path):
    path = _write_translations(tmp_path, [
        ("publications", "section", "Publications", "Publications"),
        ("montreal", "location", "Montreal, Canada", "Montreal, Canada"),
    ])
    table = load_translations(path)

    assert table.lookup("section", "publications", "en") == "Publications"
    assert table.lookup("location", "montreal", "fr") == "Montreal, Canada"
    assert table.lookup("section", "nonexistent", "en") is None


def test_resolve_or_literal_falls_back_to_the_id(tmp_path):
    path = _write_translations(tmp_path, [
        ("montreal", "location", "Montreal, Canada", "Montreal, Canada"),
    ])
    table = load_translations(path)

    assert table.resolve_or_literal("location", "montreal", "en") == "Montreal, Canada"
    assert table.resolve_or_literal("location", "some-unlisted-town", "en") == "some-unlisted-town"


def test_load_translations_tolerates_utf8_bom(tmp_path):
    path = tmp_path / "translations.csv"
    content = "id,category,en,fr\npublications,section,Publications,Publications\n"
    path.write_text(content, encoding="utf-8-sig")

    table = load_translations(path)

    assert table.lookup("section", "publications", "en") == "Publications"


def test_missing_translations_does_not_crash_on_a_ragged_row(tmp_path):
    path = tmp_path / "translations.csv"
    # Fewer columns than the header: csv.DictReader fills missing trailing
    # keys with None (its `restval`), not "".
    path.write_text("id,category,en,fr\nragged,section,OnlyEnglish\n", encoding="utf-8")

    table = load_translations(path)
    missing = table.missing_translations()

    assert len(missing) == 1
    assert missing[0].id == "ragged"


def test_missing_translations_finds_blank_sides(tmp_path):
    path = _write_translations(tmp_path, [
        ("complete", "section", "Complete", "Complet"),
        ("missing_fr", "section", "Missing French", ""),
    ])
    table = load_translations(path)

    missing = table.missing_translations()

    assert len(missing) == 1
    assert missing[0].id == "missing_fr"


def test_add_translation_creates_translations_csv_with_header_and_row(tmp_path, monkeypatch):
    calls = _no_commit(monkeypatch)

    entry = add_translation(tmp_path, "location", "montreal", "Montreal", "Montréal")

    assert entry.id == "montreal"
    content = (tmp_path / "translations.csv").read_text(encoding="utf-8")
    assert content.splitlines()[0] == "id,category,en,fr"
    assert "montreal,location,Montreal,Montréal" in content
    assert calls == [(tmp_path, "translations.csv", "Added translation location:montreal")]


def test_add_translation_appends_to_existing_translations_csv(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    _write_translations(tmp_path, [("publications", "section", "Publications", "Publications")])

    add_translation(tmp_path, "location", "montreal", "Montreal", "Montréal")

    table = load_translations(tmp_path / "translations.csv")
    assert table.lookup("section", "publications", "en") == "Publications"
    assert table.lookup("location", "montreal", "fr") == "Montréal"


def test_add_translation_raises_for_an_existing_pair(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    _write_translations(tmp_path, [("montreal", "location", "Montreal", "Montréal")])

    with pytest.raises(TranslationExists):
        add_translation(tmp_path, "location", "montreal", "Montreal", "Montréal encore")


def test_edit_translation_updates_matching_pair_and_keeps_others(tmp_path, monkeypatch):
    calls = _no_commit(monkeypatch)
    _write_translations(tmp_path, [
        ("publications", "section", "Publications", "Publications"),
        ("montreal", "location", "Montreal", ""),
    ])

    updated = edit_translation(tmp_path, "location", "montreal", "Montreal", "Montréal")

    assert updated.fr == "Montréal"
    table = load_translations(tmp_path / "translations.csv")
    assert table.lookup("section", "publications", "en") == "Publications"
    assert table.lookup("location", "montreal", "fr") == "Montréal"
    assert calls == [(tmp_path, "translations.csv", "Edited translation location:montreal")]


def test_edit_translation_raises_for_unknown_pair(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    _write_translations(tmp_path, [("montreal", "location", "Montreal", "Montréal")])

    with pytest.raises(TranslationNotFound):
        edit_translation(tmp_path, "location", "nonexistent", "X", "Y")


def test_delete_translation_removes_matching_pair(tmp_path, monkeypatch):
    calls = _no_commit(monkeypatch)
    _write_translations(tmp_path, [
        ("publications", "section", "Publications", "Publications"),
        ("montreal", "location", "Montreal", "Montréal"),
    ])

    delete_translation(tmp_path, "location", "montreal")

    table = load_translations(tmp_path / "translations.csv")
    assert table.lookup("section", "publications", "en") == "Publications"
    assert not table.exists("location", "montreal")
    assert calls == [(tmp_path, "translations.csv", "Deleted translation location:montreal")]


def test_delete_translation_raises_for_unknown_pair(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    _write_translations(tmp_path, [("montreal", "location", "Montreal", "Montréal")])

    with pytest.raises(TranslationNotFound):
        delete_translation(tmp_path, "location", "nonexistent")


def test_lookup_is_case_insensitive(tmp_path):
    table = load_translations(_write_translations(tmp_path, [
        ("montreal", "location", "Montreal", "Montréal"),
    ]))

    assert table.exists("LOCATION", "Montreal")
    assert table.get("location", "MONTREAL") is not None
    assert table.lookup("Location", "montreal", "fr") == "Montréal"


def test_add_translation_rejects_a_differently_cased_existing_pair(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    _write_translations(tmp_path, [("montreal", "location", "Montreal", "Montréal")])

    with pytest.raises(TranslationExists):
        add_translation(tmp_path, "location", "Montreal", "Montreal", "Montréal encore")


def test_edit_translation_matches_case_insensitively_and_preserves_stored_casing(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    _write_translations(tmp_path, [("montreal", "location", "Montreal", "")])

    updated = edit_translation(tmp_path, "location", "Montreal", "Montreal", "Montréal")

    assert updated.id == "montreal"
    table = load_translations(tmp_path / "translations.csv")
    assert table.lookup("location", "montreal", "fr") == "Montréal"
    entries = table.all()
    assert len(entries) == 1
    assert entries[0].id == "montreal"


def test_delete_translation_matches_case_insensitively(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    _write_translations(tmp_path, [("montreal", "location", "Montreal", "Montréal")])

    delete_translation(tmp_path, "location", "MONTREAL")

    table = load_translations(tmp_path / "translations.csv")
    assert table.all() == []
