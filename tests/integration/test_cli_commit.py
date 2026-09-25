import subprocess

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
    (tmp_path / "entries" / "translations.csv").write_text("id,category,en,fr\n")
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First Widget,draft\ndef456,Second Widget,published\n",
        encoding="utf-8",
    )
    return tmp_path


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, check=True, capture_output=True)


def test_commit_stages_and_commits_pending_changes(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    (repo / "entries" / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First Widget,draft\ndef456,Second Widget,published\nghi789,Third Widget,draft\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["commit"])

    assert result.exit_code == 0
    assert "committed" in result.stdout.lower() or "Updated" in result.stdout
    log = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=repo, check=True, capture_output=True, text=True)
    assert "widgets.csv" in log.stdout


def test_commit_reports_nothing_to_do_on_clean_repo(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["commit"])

    assert result.exit_code == 0
    assert "nothing to commit" in result.stdout.lower()


def test_commit_accepts_custom_message(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    (repo / "entries" / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First Widget,draft\ndef456,Second Widget,published\nghi789,Third Widget,draft\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["commit", "-m", "Manual fix"])

    assert result.exit_code == 0
    log = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=repo, check=True, capture_output=True, text=True)
    assert log.stdout.strip() == "Manual fix"
