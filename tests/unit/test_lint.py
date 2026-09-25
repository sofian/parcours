import json

import pytest

from parcours.core.lint import ConfigError, run_lint


def _setup_data_repo(tmp_path):
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
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "translations.csv").write_text("id,category,en,fr\nwidgets,section,Widgets,Widgets\n")
    return tmp_path


def test_no_issues_for_valid_data(tmp_path):
    repo = _setup_data_repo(tmp_path)
    (repo / "entries" / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")

    assert run_lint(repo) == []


def test_flags_a_missing_required_field(tmp_path):
    repo = _setup_data_repo(tmp_path)
    (repo / "entries" / "widgets.csv").write_text("id,title_en,status\nwidget-1,,draft\n")

    issues = run_lint(repo)

    assert any(i.field == "title_en" for i in issues)


def test_flags_a_missing_translation(tmp_path):
    repo = _setup_data_repo(tmp_path)
    (repo / "entries" / "translations.csv").write_text("id,category,en,fr\nwidgets,section,Widgets,\n")
    (repo / "entries" / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")

    issues = run_lint(repo)

    assert any(i.category == "translations" for i in issues)


def test_category_filter_only_checks_that_category(tmp_path):
    repo = _setup_data_repo(tmp_path)
    (repo / "categories" / "gadgets.yaml").write_text("""
name: gadgets
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en, required: true}
""")
    (repo / "entries" / "widgets.csv").write_text("id,title_en,status\nwidget-1,,draft\n")
    (repo / "entries" / "gadgets.csv").write_text("id,title_en\ngadget-1,,\n")

    issues = run_lint(repo, category_filter="widgets")

    assert all(i.category in ("widgets", "translations") for i in issues)
    assert any(i.category == "widgets" for i in issues)


def test_publications_handler_is_wired_up(tmp_path):
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
    (tmp_path / "vocab.yaml").write_text("{}\n")
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "translations.csv").write_text("id,category,en,fr\n")
    (tmp_path / "reference").mkdir()
    (tmp_path / "reference" / "library.json").write_text(json.dumps([]))
    (tmp_path / "entries" / "publications.csv").write_text("id,citekey\npub-1,nonexistent-key\n")

    issues = run_lint(tmp_path)

    assert any(i.field == "citekey" for i in issues)


def test_flags_a_glossary_value_with_no_matching_entry_as_a_warning(tmp_path):
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

    issues = run_lint(repo)

    matches = [i for i in issues if i.field == "location"]
    assert len(matches) == 1
    assert matches[0].severity == "warning"
    assert "Montreal" in matches[0].message


def test_glossary_field_with_a_matching_entry_has_no_issue(tmp_path):
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
    (repo / "entries" / "translations.csv").write_text(
        "id,category,en,fr\nwidgets,section,Widgets,Widgets\nMontreal,location,Montreal,Montréal\n"
    )
    (repo / "entries" / "widgets.csv").write_text(
        "id,title_en,status,location\nwidget-1,A Widget,draft,Montreal\n"
    )

    issues = run_lint(repo)

    assert not any(i.field == "location" for i in issues)


def test_glossary_warning_never_counts_toward_error_severity(tmp_path):
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

    issues = run_lint(repo)

    assert all(i.severity == "warning" for i in issues if i.field == "location")
    assert not any(i.severity == "error" for i in issues if i.field == "location")


def test_unregistered_vocab_name_raises_config_error_not_a_crash(tmp_path):
    repo = _setup_data_repo(tmp_path)
    (repo / "categories" / "widgets.yaml").write_text("""
name: widgets
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en, required: true}
  - {name: status, required: true, vocab: nope}
""")
    (repo / "entries" / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")

    with pytest.raises(ConfigError, match="nope"):
        run_lint(repo)
