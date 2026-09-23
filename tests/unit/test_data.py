import duckdb
import pytest

from parcours.core.data import load_category_rows, query_category_rows


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


def test_query_with_no_filters_returns_every_row(tmp_path):
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nw1,First,draft\nw2,Second,published\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets")

    assert [r["id"] for r in rows] == ["w1", "w2"]


def test_query_filters_by_allowed_values(tmp_path):
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nw1,First,draft\nw2,Second,published\nw3,Third,published\n",
        encoding="utf-8",
    )

    rows = query_category_rows(tmp_path, "widgets", filters={"status": ["published"]})

    assert sorted(r["id"] for r in rows) == ["w2", "w3"]


def test_query_filters_by_a_scalar_value(tmp_path):
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nw1,First,draft\nw2,Second,published\nw3,Third,published\n",
        encoding="utf-8",
    )

    rows = query_category_rows(tmp_path, "widgets", filters={"status": "published"})

    assert sorted(r["id"] for r in rows) == ["w2", "w3"]


def test_query_filters_by_multiple_fields_anded_together(tmp_path):
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nw1,First,draft\nw2,Second,published\nw3,First,published\n",
        encoding="utf-8",
    )

    rows = query_category_rows(
        tmp_path, "widgets", filters={"status": ["published"], "title_en": ["First"]}
    )

    assert [r["id"] for r in rows] == ["w3"]


def test_query_orders_ascending_by_default(tmp_path):
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,start_date\nw1,B,2022\nw2,A,2020\nw3,C,2021\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets", order_by="start_date")

    assert [r["id"] for r in rows] == ["w2", "w3", "w1"]


def test_query_orders_descending(tmp_path):
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,start_date\nw1,B,2022\nw2,A,2020\nw3,C,2021\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets", order_by="start_date desc")

    assert [r["id"] for r in rows] == ["w1", "w3", "w2"]


def test_query_rejects_invalid_order_direction(tmp_path):
    (tmp_path / "widgets.csv").write_text("id,title_en\nw1,First\n", encoding="utf-8")

    with pytest.raises(ValueError, match="sideways"):
        query_category_rows(tmp_path, "widgets", order_by="title_en sideways")


def test_query_applies_limit(tmp_path):
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,start_date\nw1,A,2020\nw2,B,2021\nw3,C,2022\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets", order_by="start_date", limit=2)

    assert [r["id"] for r in rows] == ["w1", "w2"]


def test_query_missing_csv_returns_empty_list(tmp_path):
    assert query_category_rows(tmp_path, "nonexistent") == []


def test_query_unknown_filter_field_raises_clear_error(tmp_path):
    (tmp_path / "widgets.csv").write_text("id,title_en\nw1,First\n", encoding="utf-8")

    with pytest.raises(ValueError, match="widgets"):
        query_category_rows(tmp_path, "widgets", filters={"nonexistent_field": ["x"]})
