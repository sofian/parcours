import pytest

from parcours.core.entries import EntryNotFound, add_entry, delete_entry, edit_entry, generate_id
from parcours.core.schema import CategorySchema, FieldSpec


def _schema():
    return CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="title_en", required=True),
            FieldSpec(name="status"),
        ],
    )


def _no_commit(monkeypatch):
    calls = []

    def fake_commit(data_dir, filename, message):
        calls.append((data_dir, filename, message))

    monkeypatch.setattr("parcours.core.entries._git_commit", fake_commit)
    return calls


def test_generate_id_is_six_hex_chars(tmp_path):
    row_id = generate_id(tmp_path, "widgets")
    assert len(row_id) == 6
    int(row_id, 16)  # doesn't raise


def test_generate_id_avoids_collision_with_existing_ids(tmp_path, monkeypatch):
    (tmp_path / "widgets.csv").write_text("id,title_en,status\nabc123,A,draft\n", encoding="utf-8")
    responses = iter(["abc123", "def456"])
    monkeypatch.setattr("parcours.core.entries.secrets.token_hex", lambda n: next(responses))

    row_id = generate_id(tmp_path, "widgets")

    assert row_id == "def456"


def test_add_entry_creates_csv_with_header_and_generated_id(tmp_path, monkeypatch):
    calls = _no_commit(monkeypatch)
    schema = _schema()

    row = add_entry(tmp_path, schema, {"title_en": "A Widget", "status": "draft"})

    assert row["title_en"] == "A Widget"
    assert len(row["id"]) == 6
    content = (tmp_path / "widgets.csv").read_text(encoding="utf-8")
    assert content.splitlines()[0] == "id,title_en,status"
    assert row["id"] in content
    assert calls == [(tmp_path, "widgets.csv", f"Added widgets entry {row['id']}")]


def test_add_entry_appends_to_existing_csv(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    schema = _schema()
    (tmp_path / "widgets.csv").write_text("id,title_en,status\nabc123,First,draft\n", encoding="utf-8")

    add_entry(tmp_path, schema, {"title_en": "Second", "status": "published"})

    lines = (tmp_path / "widgets.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert "First" in lines[1]
    assert "Second" in lines[2]


def test_edit_entry_updates_matching_row_and_keeps_others(tmp_path, monkeypatch):
    calls = _no_commit(monkeypatch)
    schema = _schema()
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First,draft\ndef456,Second,draft\n", encoding="utf-8"
    )

    updated = edit_entry(tmp_path, schema, "abc123", {"title_en": "First (revised)", "status": "published"})

    assert updated == {"id": "abc123", "title_en": "First (revised)", "status": "published"}
    lines = (tmp_path / "widgets.csv").read_text(encoding="utf-8").splitlines()
    assert "First (revised)" in lines[1]
    assert "Second" in lines[2]
    assert calls == [(tmp_path, "widgets.csv", "Edited widgets entry abc123")]


def test_edit_entry_raises_for_unknown_id(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    schema = _schema()
    (tmp_path / "widgets.csv").write_text("id,title_en,status\nabc123,First,draft\n", encoding="utf-8")

    with pytest.raises(EntryNotFound):
        edit_entry(tmp_path, schema, "nonexistent", {"title_en": "X", "status": "draft"})


def test_delete_entry_removes_matching_row(tmp_path, monkeypatch):
    calls = _no_commit(monkeypatch)
    schema = _schema()
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First,draft\ndef456,Second,draft\n", encoding="utf-8"
    )

    delete_entry(tmp_path, schema, "abc123")

    lines = (tmp_path / "widgets.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "Second" in lines[1]
    assert calls == [(tmp_path, "widgets.csv", "Deleted widgets entry abc123")]


def test_delete_entry_raises_for_unknown_id(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    schema = _schema()
    (tmp_path / "widgets.csv").write_text("id,title_en,status\nabc123,First,draft\n", encoding="utf-8")

    with pytest.raises(EntryNotFound):
        delete_entry(tmp_path, schema, "nonexistent")


def test_write_preserves_lf_line_endings(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    schema = _schema()
    (tmp_path / "widgets.csv").write_bytes(b"id,title_en,status\nabc123,First,draft\n")

    add_entry(tmp_path, schema, {"title_en": "Second", "status": "published"})

    raw = (tmp_path / "widgets.csv").read_bytes()
    assert b"\r\n" not in raw
