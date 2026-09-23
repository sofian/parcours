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


class NotASelectQuery(Exception):
    """Raised by run_select_query when given SQL that isn't a read-only
    SELECT (or WITH ... SELECT) statement. `parco query` never mutates
    data — that stays exclusively through add/edit/delete, which
    auto-commit to git; an ad-hoc write here would touch a CSV with no
    git-history undo path."""


def run_select_query(data_dir: Path, sql: str) -> tuple[list[str], list[dict]]:
    """Runs a read-only SQL query against every category CSV in
    `data_dir`, each registered as a view named after its category
    (e.g. `FROM publications`, matching how every example in this
    project's own docs already writes it) — no `.csv` suffix, no
    quoting, and ALL_VARCHAR-typed like every other read path in this
    codebase."""
    stripped = sql.strip()
    first_word = stripped.split(None, 1)[0].lower() if stripped else ""
    if first_word not in ("select", "with"):
        raise NotASelectQuery(
            f"Only SELECT (or WITH ... SELECT) queries are allowed, got: {stripped[:50]!r}"
        )

    # DuckDB's execute() runs every statement in a semicolon-separated
    # string, so checking only the first word is NOT enough on its own —
    # verified directly: "SELECT 1; COPY (SELECT 'x') TO 'grants.csv'"
    # passes the check above and then silently overwrites a real file,
    # with no git-history undo path. A single harmless trailing `;` is
    # tolerated; anything after it is not.
    body = stripped[:-1] if stripped.endswith(";") else stripped
    if ";" in body:
        raise NotASelectQuery(
            "Only a single SELECT (or WITH ... SELECT) statement is allowed "
            "— remove the semicolon-separated second statement"
        )

    connection = duckdb.connect(database=":memory:")
    try:
        for csv_path in sorted(data_dir.glob("*.csv")):
            category_name = csv_path.stem.replace('"', '""')
            escaped_path = str(csv_path).replace("'", "''")
            connection.execute(
                f'CREATE VIEW "{category_name}" AS '
                f"SELECT * FROM read_csv_auto('{escaped_path}', ALL_VARCHAR=TRUE)"
            )

        try:
            result = connection.execute(body)
        except duckdb.Error as exc:
            raise ValueError(f"Query failed: {exc}") from exc

        columns = [description[0] for description in result.description]
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        return columns, rows
    finally:
        connection.close()


def format_table(columns: list[str], rows: list[dict]) -> str:
    """Plain column-aligned text — no DuckDB/relation dependency, so
    this works regardless of when the connection that produced `rows`
    was closed."""
    if not rows:
        return "(no rows)"

    widths = [
        max(len(col), max((len(str(row.get(col, ""))) for row in rows), default=0))
        for col in columns
    ]

    def _format_row(values) -> str:
        return " | ".join(str(v).ljust(w) for v, w in zip(values, widths))

    lines = [_format_row(columns), "-+-".join("-" * w for w in widths)]
    for row in rows:
        lines.append(_format_row([row.get(col, "") for col in columns]))
    return "\n".join(lines)
