from typer.testing import CliRunner

from parcours.cli.main import app

runner = CliRunner()


def _setup_data_repo(tmp_path):
    (tmp_path / "parco.yaml").write_text("name: test-repo\n")
    return tmp_path


def test_translation_add_creates_translations_csv_and_commits(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.translations.git_commit", lambda *a, **k: None)

    result = runner.invoke(app, ["translation", "add", "location", "montreal", "--en", "Montreal", "--fr", "Montréal"])

    assert result.exit_code == 0, result.stdout
    assert "Added translation location:montreal" in result.stdout
    content = (repo / "translations.csv").read_text(encoding="utf-8")
    assert "montreal,location,Montreal,Montréal" in content


def test_translation_add_prompts_for_missing_en_fr(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.translations.git_commit", lambda *a, **k: None)

    result = runner.invoke(app, ["translation", "add", "location", "montreal"], input="Montreal\nMontréal\n")

    assert result.exit_code == 0, result.stdout
    content = (repo / "translations.csv").read_text(encoding="utf-8")
    assert "montreal,location,Montreal,Montréal" in content


def test_translation_add_rejects_an_existing_pair(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "translations.csv").write_text("id,category,en,fr\nmontreal,location,Montreal,Montréal\n", encoding="utf-8")
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["translation", "add", "location", "montreal", "--en", "X", "--fr", "Y"])

    assert result.exit_code == 2
    assert "already exists" in result.stdout


def test_translation_edit_updates_existing_pair(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "translations.csv").write_text("id,category,en,fr\nmontreal,location,Montreal,\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.translations.git_commit", lambda *a, **k: None)

    result = runner.invoke(app, ["translation", "edit", "location", "montreal", "--fr", "Montréal"], input="\n")

    assert result.exit_code == 0, result.stdout
    content = (repo / "translations.csv").read_text(encoding="utf-8")
    assert "montreal,location,Montreal,Montréal" in content


def test_translation_edit_unknown_pair_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["translation", "edit", "location", "nonexistent", "--en", "X"])

    assert result.exit_code == 2
    assert "No translation" in result.stdout


def test_translation_delete_confirms_and_removes(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "translations.csv").write_text(
        "id,category,en,fr\nmontreal,location,Montreal,Montréal\npublications,section,Publications,Publications\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.translations.git_commit", lambda *a, **k: None)

    result = runner.invoke(app, ["translation", "delete", "location", "montreal"], input="y\n")

    assert result.exit_code == 0, result.stdout
    content = (repo / "translations.csv").read_text(encoding="utf-8")
    assert "montreal" not in content
    assert "publications" in content


def test_translation_delete_declined_leaves_file_unchanged(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "translations.csv").write_text("id,category,en,fr\nmontreal,location,Montreal,Montréal\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    before = (repo / "translations.csv").read_bytes()

    result = runner.invoke(app, ["translation", "delete", "location", "montreal"], input="n\n")

    assert result.exit_code == 0
    assert "Aborted" in result.stdout
    assert (repo / "translations.csv").read_bytes() == before


def test_translation_delete_unknown_pair_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["translation", "delete", "location", "nonexistent"])

    assert result.exit_code == 2
    assert "No translation" in result.stdout


def test_translation_list_shows_everything_with_no_filters(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "translations.csv").write_text(
        "id,category,en,fr\nmontreal,location,Montreal,Montréal\npublications,section,Publications,Publications\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["translation", "list"])

    assert result.exit_code == 0
    assert "montreal" in result.stdout
    assert "publications" in result.stdout


def test_translation_list_filters_by_category(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "translations.csv").write_text(
        "id,category,en,fr\nmontreal,location,Montreal,Montréal\npublications,section,Publications,Publications\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["translation", "list", "--category", "location"])

    assert result.exit_code == 0
    assert "montreal" in result.stdout
    assert "publications" not in result.stdout


def test_translation_list_reports_none_when_translations_csv_missing(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["translation", "list"])

    assert result.exit_code == 0
    assert "No translations found" in result.stdout
