from parcours.core.labels import load_labels


def _write_labels(tmp_path, rows):
    import csv
    from io import StringIO
    path = tmp_path / "labels.csv"
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "category", "en", "fr"])
    for row in rows:
        writer.writerow(row)
    path.write_text(output.getvalue(), encoding="utf-8")
    return path


def test_lookup_by_category_and_id(tmp_path):
    path = _write_labels(tmp_path, [
        ("publications", "section", "Publications", "Publications"),
        ("montreal", "location", "Montreal, Canada", "Montreal, Canada"),
    ])
    table = load_labels(path)

    assert table.lookup("section", "publications", "en") == "Publications"
    assert table.lookup("location", "montreal", "fr") == "Montreal, Canada"
    assert table.lookup("section", "nonexistent", "en") is None


def test_resolve_or_literal_falls_back_to_the_id(tmp_path):
    path = _write_labels(tmp_path, [
        ("montreal", "location", "Montreal, Canada", "Montreal, Canada"),
    ])
    table = load_labels(path)

    assert table.resolve_or_literal("location", "montreal", "en") == "Montreal, Canada"
    assert table.resolve_or_literal("location", "some-unlisted-town", "en") == "some-unlisted-town"


def test_load_labels_tolerates_utf8_bom(tmp_path):
    path = tmp_path / "labels.csv"
    content = "id,category,en,fr\npublications,section,Publications,Publications\n"
    path.write_text(content, encoding="utf-8-sig")

    table = load_labels(path)

    assert table.lookup("section", "publications", "en") == "Publications"


def test_missing_translations_does_not_crash_on_a_ragged_row(tmp_path):
    path = tmp_path / "labels.csv"
    # Fewer columns than the header: csv.DictReader fills missing trailing
    # keys with None (its `restval`), not "".
    path.write_text("id,category,en,fr\nragged,section,OnlyEnglish\n", encoding="utf-8")

    table = load_labels(path)
    missing = table.missing_translations()

    assert len(missing) == 1
    assert missing[0].id == "ragged"


def test_missing_translations_finds_blank_sides(tmp_path):
    path = _write_labels(tmp_path, [
        ("complete", "section", "Complete", "Complet"),
        ("missing_fr", "section", "Missing French", ""),
    ])
    table = load_labels(path)

    missing = table.missing_translations()

    assert len(missing) == 1
    assert missing[0].id == "missing_fr"
