from typer.testing import CliRunner

from parcours.cli.main import app

runner = CliRunner()


def _setup_data_repo(tmp_path):
    (tmp_path / "parco.yaml").write_text("name: test-repo\n")
    (tmp_path / "categories").mkdir()
    (tmp_path / "categories" / "widgets.yaml").write_text("""
name: widgets
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en, required: true}
  - {name: status, required: true, vocab: widget_status}
""")
    (tmp_path / "vocab.yaml").write_text("widget_status: [draft, published]\n")
    (tmp_path / "translations.csv").write_text("id,category,en,fr\n")
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First Widget,draft\ndef456,Second Widget,draft\n",
        encoding="utf-8",
    )
    return tmp_path


def test_edit_finds_by_search_and_updates(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries.git_commit", lambda *a, **k: None)
    monkeypatch.setattr("parcours.core.entries.is_file_dirty", lambda *a, **k: False)

    result = runner.invoke(
        app, ["edit", "widgets", "--search", "First"], input="1\nFirst Widget (revised)\n2\ny\n"
    )

    assert result.exit_code == 0, result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert "First Widget (revised)" in content
    assert ",published" in content
    assert "abc123" in content


def test_edit_prefills_wizard_with_existing_values(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries.git_commit", lambda *a, **k: None)
    monkeypatch.setattr("parcours.core.entries.is_file_dirty", lambda *a, **k: False)

    result = runner.invoke(
        app, ["edit", "widgets", "--search", "First"], input="1\n\n\ny\n"
    )

    assert result.exit_code == 0, result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert "First Widget" in content
    assert ",draft" in content


def test_edit_with_no_category_shows_a_real_error_and_the_available_categories(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["edit", "--search", "First"])

    assert result.exit_code == 2
    assert "required" in result.stdout.lower()
    assert "Available categories" in result.stdout
    assert "widgets" in result.stdout


def test_edit_no_matches_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["edit", "widgets", "--search", "nonexistent"])

    assert result.exit_code == 0
    assert "No matching entries found" in result.stdout
    assert "Nothing selected" not in result.stdout


def test_edit_cancel_at_picker_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["edit", "widgets", "--search", "Widget"], input="\n")

    assert result.exit_code == 0
    assert "Nothing selected" in result.stdout
