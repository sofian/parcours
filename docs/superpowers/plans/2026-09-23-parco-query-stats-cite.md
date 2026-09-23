# parco query / stats / citation formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `parco query` (read-only ad-hoc SQL), `parco stats` (count aggregation), and `parco list --format citation` (citation formatting via citeproc-py — there is **no** standalone `parco cite` command, that was explicitly ruled out during design), plus the filtering vocabulary (`--search`/`--filter`/`--after`/`--before`) shared between `list` and `stats`.

**Architecture:** `core/data.py` gains a SELECT-only ad-hoc-query function and a date-range filter on the existing `query_category_rows`; a new `core/stats.py` aggregates already-fetched rows in Python — the same stage of the pipeline `--search`'s own substring matching already runs at (Python-side, after the SQL-side `filters`/`date_range`), rather than mixing SQL-side and Python-side aggregation; a new `core/citations.py` wraps `citeproc-py` against CSL-JSON records already resolved via the existing `PublicationsHandler`. All new CLI surface (`query`, `stats`, `list`'s new flags) lives in `cli/main.py`, reusing the existing `_find_repo_or_exit`/`_load_schema_or_exit`/category-discovery helpers rather than duplicating them.

**Tech Stack:** Python ≥3.11, DuckDB (already a dependency), PyYAML, **citeproc-py** (new dependency, `>=0.11`), pytest.

**Spec:** `SPECS.md` — see `## CLI` → `### Query`, `### Stats`, `### Filtering (shared by list and stats)`, the `--format citation` paragraphs inside `### Data entry`, and `## Citation formatting`.

## Global Constraints

- **Hexagonal split** (`CLAUDE.md`): `parcours/core/` never does interactive I/O — no `print()`, `input()`, `sys.exit()`, no `typer` import. Takes structured args, returns structured results, or raises typed exceptions. `parcours/cli/main.py` owns **all** prompts, confirmations, and output formatting.
- **No placeholders**: every step below contains real, complete code — no "TODO", no "similar to Task N", no "add appropriate error handling".
- **Commit style** (`CLAUDE.md`): short, one-line imperative messages, past tense, capitalized first letter, no body paragraphs, **no** `Co-Authored-With` lines ever.
- **YAML**: always `yaml.safe_load`/`yaml.safe_dump` — never the plain `Loader`/`Dumper`.
- **`query` is SELECT-only**: data mutation stays exclusively through `add`/`edit`/`delete`, which auto-commit to git. `query` never writes to a CSV.
- **Tests**: fixture data only, never real user data; core tests touch no git and no filesystem beyond a temp dir.
- **Model tiering** (for whoever executes this plan via SDD): Task 1 is mechanical (a small, well-specified refactor + additive change) — cheap model with careful review, since it touches shared infrastructure (`query_category_rows`) three other tasks depend on. Tasks 2 and 4 are self-contained new features with complete reference code — standard model. Task 3 integrates several pieces (shared CLI helpers + a new aggregation module) — standard model. Task 5 is the integration finale, touching the most call sites — standard model, reviewed carefully for regressions in `list`'s existing behavior.

## A note on scope, resolved during planning (read before starting Task 5)

SPECS.md's "Citation formatting" section lists `publications`/`review`/`catalog`/`press` as the v1 citekey-capable categories, and says to gate `--format citation` "the exact same check `core/build.py` already uses" — `isinstance(handler, PublicationsHandler)`. **These two statements conflict in the real code**: `publications`/`review`/`catalog` declare `handler: publications` in their schema (so `load_handler` returns a real `PublicationsHandler`, and the `isinstance` check works), but `press` declares `handler: generic` with a differently-shaped `options: {zotero: {json: ...}}` (confirmed by reading `parcours/starter_config/categories/press.yaml`) — its loaded handler is a plain `GenericHandler`, which has no `resolve()` method at all and is never an instance of `PublicationsHandler`. `press`'s Zotero capability was drafted as a `Citable` protocol in `core/handlers/base.py` (`runtime_checkable`, method `citation(self, key, style, lang) -> str`) but **no handler class implements it** — it's dead, unimplemented interface today.

**Resolution for this plan:** `--format citation` in Task 5 uses `isinstance(handler, PublicationsHandler)` exactly as instructed, which means `press` is **not** citation-capable in this first cut, narrower than SPECS.md's prose list. This is the conservative, correct-for-the-real-code choice — extending `press` support would mean either reshaping its schema to use `handler: publications` (a behavior change to an already-shipped category, out of scope here) or building the `Citable` protocol into `GenericHandler` for schemas with `options.zotero.json` (new handler-architecture work, not part of this plan's approved design). The category-discovery helper `_citation_capable_categories` (Task 5) derives its list dynamically from real schemas at runtime (never a hardcoded `["publications", "review", "catalog", "press"]` literal), so this narrowing is automatic and self-correcting the day someone actually builds `press`'s capability properly — no code here will need to change.

## A note on `parco query`'s relative-path resolution, resolved during planning

Rather than requiring users to write absolute paths or quoted `.csv` filenames in their SQL (or reaching for `os.chdir`, which has process-wide side effects unsafe for a CLI command), `run_select_query` (Task 2) registers each category's CSV as a DuckDB `VIEW` named after the category (e.g. `CREATE VIEW publications AS SELECT * FROM read_csv_auto('/abs/path/publications.csv', ALL_VARCHAR=TRUE)`) before running the user's query. This was verified directly: DuckDB does **not** resolve a bare relative filename against anything but the Python process's own cwd (confirmed: `SELECT * FROM 'widgets.csv'` fails from an unrelated cwd), and `CREATE VIEW ... AS SELECT ... FROM read_csv_auto(?, ...)` cannot take a parameterized `?` for the path (`_duckdb.BinderException: Binder Error: Unexpected prepared parameter` — DDL statements aren't preparable in this DuckDB version), so the absolute path is escaped (`'` → `''`) and interpolated into the view-creation SQL text directly — safe here because the path is built entirely from `data_dir` and a `*.csv` glob result, never from user input. This also means a user's query can write exactly what SPECS.md's/README's own examples already show — `SELECT year, count(*) FROM publications GROUP BY year`, no `.csv` suffix, no quoting — and gets `ALL_VARCHAR` typing automatically, consistent with every other read path in this codebase.

## A note on `--format table`'s rendering, resolved during planning

The original plan sketch suggested reusing DuckDB's own relation `str()` (which prints a nice box-drawing table) for `--format table`. That doesn't fit cleanly here: `run_select_query` closes its DuckDB connection before returning (matching every other function in `core/data.py`, and keeping the connection's lifetime from leaking into the CLI layer), and a DuckDB relation object is not safe to stringify after its connection closes. Task 2 instead adds a small, pure `format_table(columns, rows) -> str` to `core/data.py` — plain column-aligned text, no DuckDB/relation dependency, fully unit-testable on its own.

---

### Task 1: `CategorySchema.default_date_field()` + `query_category_rows`'s date-range filter

**Files:**
- Modify: `parcours/core/schema.py`
- Modify: `parcours/core/data.py`
- Modify: `parcours/core/init.py`
- Test: `tests/unit/test_schema.py`
- Test: `tests/unit/test_data.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `CategorySchema.default_date_field() -> str | None` (consumed by Task 3's `stats --by year` and `--after`/`--before` resolution, and by `core/init.py`'s existing section-generation code, refactored in this task to use it instead of duplicating the check). `query_category_rows(..., date_range: tuple[str, str | None, str | None] | None = None)` (consumed by Task 3 and Task 5).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_schema.py`:
```python
from parcours.core.schema import CategorySchema, FieldSpec, load_category_schema, load_all_schemas


def test_default_date_field_prefers_start_date_over_date():
    schema = CategorySchema(
        name="grants",
        fields=[FieldSpec(name="start_date", type="date"), FieldSpec(name="date", type="date")],
    )
    assert schema.default_date_field() == "start_date"


def test_default_date_field_falls_back_to_plain_date():
    schema = CategorySchema(name="artworks", fields=[FieldSpec(name="date", type="date")])
    assert schema.default_date_field() == "date"


def test_default_date_field_none_when_neither_present():
    schema = CategorySchema(name="publications", fields=[FieldSpec(name="citekey")])
    assert schema.default_date_field() is None
```
(Add this import line alongside the file's existing `from parcours.core.schema import ...` line rather than duplicating the import statement — check the file's current top-of-file import first.)

Append to `tests/unit/test_data.py`:
```python
def test_query_date_range_after_only(tmp_path):
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,start_date\nw1,A,2020\nw2,B,2021\nw3,C,2022\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets", date_range=("start_date", "2021", None))

    assert sorted(r["id"] for r in rows) == ["w2", "w3"]


def test_query_date_range_before_only(tmp_path):
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,start_date\nw1,A,2020\nw2,B,2021\nw3,C,2022\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets", date_range=("start_date", None, "2021"))

    assert sorted(r["id"] for r in rows) == ["w1", "w2"]


def test_query_date_range_both_bounds(tmp_path):
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,start_date\nw1,A,2020\nw2,B,2021\nw3,C,2022\n", encoding="utf-8"
    )

    rows = query_category_rows(tmp_path, "widgets", date_range=("start_date", "2021", "2021"))

    assert [r["id"] for r in rows] == ["w2"]


def test_query_date_range_combines_with_filters(tmp_path):
    (tmp_path / "widgets.csv").write_text(
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_schema.py tests/unit/test_data.py -v`
Expected: FAIL — `default_date_field` doesn't exist yet; `date_range` is an unexpected keyword argument.

- [ ] **Step 3: Implement `CategorySchema.default_date_field()`**

In `parcours/core/schema.py`, add this method to the `CategorySchema` dataclass (alongside `field_names`/`get_field`):
```python
    def default_date_field(self) -> str | None:
        """The field `--by year`/`--after`/`--before` treat as this
        category's one designated date — `start_date` if present (a
        range's beginning), else plain `date` (a single point in time),
        else None. The same convention `core/init.py`'s generated
        `order_by` already uses."""
        field_names = self.field_names()
        if "start_date" in field_names:
            return "start_date"
        if "date" in field_names:
            return "date"
        return None
```

- [ ] **Step 4: Implement `query_category_rows`'s `date_range` parameter**

In `parcours/core/data.py`, replace the current `query_category_rows` function with:
```python
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
```
(This is behavior-preserving for every existing caller: `filters`-only, `order_by`-only, and `limit`-only calls produce byte-identical SQL to before — only `date_range` is new. Comparing ISO partial-date strings lexicographically, e.g. `"2024-03" >= "2024-01"`, is correct for same-precision values but not reliably correct across mixed precision within one field — documented as a known limitation in this plan's closing section, not fixed here.)

- [ ] **Step 5: Refactor `core/init.py`'s `_section_order_by` to use the new method**

In `parcours/core/init.py`, replace:
```python
def _section_order_by(schema: CategorySchema) -> str | None:
    field_names = schema.field_names()
    if "start_date" in field_names:
        return "start_date desc"
    if "date" in field_names:
        return "date desc"
    return None
```
with:
```python
def _section_order_by(schema: CategorySchema) -> str | None:
    date_field = schema.default_date_field()
    return f"{date_field} desc" if date_field else None
```
(Same external behavior — `_build_sections`, its only caller, is unchanged. `CategorySchema` is already imported in this file.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/unit/test_schema.py tests/unit/test_data.py -v`
Expected: PASS (3 new schema tests, 4 new data tests)

- [ ] **Step 7: Run the full suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all prior tests plus this task's 7 new ones — pay particular attention to `tests/integration/test_init.py::test_scaffold_repo_generated_sections_use_the_generic_order_by_rule`, which exercises `_section_order_by` end-to-end and must still pass unchanged after the refactor)

- [ ] **Step 8: Commit**

```bash
git add parcours/core/schema.py parcours/core/data.py parcours/core/init.py tests/unit/test_schema.py tests/unit/test_data.py
git commit -m "Added CategorySchema.default_date_field and date-range filtering to query_category_rows"
```

---

### Task 2: `parco query` — SELECT-only ad-hoc SQL

**Files:**
- Modify: `parcours/core/data.py`
- Modify: `parcours/cli/main.py`
- Test: `tests/unit/test_data.py`
- Test: `tests/integration/test_cli_query.py`

**Interfaces:**
- Consumes: nothing new from other tasks in this plan (independent of Task 1).
- Produces: `run_select_query(data_dir: Path, sql: str) -> tuple[list[str], list[dict]]`, `NotASelectQuery` exception, `format_table(columns: list[str], rows: list[dict]) -> str` (all in `core/data.py`). The `query` Typer command.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_data.py`:
```python
from parcours.core.data import NotASelectQuery, format_table, run_select_query


def test_run_select_query_reads_a_category_by_name(tmp_path):
    (tmp_path / "widgets.csv").write_text(
        "id,title_en\nw1,First\nw2,Second\n", encoding="utf-8"
    )

    columns, rows = run_select_query(tmp_path, "SELECT id, title_en FROM widgets ORDER BY id")

    assert columns == ["id", "title_en"]
    assert rows == [{"id": "w1", "title_en": "First"}, {"id": "w2", "title_en": "Second"}]


def test_run_select_query_with_cte(tmp_path):
    (tmp_path / "widgets.csv").write_text("id,status\nw1,draft\nw2,published\n", encoding="utf-8")

    columns, rows = run_select_query(
        tmp_path,
        "WITH published AS (SELECT * FROM widgets WHERE status = 'published') "
        "SELECT id FROM published",
    )

    assert rows == [{"id": "w2"}]


def test_run_select_query_joins_across_two_categories(tmp_path):
    (tmp_path / "widgets.csv").write_text("id,gadget_id\nw1,g1\n", encoding="utf-8")
    (tmp_path / "gadgets.csv").write_text("id,name\ng1,Gadget One\n", encoding="utf-8")

    columns, rows = run_select_query(
        tmp_path,
        "SELECT widgets.id, gadgets.name FROM widgets "
        "JOIN gadgets ON widgets.gadget_id = gadgets.id",
    )

    assert rows == [{"id": "w1", "name": "Gadget One"}]


def test_run_select_query_rejects_non_select_statements(tmp_path):
    (tmp_path / "widgets.csv").write_text("id,status\nw1,draft\n", encoding="utf-8")

    with pytest.raises(NotASelectQuery):
        run_select_query(tmp_path, "DELETE FROM widgets")


def test_run_select_query_rejects_update(tmp_path):
    (tmp_path / "widgets.csv").write_text("id,status\nw1,draft\n", encoding="utf-8")

    with pytest.raises(NotASelectQuery):
        run_select_query(tmp_path, "UPDATE widgets SET status = 'x'")


def test_run_select_query_leaves_the_csv_untouched(tmp_path):
    csv_path = tmp_path / "widgets.csv"
    csv_path.write_text("id,status\nw1,draft\n", encoding="utf-8")
    before = csv_path.read_bytes()

    with pytest.raises(NotASelectQuery):
        run_select_query(tmp_path, "DROP TABLE widgets")

    assert csv_path.read_bytes() == before


def test_run_select_query_rejects_a_chained_second_statement(tmp_path):
    (tmp_path / "widgets.csv").write_text("id,status\nw1,draft\n", encoding="utf-8")

    with pytest.raises(NotASelectQuery):
        run_select_query(tmp_path, "SELECT * FROM widgets; DROP TABLE widgets")


def test_run_select_query_rejects_a_chained_copy_that_would_overwrite_a_real_csv(tmp_path):
    # A real, verified exploit if only the first word were checked: DuckDB's
    # execute() runs every semicolon-separated statement, so a chained COPY
    # can silently overwrite any file on disk, including another category's
    # real CSV, with no git-history undo path.
    csv_path = tmp_path / "widgets.csv"
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
    (tmp_path / "widgets.csv").write_text("id,status\nw1,draft\n", encoding="utf-8")

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
    csv_path = tmp_path / "widgets.csv"
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
    (tmp_path / "widgets.csv").write_text("id,status\nw1,draft\n", encoding="utf-8")

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
```
Create `tests/integration/test_cli_query.py`:
```python
from typer.testing import CliRunner

from parcours.cli.main import app

runner = CliRunner()


def _setup_data_repo(tmp_path):
    (tmp_path / "parco.yaml").write_text("name: test-repo\n")
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nw1,First,draft\nw2,Second,published\n", encoding="utf-8"
    )
    return tmp_path


def test_query_prints_a_table_by_default(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["query", "SELECT id, title_en FROM widgets ORDER BY id"])

    assert result.exit_code == 0, result.stdout
    assert "First" in result.stdout
    assert "Second" in result.stdout


def test_query_format_csv(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["query", "SELECT id, status FROM widgets ORDER BY id", "--format", "csv"]
    )

    assert result.exit_code == 0, result.stdout
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "id,status"
    assert lines[1] == "w1,draft"


def test_query_format_json(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["query", "SELECT id FROM widgets WHERE id = 'w1'", "--format", "json"]
    )

    assert result.exit_code == 0, result.stdout
    assert '"id": "w1"' in result.stdout


def test_query_rejects_non_select_with_exit_code_2(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["query", "DELETE FROM widgets"])

    assert result.exit_code == 2
    assert "SELECT" in result.stdout


def test_query_rejects_unknown_format(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["query", "SELECT id FROM widgets", "--format", "xml"]
    )

    assert result.exit_code == 2
    assert "table" in result.stdout.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_data.py tests/integration/test_cli_query.py -v`
Expected: FAIL — `run_select_query`/`format_table`/`NotASelectQuery` don't exist; no `query` command registered.

- [ ] **Step 3: Implement `run_select_query` and `format_table` in `core/data.py`**

Add these imports to the existing import block at the top of `parcours/core/data.py`:
```python
from pathlib import Path

import duckdb
```
(already present — no change needed there). Append to the end of the file:
```python
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
    connection = duckdb.connect(database=":memory:")
    try:
        # A naive "does the string start with select/with, and does it
        # contain a semicolon" check was tried and replaced: it let
        # "WITH x AS (SELECT 1) DELETE FROM widgets WHERE id='w1'" through
        # (first word "with", no `;`) even though DuckDB parses it as a
        # DELETE statement, not a SELECT — verified live. It also
        # falsely rejected a harmless `;` inside a string literal or SQL
        # comment (e.g. `SELECT 'a;b'`). `extract_statements` is a real
        # parse (verified: it does NOT require the referenced tables/
        # views to exist yet, so this runs before the views below are
        # created) that reports the true statement count and each
        # statement's real type — one mechanism replaces both ad-hoc
        # string checks and closes the false negative and both false
        # positives at once.
        try:
            statements = connection.extract_statements(sql)
        except duckdb.Error as exc:
            raise NotASelectQuery(f"Could not parse query: {exc}") from exc

        if len(statements) != 1:
            raise NotASelectQuery(
                f"Only a single SELECT (or WITH ... SELECT) statement is allowed, "
                f"got {len(statements)} statements"
            )
        if statements[0].type != duckdb.StatementType.SELECT:
            raise NotASelectQuery(
                "Only SELECT (or WITH ... SELECT) queries are allowed, got a "
                f"{statements[0].type} statement"
            )

        for csv_path in sorted(data_dir.glob("*.csv")):
            category_name = csv_path.stem.replace('"', '""')
            escaped_path = str(csv_path).replace("'", "''")
            connection.execute(
                f'CREATE VIEW "{category_name}" AS '
                f"SELECT * FROM read_csv_auto('{escaped_path}', ALL_VARCHAR=TRUE)"
            )

        try:
            result = connection.execute(sql)
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
```

- [ ] **Step 4: Add the `query` command to `parcours/cli/main.py`**

Add these imports to the top-of-file import block:
```python
import csv
import json
import sys
```
and add to the existing `from ..core.data import ...` line (currently `from ..core.data import load_category_rows`):
```python
from ..core.data import (
    NotASelectQuery,
    format_table,
    load_category_rows,
    query_category_rows,
    run_select_query,
)
```
(`query_category_rows` is imported here in anticipation of Task 3/5's needs in this same file — importing it now is harmless even though this task doesn't call it yet; if your project's linting flags unused imports, it's fine to add it in Task 3 instead — but importing it now avoids a diff churn later. Either is acceptable; pick one and be consistent.)

Append this command (after `lint`, before `list_command` — order in the file doesn't affect behavior, this placement just keeps read-only commands grouped):
```python
def _print_csv(columns: list[str], rows: list[dict]) -> None:
    writer = csv.writer(sys.stdout)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(col, "") for col in columns])


@app.command()
def query(
    sql: str = typer.Argument(..., help="A SELECT (or WITH...SELECT) query, e.g. \"SELECT year, count(*) FROM publications GROUP BY year\""),
    fmt: str = typer.Option("table", "--format", help="Output format: table, csv, or json"),
):
    """Run a read-only SQL query directly against your category CSVs."""
    data_dir = _find_repo_or_exit()

    if fmt not in ("table", "csv", "json"):
        typer.echo(f"Unknown format: '{fmt}' (expected table, csv, or json)")
        raise typer.Exit(code=2)

    try:
        columns, rows = run_select_query(data_dir, sql)
    except NotASelectQuery as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    if fmt == "table":
        typer.echo(format_table(columns, rows))
    elif fmt == "csv":
        _print_csv(columns, rows)
    else:
        typer.echo(json.dumps(rows, indent=2))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_data.py tests/integration/test_cli_query.py -v`
Expected: PASS (13 new unit tests, 5 new integration tests)

- [ ] **Step 6: Run the full suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all prior tests plus this task's new ones)

- [ ] **Step 7: Commit**

```bash
git add parcours/core/data.py parcours/cli/main.py tests/unit/test_data.py tests/integration/test_cli_query.py
git commit -m "Added parco query: SELECT-only ad-hoc SQL against category CSVs"
```

---

### Task 3: Shared filtering helpers + `parco stats`

**Files:**
- Create: `parcours/core/stats.py`
- Modify: `parcours/cli/main.py`
- Test: `tests/unit/test_stats.py`
- Test: `tests/integration/test_cli_stats.py`

**Interfaces:**
- Consumes: `CategorySchema.default_date_field()` and `query_category_rows(..., date_range=...)` (Task 1), `search_rows` (existing, `cli/wizard.py`).
- Produces: `aggregate_counts(schema, rows, by) -> list[tuple[str, int]]` and `UnknownStatsField` (in `core/stats.py`). CLI-layer helpers `_parse_filter_flags` and `_resolve_date_range` (in `cli/main.py`) — Task 5 reuses both of these for `list`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_stats.py`:
```python
import pytest

from parcours.core.schema import CategorySchema, FieldSpec
from parcours.core.stats import UnknownStatsField, aggregate_counts


def _schema():
    return CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="status", required=True),
            FieldSpec(name="start_date", type="date"),
        ],
    )


def test_aggregates_by_a_plain_field():
    rows = [
        {"status": "draft"}, {"status": "published"}, {"status": "published"},
    ]

    counts = aggregate_counts(_schema(), rows, "status")

    assert counts == [("draft", 1), ("published", 2)]


def test_aggregates_blank_values_under_a_labeled_group():
    rows = [{"status": "draft"}, {"status": ""}]

    counts = aggregate_counts(_schema(), rows, "status")

    assert ("(blank)", 1) in counts


def test_aggregates_by_year_extracted_from_the_date_field():
    rows = [
        {"start_date": "2024-01"}, {"start_date": "2024-09"}, {"start_date": "2020"},
    ]

    counts = aggregate_counts(_schema(), rows, "year")

    assert counts == [("2020", 1), ("2024", 2)]


def test_by_year_ignores_unparseable_dates_rather_than_crashing():
    rows = [{"start_date": "2024-01"}, {"start_date": "not-a-date"}, {"start_date": ""}]

    counts = aggregate_counts(_schema(), rows, "year")

    assert counts == [("2024", 1)]


def test_by_year_raises_when_category_has_no_date_field():
    schema = CategorySchema(name="skills", fields=[FieldSpec(name="name")])

    with pytest.raises(UnknownStatsField):
        aggregate_counts(schema, [{"name": "Python"}], "year")


def test_unknown_field_raises():
    with pytest.raises(UnknownStatsField):
        aggregate_counts(_schema(), [{"status": "draft"}], "nonexistent")


def test_results_are_sorted_by_group_value():
    rows = [{"status": "published"}, {"status": "draft"}, {"status": "accepted"}]

    counts = aggregate_counts(_schema(), rows, "status")

    assert [value for value, _ in counts] == ["accepted", "draft", "published"]
```

Create `tests/integration/test_cli_stats.py`:
```python
from typer.testing import CliRunner

from parcours.cli.main import app

runner = CliRunner()


def _setup_data_repo(tmp_path):
    (tmp_path / "parco.yaml").write_text("name: test-repo\n")
    (tmp_path / "categories").mkdir()
    (tmp_path / "categories" / "publications.yaml").write_text("""
name: publications
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en, required: true}
  - {name: status, required: true}
  - {name: start_date, type: date, precision: year}
""")
    (tmp_path / "vocab.yaml").write_text("{}\n")
    (tmp_path / "translations.csv").write_text("id,category,en,fr\n")
    (tmp_path / "publications.csv").write_text(
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

    result = runner.invoke(app, ["stats", "publications", "--by", "status"])

    assert result.exit_code == 0, result.stdout
    assert "published: 2" in result.stdout
    assert "under-review: 1" in result.stdout


def test_stats_counts_by_year(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["stats", "publications", "--by", "year"])

    assert result.exit_code == 0, result.stdout
    assert "2020: 2" in result.stdout
    assert "2024: 1" in result.stdout


def test_stats_applies_filter_before_counting(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["stats", "publications", "--by", "year", "--filter", "status=published"]
    )

    assert result.exit_code == 0, result.stdout
    assert "2020: 2" in result.stdout
    assert "2024" not in result.stdout


def test_stats_applies_search(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["stats", "publications", "--by", "status", "--search", "First"])

    assert result.exit_code == 0, result.stdout
    assert "published: 1" in result.stdout
    assert "under-review" not in result.stdout


def test_stats_applies_after_before(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["stats", "publications", "--by", "status", "--after", "2021"]
    )

    assert result.exit_code == 0, result.stdout
    assert "under-review: 1" in result.stdout
    assert "published" not in result.stdout


def test_stats_unknown_field_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["stats", "publications", "--by", "nonexistent"])

    assert result.exit_code == 2
    assert "Unknown field" in result.stdout


def test_stats_bad_filter_syntax_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["stats", "publications", "--by", "status", "--filter", "not-a-key-value-pair"]
    )

    assert result.exit_code == 2
    assert "field=value" in result.stdout


def test_stats_unknown_filter_field_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["stats", "publications", "--by", "status", "--filter", "nonexistent=x"]
    )

    assert result.exit_code == 2
    assert "Unknown field" in result.stdout


def test_stats_with_no_category_shows_a_real_error_and_available_categories(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["stats", "--by", "status"])

    assert result.exit_code == 2
    assert "required" in result.stdout.lower()
    assert "publications" in result.stdout


def test_stats_no_matching_rows_reports_no_entries(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["stats", "publications", "--by", "status", "--search", "nonexistent"]
    )

    assert result.exit_code == 0
    assert "No entries found" in result.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_stats.py tests/integration/test_cli_stats.py -v`
Expected: FAIL — `core.stats` module doesn't exist; no `stats` command registered.

- [ ] **Step 3: Create `parcours/core/stats.py`**

```python
"""Count-only aggregation for `parco stats` (see SPECS.md, "CLI" ->
"Stats"). Takes rows already fetched and filtered (via
`query_category_rows` and, for free-text search, `cli/wizard.py`'s
`search_rows`) and aggregates them in Python — one consistent
fetch-then-filter-then-aggregate pipeline rather than mixing SQL-side
and Python-side stages, since `--search` is already Python-side.
Core layer: no printing, no prompting."""

from collections import Counter

from .dates import InvalidDateError, parse_partial_date
from .schema import CategorySchema


class UnknownStatsField(Exception):
    """Raised when `--by` names a field that isn't in the category's
    schema, or is the literal "year" for a category with no
    `default_date_field()`."""


def aggregate_counts(schema: CategorySchema, rows: list[dict], by: str) -> list[tuple[str, int]]:
    if by == "year":
        date_field = schema.default_date_field()
        if date_field is None:
            raise UnknownStatsField(f"'{schema.name}' has no date field to group by year")
        counter: Counter = Counter()
        for row in rows:
            value = row.get(date_field)
            if not value:
                continue
            try:
                counter[str(parse_partial_date(value).year)] += 1
            except InvalidDateError:
                continue
        return sorted(counter.items(), key=lambda pair: pair[0])

    if schema.get_field(by) is None:
        raise UnknownStatsField(f"Unknown field '{by}' for category '{schema.name}'")

    counter = Counter(row.get(by) or "(blank)" for row in rows)
    return sorted(counter.items(), key=lambda pair: pair[0])
```

- [ ] **Step 4: Add the shared filtering helpers and the `stats` command to `parcours/cli/main.py`**

Add to the existing `from ..core.data import (...)` block (from Task 2): add `query_category_rows` if it isn't already there (it was added preemptively in Task 2 — confirm it's present, don't duplicate the import).

Add a new import line:
```python
from ..core.stats import UnknownStatsField, aggregate_counts
```

Add these two shared helpers near `_load_schema_or_exit`/`_require_category_or_exit`:
```python
def _parse_filter_flags(schema: CategorySchema, filter_flags: list[str]) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for flag in filter_flags:
        if "=" not in flag:
            typer.echo(f"Invalid --filter '{flag}' (expected field=value)")
            raise typer.Exit(code=2)
        field_name, value = flag.split("=", 1)
        if schema.get_field(field_name) is None:
            typer.echo(f"Unknown field: '{field_name}'")
            raise typer.Exit(code=2)
        filters.setdefault(field_name, []).append(value)
    return filters


def _resolve_date_range(
    schema: CategorySchema, after: str | None, before: str | None
) -> tuple[str, str | None, str | None] | None:
    if after is None and before is None:
        return None
    date_field = schema.default_date_field()
    if date_field is None:
        typer.echo(f"'{schema.name}' has no date field to filter on with --after/--before.")
        raise typer.Exit(code=2)
    return (date_field, after, before)
```

Append the `stats` command (after `query`, before `list_command`):
```python
@app.command()
def stats(
    category: str = typer.Argument(None, help="Category to aggregate"),
    by: str = typer.Option(..., "--by", help="Field to group by, or 'year' for the category's date field"),
    search: str = typer.Option(None, "--search", help="Only count entries matching this text"),
    filter_flags: list[str] = typer.Option(None, "--filter", help="field=value, repeatable"),
    after: str = typer.Option(None, "--after", help="Inclusive lower bound on the category's date field"),
    before: str = typer.Option(None, "--before", help="Inclusive upper bound on the category's date field"),
):
    """Count entries in a category, grouped by a field (or 'year')."""
    data_dir = _find_repo_or_exit()
    schema = _require_category_or_exit(data_dir, category)

    filters = _parse_filter_flags(schema, filter_flags or [])
    date_range = _resolve_date_range(schema, after, before)

    rows = query_category_rows(data_dir, category, filters=filters, date_range=date_range)
    if search:
        rows = search_rows(rows, search)

    try:
        counts = aggregate_counts(schema, rows, by)
    except UnknownStatsField as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    if not counts:
        typer.echo("No entries found.")
        raise typer.Exit(code=0)

    for value, count in counts:
        typer.echo(f"{value}: {count}")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_stats.py tests/integration/test_cli_stats.py -v`
Expected: PASS (7 new unit tests, 10 new integration tests)

- [ ] **Step 6: Run the full suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all prior tests plus this task's new ones)

- [ ] **Step 7: Commit**

```bash
git add parcours/core/stats.py parcours/cli/main.py tests/unit/test_stats.py tests/integration/test_cli_stats.py
git commit -m "Added parco stats with the shared --search/--filter/--after/--before filtering"
```

---

### Task 4: citeproc-py foundation — bundled CSL styles + `core/citations.py`

**Files:**
- Modify: `pyproject.toml`
- Create: `parcours/starter_config/csl_styles/apa.csl` (downloaded, real content — see Step 3)
- Create: `parcours/starter_config/csl_styles/chicago-author-date.csl` (downloaded, real content)
- Create: `parcours/starter_config/csl_styles/modern-language-association.csl` (downloaded, real content)
- Create: `parcours/core/citations.py`
- Test: `tests/unit/test_citations.py`

**Interfaces:**
- Consumes: nothing from other tasks in this plan (independent).
- Produces: `render_citations(records, style_path) -> list[str]`, `resolve_style(style_name_or_path) -> Path`, `UnknownCitationStyle` (in `core/citations.py`). Consumed by Task 5.

This task adds `citeproc-py` as a real dependency — **verified against the actually-installed package** (not assumed): its real top-level API is `from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle` and `from citeproc.source.json import CiteProcJSON`; `CitationStylesStyle(path, validate=False)` needs no separate schema files; `CitationStylesBibliography(style, source, formatter_module)` takes a *module* (or module-like object) exposing `preformat(text)` and `Italic`/`Bold`/`Oblique`/`Light`/`Underline`/`Superscript`/`Subscript`/`SmallCaps` — confirmed by reading `citeproc/formatter/html.py`'s real source. `citeproc-py` ships **no** Markdown formatter (only `.plain`, `.html`, `.rst` — `.rst` uses Sphinx role syntax, not real Markdown), so this task writes a small custom one. Registering `Citation`s in a specific order and calling `bibliography()` afterward **preserves that registration order** (verified directly: registering "zzz2020" then "aaa2024" printed "zzz" first, not re-sorted alphabetically) — this matters for Task 5, which must print citations in the same order `list` already determined.

- [ ] **Step 1: Add the `citeproc-py` dependency**

In `pyproject.toml`, replace:
```toml
dependencies = [
    "typer>=0.12",
    "duckdb>=1.0",
    "pyyaml>=6.0",
    "platformdirs>=4.0",
    "rendercv[full]>=2.8",
]
```
with:
```toml
dependencies = [
    "typer>=0.12",
    "duckdb>=1.0",
    "pyyaml>=6.0",
    "platformdirs>=4.0",
    "rendercv[full]>=2.8",
    "citeproc-py>=0.11",
]
```
and replace:
```toml
[tool.setuptools.package-data]
parcours = ["starter_config/**/*.yaml", "starter_config/**/*.csv"]
```
with:
```toml
[tool.setuptools.package-data]
parcours = ["starter_config/**/*.yaml", "starter_config/**/*.csv", "starter_config/csl_styles/**/*.csl"]
```

Install it into the venv: `pip install -e ".[dev]"` (this pulls in `citeproc-py`, confirmed to also install `lxml` as its own dependency).

- [ ] **Step 2: Download the three real bundled CSL style files**

These are real files from the canonical `citation-style-language/styles` GitHub repository — confirmed these exact URLs resolve (HTTP 200) by fetching them directly. Do not fabricate or hand-write CSL XML content; download the real files:
```bash
mkdir -p parcours/starter_config/csl_styles
curl -sL -o parcours/starter_config/csl_styles/apa.csl \
  https://raw.githubusercontent.com/citation-style-language/styles/master/apa.csl
curl -sL -o parcours/starter_config/csl_styles/chicago-author-date.csl \
  https://raw.githubusercontent.com/citation-style-language/styles/master/chicago-author-date.csl
curl -sL -o parcours/starter_config/csl_styles/modern-language-association.csl \
  https://raw.githubusercontent.com/citation-style-language/styles/master/modern-language-association.csl
```
(Note: MLA's real filename in the upstream repo is `modern-language-association.csl`, not `mla.csl` — the short user-facing name `mla` is mapped to this filename in `core/citations.py`'s `_BUNDLED_STYLES` dict below, so nobody ever has to type the long name.) Verify each file downloaded successfully and looks like real CSL XML (starts with `<?xml version="1.0"...` and contains a `<style` root element) before proceeding — a failed download would silently produce an empty or HTML-error-page file that breaks Step 5's tests in a confusing way.

- [ ] **Step 3: Write the failing tests**

Create `tests/unit/test_citations.py`:
```python
from pathlib import Path

import pytest

from parcours.core.citations import UnknownCitationStyle, render_citations, resolve_style

_BUNDLED_STYLES_DIR = Path(__file__).parent.parent.parent / "parcours" / "starter_config" / "csl_styles"


def _widget_record(citekey="doe2024widgets"):
    return {
        "id": citekey,
        "type": "article-journal",
        "title": "On Widgets",
        "author": [{"given": "Jane", "family": "Doe"}],
        "container-title": "Journal of Widgets",
        "issued": {"date-parts": [[2024, 3]]},
        "volume": "12",
        "page": "1-20",
    }


def test_resolve_style_maps_bundled_short_names():
    assert resolve_style("apa") == _BUNDLED_STYLES_DIR / "apa.csl"
    assert resolve_style("chicago-author-date") == _BUNDLED_STYLES_DIR / "chicago-author-date.csl"
    assert resolve_style("mla") == _BUNDLED_STYLES_DIR / "modern-language-association.csl"


def test_resolve_style_accepts_a_custom_path(tmp_path):
    custom = tmp_path / "custom.csl"
    custom.write_text("<style/>", encoding="utf-8")

    assert resolve_style(str(custom)) == custom


def test_resolve_style_rejects_an_unknown_name_or_missing_path():
    with pytest.raises(UnknownCitationStyle):
        resolve_style("not-a-real-style-or-path")


def test_render_citations_apa_italicizes_the_journal_title_as_markdown():
    style_path = resolve_style("apa")

    citations = render_citations([_widget_record()], style_path)

    assert len(citations) == 1
    assert "*Journal of Widgets*" in citations[0]
    assert "Doe" in citations[0]
    assert "2024" in citations[0]
    assert "<i>" not in citations[0]


def test_render_citations_preserves_registration_order():
    style_path = resolve_style("apa")
    records = [
        {
            "id": "zzz2020", "type": "article-journal", "title": "Zebra Study",
            "author": [{"given": "A", "family": "Zed"}], "container-title": "J",
            "issued": {"date-parts": [[2020]]},
        },
        {
            "id": "aaa2024", "type": "article-journal", "title": "Aardvark Study",
            "author": [{"given": "B", "family": "Aab"}], "container-title": "J",
            "issued": {"date-parts": [[2024]]},
        },
    ]

    citations = render_citations(records, style_path)

    assert "Zebra" in citations[0]
    assert "Aardvark" in citations[1]


def test_render_citations_empty_list_returns_empty_list():
    assert render_citations([], resolve_style("apa")) == []
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `pytest tests/unit/test_citations.py -v`
Expected: FAIL — `parcours.core.citations` doesn't exist yet.

- [ ] **Step 5: Create `parcours/core/citations.py`**

```python
"""Renders CSL-JSON records (already resolved via
`handlers.publications.PublicationsHandler.resolve`) as formatted
citations via citeproc-py (see SPECS.md, "Citation formatting"). Core
layer: no prompting, no printing — the CLI `list --format citation`
command owns all output."""

from pathlib import Path

from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle
from citeproc.source.json import CiteProcJSON

_BUNDLED_STYLES = {
    "apa": "apa.csl",
    "chicago-author-date": "chicago-author-date.csl",
    "mla": "modern-language-association.csl",
}


class UnknownCitationStyle(Exception):
    """Raised by resolve_style when given neither a bundled short name
    nor an existing .csl file path."""


def _starter_config_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "starter_config"


def resolve_style(style_name_or_path: str) -> Path:
    bundled_filename = _BUNDLED_STYLES.get(style_name_or_path)
    if bundled_filename:
        return _starter_config_dir() / "csl_styles" / bundled_filename

    path = Path(style_name_or_path)
    if not path.is_file():
        raise UnknownCitationStyle(
            f"Unknown citation style: '{style_name_or_path}' "
            f"(expected one of {', '.join(_BUNDLED_STYLES)}, or a path to a .csl file)"
        )
    return path


class _MarkdownFormatter:
    """citeproc-py ships no Markdown formatter (only .plain/.html/.rst;
    .rst uses Sphinx role syntax, not real Markdown) — this mirrors the
    exact shape citeproc.formatter.html exposes, verified against its
    real source, swapping HTML tags for `*italic*`/`**bold**`."""

    @staticmethod
    def preformat(text):
        return str(text)

    class Italic(str):
        def __new__(cls, text):
            return super().__new__(cls, "*{}*".format(text))

    class Bold(str):
        def __new__(cls, text):
            return super().__new__(cls, "**{}**".format(text))

    Oblique = Italic
    Light = str
    Underline = str

    class Superscript(str):
        def __new__(cls, text):
            return super().__new__(cls, "^{}^".format(text))

    class Subscript(str):
        def __new__(cls, text):
            return super().__new__(cls, "~{}~".format(text))

    SmallCaps = str


def render_citations(records: list[dict], style_path: Path) -> list[str]:
    """Renders each CSL-JSON record in `records`, in the given order,
    as a formatted citation string. `records` must already be resolved
    (e.g. via `PublicationsHandler.resolve`) — callers are responsible
    for only passing records that exist."""
    if not records:
        return []

    bib_source = CiteProcJSON(records)
    style = CitationStylesStyle(str(style_path), validate=False)
    bibliography = CitationStylesBibliography(style, bib_source, _MarkdownFormatter)

    for record in records:
        citation = Citation([CitationItem(record["id"])])
        bibliography.register(citation)
        bibliography.cite(citation, lambda undefined_keys: None)

    return [str(item) for item in bibliography.bibliography()]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/unit/test_citations.py -v`
Expected: PASS (6 tests — this is a real functional test against the actually-downloaded `apa.csl`, not mocked, so a failure here likely means Step 2's download didn't work correctly; re-verify the downloaded files if this fails)

- [ ] **Step 7: Run the full suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all prior tests plus this task's 6 new ones)

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml parcours/starter_config/csl_styles parcours/core/citations.py tests/unit/test_citations.py
git commit -m "Added citeproc-py citation rendering with bundled CSL styles"
```

---

### Task 5: `parco list --format citation` + filtering wired onto `list`

**Files:**
- Modify: `parcours/core/repo.py`
- Modify: `parcours/cli/main.py`
- Test: `tests/unit/test_repo.py`
- Test: `tests/integration/test_cli_list.py`

**Interfaces:**
- Consumes: `render_citations`/`resolve_style`/`UnknownCitationStyle` (Task 4), `_parse_filter_flags`/`_resolve_date_range` (Task 3), `query_category_rows` (Task 1/existing), `PublicationsHandler` (existing, `core/handlers/publications.py`), `load_handler`/`HandlerContext` (existing, already imported in `cli/main.py`).
- Produces: `load_repo_config(data_dir) -> dict` (in `core/repo.py`). The final, fully-wired `list` command.

This is the integration finale — read this plan's "A note on scope, resolved during planning" section again before starting: `--format citation` uses `isinstance(handler, PublicationsHandler)`, which covers `publications`/`review`/`catalog` but **not** `press` in the real, current code (`press` uses `handler: generic`) — this is intentional, not a bug to fix here.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_repo.py` (check the file's existing imports first and extend them rather than duplicating):
```python
from parcours.core.repo import load_repo_config


def test_load_repo_config_reads_parco_yaml(tmp_path):
    (tmp_path / "parco.yaml").write_text("citation_style: chicago-author-date\n", encoding="utf-8")

    config = load_repo_config(tmp_path)

    assert config == {"citation_style": "chicago-author-date"}


def test_load_repo_config_missing_file_returns_empty_dict(tmp_path):
    assert load_repo_config(tmp_path) == {}


def test_load_repo_config_empty_file_returns_empty_dict(tmp_path):
    (tmp_path / "parco.yaml").write_text("", encoding="utf-8")

    assert load_repo_config(tmp_path) == {}
```

Append to `tests/integration/test_cli_list.py`:
```python
def _setup_publications_repo(tmp_path):
    (tmp_path / "parco.yaml").write_text("name: test-repo\n")
    (tmp_path / "categories").mkdir()
    (tmp_path / "categories" / "publications.yaml").write_text("""
name: publications
handler: publications
options:
  json: zotero/library.json
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
    (tmp_path / "translations.csv").write_text("id,category,en,fr\n")
    (tmp_path / "widgets.csv").write_text("id,title_en\nw1,A Widget\n", encoding="utf-8")
    (tmp_path / "publications.csv").write_text(
        "id,citekey\np1,doe2024widgets\np2,nonexistent-key\n", encoding="utf-8"
    )
    (tmp_path / "zotero").mkdir()
    (tmp_path / "zotero" / "library.json").write_text("""[
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
    assert "not found in Zotero" in result.stdout


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


def test_list_format_citation_reads_default_style_from_parco_yaml(tmp_path, monkeypatch):
    repo = _setup_publications_repo(tmp_path)
    (repo / "parco.yaml").write_text("citation_style: chicago-author-date\n")
    monkeypatch.chdir(repo)

    result = runner.invoke(
        app, ["list", "publications", "--format", "citation", "--search", "doe2024widgets"]
    )

    assert result.exit_code == 0, result.stdout
    assert "Doe" in result.stdout


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


def test_list_after_before(tmp_path, monkeypatch):
    repo = _setup_ordering_repo(tmp_path)
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
```
(These new tests reuse `_setup_ordering_repo` and `_setup_data_repo`, already defined earlier in this same file from prior tasks — do not redefine them.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_repo.py tests/integration/test_cli_list.py -v`
Expected: FAIL — `load_repo_config` doesn't exist; `list` has no `--format`/`--filter`/`--after`/`--before`/`--style` flags yet.

- [ ] **Step 3: Add `load_repo_config` to `parcours/core/repo.py`**

Append to `parcours/core/repo.py`:
```python
def load_repo_config(data_dir: Path) -> dict:
    """Reads `parco.yaml`'s own content (distinct from just checking it
    exists, which `find_data_repo` already does) — e.g. `citation_style`
    for `list --format citation`'s default. Returns {} if the file is
    missing or empty, never raises."""
    config_path = data_dir / MARKER_FILENAME
    if not config_path.is_file():
        return {}
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
```

- [ ] **Step 4: Wire `--format citation`/`--style`/`--filter`/`--after`/`--before` into `list_command`**

Add to the existing `from ..core.repo import DataRepoNotFound, find_data_repo` line in `cli/main.py`:
```python
from ..core.repo import DataRepoNotFound, find_data_repo, load_repo_config
```
Add a new import:
```python
from ..core.citations import UnknownCitationStyle, render_citations, resolve_style
```
Add `PublicationsHandler` to the existing handler imports (check what's already imported from `..core.handlers` and `..core.handlers.publications` — `load_handler`/`HandlerContext` are already imported; add):
```python
from ..core.handlers.publications import PublicationsHandler
```

Replace the existing `list_command` function entirely with:
```python
@app.command(name="list")
def list_command(
    category: str = typer.Argument(None, help="Category to list (omit to see available categories)"),
    search: str = typer.Option(None, "--search", help="Only show entries matching this text"),
    order_by: str = typer.Option(None, "--order-by", help="Sort by this field"),
    desc: bool = typer.Option(False, "--desc", help="Sort descending (requires --order-by)"),
    filter_flags: list[str] = typer.Option(None, "--filter", help="field=value, repeatable"),
    after: str = typer.Option(None, "--after", help="Inclusive lower bound on the category's date field"),
    before: str = typer.Option(None, "--before", help="Inclusive upper bound on the category's date field"),
    fmt: str = typer.Option("table", "--format", help="Output format: table or citation"),
    style: str = typer.Option(None, "--style", help="Citation style: apa, chicago-author-date, mla, or a path to a .csl file"),
):
    """List entries in a category, optionally filtered/sorted, as summaries or citations."""
    data_dir = _find_repo_or_exit()

    if category is None:
        _print_available_categories(data_dir)
        raise typer.Exit(code=0)

    schema = _load_schema_or_exit(data_dir, category)

    if fmt not in ("table", "citation"):
        typer.echo(f"Unknown format: '{fmt}' (expected table or citation)")
        raise typer.Exit(code=2)

    handler = None
    if fmt == "citation":
        handler = load_handler(schema, HandlerContext(data_dir=data_dir))
        if not isinstance(handler, PublicationsHandler):
            capable = _citation_capable_categories(data_dir)
            typer.echo(
                f"'{category}' doesn't support --format citation. "
                f"Categories that do: {', '.join(capable) or '(none configured)'}"
            )
            raise typer.Exit(code=2)

    if desc and not order_by:
        typer.echo("--desc requires --order-by")
        raise typer.Exit(code=2)
    if order_by and schema.get_field(order_by) is None:
        typer.echo(f"Unknown field: '{order_by}'")
        raise typer.Exit(code=2)

    filters = _parse_filter_flags(schema, filter_flags or [])
    date_range = _resolve_date_range(schema, after, before)

    rows = query_category_rows(data_dir, category, filters=filters, date_range=date_range)
    if search:
        rows = search_rows(rows, search)
    if order_by:
        rows = order_rows(schema, rows, order_by, descending=desc)

    if not rows:
        typer.echo("No entries found.")
        raise typer.Exit(code=0)

    if fmt == "citation":
        _print_citations(data_dir, rows, handler, style)
        return

    extra_fields = [order_by] if order_by else None
    for row in rows:
        typer.echo(row_summary(schema, row, extra_fields=extra_fields))


def _citation_capable_categories(data_dir: Path) -> list[str]:
    capable = []
    for name, category_schema in sorted(load_all_schemas(data_dir / "categories").items()):
        category_handler = load_handler(category_schema, HandlerContext(data_dir=data_dir))
        if isinstance(category_handler, PublicationsHandler):
            capable.append(name)
    return capable


def _print_citations(
    data_dir: Path, rows: list[dict], handler: PublicationsHandler, style: str | None
) -> None:
    style_name = style or load_repo_config(data_dir).get("citation_style", "apa")
    try:
        style_path = resolve_style(style_name)
    except UnknownCitationStyle as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    resolved_records = []
    row_has_record = []
    for row in rows:
        citekey = row.get("citekey") or ""
        record = handler.resolve(citekey) if citekey else None
        row_has_record.append(record is not None)
        if record is not None:
            resolved_records.append(record)

    citations = iter(render_citations(resolved_records, style_path))
    for row, has_record in zip(rows, row_has_record):
        if has_record:
            typer.echo(next(citations))
        else:
            typer.echo(f"[citekey '{row.get('citekey', '')}' not found in Zotero]")
```
(This replaces the row-fetching call from `load_category_rows(data_dir, category)` to `query_category_rows(data_dir, category, filters=filters, date_range=date_range)` — behaviorally identical to the old call when `filters`/`date_range` are both empty/`None`, since `query_category_rows` with no optional arguments runs the exact same unfiltered `SELECT * FROM read_csv_auto(...)` as `load_category_rows`. `load_category_rows` itself stays imported and unchanged for `add`/`edit`/`delete`'s continued use.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_repo.py tests/integration/test_cli_list.py -v`
Expected: PASS (3 new repo tests, 9 new list tests, plus every pre-existing `test_cli_list.py` test still passing unchanged)

- [ ] **Step 6: Run the full suite to verify everything passes**

Run: `pytest tests/ -v`
Expected: PASS (every test across every task in every plan this session)

- [ ] **Step 7: Commit**

```bash
git add parcours/core/repo.py parcours/cli/main.py tests/unit/test_repo.py tests/integration/test_cli_list.py
git commit -m "Wired --format citation and shared filtering onto parco list"
```

---

## What this plan deliberately does not cover

- `query`'s citation-format support — only `list` gets `--format citation`, per the approved design (`query` is raw SQL with no schema/handler awareness to resolve a citekey against).
- `press`'s citation support — `press` uses `handler: generic` with a differently-shaped Zotero `options` block, so `isinstance(handler, PublicationsHandler)` doesn't cover it (see this plan's "A note on scope" section). Extending it needs either a schema change to `press` or building the already-drafted-but-unimplemented `Citable` protocol into `GenericHandler` — neither is part of this plan.
- `artworks`' `person_list`-based citation synthesis (building a CSL item from `co_authors`/`collaborators`/`identity.yaml` rather than a real Zotero record) — Zotero-backed categories only for this pass, per the approved design.
- Currency-converted `stats` aggregation — count-only; dollar totals wait for the currency-conversion subsystem, which doesn't exist in any form yet.
- Mixed-date-precision correctness in `--after`/`--before` — comparing ISO partial-date strings lexicographically is correct within one precision (`"2024-03" >= "2024-01"`) but not reliably correct across mixed precision in the same field (`"2024"` vs `"2024-01"`) — an acceptable, documented limitation for this first cut, not a full mixed-precision-aware range comparison.
- Any change to `edit`/`delete`'s filtering — only `list`/`stats` gain the shared filtering vocabulary, per the approved design; `edit`/`delete` keep their existing `--search`-only substring-and-pick flow.
- A `parco.yaml` wizard prompt for `citation_style` during `parco init` — `init`'s wizard is unchanged by this plan; a user who wants a non-default citation style sets `citation_style` in `parco.yaml` by hand, or passes `--style` per invocation.
