# Add/Edit/Delete Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `parco add`/`parco edit`/`parco delete` — the interactive wizard that lets a user actually create, modify, and remove CV entries, on top of the foundation plan's schema/vocab/handler/lint machinery.

**Architecture:** A new `parcours/core/entries.py` owns row-level CSV add/edit/delete plus id generation and the per-write git auto-commit (all core-layer: no prompting). A new `parcours/cli/wizard.py` owns every interactive piece (per-field prompting, the confirm-before-write screen, the duplicate-check prompt, and search/pick) as plain functions the CLI commands call. `parcours/cli/main.py` gains `add`/`edit`/`delete` commands that wire the two together. A small refactor promotes `lint.py`'s private handler-loading into a shared `parcours/core/handlers/load_handler`, since the wizard needs it too.

**Tech Stack:** Same as the foundation plan — Python ≥3.11, Typer, DuckDB (via existing `load_category_rows`), pytest. No new dependencies: id generation uses the stdlib `secrets` module, CSV writing uses the stdlib `csv` module, auto-commit uses the stdlib `subprocess` module.

**Spec:** SPECS.md (repo root) — see "Data entry (wizard-first, not flag-required)", "Finding a row to edit or delete", "Duplicate detection", and "Auto-commit" under the CLI section; "IDs" under Data layer.

## Global Constraints

- `parcours/core/` never does interactive I/O — no `print()`, `input()`, `typer.echo/prompt/confirm`, `sys.exit()`. `entries.py` returns structured dicts or raises typed exceptions; it does not print or ask anything, even though it does perform file and git I/O (that's data access, not user interaction).
- All prompting, confirmation, and output formatting lives in the CLI layer (`parcours/cli/wizard.py` and `parcours/cli/main.py`).
- IDs are a bare 6-hex-character random token (`secrets.token_hex(3)`), no category prefix, no year — re-rolled on collision against existing ids in that category's CSV.
- The duplicate check runs **after** the confirm-before-write screen, **before** the actual write, and is always a soft warning the user can override — never a hard block.
- Auto-commit is a plain local `git add` + `git commit` against the data repo on every successful `add`/`edit`/`delete` write — no remote interaction (that's the separate, future `sync.py`).
- The same field-collection wizard code path serves both `add` and `edit`; `edit` differs only in supplying existing values as prefill and keeping the existing id.
- CSV writes use `encoding="utf-8"`, `newline=""` (avoids doubled line endings on Windows, matching the CSV round-trip/line-ending testing rule in CLAUDE.md).
- No new third-party dependencies.

---

### Task 1: `core/entries.py` — id generation, row CRUD, per-write auto-commit

**Files:**
- Create: `parcours/core/entries.py`
- Test: `tests/unit/test_entries.py`
- Test: `tests/integration/test_entries_git.py`

**Interfaces:**
- Consumes: `parcours.core.data.load_category_rows` (Task 9 of the foundation plan), `parcours.core.schema.CategorySchema`/`.field_names()` (foundation Task 2).
- Produces: `generate_id(data_dir: Path, category_name: str) -> str`; `add_entry(data_dir: Path, schema: CategorySchema, values: dict) -> dict`; `edit_entry(data_dir: Path, schema: CategorySchema, row_id: str, values: dict) -> dict`; `delete_entry(data_dir: Path, schema: CategorySchema, row_id: str) -> None`; `EntryNotFound` (exception, raised by `edit_entry`/`delete_entry` for an unknown `row_id`). `_git_commit(data_dir, filename, message)` is a private, monkeypatchable seam later tasks' tests will not call directly, but this task's own tests must mock it (unit tests) or exercise it for real (the one integration test).

- [ ] **Step 1: Write the failing unit tests**

```python
# tests/unit/test_entries.py
import pytest

from parcours.core.entries import EntryNotFound, add_entry, delete_entry, edit_entry, generate_id
from parcours.core.schema import CategorySchema, FieldSpec


def _schema():
    return CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="title_en", required=True),
            FieldSpec(name="status"),
        ],
    )


def _no_commit(monkeypatch):
    calls = []

    def fake_commit(data_dir, filename, message):
        calls.append((data_dir, filename, message))

    monkeypatch.setattr("parcours.core.entries._git_commit", fake_commit)
    return calls


def test_generate_id_is_six_hex_chars(tmp_path):
    row_id = generate_id(tmp_path, "widgets")
    assert len(row_id) == 6
    int(row_id, 16)  # doesn't raise


def test_generate_id_avoids_collision_with_existing_ids(tmp_path, monkeypatch):
    (tmp_path / "widgets.csv").write_text("id,title_en,status\nabc123,A,draft\n", encoding="utf-8")
    responses = iter(["abc123", "def456"])
    monkeypatch.setattr("parcours.core.entries.secrets.token_hex", lambda n: next(responses))

    row_id = generate_id(tmp_path, "widgets")

    assert row_id == "def456"


def test_add_entry_creates_csv_with_header_and_generated_id(tmp_path, monkeypatch):
    calls = _no_commit(monkeypatch)
    schema = _schema()

    row = add_entry(tmp_path, schema, {"title_en": "A Widget", "status": "draft"})

    assert row["title_en"] == "A Widget"
    assert len(row["id"]) == 6
    content = (tmp_path / "widgets.csv").read_text(encoding="utf-8")
    assert content.splitlines()[0] == "id,title_en,status"
    assert row["id"] in content
    assert calls == [(tmp_path, "widgets.csv", f"Added widgets entry {row['id']}")]


def test_add_entry_appends_to_existing_csv(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    schema = _schema()
    (tmp_path / "widgets.csv").write_text("id,title_en,status\nabc123,First,draft\n", encoding="utf-8")

    add_entry(tmp_path, schema, {"title_en": "Second", "status": "published"})

    lines = (tmp_path / "widgets.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert "First" in lines[1]
    assert "Second" in lines[2]


def test_edit_entry_updates_matching_row_and_keeps_others(tmp_path, monkeypatch):
    calls = _no_commit(monkeypatch)
    schema = _schema()
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First,draft\ndef456,Second,draft\n", encoding="utf-8"
    )

    updated = edit_entry(tmp_path, schema, "abc123", {"title_en": "First (revised)", "status": "published"})

    assert updated == {"id": "abc123", "title_en": "First (revised)", "status": "published"}
    lines = (tmp_path / "widgets.csv").read_text(encoding="utf-8").splitlines()
    assert "First (revised)" in lines[1]
    assert "Second" in lines[2]
    assert calls == [(tmp_path, "widgets.csv", "Edited widgets entry abc123")]


def test_edit_entry_raises_for_unknown_id(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    schema = _schema()
    (tmp_path / "widgets.csv").write_text("id,title_en,status\nabc123,First,draft\n", encoding="utf-8")

    with pytest.raises(EntryNotFound):
        edit_entry(tmp_path, schema, "nonexistent", {"title_en": "X", "status": "draft"})


def test_delete_entry_removes_matching_row(tmp_path, monkeypatch):
    calls = _no_commit(monkeypatch)
    schema = _schema()
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First,draft\ndef456,Second,draft\n", encoding="utf-8"
    )

    delete_entry(tmp_path, schema, "abc123")

    lines = (tmp_path / "widgets.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "Second" in lines[1]
    assert calls == [(tmp_path, "widgets.csv", "Deleted widgets entry abc123")]


def test_delete_entry_raises_for_unknown_id(tmp_path, monkeypatch):
    _no_commit(monkeypatch)
    schema = _schema()
    (tmp_path / "widgets.csv").write_text("id,title_en,status\nabc123,First,draft\n", encoding="utf-8")

    with pytest.raises(EntryNotFound):
        delete_entry(tmp_path, schema, "nonexistent")
```

- [ ] **Step 2: Run the unit tests to verify they fail**

Run: `pytest tests/unit/test_entries.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.entries'`

- [ ] **Step 3: Implement `entries.py`**

```python
# parcours/core/entries.py
"""Row-level add/edit/delete for a category's CSV: id generation, the
actual CSV rewrite, and the per-write auto-commit to the data repo (see
SPECS.md, "Data entry" and "Auto-commit"). Core layer: no prompting or
printing — the CLI wizard owns all of that."""

import csv
import secrets
import subprocess
from pathlib import Path

from .data import load_category_rows
from .schema import CategorySchema

_ID_BYTES = 3  # secrets.token_hex(3) -> 6 hex characters


class EntryNotFound(Exception):
    """Raised by edit_entry/delete_entry for an id that doesn't exist in
    that category's CSV."""


def generate_id(data_dir: Path, category_name: str) -> str:
    existing_ids = {row.get("id") for row in load_category_rows(data_dir, category_name)}
    while True:
        candidate = secrets.token_hex(_ID_BYTES)
        if candidate not in existing_ids:
            return candidate


def _csv_path(data_dir: Path, category_name: str) -> Path:
    return data_dir / f"{category_name}.csv"


def _write_all_rows(csv_path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _git_commit(data_dir: Path, filename: str, message: str) -> None:
    subprocess.run(["git", "add", filename], cwd=data_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=data_dir, check=True, capture_output=True)


def add_entry(data_dir: Path, schema: CategorySchema, values: dict) -> dict:
    row_id = generate_id(data_dir, schema.name)
    row = {"id": row_id, **values}

    rows = load_category_rows(data_dir, schema.name)
    rows.append(row)
    _write_all_rows(_csv_path(data_dir, schema.name), schema.field_names(), rows)
    _git_commit(data_dir, f"{schema.name}.csv", f"Added {schema.name} entry {row_id}")
    return row


def edit_entry(data_dir: Path, schema: CategorySchema, row_id: str, values: dict) -> dict:
    rows = load_category_rows(data_dir, schema.name)
    if not any(row.get("id") == row_id for row in rows):
        raise EntryNotFound(f"No {schema.name} entry with id '{row_id}'")

    updated_row = {"id": row_id, **values}
    new_rows = [updated_row if row.get("id") == row_id else row for row in rows]
    _write_all_rows(_csv_path(data_dir, schema.name), schema.field_names(), new_rows)
    _git_commit(data_dir, f"{schema.name}.csv", f"Edited {schema.name} entry {row_id}")
    return updated_row


def delete_entry(data_dir: Path, schema: CategorySchema, row_id: str) -> None:
    rows = load_category_rows(data_dir, schema.name)
    if not any(row.get("id") == row_id for row in rows):
        raise EntryNotFound(f"No {schema.name} entry with id '{row_id}'")

    new_rows = [row for row in rows if row.get("id") != row_id]
    _write_all_rows(_csv_path(data_dir, schema.name), schema.field_names(), new_rows)
    _git_commit(data_dir, f"{schema.name}.csv", f"Deleted {schema.name} entry {row_id}")
```

- [ ] **Step 4: Run the unit tests to verify they pass**

Run: `pytest tests/unit/test_entries.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Write the failing integration test for the real git commit**

```python
# tests/integration/test_entries_git.py
import subprocess

from parcours.core.entries import add_entry
from parcours.core.schema import CategorySchema, FieldSpec


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)


def test_add_entry_creates_a_real_git_commit(tmp_path):
    _init_git_repo(tmp_path)
    schema = CategorySchema(
        name="widgets",
        fields=[FieldSpec(name="id", generated=True), FieldSpec(name="title_en", required=True)],
    )

    row = add_entry(tmp_path, schema, {"title_en": "A Widget"})

    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout
    assert f"Added widgets entry {row['id']}" in log
```

This test should already exist as a failing/erroring test only if `tests/integration/__init__.py` or the entries module were missing — both already exist by this point (foundation plan's Task 10 created `tests/integration/__init__.py`; Step 3 above created `entries.py`), so this test should pass immediately once written. Still run it to confirm.

Run: `pytest tests/integration/test_entries_git.py -v`
Expected: PASS (1 test)

- [ ] **Step 6: Run the full suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all prior tests plus this task's 9 new ones)

- [ ] **Step 7: Commit**

```bash
git add parcours/core/entries.py tests/unit/test_entries.py tests/integration/test_entries_git.py
git commit -m "Added entry CRUD, id generation, and per-write auto-commit"
```

---

### Task 2: Shared handler registry + wizard's field-collection loop

**Files:**
- Create: `parcours/core/handlers/__init__.py` (currently empty)
- Modify: `parcours/core/lint.py` (replace its private handler-loading with the shared one)
- Create: `parcours/cli/wizard.py`
- Test: `tests/unit/test_wizard.py`

**Interfaces:**
- Consumes: `parcours.core.handlers.base.CategoryHandler`/`HandlerContext` (foundation Task 7), `.generic.GenericHandler` (foundation Task 7), `.publications.PublicationsHandler` (foundation Task 8), `parcours.core.schema.CategorySchema`/`FieldSpec`/`.get_field()` (foundation Task 2).
- Produces: `load_handler(schema: CategorySchema, context: HandlerContext) -> CategoryHandler` (in `parcours/core/handlers/__init__.py` — replaces `lint.py`'s private `_load_handler`/`_BUILTIN_HANDLERS`, which this task removes); `collect_field_values(schema: CategorySchema, vocab: dict, prefill: dict[str, str] | None = None) -> dict[str, str]` (in `parcours/cli/wizard.py` — the field-by-field prompting loop later tasks call for both `add` and `edit`).

- [ ] **Step 1: Write the failing unit tests**

```python
# tests/unit/test_wizard.py
from parcours.cli import wizard
from parcours.core.schema import CategorySchema, FieldSpec


def _prompt_sequence(monkeypatch, answers):
    it = iter(answers)
    monkeypatch.setattr(wizard.typer, "prompt", lambda *a, **k: next(it))
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)


def _schema():
    return CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="title_en", required=True),
            FieldSpec(name="status", vocab="widget_status"),
        ],
    )


def test_skips_generated_fields(monkeypatch):
    _prompt_sequence(monkeypatch, ["A Widget", "1"])
    values = wizard.collect_field_values(_schema(), {"widget_status": ["draft", "published"]})
    assert "id" not in values


def test_plain_field_collects_typed_value(monkeypatch):
    _prompt_sequence(monkeypatch, ["A Widget", "1"])
    values = wizard.collect_field_values(_schema(), {"widget_status": ["draft", "published"]})
    assert values["title_en"] == "A Widget"


def test_required_plain_field_reprompts_on_blank(monkeypatch):
    _prompt_sequence(monkeypatch, ["", "A Widget", "1"])
    values = wizard.collect_field_values(_schema(), {"widget_status": ["draft", "published"]})
    assert values["title_en"] == "A Widget"


def test_vocab_field_picks_by_number(monkeypatch):
    _prompt_sequence(monkeypatch, ["A Widget", "2"])
    values = wizard.collect_field_values(_schema(), {"widget_status": ["draft", "published"]})
    assert values["status"] == "published"


def test_optional_vocab_field_can_be_skipped(monkeypatch):
    schema = CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="status", vocab="widget_status", required=False),
        ],
    )
    _prompt_sequence(monkeypatch, ["0"])
    values = wizard.collect_field_values(schema, {"widget_status": ["draft", "published"]})
    assert values["status"] == ""


def test_require_one_of_group_reprompts_when_all_blank(monkeypatch):
    schema = CategorySchema(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="title_en", required=False),
            FieldSpec(name="title_fr", required=False),
        ],
        require_one_of=[["title_en", "title_fr"]],
    )
    _prompt_sequence(monkeypatch, ["", "", "A Widget", ""])
    values = wizard.collect_field_values(schema, {})
    assert values["title_en"] == "A Widget"
    assert values["title_fr"] == ""


def test_prefill_becomes_the_shown_default(monkeypatch):
    calls = []

    def fake_prompt(text, default="", show_default=True):
        calls.append(default)
        return default or "typed"

    monkeypatch.setattr(wizard.typer, "prompt", fake_prompt)
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)

    schema = CategorySchema(
        name="widgets",
        fields=[FieldSpec(name="id", generated=True), FieldSpec(name="title_en", required=True)],
    )
    values = wizard.collect_field_values(schema, {}, prefill={"title_en": "Existing Title"})

    assert calls == ["Existing Title"]
    assert values["title_en"] == "Existing Title"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_wizard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.cli.wizard'`

- [ ] **Step 3: Implement the shared handler registry**

```python
# parcours/core/handlers/__init__.py
"""Registry of built-in category handlers, resolved from a schema's
`handler:` field (see SPECS.md, "Category handlers"). Shared by
`core.lint` and the CLI wizard — neither should duplicate this
resolution logic."""

import importlib

from .base import CategoryHandler, HandlerContext
from .generic import GenericHandler
from .publications import PublicationsHandler

BUILTIN_HANDLERS = {
    "generic": GenericHandler,
    "publications": PublicationsHandler,
}


def load_handler(schema, context: HandlerContext) -> CategoryHandler:
    handler_name = schema.handler
    if ":" in handler_name:
        module_name, class_name = handler_name.split(":")
        module = importlib.import_module(module_name)
        handler_cls = getattr(module, class_name)
    else:
        handler_cls = BUILTIN_HANDLERS[handler_name]
    return handler_cls(schema, context)
```

- [ ] **Step 4: Update `lint.py` to use the shared registry**

In `parcours/core/lint.py`, replace:

```python
import importlib
from pathlib import Path

from .data import load_category_rows
from .handlers.base import HandlerContext
from .handlers.generic import GenericHandler
from .handlers.publications import PublicationsHandler
from .labels import load_labels
from .schema import CategorySchema, load_all_schemas
from .validation import LintIssue, validate_common
from .vocab import VocabError, load_vocab

_BUILTIN_HANDLERS = {
    "generic": GenericHandler,
    "publications": PublicationsHandler,
}


class ConfigError(Exception):
    """Raised when `parco lint` can't run because of a data-repo
    misconfiguration (bad schema, missing vocab/labels file, unknown
    handler, etc.) rather than a real lint issue with the data itself."""


def _load_handler(schema: CategorySchema, context: HandlerContext):
    handler_name = schema.handler
    if ":" in handler_name:
        module_name, class_name = handler_name.split(":")
        module = importlib.import_module(module_name)
        handler_cls = getattr(module, class_name)
    else:
        handler_cls = _BUILTIN_HANDLERS[handler_name]
    return handler_cls(schema, context)
```

with:

```python
from pathlib import Path

from .data import load_category_rows
from .handlers import load_handler
from .handlers.base import HandlerContext
from .labels import load_labels
from .schema import load_all_schemas
from .validation import LintIssue, validate_common
from .vocab import VocabError, load_vocab


class ConfigError(Exception):
    """Raised when `parco lint` can't run because of a data-repo
    misconfiguration (bad schema, missing vocab/labels file, unknown
    handler, etc.) rather than a real lint issue with the data itself."""
```

And inside `run_lint`, replace the line `handler = _load_handler(schema, HandlerContext(data_dir=data_dir))` with `handler = load_handler(schema, HandlerContext(data_dir=data_dir))`. Nothing else in `lint.py` changes.

Run: `pytest tests/unit/test_lint.py tests/integration/test_cli_lint.py -v`
Expected: PASS (all existing lint tests, unchanged — this refactor is behavior-preserving)

- [ ] **Step 5: Implement the wizard's field-collection loop**

```python
# parcours/cli/wizard.py
"""Every interactive piece of the add/edit/delete wizard: per-field
prompting, the confirm-before-write screen, the duplicate-check prompt,
and search/pick. CLI layer only — nothing here is imported by core (see
SPECS.md, "Data entry" and "Finding a row to edit or delete")."""

from datetime import date

import typer

from ..core.schema import CategorySchema, FieldSpec


def _require_one_of_group(schema: CategorySchema, field_name: str) -> list[str] | None:
    for group in schema.require_one_of:
        if field_name in group:
            return group
    return None


def _ask_vocab_field(field: FieldSpec, choices: list[str], current: str | None) -> str:
    typer.echo(f"{field.name}:")
    for i, choice in enumerate(choices, start=1):
        typer.echo(f"  {i}. {choice}")
    if not field.required:
        typer.echo("  0. [skip]")

    default_number = None
    if current and current in choices:
        default_number = choices.index(current) + 1

    while True:
        answer = typer.prompt("Choice", default=default_number, show_default=default_number is not None)
        try:
            number = int(answer)
        except (TypeError, ValueError):
            typer.echo("Please enter a number.")
            continue
        if number == 0 and not field.required:
            return ""
        if 1 <= number <= len(choices):
            return choices[number - 1]
        typer.echo("Not a valid choice.")


def _ask_plain_field(field: FieldSpec, current: str | None) -> str:
    default = current or ""
    if not current and field.type == "date":
        default = str(date.today().year)
    prompt_suffix = "" if field.required else " ([Enter] to skip)"

    while True:
        answer = typer.prompt(f"{field.name}{prompt_suffix}", default=default, show_default=bool(default)).strip()
        if field.required and not answer:
            typer.echo(f"'{field.name}' is required.")
            continue
        return answer


def _ask_field(field: FieldSpec, vocab: dict, current: str | None) -> str:
    if field.vocab:
        return _ask_vocab_field(field, vocab.get(field.vocab, []), current)
    return _ask_plain_field(field, current)


def collect_field_values(
    schema: CategorySchema, vocab: dict, prefill: dict[str, str] | None = None
) -> dict[str, str]:
    prefill = prefill or {}
    values: dict[str, str] = {}
    handled_groups: set[tuple[str, ...]] = set()

    for field in schema.fields:
        if field.generated:
            continue

        group = _require_one_of_group(schema, field.name)
        if group is not None:
            group_key = tuple(group)
            if group_key in handled_groups:
                continue
            handled_groups.add(group_key)

            while True:
                for name in group:
                    group_field = schema.get_field(name)
                    values[name] = _ask_field(group_field, vocab, prefill.get(name))
                if any(values[name].strip() for name in group):
                    break
                typer.echo(f"At least one of {group} must be filled in.")
            continue

        values[field.name] = _ask_field(field, vocab, prefill.get(field.name))

    return values
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/unit/test_wizard.py -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Run the full suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all prior tests plus this task's 7 new ones; the `lint.py` refactor must not change any existing test's outcome)

- [ ] **Step 8: Commit**

```bash
git add parcours/core/handlers/__init__.py parcours/core/lint.py parcours/cli/wizard.py tests/unit/test_wizard.py
git commit -m "Added shared handler registry and the wizard's field-collection loop"
```

---

### Task 3: Confirm-before-write + duplicate check + `parco add`

**Files:**
- Modify: `parcours/cli/wizard.py` (add `confirm_and_check_duplicates`)
- Modify: `parcours/cli/main.py` (add the `add` command, `_parse_prefill_flags`, `_load_schema_or_exit`)
- Test: `tests/integration/test_cli_add.py`

**Interfaces:**
- Consumes: `collect_field_values` (Task 2), `parcours.core.handlers.base.Match`/`HandlerContext` (foundation Task 7), `parcours.core.handlers.load_handler` (Task 2), `parcours.core.entries.add_entry` (Task 1), `parcours.core.data.load_category_rows` (foundation Task 9), `parcours.core.schema.load_all_schemas` (foundation Task 2), `parcours.core.vocab.load_vocab` (foundation Task 3), `parcours.core.repo.find_data_repo`/`DataRepoNotFound` (foundation Task 1).
- Produces: `confirm_and_check_duplicates(handler, values: dict[str, str], existing_rows: list[dict], self_id: str | None = None) -> bool` (in `wizard.py` — later tasks reuse this unchanged for `edit`); the `add` Typer command; `_parse_prefill_flags(args: list[str]) -> dict[str, str]` and `_load_schema_or_exit(data_dir, category) -> CategorySchema` (in `main.py` — later tasks reuse both unchanged).

- [ ] **Step 1: Write the failing integration tests**

```python
# tests/integration/test_cli_add.py
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
dedup:
  - when: [{exact: title_en}]
    as: duplicate
""")
    (tmp_path / "vocab.yaml").write_text("widget_status: [draft, published]\n")
    (tmp_path / "labels.csv").write_text("id,category,en,fr\n")
    return tmp_path


def test_add_writes_a_new_row_and_commits(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries._git_commit", lambda *a, **k: None)

    result = runner.invoke(app, ["add", "widgets"], input="A Widget\n1\ny\n")

    assert result.exit_code == 0, result.stdout
    assert "Added widgets entry" in result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert "A Widget" in content
    assert ",draft" in content


def test_add_aborts_when_confirm_declined(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries._git_commit", lambda *a, **k: None)

    result = runner.invoke(app, ["add", "widgets"], input="A Widget\n1\nn\n")

    assert result.exit_code == 0
    assert "Aborted" in result.stdout
    assert not (repo / "widgets.csv").exists()


def test_add_warns_on_duplicate_and_can_proceed_anyway(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "widgets.csv").write_text("id,title_en,status\nabc123,A Widget,draft\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries._git_commit", lambda *a, **k: None)

    result = runner.invoke(app, ["add", "widgets"], input="A Widget\n1\ny\ny\n")

    assert result.exit_code == 0, result.stdout
    assert "Possible duplicates found" in result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert content.count("A Widget") == 2


def test_add_prefill_flags_are_used_as_wizard_defaults(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries._git_commit", lambda *a, **k: None)

    result = runner.invoke(
        app, ["add", "widgets", "--title_en", "Prefilled Widget"], input="\n1\ny\n"
    )

    assert result.exit_code == 0, result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert "Prefilled Widget" in content


def test_add_rejects_unknown_flag(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["add", "widgets", "--nope", "x"])

    assert result.exit_code == 2
    assert "Unknown or non-writable" in result.stdout


def test_add_unknown_category_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["add", "nonexistent"])

    assert result.exit_code == 2
    assert "Unknown category" in result.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/integration/test_cli_add.py -v`
Expected: FAIL — no `add` command registered on `app` yet (Typer/Click will report "No such command 'add'")

- [ ] **Step 3: Add `confirm_and_check_duplicates` to `wizard.py`**

Append to `parcours/cli/wizard.py`:

```python
def confirm_and_check_duplicates(
    handler, values: dict[str, str], existing_rows: list[dict], self_id: str | None = None
) -> bool:
    """Show the confirm-before-write screen, then run the category
    handler's dedup check. Returns True if the write should proceed."""
    typer.echo("\nReview:")
    for name, value in values.items():
        typer.echo(f"  {name}: {value or '(skip)'}")

    if not typer.confirm("Write this entry?"):
        return False

    candidate = {"id": self_id or "", **values}
    matches = handler.find_matches(candidate, existing_rows)

    for match in matches:
        if match.kind == "related":
            typer.echo(f"Related existing entry {match.existing_row_id}: {match.reason}")

    duplicates = [m for m in matches if m.kind == "duplicate"]
    if duplicates:
        typer.echo("\nPossible duplicates found:")
        for match in duplicates:
            typer.echo(f"  {match.existing_row_id}: {match.reason}")
        if not typer.confirm("Add anyway?"):
            return False

    return True
```

- [ ] **Step 4: Add the `add` command to `main.py`**

Replace the full contents of `parcours/cli/main.py` with:

```python
# parcours/cli/main.py
"""The Typer app — thin, owns all prompts/printing (see SPECS.md, "Code
architecture: modular core + thin interfaces")."""

from pathlib import Path

import typer

from ..core.data import load_category_rows
from ..core.entries import add_entry
from ..core.handlers import load_handler
from ..core.handlers.base import HandlerContext
from ..core.lint import ConfigError, run_lint
from ..core.repo import DataRepoNotFound, find_data_repo
from ..core.schema import CategorySchema, load_all_schemas
from ..core.vocab import load_vocab
from .wizard import collect_field_values, confirm_and_check_duplicates

app = typer.Typer()


@app.callback()
def main():
    """Parcours: a personal, git-tracked academic/artistic CV data system."""


@app.command()
def lint(category: str = typer.Argument(None, help="Only lint this category")):
    """Check category data against its schema, vocab, and labels."""
    try:
        data_dir = find_data_repo()
    except DataRepoNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    try:
        issues = run_lint(data_dir, category_filter=category)
    except ConfigError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    if not issues:
        typer.echo("No lint issues found.")
        raise typer.Exit(code=0)

    for issue in issues:
        location = issue.category
        if issue.row_id:
            location += f"[{issue.row_id}]"
        if issue.field:
            location += f".{issue.field}"
        typer.echo(f"{issue.severity.upper()}: {location}: {issue.message}")

    error_count = sum(1 for i in issues if i.severity == "error")
    raise typer.Exit(code=1 if error_count else 0)


def _load_schema_or_exit(data_dir: Path, category: str) -> CategorySchema:
    schemas = load_all_schemas(data_dir / "categories")
    if category not in schemas:
        typer.echo(f"Unknown category: '{category}'")
        raise typer.Exit(code=2)
    return schemas[category]


def _parse_prefill_flags(args: list[str]) -> dict[str, str]:
    prefill: dict[str, str] = {}
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            raise typer.BadParameter(f"Expected a --field flag, got '{token}'")
        name = token[2:]
        if i + 1 >= len(args):
            raise typer.BadParameter(f"Missing value for --{name}")
        prefill[name] = args[i + 1]
        i += 2
    return prefill


def _reject_unknown_fields(schema: CategorySchema, prefill: dict[str, str]) -> None:
    unknown = [
        name for name in prefill
        if schema.get_field(name) is None or schema.get_field(name).generated
    ]
    if unknown:
        typer.echo(f"Unknown or non-writable field(s): {', '.join(unknown)}")
        raise typer.Exit(code=2)


@app.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
def add(ctx: typer.Context, category: str = typer.Argument(..., help="Category to add an entry to")):
    """Interactively add a new entry to a category. Extra --field value flags pre-fill the wizard."""
    try:
        data_dir = find_data_repo()
    except DataRepoNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    schema = _load_schema_or_exit(data_dir, category)
    prefill = _parse_prefill_flags(ctx.args)
    _reject_unknown_fields(schema, prefill)

    vocab = load_vocab(data_dir / "vocab.yaml")
    handler = load_handler(schema, HandlerContext(data_dir=data_dir))
    existing_rows = load_category_rows(data_dir, category)

    values = collect_field_values(schema, vocab, prefill=prefill)
    if not confirm_and_check_duplicates(handler, values, existing_rows):
        typer.echo("Aborted, nothing written.")
        raise typer.Exit(code=0)

    row = add_entry(data_dir, schema, values)
    typer.echo(f"Added {category} entry {row['id']}.")


if __name__ == "__main__":
    app()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/integration/test_cli_add.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Run the full suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all prior tests plus this task's 6 new ones)

- [ ] **Step 7: Commit**

```bash
git add parcours/cli/wizard.py parcours/cli/main.py tests/integration/test_cli_add.py
git commit -m "Added confirm-before-write, duplicate check, and the parco add command"
```

---

### Task 4: Search/pick + `parco edit`

**Files:**
- Modify: `parcours/cli/wizard.py` (add `search_rows`, `pick_row`, and their private helpers)
- Modify: `parcours/cli/main.py` (add the `edit` command)
- Test: `tests/unit/test_wizard.py` (extend with search/pick tests)
- Test: `tests/integration/test_cli_edit.py`

**Interfaces:**
- Consumes: `collect_field_values`, `confirm_and_check_duplicates` (Task 2/3), `parcours.core.entries.edit_entry` (Task 1), everything `add` already wires (Task 3).
- Produces: `search_rows(rows: list[dict], search_text: str) -> list[dict]`; `pick_row(schema: CategorySchema, matches: list[dict]) -> dict | None` (both in `wizard.py` — Task 5's `delete` reuses both unchanged); the `edit` Typer command.

- [ ] **Step 1: Write the failing unit tests for search/pick**

Append to `tests/unit/test_wizard.py`:

```python
def test_search_rows_matches_substring_case_insensitively():
    rows = [
        {"id": "abc123", "title_en": "Machine Learning Art"},
        {"id": "def456", "title_en": "Completely Unrelated"},
    ]
    matches = wizard.search_rows(rows, "machine")
    assert [m["id"] for m in matches] == ["abc123"]


def test_search_rows_matches_across_any_field():
    rows = [
        {"id": "abc123", "title_en": "A Widget", "status": "draft"},
        {"id": "def456", "title_en": "B Widget", "status": "published"},
    ]
    matches = wizard.search_rows(rows, "published")
    assert [m["id"] for m in matches] == ["def456"]


def test_pick_row_returns_none_for_no_matches(monkeypatch):
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)
    assert wizard.pick_row(_schema(), []) is None


def test_pick_row_returns_the_chosen_row(monkeypatch):
    rows = [{"id": "abc123", "title_en": "A"}, {"id": "def456", "title_en": "B"}]
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)
    monkeypatch.setattr(wizard.typer, "prompt", lambda *a, **k: "2")

    picked = wizard.pick_row(_schema(), rows)

    assert picked["id"] == "def456"


def test_pick_row_returns_none_when_cancelled(monkeypatch):
    rows = [{"id": "abc123", "title_en": "A"}]
    monkeypatch.setattr(wizard.typer, "echo", lambda *a, **k: None)
    monkeypatch.setattr(wizard.typer, "prompt", lambda *a, **k: "")

    assert wizard.pick_row(_schema(), rows) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_wizard.py -v`
Expected: FAIL with `AttributeError: module 'parcours.cli.wizard' has no attribute 'search_rows'` (and similarly for `pick_row`)

- [ ] **Step 3: Implement search/pick in `wizard.py`**

Append to `parcours/cli/wizard.py`:

```python
def _display_fields(schema: CategorySchema) -> list[str]:
    names: list[str] = [f.name for f in schema.fields if f.required]
    for group in schema.require_one_of:
        for name in group:
            if name not in names:
                names.append(name)
    return names


def _row_summary(schema: CategorySchema, row: dict) -> str:
    parts = [f"id={row.get('id', '')}"]
    for name in _display_fields(schema):
        value = row.get(name)
        if value:
            parts.append(f"{name}={value}")
    return ", ".join(parts)


def search_rows(rows: list[dict], search_text: str) -> list[dict]:
    needle = search_text.lower()
    return [
        row for row in rows
        if any(needle in str(value).lower() for value in row.values() if value)
    ]


def pick_row(schema: CategorySchema, matches: list[dict]) -> dict | None:
    if not matches:
        typer.echo("No matching entries found.")
        return None

    for i, row in enumerate(matches, start=1):
        typer.echo(f"  {i}. {_row_summary(schema, row)}")

    choice = typer.prompt("Pick a number ([Enter] to cancel)", default="", show_default=False)
    if not choice.strip():
        return None
    try:
        index = int(choice)
    except ValueError:
        typer.echo("Not a valid number.")
        return None
    if not (1 <= index <= len(matches)):
        typer.echo("Not a valid number.")
        return None
    return matches[index - 1]
```

- [ ] **Step 4: Run the wizard tests to verify they pass**

Run: `pytest tests/unit/test_wizard.py -v`
Expected: PASS (12 tests total: 7 from Task 2 + 5 new)

- [ ] **Step 5: Write the failing integration tests for `edit`**

```python
# tests/integration/test_cli_edit.py
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
    (tmp_path / "labels.csv").write_text("id,category,en,fr\n")
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First Widget,draft\ndef456,Second Widget,draft\n",
        encoding="utf-8",
    )
    return tmp_path


def test_edit_finds_by_search_and_updates(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries._git_commit", lambda *a, **k: None)

    result = runner.invoke(
        app, ["edit", "widgets", "--search", "First"], input="1\nFirst Widget (revised)\n2\ny\n"
    )

    assert result.exit_code == 0, result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert "First Widget (revised)" in content
    assert ",published" in content
    assert "abc123" in content


def test_edit_prefills_wizard_with_existing_values(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries._git_commit", lambda *a, **k: None)

    result = runner.invoke(
        app, ["edit", "widgets", "--search", "First"], input="1\n\n\ny\n"
    )

    assert result.exit_code == 0, result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert "First Widget" in content
    assert ",draft" in content


def test_edit_no_matches_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["edit", "widgets", "--search", "nonexistent"])

    assert result.exit_code == 0
    assert "No matching entries found" in result.stdout


def test_edit_cancel_at_picker_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["edit", "widgets", "--search", "Widget"], input="\n")

    assert result.exit_code == 0
    assert "Nothing selected" in result.stdout
```

- [ ] **Step 6: Add the `edit` command to `main.py`**

Add these imports to `parcours/cli/main.py` (alongside the existing ones from Task 3):

```python
from ..core.entries import edit_entry
from .wizard import pick_row, search_rows
```

Append this command to `parcours/cli/main.py`:

```python
@app.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
def edit(
    ctx: typer.Context,
    category: str = typer.Argument(..., help="Category to edit an entry in"),
    search: str = typer.Option(..., "--search", help="Text to search for"),
):
    """Search for an entry and interactively edit it."""
    try:
        data_dir = find_data_repo()
    except DataRepoNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    schema = _load_schema_or_exit(data_dir, category)
    prefill_flags = _parse_prefill_flags(ctx.args)
    _reject_unknown_fields(schema, prefill_flags)

    existing_rows = load_category_rows(data_dir, category)
    matches = search_rows(existing_rows, search)
    row = pick_row(schema, matches)
    if row is None:
        typer.echo("Nothing selected.")
        raise typer.Exit(code=0)

    vocab = load_vocab(data_dir / "vocab.yaml")
    handler = load_handler(schema, HandlerContext(data_dir=data_dir))

    prefill = {**row, **prefill_flags}
    values = collect_field_values(schema, vocab, prefill=prefill)
    if not confirm_and_check_duplicates(handler, values, existing_rows, self_id=row["id"]):
        typer.echo("Aborted, nothing written.")
        raise typer.Exit(code=0)

    updated = edit_entry(data_dir, schema, row["id"], values)
    typer.echo(f"Edited {category} entry {updated['id']}.")
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest tests/integration/test_cli_edit.py -v`
Expected: PASS (4 tests)

- [ ] **Step 8: Run the full suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all prior tests plus this task's 9 new ones: 5 wizard unit tests + 4 CLI integration tests)

- [ ] **Step 9: Commit**

```bash
git add parcours/cli/wizard.py parcours/cli/main.py tests/unit/test_wizard.py tests/integration/test_cli_edit.py
git commit -m "Added search/pick and the parco edit command"
```

---

### Task 5: `parco delete`

**Files:**
- Modify: `parcours/cli/main.py` (add the `delete` command)
- Test: `tests/integration/test_cli_delete.py`

**Interfaces:**
- Consumes: `search_rows`, `pick_row` (Task 4), `parcours.core.entries.delete_entry` (Task 1).
- Produces: the `delete` Typer command. Nothing later depends on this task — it's the plan's last piece.

- [ ] **Step 1: Write the failing integration tests**

```python
# tests/integration/test_cli_delete.py
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
""")
    (tmp_path / "vocab.yaml").write_text("{}\n")
    (tmp_path / "labels.csv").write_text("id,category,en,fr\n")
    (tmp_path / "widgets.csv").write_text(
        "id,title_en\nabc123,First Widget\ndef456,Second Widget\n", encoding="utf-8"
    )
    return tmp_path


def test_delete_confirms_and_removes_the_row(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("parcours.core.entries._git_commit", lambda *a, **k: None)

    result = runner.invoke(app, ["delete", "widgets", "--search", "First"], input="1\ny\n")

    assert result.exit_code == 0, result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert "First Widget" not in content
    assert "Second Widget" in content


def test_delete_aborts_when_confirm_declined(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["delete", "widgets", "--search", "First"], input="1\nn\n")

    assert result.exit_code == 0
    assert "Aborted" in result.stdout
    content = (repo / "widgets.csv").read_text(encoding="utf-8")
    assert "First Widget" in content


def test_delete_no_matches_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["delete", "widgets", "--search", "nonexistent"])

    assert result.exit_code == 0
    assert "No matching entries found" in result.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/integration/test_cli_delete.py -v`
Expected: FAIL — no `delete` command registered on `app` yet

- [ ] **Step 3: Add the `delete` command to `main.py`**

Add this import to `parcours/cli/main.py` (alongside the existing ones):

```python
from ..core.entries import delete_entry
```

Append this command:

```python
@app.command()
def delete(
    category: str = typer.Argument(..., help="Category to delete an entry from"),
    search: str = typer.Option(..., "--search", help="Text to search for"),
):
    """Search for an entry and delete it after one confirmation."""
    try:
        data_dir = find_data_repo()
    except DataRepoNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    schema = _load_schema_or_exit(data_dir, category)
    existing_rows = load_category_rows(data_dir, category)
    matches = search_rows(existing_rows, search)
    row = pick_row(schema, matches)
    if row is None:
        typer.echo("Nothing selected.")
        raise typer.Exit(code=0)

    if not typer.confirm(
        f"Delete {category} entry {row['id']}? This cannot be undone via the CLI (git history keeps it)."
    ):
        typer.echo("Aborted, nothing deleted.")
        raise typer.Exit(code=0)

    delete_entry(data_dir, schema, row["id"])
    typer.echo(f"Deleted {category} entry {row['id']}.")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/integration/test_cli_delete.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full suite to verify everything passes**

Run: `pytest tests/ -v`
Expected: PASS (all tests across every task in both plans)

- [ ] **Step 6: Commit**

```bash
git add parcours/cli/main.py tests/integration/test_cli_delete.py
git commit -m "Added the parco delete command"
```

---

## What this plan deliberately does not cover

Follow-up plans, once this wizard exists:
- `sync`/remotes (a genuinely separate concern from this plan's per-write local auto-commit — see SPECS.md's Auto-commit section) and currency conversion/`refresh rates`.
- `build` (profile → RenderCV YAML → rendered output) and `views.yaml` loading.
- `refresh zotero` and `import ccv` (the actual importers) — this plan's dedup reuse (`handler.find_matches`) is exactly what those will call non-interactively, but neither importer exists yet.
- `parco lint --fix` (unambiguous auto-fixes) — unrelated to this plan's scope.
- A schema-level "display field" convention — deliberately not introduced; search/pick derive their summary line generically from `required` + `require_one_of` fields (see SPECS.md's "Finding a row to edit or delete").
- Extra ad hoc CSV columns beyond what a category's schema declares — `entries.py`'s rewrite functions always use `schema.field_names()` as the column set, so a hand-added column not in the schema would be silently dropped on the next `add`/`edit`/`delete` write to that category. Not expected to occur in a config-driven system, but worth a lint check in a future pass if it ever does.
- Concurrent-write safety (two `parco add` processes racing on the same CSV) — this is a single-user, local-first CLI tool; out of scope by design, matching the rest of the project.
