from parcours.core.data import load_category_rows


def test_loads_rows_as_dicts_with_string_values(tmp_path):
    csv_path = tmp_path / "widgets.csv"
    csv_path.write_text("id,title_en,start_date\nwidget-1,A Widget,2024-09\n", encoding="utf-8")

    rows = load_category_rows(tmp_path, "widgets")

    assert rows == [{"id": "widget-1", "title_en": "A Widget", "start_date": "2024-09"}]


def test_missing_csv_returns_empty_list(tmp_path):
    assert load_category_rows(tmp_path, "nonexistent") == []


def test_values_stay_as_strings_even_when_numeric(tmp_path):
    csv_path = tmp_path / "grants.csv"
    csv_path.write_text("id,amount\ngrant-1,50000\n", encoding="utf-8")

    rows = load_category_rows(tmp_path, "grants")

    assert rows[0]["amount"] == "50000"
    assert isinstance(rows[0]["amount"], str)
