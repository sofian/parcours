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
  - {name: status, required: true}
  - {name: start_date, type: date, precision: year}
""")
    (tmp_path / "vocab.yaml").write_text("{}\n")
    (tmp_path / "translations.csv").write_text("id,category,en,fr\n")
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status,start_date\n"
        "p1,First,published,2020\n"
        "p2,Second,published,2020\n"
        "p3,Third,under-review,2024\n",
        encoding="utf-8",
    )
    return tmp_path


def test_stats_counts_by_plain_field(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["stats", "widgets", "--by", "status"])

    assert result.exit_code == 0, result.stdout
    assert "published: 2" in result.stdout
    assert "under-review: 1" in result.stdout


def test_stats_counts_by_year(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["stats", "widgets", "--by", "year"])

    assert result.exit_code == 0, result.stdout
    assert "2020: 2" in result.stdout
    assert "2024: 1" in result.stdout


def test_stats_applies_filter_before_counting(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["stats", "widgets", "--by", "year", "--filter", "status=published"]
    )

    assert result.exit_code == 0, result.stdout
    assert "2020: 2" in result.stdout
    assert "2024" not in result.stdout


def test_stats_applies_search(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["stats", "widgets", "--by", "status", "--search", "First"])

    assert result.exit_code == 0, result.stdout
    assert "published: 1" in result.stdout
    assert "under-review" not in result.stdout


def test_stats_applies_after_before(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["stats", "widgets", "--by", "status", "--after", "2021"]
    )

    assert result.exit_code == 0, result.stdout
    assert "under-review: 1" in result.stdout
    assert "published" not in result.stdout


def test_stats_unknown_field_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["stats", "widgets", "--by", "nonexistent"])

    assert result.exit_code == 2
    assert "Unknown field" in result.stdout


def test_stats_bad_filter_syntax_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["stats", "widgets", "--by", "status", "--filter", "not-a-key-value-pair"]
    )

    assert result.exit_code == 2
    assert "field=value" in result.stdout


def test_stats_unknown_filter_field_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["stats", "widgets", "--by", "status", "--filter", "nonexistent=x"]
    )

    assert result.exit_code == 2
    assert "Unknown field" in result.stdout


def test_stats_with_no_category_shows_a_real_error_and_available_categories(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["stats", "--by", "status"])

    assert result.exit_code == 2
    assert "required" in result.stdout.lower()
    assert "widgets" in result.stdout


def test_stats_no_matching_rows_reports_no_entries(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["stats", "widgets", "--by", "status", "--search", "nonexistent"]
    )

    assert result.exit_code == 0
    assert "No entries found" in result.stdout


def test_stats_on_the_real_publications_schema_has_no_date_field_for_by_year(tmp_path, monkeypatch):
    # The real shipped `publications` category has no local date field
    # (dates live in Zotero) — `--by year` must fail cleanly, not with
    # a traceback. This pins the documented SPECS.md gap so it can't
    # silently start passing (or silently start failing differently)
    # without this test forcing attention to it.
    repo = tmp_path
    (repo / "parco.yaml").write_text("name: test-repo\n")
    (repo / "categories").mkdir()
    (repo / "categories" / "publications.yaml").write_text("""
name: publications
handler: publications
options:
  json: reference/library.json
fields:
  - {name: id, generated: true}
  - {name: citekey, required: true}
""")
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "translations.csv").write_text("id,category,en,fr\n")
    (repo / "publications.csv").write_text("id,citekey\np1,doe2024\n", encoding="utf-8")
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["stats", "publications", "--by", "year"])

    assert result.exit_code == 2
    assert "date field" in result.stdout
