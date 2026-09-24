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
""")
    (tmp_path / "vocab.yaml").write_text("{}\n")
    (tmp_path / "translations.csv").write_text("id,category,en,fr\n")
    (tmp_path / "widgets.csv").write_text(
        "id,title_en\nabc123,First Widget\ndef456,Second Widget\n", encoding="utf-8"
    )
    return tmp_path


def test_delete_confirms_and_removes_the_row(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries.git_commit", lambda *a, **k: None)
    monkeypatch.setattr("parcours.core.entries.is_file_dirty", lambda *a, **k: False)
    monkeypatch.setattr("parcours.cli.main.is_file_dirty", lambda *a, **k: False)

    result = runner.invoke(app, ["delete", "widgets", "--search", "First"], input="1\ny\n")

    assert result.exit_code == 0, result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert "First Widget" not in content
    assert "Second Widget" in content


def test_delete_aborts_when_confirm_declined(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["delete", "widgets", "--search", "First"], input="1\nn\n")

    assert result.exit_code == 0
    assert "Aborted" in result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert "First Widget" in content


def test_delete_with_no_category_shows_a_real_error_and_the_available_categories(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["delete", "--search", "First"])

    assert result.exit_code == 2
    assert "required" in result.stdout.lower()
    assert "Available categories" in result.stdout
    assert "widgets" in result.stdout


def test_delete_no_matches_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["delete", "widgets", "--search", "nonexistent"])

    assert result.exit_code == 0
    assert "No matching entries found" in result.stdout
    assert "Nothing selected" not in result.stdout
