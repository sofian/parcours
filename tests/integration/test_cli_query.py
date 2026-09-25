from typer.testing import CliRunner

from parcours.cli.main import app

runner = CliRunner()


def _setup_data_repo(tmp_path):
    (tmp_path / "parco.yaml").write_text("name: test-repo\n")
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,status\nw1,First,draft\nw2,Second,published\n", encoding="utf-8"
    )
    return tmp_path


def test_query_prints_a_table_by_default(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["query", "SELECT id, title_en FROM widgets ORDER BY id"])

    assert result.exit_code == 0, result.stdout
    assert "First" in result.stdout
    assert "Second" in result.stdout


def test_query_format_csv(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["query", "SELECT id, status FROM widgets ORDER BY id", "--format", "csv"]
    )

    assert result.exit_code == 0, result.stdout
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "id,status"
    assert lines[1] == "w1,draft"


def test_query_format_json(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["query", "SELECT id FROM widgets WHERE id = 'w1'", "--format", "json"]
    )

    assert result.exit_code == 0, result.stdout
    assert '"id": "w1"' in result.stdout


def test_query_rejects_non_select_with_exit_code_2(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["query", "DELETE FROM widgets"])

    assert result.exit_code == 2
    assert "SELECT" in result.stdout


def test_query_rejects_unknown_format(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["query", "SELECT id FROM widgets", "--format", "xml"]
    )

    assert result.exit_code == 2
    assert "table" in result.stdout.lower()
