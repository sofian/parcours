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
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "translations.csv").write_text("id,category,en,fr\nwidgets,section,Widgets,Widgets\n")
    return tmp_path


def test_lint_command_reports_no_issues_with_exit_code_zero(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "entries" / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["lint"])

    assert result.exit_code == 0
    assert "No lint issues found" in result.stdout


def test_lint_command_reports_issues_with_nonzero_exit_code(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "entries" / "widgets.csv").write_text("id,title_en,status\nwidget-1,,draft\n")
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
    (repo / "entries" / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")
    (repo / "vocab.yaml").unlink()
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["lint"])

    assert result.exit_code == 2
    assert "Config error" in result.stdout


def test_lint_command_accepts_a_category_filter(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "entries" / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")
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
    (repo / "entries" / "widgets.csv").write_text(
        "id,title_en,status,location\nwidget-1,A Widget,draft,Montreal\n"
    )
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["lint"])

    assert result.exit_code == 0, result.stdout
    assert "WARNING" in result.stdout
    assert "Montreal" in result.stdout


def _mock_git(monkeypatch):
    monkeypatch.setattr("parcours.core.entries.git_commit", lambda *a, **k: None)
    monkeypatch.setattr("parcours.core.entries.is_file_dirty", lambda *a, **k: False)
    monkeypatch.setattr("parcours.core.translations.git_commit", lambda *a, **k: None)
    monkeypatch.setattr("parcours.core.translations.is_file_dirty", lambda *a, **k: False)
    monkeypatch.setattr("parcours.cli.main.is_file_dirty", lambda *a, **k: False)


def test_fix_interactive_fixes_a_blank_required_field(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "entries" / "widgets.csv").write_text("id,title_en,status\nwidget-1,,draft\n")
    monkeypatch.chdir(repo)
    _mock_git(monkeypatch)

    result = runner.invoke(app, ["lint", "--fix-interactive"], input="\nNew Title\ny\n")

    assert result.exit_code == 0, result.stdout
    assert "1 row(s) fixed" in result.stdout
    content = (repo / "entries" / "widgets.csv").read_text(encoding="utf-8")
    assert "New Title" in content


def test_fix_interactive_adds_a_translation_for_a_glossary_warning(tmp_path, monkeypatch):
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
    (repo / "entries" / "widgets.csv").write_text(
        "id,title_en,status,location\nwidget-1,A Widget,draft,Montreal\n"
    )
    monkeypatch.chdir(repo)
    _mock_git(monkeypatch)

    result = runner.invoke(app, ["lint", "--fix-interactive"], input="\nMontreal\nMontréal\n")

    assert result.exit_code == 0, result.stdout
    assert "1 translation(s) added" in result.stdout
    translations = (repo / "entries" / "translations.csv").read_text(encoding="utf-8")
    assert "Montreal,location,Montreal,Montréal" in translations
    # The row itself is untouched — only translations.csv changed.
    widgets = (repo / "entries" / "widgets.csv").read_text(encoding="utf-8")
    assert "Montreal" in widgets


def test_fix_interactive_skip_leaves_the_issue_unresolved(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "entries" / "widgets.csv").write_text("id,title_en,status\nwidget-1,,draft\n")
    monkeypatch.chdir(repo)
    _mock_git(monkeypatch)

    result = runner.invoke(app, ["lint", "--fix-interactive"], input="s\n")

    assert result.exit_code == 0, result.stdout
    assert "0 row(s) fixed, 1 issue(s) skipped" in result.stdout
    content = (repo / "entries" / "widgets.csv").read_text(encoding="utf-8")
    assert "widget-1,,draft" in content


def test_fix_interactive_quit_stops_processing_remaining_rows(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "entries" / "widgets.csv").write_text(
        "id,title_en,status\nwidget-1,,draft\nwidget-2,,draft\n"
    )
    monkeypatch.chdir(repo)
    _mock_git(monkeypatch)

    result = runner.invoke(app, ["lint", "--fix-interactive"], input="q\n")

    assert result.exit_code == 0, result.stdout
    content = (repo / "entries" / "widgets.csv").read_text(encoding="utf-8")
    assert "widget-1,,draft" in content
    assert "widget-2,,draft" in content
