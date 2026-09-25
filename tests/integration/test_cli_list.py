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
    (repo / "entries" / "widgets.csv").unlink()
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
    assert "widgets" in result.stdout


def test_list_with_no_category_shows_available_categories_not_an_error(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "widgets"
    assert "Available categories" not in result.stdout
    assert "Unknown category" not in result.stdout
    assert "required" not in result.stdout.lower()


def test_list_is_read_only_and_does_not_write_or_commit(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    before = (repo / "entries" / "widgets.csv").read_bytes()

    result = runner.invoke(app, ["list", "widgets"])

    assert result.exit_code == 0
    assert (repo / "entries" / "widgets.csv").read_bytes() == before


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
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "translations.csv").write_text("id,category,en,fr\n")
    (tmp_path / "entries" / "presentations.csv").write_text(
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


def _setup_publications_repo(tmp_path):
    (tmp_path / "parco.yaml").write_text("name: test-repo\n")
    (tmp_path / "categories").mkdir()
    (tmp_path / "categories" / "publications.yaml").write_text("""
name: publications
handler: publications
options:
  json: reference/library.json
fields:
  - {name: id, generated: true}
  - {name: citekey, required: true}
""")
    (tmp_path / "categories" / "widgets.yaml").write_text("""
name: widgets
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en, required: true}
""")
    (tmp_path / "vocab.yaml").write_text("{}\n")
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "translations.csv").write_text("id,category,en,fr\n")
    (tmp_path / "entries" / "widgets.csv").write_text("id,title_en\nw1,A Widget\n", encoding="utf-8")
    (tmp_path / "entries" / "publications.csv").write_text(
        "id,citekey\np1,doe2024widgets\np2,nonexistent-key\n", encoding="utf-8"
    )
    (tmp_path / "reference").mkdir()
    (tmp_path / "reference" / "library.json").write_text("""[
        {
            "id": "doe2024widgets",
            "type": "article-journal",
            "title": "On Widgets",
            "author": [{"given": "Jane", "family": "Doe"}],
            "container-title": "Journal of Widgets",
            "issued": {"date-parts": [[2024, 3]]}
        }
    ]""", encoding="utf-8")
    return tmp_path


def test_list_format_citation_renders_a_resolved_citekey(tmp_path, monkeypatch):
    repo = _setup_publications_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "publications", "--format", "citation"])

    assert result.exit_code == 0, result.stdout
    assert "*Journal of Widgets*" in result.stdout
    assert "Doe" in result.stdout


def test_list_format_citation_shows_a_note_for_an_unresolved_citekey(tmp_path, monkeypatch):
    repo = _setup_publications_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["list", "publications", "--format", "citation", "--search", "nonexistent-key"]
    )

    assert result.exit_code == 0, result.stdout
    assert "not found in citation export" in result.stdout


def test_list_format_citation_rejects_a_non_capable_category(tmp_path, monkeypatch):
    repo = _setup_publications_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "widgets", "--format", "citation"])

    assert result.exit_code == 2
    assert "publications" in result.stdout


def test_list_format_citation_uses_custom_style_flag(tmp_path, monkeypatch):
    repo = _setup_publications_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app,
        ["list", "publications", "--format", "citation", "--style", "chicago-author-date",
         "--search", "doe2024widgets"],
    )

    assert result.exit_code == 0, result.stdout
    assert "Doe" in result.stdout
    # APA (the default) wraps the year in parentheses ("Doe, J. (2024)...");
    # chicago-author-date does not ("Doe, J. 2024...") — verified empirically
    # against the real installed citeproc-py. This confirms the requested
    # style was actually used, not just that some citation rendered.
    assert "(2024)" not in result.stdout


def test_list_format_citation_reads_default_style_from_parco_yaml(tmp_path, monkeypatch):
    repo = _setup_publications_repo(tmp_path)
    (repo / "parco.yaml").write_text("citation_style: chicago-author-date\n")
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["list", "publications", "--format", "citation", "--search", "doe2024widgets"]
    )

    assert result.exit_code == 0, result.stdout
    assert "Doe" in result.stdout
    # Same distinguishing check as test_list_format_citation_uses_custom_style_flag:
    # APA (the fallback if parco.yaml's citation_style were ignored) would
    # render "(2024)"; chicago-author-date does not.
    assert "(2024)" not in result.stdout


def test_list_format_citation_handles_duplicate_citekeys_without_crashing(tmp_path, monkeypatch):
    repo = _setup_publications_repo(tmp_path)
    monkeypatch.chdir(repo)
    # A second row citing the SAME resolvable citekey as an existing row.
    with open(repo / "entries" / "publications.csv", "a", encoding="utf-8") as fh:
        fh.write("p3,doe2024widgets\n")

    result = runner.invoke(app, ["list", "publications", "--format", "citation"])

    assert result.exit_code == 0, result.stdout
    # Both rows citing the same key must render the SAME citation, not crash.
    lines = [line for line in result.stdout.splitlines() if "Journal of Widgets" in line]
    assert len(lines) == 2
    assert lines[0] == lines[1]


def test_list_format_citation_blank_citekey_does_not_print_the_word_none(tmp_path, monkeypatch):
    repo = _setup_publications_repo(tmp_path)
    monkeypatch.chdir(repo)
    with open(repo / "entries" / "publications.csv", "a", encoding="utf-8") as fh:
        fh.write("p4,\n")

    result = runner.invoke(app, ["list", "publications", "--format", "citation"])

    assert result.exit_code == 0, result.stdout
    assert "'None'" not in result.stdout


def test_list_unknown_format_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_publications_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "widgets", "--format", "xml"])

    assert result.exit_code == 2
    assert "table" in result.stdout.lower()


def test_list_filter_flag(tmp_path, monkeypatch):
    repo = _setup_ordering_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "presentations", "--filter", "weight=5"])

    assert result.exit_code == 0, result.stdout
    assert "id=a1" in result.stdout
    assert "id=d4" not in result.stdout


def _setup_date_filter_repo(tmp_path):
    # A separate fixture from `_setup_ordering_repo`: that one names its date
    # field `event_date`, which `CategorySchema.default_date_field()` doesn't
    # recognize (by design, it only matches `start_date`/`date` — see
    # core/schema.py). `--after`/`--before` need a field literally named
    # `date` to resolve, so this uses that name instead, mirroring the real
    # `presentations` schema in SPECS.md.
    (tmp_path / "parco.yaml").write_text("name: test-repo\n")
    (tmp_path / "categories").mkdir()
    (tmp_path / "categories" / "presentations.yaml").write_text("""
name: presentations
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en, required: true}
  - {name: date, type: date, precision: year}
""")
    (tmp_path / "vocab.yaml").write_text("{}\n")
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "translations.csv").write_text("id,category,en,fr\n")
    (tmp_path / "entries" / "presentations.csv").write_text(
        "id,title_en,date\n"
        "a1,Middle Talk,2022\n"
        "b2,Oldest Talk,2019\n"
        "c3,Newest Talk,2024\n",
        encoding="utf-8",
    )
    return tmp_path


def test_list_after_before(tmp_path, monkeypatch):
    repo = _setup_date_filter_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "presentations", "--after", "2020", "--before", "2022"])

    assert result.exit_code == 0, result.stdout
    assert "id=a1" in result.stdout
    assert "id=b2" not in result.stdout
    assert "id=c3" not in result.stdout


def test_list_after_with_no_date_field_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["list", "widgets", "--after", "2020"])

    assert result.exit_code == 2
    assert "date field" in result.stdout
