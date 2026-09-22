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
dedup:
  - when: [{exact: title_en}]
    as: duplicate
""")
    (tmp_path / "vocab.yaml").write_text("widget_status: [draft, published]\n")
    (tmp_path / "labels.csv").write_text("id,category,en,fr\n")
    return tmp_path


def test_add_writes_a_new_row_and_commits(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries._git_commit", lambda *a, **k: None)

    result = runner.invoke(app, ["add", "widgets"], input="A Widget\n1\ny\n")

    assert result.exit_code == 0, result.stdout
    assert "Added widgets entry" in result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert "A Widget" in content
    assert ",draft" in content


def test_add_aborts_when_confirm_declined(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries._git_commit", lambda *a, **k: None)

    result = runner.invoke(app, ["add", "widgets"], input="A Widget\n1\nn\n")

    assert result.exit_code == 0
    assert "Aborted" in result.stdout
    assert not (repo / "widgets.csv").exists()


def test_add_warns_on_duplicate_and_can_proceed_anyway(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "widgets.csv").write_text("id,title_en,status\nabc123,A Widget,draft\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries._git_commit", lambda *a, **k: None)

    result = runner.invoke(app, ["add", "widgets"], input="A Widget\n1\ny\ny\n")

    assert result.exit_code == 0, result.stdout
    assert "Possible duplicates found" in result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert content.count("A Widget") == 2


def test_add_prefill_flags_are_used_as_wizard_defaults(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries._git_commit", lambda *a, **k: None)

    result = runner.invoke(
        app, ["add", "widgets", "--title_en", "Prefilled Widget"], input="\n1\ny\n"
    )

    assert result.exit_code == 0, result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert "Prefilled Widget" in content


def test_add_rejects_unknown_flag(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["add", "widgets", "--nope", "x"])

    assert result.exit_code == 2
    assert "Unknown or non-writable" in result.stdout


def test_add_unknown_category_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["add", "nonexistent"])

    assert result.exit_code == 2
    assert "Unknown category" in result.stdout
