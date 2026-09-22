"""Reads a category's CSV via DuckDB — "SQL queries run directly on CSVs,
no import step" (SPECS.md, "Architecture overview"). Every column loads
as a string (`ALL_VARCHAR`), matching the validation/handler code, which
expects string values throughout."""

from pathlib import Path

import duckdb


def load_category_rows(data_dir: Path, category_name: str) -> list[dict]:
    csv_path = data_dir / f"{category_name}.csv"
    if not csv_path.is_file():
        return []

    connection = duckdb.connect(database=":memory:")
    try:
        result = connection.execute(
            "SELECT * FROM read_csv_auto(?, ALL_VARCHAR=TRUE)", [str(csv_path)]
        )
        columns = [description[0] for description in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]
    finally:
        connection.close()
