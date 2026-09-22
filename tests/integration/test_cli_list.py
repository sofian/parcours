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


def _setup_ordering_repo(tmp_path):
    (tmp_path / "parco.yaml").write_text("name: test-repo\n")
    (tmp_path / "categories").mkdir()
    (tmp_path / "categories" / "presentations.yaml").write_text("""
name: presentations
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en, required: true}
  - {name: event_date, type: date, precision: year}
  - {name: weight, type: int}
""")
    (tmp_path / "vocab.yaml").write_text("{}\n")
    (tmp_path / "labels.csv").write_text("id,category,en,fr\n")
    (tmp_path / "presentations.csv").write_text(
        "id,title_en,event_date,weight\n"
        "a1,Middle Talk,2022,5\n"
        "b2,Oldest Talk,2019,\n"
        "c3,Newest Talk,2024,\n"
        "d4,No Date Talk,,10\n",
        encoding="utf-8",
    )
    return tmp_path


def test_list_order_by_date_is_ascending_with_blanks_last(tmp_path, monkeypatch):
    repo = _setup_ordering_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "presentations", "--order-by", "event_date"])

    assert result.exit_code == 0, result.stdout
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert [line.split(",")[0] for line in lines] == [
        "id=b2", "id=a1", "id=c3", "id=d4",
    ]


def test_list_order_by_date_desc_still_puts_blanks_last(tmp_path, monkeypatch):
    repo = _setup_ordering_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "presentations", "--order-by", "event_date", "--desc"])

    assert result.exit_code == 0, result.stdout
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert [line.split(",")[0] for line in lines] == [
        "id=c3", "id=a1", "id=b2", "id=d4",
    ]


def test_list_order_by_int_field_sorts_numerically_not_lexically(tmp_path, monkeypatch):
    repo = _setup_ordering_repo(tmp_path)
    monkeypatch.chdir(repo)
    # weight=5 (a1) should sort before weight=10 (d4) numerically,
    # which a plain string sort would get backwards ("10" < "5").

    result = runner.invoke(app, ["list", "presentations", "--order-by", "weight"])

    assert result.exit_code == 0, result.stdout
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    ids_with_weight = [line.split(",")[0] for line in lines if "weight=" in line]
    assert ids_with_weight == ["id=a1", "id=d4"]


def test_list_order_by_unknown_field_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_ordering_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "presentations", "--order-by", "nonexistent"])

    assert result.exit_code == 2
    assert "Unknown field" in result.stdout


def test_list_desc_without_order_by_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_ordering_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "presentations", "--desc"])

    assert result.exit_code == 2
    assert "--desc requires --order-by" in result.stdout
