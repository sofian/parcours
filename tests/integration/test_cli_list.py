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
    (tmp_path / "labels.csv").write_text("id,category,en,fr\n")
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First Widget,draft\ndef456,Second Widget,published\n",
        encoding="utf-8",
    )
    return tmp_path


def test_list_shows_every_row_when_no_search_given(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "widgets"])

    assert result.exit_code == 0
    assert "First Widget" in result.stdout
    assert "Second Widget" in result.stdout


def test_list_filters_by_search_text(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "widgets", "--search", "First"])

    assert result.exit_code == 0
    assert "First Widget" in result.stdout
    assert "Second Widget" not in result.stdout


def test_list_reports_no_entries_for_empty_category(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "widgets.csv").unlink()
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "widgets"])

    assert result.exit_code == 0
    assert "No entries found" in result.stdout


def test_list_no_search_matches_reports_no_entries(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "widgets", "--search", "nonexistent"])

    assert result.exit_code == 0
    assert "No entries found" in result.stdout


def test_list_unknown_category_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "nonexistent"])

    assert result.exit_code == 2
    assert "Unknown category" in result.stdout


def test_list_is_read_only_and_does_not_write_or_commit(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    before = (repo / "widgets.csv").read_bytes()

    result = runner.invoke(app, ["list", "widgets"])

    assert result.exit_code == 0
    assert (repo / "widgets.csv").read_bytes() == before
