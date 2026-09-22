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
    (tmp_path / "translations.csv").write_text("id,category,en,fr\nwidgets,section,Widgets,Widgets\n")
    return tmp_path


def test_lint_command_reports_no_issues_with_exit_code_zero(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["lint"])

    assert result.exit_code == 0
    assert "No lint issues found" in result.stdout


def test_lint_command_reports_issues_with_nonzero_exit_code(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "widgets.csv").write_text("id,title_en,status\nwidget-1,,draft\n")
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["lint"])

    assert result.exit_code == 1
    assert "title_en" in result.stdout


def test_lint_command_fails_clearly_with_no_data_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "empty_home")

    result = runner.invoke(app, ["lint"])

    assert result.exit_code == 2
    assert "No data repo found" in result.stdout


def test_lint_command_exits_2_with_clear_message_on_missing_vocab_file(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")
    (repo / "vocab.yaml").unlink()
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["lint"])

    assert result.exit_code == 2
    assert "Config error" in result.stdout


def test_lint_command_accepts_a_category_filter(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["lint", "widgets"])

    assert result.exit_code == 0


def test_lint_command_reports_a_glossary_warning_but_exits_zero(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "categories" / "widgets.yaml").write_text("""
name: widgets
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en, required: true}
  - {name: status, required: true, vocab: widget_status}
  - {name: location, glossary: location}
""")
    (repo / "widgets.csv").write_text(
        "id,title_en,status,location\nwidget-1,A Widget,draft,Montreal\n"
    )
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["lint"])

    assert result.exit_code == 0, result.stdout
    assert "WARNING" in result.stdout
    assert "Montreal" in result.stdout
