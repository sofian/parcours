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


def query_category_rows(
    data_dir: Path,
    category_name: str,
    filters: dict[str, list[str]] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    date_range: tuple[str, str | None, str | None] | None = None,
) -> list[dict]:
    csv_path = data_dir / f"{category_name}.csv"
    if not csv_path.is_file():
        return []

    query = "SELECT * FROM read_csv_auto(?, ALL_VARCHAR=TRUE)"
    params: list = [str(csv_path)]
    clauses: list[str] = []

    if filters:
        for field_name, allowed_values in filters.items():
            # A profile's `filter` is "simple key→value" — a scalar would
            # otherwise be iterated character-by-character below.
            if not isinstance(allowed_values, (list, tuple)):
                allowed_values = [allowed_values]
            placeholders = ", ".join("?" for _ in allowed_values)
            clauses.append(f'"{field_name}" IN ({placeholders})')
            params.extend(allowed_values)

    if date_range:
        date_field, after, before = date_range
        if after is not None:
            clauses.append(f'"{date_field}" >= ?')
            params.append(after)
        if before is not None:
            clauses.append(f'"{date_field}" <= ?')
            params.append(before)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    if order_by:
        parts = order_by.split()
        field_name = parts[0]
        direction_str = parts[1] if len(parts) > 1 else ""
        direction = direction_str.upper() if direction_str else "ASC"
        if direction not in ("ASC", "DESC"):
            raise ValueError(
                f"Invalid order_by direction '{direction_str}' for category '{category_name}' "
                "(expected 'asc' or 'desc')"
            )
        query += f' ORDER BY "{field_name}" {direction}'

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    connection = duckdb.connect(database=":memory:")
    try:
        try:
            result = connection.execute(query, params)
        except duckdb.BinderException as exc:
            raise ValueError(
                f"Invalid filter/order_by field for category '{category_name}': {exc}"
            ) from exc
        columns = [description[0] for description in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]
    finally:
        connection.close()
