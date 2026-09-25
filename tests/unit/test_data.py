import duckdb
import pytest

from parcours.core.data import load_category_rows, query_category_rows


def test_loads_rows_as_dicts_with_string_values(tmp_path):
    (tmp_path / "entries").mkdir()
    csv_path = tmp_path / "entries" / "widgets.csv"
    csv_path.write_text("id,title_en,start_date\nwidget-1,A Widget,2024-09\n", encoding="utf-8")

    rows = load_category_rows(tmp_path, "widgets")

    assert rows == [{"id": "widget-1", "title_en": "A Widget", "start_date": "2024-09"}]


def test_missing_csv_returns_empty_list(tmp_path):
    assert load_category_rows(tmp_path, "nonexistent") == []


def test_values_stay_as_strings_even_when_numeric(tmp_path):
    (tmp_path / "entries").mkdir()
    csv_path = tmp_path / "entries" / "grants.csv"
    csv_path.write_text("id,amount\ngrant-1,50000\n", encoding="utf-8")

    rows = load_category_rows(tmp_path, "grants")

    assert rows[0]["amount"] == "50000"
    assert isinstance(rows[0]["amount"], str)


def test_query_with_no_filters_returns_every_row(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,status\nw1,First,draft\nw2,Second,published\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets")

    assert [r["id"] for r in rows] == ["w1", "w2"]


def test_query_filters_by_allowed_values(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,status\nw1,First,draft\nw2,Second,published\nw3,Third,published\n",
        encoding="utf-8",
    )

    rows = query_category_rows(tmp_path, "widgets", filters={"status": ["published"]})

    assert sorted(r["id"] for r in rows) == ["w2", "w3"]


def test_query_filters_by_a_scalar_value(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,status\nw1,First,draft\nw2,Second,published\nw3,Third,published\n",
        encoding="utf-8",
    )

    rows = query_category_rows(tmp_path, "widgets", filters={"status": "published"})

    assert sorted(r["id"] for r in rows) == ["w2", "w3"]


def test_query_filters_by_multiple_fields_anded_together(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,status\nw1,First,draft\nw2,Second,published\nw3,First,published\n",
        encoding="utf-8",
    )

    rows = query_category_rows(
        tmp_path, "widgets", filters={"status": ["published"], "title_en": ["First"]}
    )

    assert [r["id"] for r in rows] == ["w3"]


def test_query_orders_ascending_by_default(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,start_date\nw1,B,2022\nw2,A,2020\nw3,C,2021\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets", order_by="start_date")

    assert [r["id"] for r in rows] == ["w2", "w3", "w1"]


def test_query_orders_descending(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,start_date\nw1,B,2022\nw2,A,2020\nw3,C,2021\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets", order_by="start_date desc")

    assert [r["id"] for r in rows] == ["w1", "w3", "w2"]


def test_query_rejects_invalid_order_direction(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text("id,title_en\nw1,First\n", encoding="utf-8")

    with pytest.raises(ValueError, match="sideways"):
        query_category_rows(tmp_path, "widgets", order_by="title_en sideways")


def test_query_applies_limit(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,start_date\nw1,A,2020\nw2,B,2021\nw3,C,2022\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets", order_by="start_date", limit=2)

    assert [r["id"] for r in rows] == ["w1", "w2"]


def test_query_missing_csv_returns_empty_list(tmp_path):
    assert query_category_rows(tmp_path, "nonexistent") == []


def test_query_unknown_filter_field_raises_clear_error(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text("id,title_en\nw1,First\n", encoding="utf-8")

    with pytest.raises(ValueError, match="widgets"):
        query_category_rows(tmp_path, "widgets", filters={"nonexistent_field": ["x"]})


def test_query_date_range_after_only(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,start_date\nw1,A,2020\nw2,B,2021\nw3,C,2022\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets", date_range=("start_date", "2021", None))

    assert sorted(r["id"] for r in rows) == ["w2", "w3"]


def test_query_date_range_before_only(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,start_date\nw1,A,2020\nw2,B,2021\nw3,C,2022\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets", date_range=("start_date", None, "2021"))

    assert sorted(r["id"] for r in rows) == ["w1", "w2"]


def test_query_date_range_both_bounds(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,start_date\nw1,A,2020\nw2,B,2021\nw3,C,2022\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets", date_range=("start_date", "2021", "2021"))

    assert [r["id"] for r in rows] == ["w2"]


def test_query_date_range_combines_with_filters(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en,status,start_date\n"
        "w1,A,draft,2020\nw2,B,published,2021\nw3,C,published,2022\n",
        encoding="utf-8",
    )

    rows = query_category_rows(
        tmp_path, "widgets",
        filters={"status": ["published"]},
        date_range=("start_date", "2021", None),
    )

    assert sorted(r["id"] for r in rows) == ["w2", "w3"]


from parcours.core.data import NotASelectQuery, format_table, run_select_query


def test_run_select_query_reads_a_category_by_name(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text(
        "id,title_en\nw1,First\nw2,Second\n", encoding="utf-8"
    )

    columns, rows = run_select_query(tmp_path, "SELECT id, title_en FROM widgets ORDER BY id")

    assert columns == ["id", "title_en"]
    assert rows == [{"id": "w1", "title_en": "First"}, {"id": "w2", "title_en": "Second"}]


def test_run_select_query_with_cte(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text("id,status\nw1,draft\nw2,published\n", encoding="utf-8")

    columns, rows = run_select_query(
        tmp_path,
        "WITH published AS (SELECT * FROM widgets WHERE status = 'published') "
        "SELECT id FROM published",
    )

    assert rows == [{"id": "w2"}]


def test_run_select_query_joins_across_two_categories(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text("id,gadget_id\nw1,g1\n", encoding="utf-8")
    (tmp_path / "entries" / "gadgets.csv").write_text("id,name\ng1,Gadget One\n", encoding="utf-8")

    columns, rows = run_select_query(
        tmp_path,
        "SELECT widgets.id, gadgets.name FROM widgets "
        "JOIN gadgets ON widgets.gadget_id = gadgets.id",
    )

    assert rows == [{"id": "w1", "name": "Gadget One"}]


def test_run_select_query_rejects_non_select_statements(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text("id,status\nw1,draft\n", encoding="utf-8")

    with pytest.raises(NotASelectQuery):
        run_select_query(tmp_path, "DELETE FROM widgets")


def test_run_select_query_rejects_update(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text("id,status\nw1,draft\n", encoding="utf-8")

    with pytest.raises(NotASelectQuery):
        run_select_query(tmp_path, "UPDATE widgets SET status = 'x'")


def test_run_select_query_leaves_the_csv_untouched(tmp_path):
    (tmp_path / "entries").mkdir()
    csv_path = tmp_path / "entries" / "widgets.csv"
    csv_path.write_text("id,status\nw1,draft\n", encoding="utf-8")
    before = csv_path.read_bytes()

    with pytest.raises(NotASelectQuery):
        run_select_query(tmp_path, "DROP TABLE widgets")

    assert csv_path.read_bytes() == before


def test_run_select_query_rejects_a_chained_second_statement(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text("id,status\nw1,draft\n", encoding="utf-8")

    with pytest.raises(NotASelectQuery):
        run_select_query(tmp_path, "SELECT * FROM widgets; DROP TABLE widgets")


def test_run_select_query_rejects_a_chained_copy_that_would_overwrite_a_real_csv(tmp_path):
    # A real, verified exploit if only the first word were checked: DuckDB's
    # execute() runs every semicolon-separated statement, so a chained COPY
    # can silently overwrite any file on disk, including another category's
    # real CSV, with no git-history undo path.
    (tmp_path / "entries").mkdir()
    csv_path = tmp_path / "entries" / "widgets.csv"
    csv_path.write_text("id,status\nw1,draft\n", encoding="utf-8")
    before = csv_path.read_bytes()
    escaped = str(csv_path).replace("'", "''")

    with pytest.raises(NotASelectQuery):
        run_select_query(
            tmp_path,
            f"SELECT 1 as x; COPY (SELECT 'PWNED' as y) TO '{escaped}'",
        )

    assert csv_path.read_bytes() == before


def test_run_select_query_tolerates_one_harmless_trailing_semicolon(tmp_path):
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text("id,status\nw1,draft\n", encoding="utf-8")

    columns, rows = run_select_query(tmp_path, "SELECT id FROM widgets;")

    assert rows == [{"id": "w1"}]


def test_run_select_query_rejects_a_with_prefixed_delete(tmp_path):
    # A real, verified bypass of a naive "first word is select/with, no
    # semicolon" check: DuckDB accepts "WITH x AS (...) DELETE ..." as a
    # single, semicolon-free statement whose real type is DELETE, not
    # SELECT. It happens to mutate nothing today only because categories
    # are DuckDB VIEWs, not base tables (DuckDB itself refuses a DELETE
    # against a view) — an incidental protection, not something the
    # SELECT-only check itself was verifying before this test existed.
    (tmp_path / "entries").mkdir()
    csv_path = tmp_path / "entries" / "widgets.csv"
    csv_path.write_text("id,status\nw1,draft\n", encoding="utf-8")
    before = csv_path.read_bytes()

    with pytest.raises(NotASelectQuery):
        run_select_query(
            tmp_path,
            "WITH x AS (SELECT 1) DELETE FROM widgets WHERE id = 'w1'",
        )

    assert csv_path.read_bytes() == before


def test_run_select_query_accepts_a_semicolon_inside_a_string_literal(tmp_path):
    # The old semicolon-counting check would have falsely rejected this
    # single, legitimate statement.
    (tmp_path / "entries").mkdir()
    (tmp_path / "entries" / "widgets.csv").write_text("id,status\nw1,draft\n", encoding="utf-8")

    columns, rows = run_select_query(tmp_path, "SELECT 'a;b' AS x")

    assert rows == [{"x": "a;b"}]


def test_format_table_aligns_columns():
    text = format_table(["id", "name"], [{"id": "w1", "name": "First"}, {"id": "w2", "name": "B"}])

    lines = text.splitlines()
    assert lines[0].startswith("id ")
    assert "w1" in lines[2]
    assert "w2" in lines[3]


def test_format_table_handles_no_rows():
    assert format_table(["id"], []) == "(no rows)"
