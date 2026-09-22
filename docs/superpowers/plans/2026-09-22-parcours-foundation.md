# Parcours Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational `parcours` Python package — schema/config
loading, the category-handler system (`generic` + `publications`), DuckDB
data access, and a first working end-to-end command (`parco lint`) — so
every later command (`add`, `edit`, `sync`, `build`, `refresh`) has
something real to build on.

**Architecture:** Hexagonal core/interface split per the spec: `core/`
contains no interactive I/O (no `print`/`input`/`sys.exit`) and returns
structured data or raises typed exceptions; `cli/` is a thin Typer layer
that does all prompting and output formatting. Category behavior lives in
pluggable handlers (a `CategoryHandler` base class + two concrete
handlers), not in per-category `if` branches anywhere in core.

**Tech Stack:** Python ≥3.11, Typer (CLI), DuckDB (CSV querying), PyYAML
(`yaml.safe_load` only — never the unsafe loader), pytest (tests, via
`tmp_path` fixtures rather than committed fixture files for this plan).
No pydantic — schema/vocab/label models are plain `dataclasses`, kept
deliberately simple.

**Spec:** `SPECS.md` (repo root) — read alongside this plan. Relevant
sections: "Category handlers", "Category schemas (drafts)", "Labels /
translations", "Code architecture: modular core + thin interfaces",
"Testing & CI", "CLI" → "Validation".

## Global Constraints

- Python ≥3.11 (per `CLAUDE.md`).
- `core/` never does interactive I/O — no `print()`, `input()`,
  `sys.exit()`. Return structured results or raise typed exceptions.
- All YAML loading uses `yaml.safe_load` — never `yaml.load` with the
  default (unsafe) loader.
- No category name is ever hardcoded in `core/` — all category behavior
  comes from the schema file + its named handler.
- `snake_case` for functions/variables, `PascalCase` for classes,
  `UPPER_CASE` for constants (per `CLAUDE.md`'s Python style).
- Tests never touch real data or the real filesystem beyond `tmp_path`.
- Commit after every passing task (granular, one logical change each,
  past-tense imperative message, capital letter start, no
  `Co-Authored-By` line — per `CLAUDE.md`/global git conventions).

---

### Task 1: Package scaffold + data repo discovery

**Files:**
- Create: `pyproject.toml`
- Create: `parcours/__init__.py`
- Create: `parcours/core/__init__.py`
- Create: `parcours/core/repo.py`
- Create: `parcours/cli/__init__.py`
- Test: `tests/unit/test_repo.py`

**Interfaces:**
- Produces: `parcours.core.repo.find_data_repo(start=None, env=None, explicit=None) -> Path`,
  `parcours.core.repo.DataRepoNotFound(Exception)`, constant
  `parcours.core.repo.MARKER_FILENAME = "parco.yaml"`.

- [ ] **Step 1: Create the package skeleton**

```toml
# pyproject.toml
[project]
name = "parcours"
version = "0.1.0"
description = "A personal, portable system for maintaining academic/artistic CV data as structured, git-tracked plain text."
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "duckdb>=1.0",
    "pyyaml>=6.0",
    "platformdirs>=4.0",
]

[project.scripts]
parco = "parcours.cli.main:app"

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["parcours*"]
```

```python
# parcours/__init__.py
__version__ = "0.1.0"
```

```python
# parcours/core/__init__.py
```

```python
# parcours/cli/__init__.py
```

- [ ] **Step 2: Write the failing test for data repo discovery**

```python
# tests/unit/test_repo.py
import pytest
from pathlib import Path
from parcours.core.repo import find_data_repo, DataRepoNotFound, MARKER_FILENAME


def test_finds_marker_in_current_directory(tmp_path):
    (tmp_path / MARKER_FILENAME).write_text("name: test\n")
    assert find_data_repo(start=tmp_path, env={}) == tmp_path


def test_finds_marker_in_parent_directory(tmp_path):
    (tmp_path / MARKER_FILENAME).write_text("name: test\n")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert find_data_repo(start=nested, env={}) == tmp_path


def test_env_var_overrides_marker_search(tmp_path):
    marker_dir = tmp_path / "marker_repo"
    marker_dir.mkdir()
    (marker_dir / MARKER_FILENAME).write_text("name: test\n")
    env_dir = tmp_path / "env_repo"
    env_dir.mkdir()
    result = find_data_repo(start=marker_dir, env={"PARCO_DATA_DIR": str(env_dir)})
    assert result == env_dir


def test_explicit_path_overrides_everything(tmp_path):
    marker_dir = tmp_path / "marker_repo"
    marker_dir.mkdir()
    (marker_dir / MARKER_FILENAME).write_text("name: test\n")
    explicit_dir = tmp_path / "explicit_repo"
    explicit_dir.mkdir()
    result = find_data_repo(
        start=marker_dir,
        env={"PARCO_DATA_DIR": str(marker_dir)},
        explicit=explicit_dir,
    )
    assert result == explicit_dir


def test_falls_back_to_config_file(tmp_path, monkeypatch):
    config_home = tmp_path / "home"
    config_dir = config_home / ".config" / "parco"
    config_dir.mkdir(parents=True)
    data_repo = tmp_path / "configured_repo"
    data_repo.mkdir()
    (config_dir / "config.yaml").write_text(f"data_dir: {data_repo}\n")
    monkeypatch.setattr(Path, "home", lambda: config_home)

    no_marker_dir = tmp_path / "no_marker"
    no_marker_dir.mkdir()
    result = find_data_repo(start=no_marker_dir, env={})
    assert result == data_repo


def test_raises_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty_home")
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    with pytest.raises(DataRepoNotFound):
        find_data_repo(start=isolated, env={})


def test_explicit_path_must_exist(tmp_path):
    with pytest.raises(DataRepoNotFound):
        find_data_repo(explicit=tmp_path / "does_not_exist")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pip install -e ".[dev]" && pytest tests/unit/test_repo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.repo'`

- [ ] **Step 4: Implement `find_data_repo`**

```python
# parcours/core/repo.py
"""Locates the data repo `parco` operates on (separate from this code repo)."""

import os
from pathlib import Path

import yaml

MARKER_FILENAME = "parco.yaml"


class DataRepoNotFound(Exception):
    """Raised when no data repo can be located by any resolution method."""


def find_data_repo(
    start: Path | None = None,
    env: dict | None = None,
    explicit: Path | str | None = None,
) -> Path:
    """Locate the data repo directory.

    Resolution order: `explicit` path, then `PARCO_DATA_DIR` env var, then
    a `parco.yaml` marker file searched upward from `start`, then
    `~/.config/parco/config.yaml`'s `data_dir` value.
    """
    if explicit is not None:
        return _validate_repo(Path(explicit))

    env = os.environ if env is None else env
    if "PARCO_DATA_DIR" in env:
        return _validate_repo(Path(env["PARCO_DATA_DIR"]))

    current = Path(start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / MARKER_FILENAME).is_file():
            return candidate

    config_path = Path.home() / ".config" / "parco" / "config.yaml"
    if config_path.is_file():
        with open(config_path, "r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
        if "data_dir" in config:
            return _validate_repo(Path(config["data_dir"]).expanduser())

    raise DataRepoNotFound(
        f"No data repo found. Searched upward from {current} for "
        f"'{MARKER_FILENAME}', and checked {config_path}."
    )


def _validate_repo(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.is_dir():
        raise DataRepoNotFound(f"Data repo path does not exist: {path}")
    return path
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_repo.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml parcours/__init__.py parcours/core/__init__.py \
        parcours/core/repo.py parcours/cli/__init__.py tests/unit/test_repo.py
git commit -m "Added package scaffold and data repo discovery"
```

---

### Task 2: Category schema loading

**Files:**
- Create: `parcours/core/schema.py`
- Test: `tests/unit/test_schema.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `FieldSpec` (dataclass: `name: str`, `type: str = "string"`,
  `required: bool = False`, `vocab: str | None = None`,
  `default: object = None`, `generated: bool = False`,
  `precision: str | None = None`), `DedupRule` (dataclass:
  `conditions: list[dict]`, `outcome: str`), `CategorySchema` (dataclass:
  `name: str`, `handler: str`, `fields: list[FieldSpec]`,
  `options: dict`, `dedup: list[DedupRule]`,
  `require_one_of: list[list[str]]`, plus methods `field_names() ->
  list[str]` and `get_field(name: str) -> FieldSpec | None`),
  `load_category_schema(path: Path) -> CategorySchema`,
  `load_all_schemas(categories_dir: Path) -> dict[str, CategorySchema]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_schema.py
from parcours.core.schema import load_category_schema, load_all_schemas


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_fields_dedup_and_require_one_of(tmp_path):
    schema_file = _write(tmp_path / "widgets.yaml", """
name: widgets
handler: generic
options:
  some_option: value
fields:
  - {name: id, generated: true}
  - {name: title_en}
  - {name: title_fr}
  - {name: status, required: true, vocab: widget_status}
  - {name: start_date, type: date, precision: month, required: true}
require_one_of:
  - [title_en, title_fr]
dedup:
  - when: [{exact: id}]
    as: duplicate
""")
    schema = load_category_schema(schema_file)

    assert schema.name == "widgets"
    assert schema.handler == "generic"
    assert schema.options == {"some_option": "value"}
    assert schema.field_names() == ["id", "title_en", "title_fr", "status", "start_date"]
    assert schema.require_one_of == [["title_en", "title_fr"]]

    status_field = schema.get_field("status")
    assert status_field.required is True
    assert status_field.vocab == "widget_status"

    date_field = schema.get_field("start_date")
    assert date_field.type == "date"
    assert date_field.precision == "month"

    assert schema.get_field("nonexistent") is None

    assert len(schema.dedup) == 1
    assert schema.dedup[0].conditions == [{"exact": "id"}]
    assert schema.dedup[0].outcome == "duplicate"


def test_handler_defaults_to_generic(tmp_path):
    schema_file = _write(tmp_path / "minimal.yaml", """
name: minimal
fields:
  - {name: id, generated: true}
""")
    schema = load_category_schema(schema_file)
    assert schema.handler == "generic"
    assert schema.options == {}
    assert schema.dedup == []
    assert schema.require_one_of == []


def test_load_all_schemas_keys_by_category_name(tmp_path):
    categories_dir = tmp_path / "categories"
    categories_dir.mkdir()
    _write(categories_dir / "widgets.yaml", "name: widgets\nfields: [{name: id, generated: true}]\n")
    _write(categories_dir / "gadgets.yaml", "name: gadgets\nfields: [{name: id, generated: true}]\n")

    schemas = load_all_schemas(categories_dir)

    assert set(schemas.keys()) == {"widgets", "gadgets"}
    assert schemas["widgets"].name == "widgets"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.schema'`

- [ ] **Step 3: Implement schema loading**

```python
# parcours/core/schema.py
"""Loads a category's `categories/<name>.yaml` schema file (see SPECS.md,
"Category schemas (drafts)")."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FieldSpec:
    name: str
    type: str = "string"
    required: bool = False
    vocab: str | None = None
    default: Any = None
    generated: bool = False
    precision: str | None = None


@dataclass
class DedupRule:
    conditions: list[dict]
    outcome: str


@dataclass
class CategorySchema:
    name: str
    handler: str = "generic"
    fields: list[FieldSpec] = field(default_factory=list)
    options: dict = field(default_factory=dict)
    dedup: list[DedupRule] = field(default_factory=list)
    require_one_of: list[list[str]] = field(default_factory=list)

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    def get_field(self, name: str) -> FieldSpec | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None


def load_category_schema(path: Path) -> CategorySchema:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    fields = [FieldSpec(**f) for f in raw.get("fields", [])]
    dedup = [
        DedupRule(conditions=rule["when"], outcome=rule["as"])
        for rule in raw.get("dedup", [])
    ]
    return CategorySchema(
        name=raw["name"],
        handler=raw.get("handler", "generic"),
        fields=fields,
        options=raw.get("options", {}),
        dedup=dedup,
        require_one_of=raw.get("require_one_of", []),
    )


def load_all_schemas(categories_dir: Path) -> dict[str, CategorySchema]:
    schemas = {}
    for path in sorted(categories_dir.glob("*.yaml")):
        schema = load_category_schema(path)
        schemas[schema.name] = schema
    return schemas
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_schema.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/schema.py tests/unit/test_schema.py
git commit -m "Added category schema loading"
```

---

### Task 3: vocab.yaml loading and validation

**Files:**
- Create: `parcours/core/vocab.py`
- Test: `tests/unit/test_vocab.py`

**Interfaces:**
- Produces: `VocabError(Exception)`, `load_vocab(path: Path) ->
  dict[str, list[str]]`, `is_valid_value(vocab: dict[str, list[str]],
  vocab_name: str, value: str) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_vocab.py
import pytest
from parcours.core.vocab import load_vocab, is_valid_value, VocabError


def test_loads_named_lists(tmp_path):
    path = tmp_path / "vocab.yaml"
    path.write_text("widget_status: [draft, published]\ncolor: [red, blue]\n")

    vocab = load_vocab(path)

    assert vocab == {"widget_status": ["draft", "published"], "color": ["red", "blue"]}


def test_rejects_non_list_entries(tmp_path):
    path = tmp_path / "vocab.yaml"
    path.write_text("widget_status: not-a-list\n")

    with pytest.raises(VocabError):
        load_vocab(path)


def test_is_valid_value_true_and_false():
    vocab = {"widget_status": ["draft", "published"]}
    assert is_valid_value(vocab, "widget_status", "draft") is True
    assert is_valid_value(vocab, "widget_status", "archived") is False


def test_is_valid_value_raises_for_unknown_vocab_name():
    vocab = {"widget_status": ["draft"]}
    with pytest.raises(VocabError):
        is_valid_value(vocab, "nonexistent", "draft")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_vocab.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.vocab'`

- [ ] **Step 3: Implement vocab loading**

```python
# parcours/core/vocab.py
"""Loads and checks values against `vocab.yaml` (see SPECS.md, "vocab.yaml
(draft)")."""

from pathlib import Path

import yaml


class VocabError(Exception):
    """Raised for a malformed vocab.yaml or a reference to an unknown list."""


def load_vocab(path: Path) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    for key, values in raw.items():
        if not isinstance(values, list):
            raise VocabError(
                f"vocab.yaml entry '{key}' must be a list, got {type(values).__name__}"
            )
    return raw


def is_valid_value(vocab: dict[str, list[str]], vocab_name: str, value: str) -> bool:
    if vocab_name not in vocab:
        raise VocabError(f"Unknown vocab list: '{vocab_name}'")
    return value in vocab[vocab_name]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_vocab.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/vocab.py tests/unit/test_vocab.py
git commit -m "Added vocab.yaml loading and validation"
```

---

### Task 4: labels.csv loading, lookup, and glossary fallback

**Files:**
- Create: `parcours/core/labels.py`
- Test: `tests/unit/test_labels.py`

**Interfaces:**
- Produces: `LabelEntry` (dataclass: `id: str`, `category: str`,
  `en: str`, `fr: str`), `LabelsTable` (class with `.lookup(category,
  id_, lang) -> str | None`, `.resolve_or_literal(category, id_, lang)
  -> str`, `.missing_translations() -> list[LabelEntry]`),
  `load_labels(path: Path) -> LabelsTable`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_labels.py
from parcours.core.labels import load_labels


def _write_labels(tmp_path, rows):
    path = tmp_path / "labels.csv"
    lines = ["id,category,en,fr"] + [",".join(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_lookup_by_category_and_id(tmp_path):
    path = _write_labels(tmp_path, [
        ("publications", "section", "Publications", "Publications"),
        ("montreal", "location", "Montreal, Canada", "Montreal, Canada"),
    ])
    table = load_labels(path)

    assert table.lookup("section", "publications", "en") == "Publications"
    assert table.lookup("location", "montreal", "fr") == "Montreal, Canada"
    assert table.lookup("section", "nonexistent", "en") is None


def test_resolve_or_literal_falls_back_to_the_id(tmp_path):
    path = _write_labels(tmp_path, [
        ("montreal", "location", "Montreal, Canada", "Montreal, Canada"),
    ])
    table = load_labels(path)

    assert table.resolve_or_literal("location", "montreal", "en") == "Montreal, Canada"
    assert table.resolve_or_literal("location", "some-unlisted-town", "en") == "some-unlisted-town"


def test_missing_translations_finds_blank_sides(tmp_path):
    path = _write_labels(tmp_path, [
        ("complete", "section", "Complete", "Complet"),
        ("missing_fr", "section", "Missing French", ""),
    ])
    table = load_labels(path)

    missing = table.missing_translations()

    assert len(missing) == 1
    assert missing[0].id == "missing_fr"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_labels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.labels'`

- [ ] **Step 3: Implement labels loading**

```python
# parcours/core/labels.py
"""Loads `labels.csv`: the flat lookup for UI-facing strings *and* the
content glossary (e.g. `category: location`) — see SPECS.md, "Labels /
translations"."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LabelEntry:
    id: str
    category: str
    en: str
    fr: str


class LabelsTable:
    def __init__(self, entries: list[LabelEntry]):
        self._entries = entries
        self._by_key: dict[tuple[str, str], LabelEntry] = {
            (e.category, e.id): e for e in entries
        }

    def lookup(self, category: str, id_: str, lang: str) -> str | None:
        entry = self._by_key.get((category, id_))
        if entry is None:
            return None
        value = entry.en if lang == "en" else entry.fr
        return value or None

    def resolve_or_literal(self, category: str, id_: str, lang: str) -> str:
        """Look up a glossary/UI label; fall back to the literal id if
        unmatched, so an unrecognized value never blocks anything (see
        SPECS.md's location-glossary fallback rule)."""
        value = self.lookup(category, id_, lang)
        return value if value is not None else id_

    def missing_translations(self) -> list[LabelEntry]:
        """Entries with a blank English or French side — the "missing
        translation = fail loudly" rule applies to labels.csv's own
        finite set of UI strings, not to per-row category content."""
        return [e for e in self._entries if not e.en.strip() or not e.fr.strip()]


def load_labels(path: Path) -> LabelsTable:
    entries = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            entries.append(
                LabelEntry(
                    id=row["id"],
                    category=row["category"],
                    en=row.get("en", ""),
                    fr=row.get("fr", ""),
                )
            )
    return LabelsTable(entries)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_labels.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/labels.py tests/unit/test_labels.py
git commit -m "Added labels.csv loading with glossary fallback"
```

---

### Task 5: ISO partial date utilities

**Files:**
- Create: `parcours/core/dates.py`
- Test: `tests/unit/test_dates.py`

**Interfaces:**
- Produces: `InvalidDateError(Exception)`, `PartialDate` (dataclass:
  `year: int`, `month: int | None`, `day: int | None`, `precision: str`),
  `parse_partial_date(value: str) -> PartialDate`,
  `meets_precision_floor(value: str, minimum: str) -> bool`,
  `same_year(a: str, b: str) -> bool`, `ranges_overlap(start_a: str,
  end_a: str | None, start_b: str, end_b: str | None) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_dates.py
import pytest
from parcours.core.dates import (
    parse_partial_date,
    meets_precision_floor,
    same_year,
    ranges_overlap,
    InvalidDateError,
)


def test_parses_year_month_and_day_precision():
    assert parse_partial_date("2024").precision == "year"
    assert parse_partial_date("2024-09").precision == "month"
    assert parse_partial_date("2024-09-30").precision == "day"
    parsed = parse_partial_date("2024-09-30")
    assert (parsed.year, parsed.month, parsed.day) == (2024, 9, 30)


def test_rejects_malformed_dates():
    with pytest.raises(InvalidDateError):
        parse_partial_date("not-a-date")


def test_rejects_calendar_invalid_dates():
    with pytest.raises(InvalidDateError):
        parse_partial_date("2024-13")  # no such month
    with pytest.raises(InvalidDateError):
        parse_partial_date("2024-02-30")  # no such day in February


def test_precision_is_a_floor_not_a_ceiling():
    # A field declared precision:year still accepts a fuller date.
    assert meets_precision_floor("2024-09-30", minimum="year") is True
    assert meets_precision_floor("2024-09", minimum="year") is True
    assert meets_precision_floor("2024", minimum="year") is True
    assert meets_precision_floor("2024", minimum="month") is False
    assert meets_precision_floor("2024-09", minimum="day") is False


def test_same_year():
    assert same_year("2024-09-30", "2024-01") is True
    assert same_year("2024", "2025") is False


def test_ranges_overlap_true_cases():
    assert ranges_overlap("2020-01", "2020-06", "2020-05", "2020-12") is True
    assert ranges_overlap("2020", "2021", "2020-06", "2020-07") is True


def test_ranges_overlap_false_case():
    assert ranges_overlap("2020-01", "2020-02", "2020-06", "2020-07") is False


def test_ranges_overlap_ongoing_end_date():
    # A blank or "present" end means ongoing (open-ended).
    assert ranges_overlap("2020-01", None, "2025-01", "2025-06") is True
    assert ranges_overlap("2020-01", "present", "2099-01", "2099-06") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_dates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.dates'`

- [ ] **Step 3: Implement date utilities**

```python
# parcours/core/dates.py
"""ISO partial date parsing and comparison. `date` fields always hold
`2024`, `2024-09`, or `2024-09-30`; `precision` on a schema field is a
*minimum*, never a ceiling (see SPECS.md, "Category schemas (drafts)")."""

import calendar
import re
from dataclasses import dataclass
from datetime import date

_PATTERNS = [
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "day"),
    (re.compile(r"^\d{4}-\d{2}$"), "month"),
    (re.compile(r"^\d{4}$"), "year"),
]

_PRECISION_RANK = {"year": 0, "month": 1, "day": 2}


class InvalidDateError(Exception):
    """Raised when a value isn't a valid ISO partial date."""


@dataclass
class PartialDate:
    year: int
    month: int | None
    day: int | None
    precision: str

    def start_bound(self) -> tuple[int, int, int]:
        return (self.year, self.month or 1, self.day or 1)

    def end_bound(self) -> tuple[int, int, int]:
        month = self.month or 12
        day = self.day or calendar.monthrange(self.year, month)[1]
        return (self.year, month, day)


def parse_partial_date(value: str) -> PartialDate:
    for pattern, precision in _PATTERNS:
        if pattern.match(value):
            parts = value.split("-")
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else None
            day = int(parts[2]) if len(parts) > 2 else None
            try:
                # The regex above only checks digit *shape* (e.g. "13" passes
                # as a month); constructing a real date catches an
                # out-of-range month/day like "2024-13" or "2024-02-30".
                date(year, month or 1, day or 1)
            except ValueError as exc:
                raise InvalidDateError(f"Not a valid date: {value!r} ({exc})") from exc
            return PartialDate(year=year, month=month, day=day, precision=precision)
    raise InvalidDateError(f"Not a valid ISO partial date: {value!r}")


def meets_precision_floor(value: str, minimum: str) -> bool:
    """True if `value` is at least as precise as `minimum` (year < month < day)."""
    parsed = parse_partial_date(value)
    return _PRECISION_RANK[parsed.precision] >= _PRECISION_RANK[minimum]


def same_year(a: str, b: str) -> bool:
    return parse_partial_date(a).year == parse_partial_date(b).year


_OPEN_ENDED = (9999, 12, 31)


def ranges_overlap(
    start_a: str, end_a: str | None, start_b: str, end_b: str | None
) -> bool:
    """True if [start_a, end_a] and [start_b, end_b] intersect. A blank
    or `"present"` end means ongoing (open-ended)."""
    a_start = parse_partial_date(start_a).start_bound()
    b_start = parse_partial_date(start_b).start_bound()
    a_end = parse_partial_date(end_a).end_bound() if end_a and end_a != "present" else _OPEN_ENDED
    b_end = parse_partial_date(end_b).end_bound() if end_b and end_b != "present" else _OPEN_ENDED
    return a_start <= b_end and b_start <= a_end
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_dates.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/dates.py tests/unit/test_dates.py
git commit -m "Added ISO partial date utilities"
```

---

### Task 6: Common validation (required, vocab, require_one_of, precision)

**Files:**
- Create: `parcours/core/validation.py`
- Test: `tests/unit/test_validation.py`

**Interfaces:**
- Consumes: `parcours.core.schema.CategorySchema`/`FieldSpec` (Task 2),
  `parcours.core.vocab.is_valid_value` (Task 3),
  `parcours.core.dates.meets_precision_floor`/`InvalidDateError` (Task 5).
- Produces: `LintIssue` (dataclass: `category: str`, `row_id: str |
  None`, `field: str | None`, `message: str`, `severity: str =
  "error"`), `validate_common(schema: CategorySchema, entry: dict,
  vocab: dict) -> list[LintIssue]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_validation.py
from parcours.core.schema import CategorySchema, FieldSpec
from parcours.core.validation import validate_common


def _schema(**overrides):
    defaults = dict(
        name="widgets",
        fields=[
            FieldSpec(name="id", generated=True),
            FieldSpec(name="title_en"),
            FieldSpec(name="title_fr"),
            FieldSpec(name="status", required=True, vocab="widget_status"),
            FieldSpec(name="start_date", type="date", precision="month", required=True),
        ],
        require_one_of=[["title_en", "title_fr"]],
    )
    defaults.update(overrides)
    return CategorySchema(**defaults)


VOCAB = {"widget_status": ["draft", "published"]}


def test_passes_a_fully_valid_entry():
    entry = {
        "id": "widget-1", "title_en": "A Widget", "title_fr": "",
        "status": "draft", "start_date": "2024-09",
    }
    assert validate_common(_schema(), entry, VOCAB) == []


def test_flags_missing_required_field():
    entry = {"id": "widget-1", "title_en": "A Widget", "status": "", "start_date": "2024-09"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert any(i.field == "status" and i.severity == "error" for i in issues)


def test_flags_invalid_vocab_value():
    entry = {
        "id": "widget-1", "title_en": "A Widget",
        "status": "not-a-real-status", "start_date": "2024-09",
    }
    issues = validate_common(_schema(), entry, VOCAB)
    assert any(i.field == "status" for i in issues)


def test_flags_missing_require_one_of_group():
    entry = {"id": "widget-1", "title_en": "", "title_fr": "", "status": "draft", "start_date": "2024-09"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert any(i.field is None and "title_en" in i.message for i in issues)


def test_require_one_of_passes_with_only_one_filled():
    entry = {"id": "widget-1", "title_en": "", "title_fr": "Un Widget", "status": "draft", "start_date": "2024-09"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert issues == []


def test_flags_date_below_precision_floor():
    entry = {"id": "widget-1", "title_en": "A Widget", "status": "draft", "start_date": "2024"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert any(i.field == "start_date" for i in issues)


def test_flags_unparseable_date():
    entry = {"id": "widget-1", "title_en": "A Widget", "status": "draft", "start_date": "not-a-date"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert any(i.field == "start_date" for i in issues)


def test_generated_fields_are_never_flagged_as_missing():
    entry = {"id": "", "title_en": "A Widget", "status": "draft", "start_date": "2024-09"}
    issues = validate_common(_schema(), entry, VOCAB)
    assert not any(i.field == "id" for i in issues)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_validation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.validation'`

- [ ] **Step 3: Implement common validation**

```python
# parcours/core/validation.py
"""Required/vocab/require_one_of/date-precision checks that apply to
*every* category regardless of handler — "A handler owns: extra field
validation beyond required/vocab checks" (SPECS.md, "Category handlers")."""

from dataclasses import dataclass

from .dates import InvalidDateError, meets_precision_floor
from .schema import CategorySchema
from .vocab import is_valid_value


@dataclass
class LintIssue:
    category: str
    row_id: str | None
    field: str | None
    message: str
    severity: str = "error"


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_common(schema: CategorySchema, entry: dict, vocab: dict) -> list[LintIssue]:
    issues: list[LintIssue] = []
    row_id = entry.get("id")

    for f in schema.fields:
        if f.generated:
            continue
        value = entry.get(f.name)
        blank = _is_blank(value)

        if f.required and blank:
            issues.append(LintIssue(
                schema.name, row_id, f.name, f"'{f.name}' is required but blank",
            ))
            continue

        if blank:
            continue

        if f.vocab and not is_valid_value(vocab, f.vocab, value):
            issues.append(LintIssue(
                schema.name, row_id, f.name,
                f"'{value}' is not a valid value for vocab '{f.vocab}'",
            ))

        if f.type == "date" and f.precision:
            try:
                if not meets_precision_floor(value, f.precision):
                    issues.append(LintIssue(
                        schema.name, row_id, f.name,
                        f"'{f.name}' must have at least {f.precision} precision, got '{value}'",
                    ))
            except InvalidDateError:
                issues.append(LintIssue(
                    schema.name, row_id, f.name, f"'{f.name}' is not a valid date: '{value}'",
                ))

    for group in schema.require_one_of:
        if not any(not _is_blank(entry.get(name)) for name in group):
            issues.append(LintIssue(
                schema.name, row_id, None, f"At least one of {group} must be filled",
            ))

    return issues
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_validation.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/validation.py tests/unit/test_validation.py
git commit -m "Added common field validation shared by all handlers"
```

---

### Task 7: Fuzzy matching utility + handler base + GenericHandler

**Files:**
- Create: `parcours/core/matching.py`
- Create: `parcours/core/handlers/__init__.py`
- Create: `parcours/core/handlers/base.py`
- Create: `parcours/core/handlers/generic.py`
- Test: `tests/unit/test_matching.py`
- Test: `tests/unit/test_handler_generic.py`

**Interfaces:**
- Consumes: `parcours.core.schema.CategorySchema`/`DedupRule` (Task 2),
  `parcours.core.dates.same_year`/`ranges_overlap` (Task 5).
- Produces: `fuzzy_match(a: str, b: str, threshold: float = 0.8) ->
  bool` (matching.py); `Match` (dataclass: `existing_row_id: str`,
  `kind: str`, `reason: str`), `HandlerContext` (dataclass: `data_dir:
  Path`), `CategoryHandler` (ABC: `__init__(self, schema, context)`
  storing both as `self.schema`/`self.context`; `validate(self, entry:
  dict) -> list` returning `[]` by default; abstract
  `find_matches(self, entry: dict, existing: list[dict]) ->
  list[Match]`), `Citable`/`Importable` (`runtime_checkable` Protocols
  matching SPECS.md's handler interface draft) (base.py);
  `GenericHandler(CategoryHandler)` (generic.py).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_matching.py
from parcours.core.matching import fuzzy_match


def test_identical_strings_match():
    assert fuzzy_match("Machine Learning", "Machine Learning") is True


def test_near_duplicate_strings_match():
    assert fuzzy_match("Machine Learning Art", "Machine Learning  Art ") is True


def test_unrelated_strings_do_not_match():
    assert fuzzy_match("Machine Learning", "Completely Different Title") is False


def test_blank_strings_never_match():
    assert fuzzy_match("", "Machine Learning") is False
    assert fuzzy_match("Machine Learning", "") is False
```

```python
# tests/unit/test_handler_generic.py
from parcours.core.schema import CategorySchema, DedupRule
from parcours.core.handlers.base import HandlerContext
from parcours.core.handlers.generic import GenericHandler


def _schema(dedup):
    return CategorySchema(name="widgets", handler="generic", dedup=dedup)


def _context(tmp_path):
    return HandlerContext(data_dir=tmp_path)


def test_exact_match_flags_duplicate(tmp_path):
    schema = _schema([DedupRule(conditions=[{"exact": "organization"}], outcome="duplicate")])
    handler = GenericHandler(schema, _context(tmp_path))
    entry = {"id": "new", "organization": "Acme"}
    existing = [{"id": "old", "organization": "Acme"}]

    matches = handler.find_matches(entry, existing)

    assert len(matches) == 1
    assert matches[0].existing_row_id == "old"
    assert matches[0].kind == "duplicate"


def test_no_match_when_condition_fails(tmp_path):
    schema = _schema([DedupRule(conditions=[{"exact": "organization"}], outcome="duplicate")])
    handler = GenericHandler(schema, _context(tmp_path))
    entry = {"id": "new", "organization": "Acme"}
    existing = [{"id": "old", "organization": "Widgets Inc"}]

    assert handler.find_matches(entry, existing) == []


def test_never_matches_itself_by_id(tmp_path):
    schema = _schema([DedupRule(conditions=[{"exact": "organization"}], outcome="duplicate")])
    handler = GenericHandler(schema, _context(tmp_path))
    entry = {"id": "same", "organization": "Acme"}
    existing = [{"id": "same", "organization": "Acme"}]

    assert handler.find_matches(entry, existing) == []


def test_fuzzy_and_overlap_combined_condition(tmp_path):
    schema = _schema([DedupRule(
        conditions=[{"fuzzy": "title"}, {"overlap": ["start_date", "end_date"]}],
        outcome="duplicate",
    )])
    handler = GenericHandler(schema, _context(tmp_path))
    entry = {"id": "new", "title": "Big Grant", "start_date": "2020-01", "end_date": "2020-06"}
    existing = [{"id": "old", "title": "Big Grant", "start_date": "2020-05", "end_date": "2020-12"}]

    matches = handler.find_matches(entry, existing)

    assert len(matches) == 1


def test_same_year_matcher(tmp_path):
    schema = _schema([DedupRule(conditions=[{"same_year": "date"}], outcome="duplicate")])
    handler = GenericHandler(schema, _context(tmp_path))
    entry = {"id": "new", "date": "2024-06-01"}
    existing = [{"id": "old", "date": "2024-01-15"}]

    assert len(handler.find_matches(entry, existing)) == 1


def test_related_outcome_is_preserved(tmp_path):
    schema = _schema([DedupRule(conditions=[{"exact": "student_name"}], outcome="related")])
    handler = GenericHandler(schema, _context(tmp_path))
    entry = {"id": "new", "student_name": "Ian Example"}
    existing = [{"id": "old", "student_name": "Ian Example"}]

    matches = handler.find_matches(entry, existing)

    assert matches[0].kind == "related"


def test_generic_handler_validate_returns_no_extra_issues(tmp_path):
    schema = _schema([])
    handler = GenericHandler(schema, _context(tmp_path))
    assert handler.validate({"id": "new"}) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_matching.py tests/unit/test_handler_generic.py -v`
Expected: FAIL with `ModuleNotFoundError` for `parcours.core.matching` and `parcours.core.handlers`

- [ ] **Step 3: Implement the matching utility, handler base, and GenericHandler**

```python
# parcours/core/matching.py
"""Shared fuzzy-string matching used by dedup rules (see SPECS.md,
"Category schemas (drafts)": the `fuzzy` matcher)."""

import difflib


def fuzzy_match(a: str, b: str, threshold: float = 0.8) -> bool:
    if not a or not b:
        return False
    ratio = difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()
    return ratio >= threshold
```

```python
# parcours/core/handlers/__init__.py
```

```python
# parcours/core/handlers/base.py
"""The handler interface every category's behavior plugs into (see
SPECS.md, "Category handlers" and its "Handler interface (draft)")."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class Match:
    existing_row_id: str
    kind: str  # "duplicate" | "related"
    reason: str


@dataclass
class HandlerContext:
    data_dir: Path


class CategoryHandler(ABC):
    """Generic behavior by default; a schema's `handler:` module provides
    a subclass for anything category-specific."""

    def __init__(self, schema, context: HandlerContext):
        self.schema = schema
        self.context = context

    def validate(self, entry: dict) -> list:
        """Handler-specific validation, beyond the common
        required/vocab/require_one_of/precision checks every category
        already gets from `core.validation.validate_common`."""
        return []

    @abstractmethod
    def find_matches(self, entry: dict, existing: list[dict]) -> list[Match]:
        """Check `entry` against `existing` rows per the schema's own
        `dedup:` rules (or handler-specific logic, e.g. `publications`)."""


@runtime_checkable
class Citable(Protocol):
    def citation(self, key: str, style: str, lang: str) -> str: ...


@runtime_checkable
class Importable(Protocol):
    def plan_import(self, source, options): ...
```

```python
# parcours/core/handlers/generic.py
"""The default handler: reads a category's declarative `dedup:` rules
from its schema rather than implementing anything category-specific
(see SPECS.md, "Category handlers")."""

from ..dates import ranges_overlap, same_year
from ..matching import fuzzy_match
from .base import CategoryHandler, Match


class GenericHandler(CategoryHandler):
    def find_matches(self, entry: dict, existing: list[dict]) -> list[Match]:
        matches = []
        for rule in self.schema.dedup:
            for existing_row in existing:
                if existing_row.get("id") == entry.get("id"):
                    continue
                if self._rule_matches(rule, entry, existing_row):
                    matches.append(Match(
                        existing_row_id=existing_row["id"],
                        kind=rule.outcome,
                        reason=f"Matched dedup rule {rule.conditions}",
                    ))
        return matches

    def _rule_matches(self, rule, entry: dict, existing_row: dict) -> bool:
        return all(self._condition_matches(cond, entry, existing_row) for cond in rule.conditions)

    def _condition_matches(self, cond: dict, entry: dict, existing_row: dict) -> bool:
        if "exact" in cond:
            names = cond["exact"] if isinstance(cond["exact"], list) else [cond["exact"]]
            return any(entry.get(n) == existing_row.get(n) for n in names if entry.get(n))
        if "fuzzy" in cond:
            names = cond["fuzzy"] if isinstance(cond["fuzzy"], list) else [cond["fuzzy"]]
            return any(fuzzy_match(entry.get(n, ""), existing_row.get(n, "")) for n in names)
        if "overlap" in cond:
            start_field, end_field = cond["overlap"]
            return ranges_overlap(
                entry.get(start_field), entry.get(end_field),
                existing_row.get(start_field), existing_row.get(end_field),
            )
        if "same_year" in cond:
            field_name = cond["same_year"]
            a, b = entry.get(field_name), existing_row.get(field_name)
            return bool(a and b and same_year(a, b))
        raise ValueError(f"Unknown dedup matcher: {cond}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_matching.py tests/unit/test_handler_generic.py -v`
Expected: PASS (4 + 7 = 11 tests)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/matching.py parcours/core/handlers/ \
        tests/unit/test_matching.py tests/unit/test_handler_generic.py
git commit -m "Added fuzzy matching, handler base class, and GenericHandler"
```

---

### Task 8: PublicationsHandler (Zotero citekey resolution)

**Files:**
- Create: `parcours/core/handlers/publications.py`
- Test: `tests/unit/test_handler_publications.py`

**Interfaces:**
- Consumes: `CategoryHandler`/`Match`/`HandlerContext` (Task 7),
  `fuzzy_match` (Task 7), `LintIssue` (Task 6).
- Produces: `PublicationsHandler(CategoryHandler)` with a `resolve(self,
  citekey: str) -> dict | None` method in addition to
  `validate`/`find_matches`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_handler_publications.py
import json

from parcours.core.schema import CategorySchema
from parcours.core.handlers.base import HandlerContext
from parcours.core.handlers.publications import PublicationsHandler


def _write_csl_json(tmp_path, records):
    zotero_dir = tmp_path / "zotero"
    zotero_dir.mkdir()
    path = zotero_dir / "library.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return "zotero/library.json"


def _schema(json_rel_path):
    return CategorySchema(
        name="publications",
        handler="publications",
        options={"json": json_rel_path},
    )


def test_resolve_finds_a_known_citekey(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "audry2024plaquette", "title": "Plaquette", "DOI": "10.1/plaquette",
         "issued": {"date-parts": [[2024]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    record = handler.resolve("audry2024plaquette")

    assert record is not None
    assert record["title"] == "Plaquette"


def test_resolve_returns_none_for_unknown_citekey(tmp_path):
    json_path = _write_csl_json(tmp_path, [])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))
    assert handler.resolve("nonexistent") is None


def test_validate_flags_unresolved_citekey(tmp_path):
    json_path = _write_csl_json(tmp_path, [])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    issues = handler.validate({"id": "pub-1", "citekey": "nonexistent"})

    assert len(issues) == 1
    assert issues[0].field == "citekey"


def test_validate_passes_a_resolvable_citekey(tmp_path):
    json_path = _write_csl_json(tmp_path, [{"id": "audry2024plaquette", "title": "Plaquette"}])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    assert handler.validate({"id": "pub-1", "citekey": "audry2024plaquette"}) == []


def test_find_matches_same_citekey_is_duplicate(tmp_path):
    json_path = _write_csl_json(tmp_path, [])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))
    entry = {"id": "new", "citekey": "same-key"}
    existing = [{"id": "old", "citekey": "same-key"}]

    matches = handler.find_matches(entry, existing)

    assert len(matches) == 1
    assert matches[0].kind == "duplicate"
    assert matches[0].existing_row_id == "old"


def test_find_matches_same_doi_is_duplicate(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "key-a", "title": "Title A", "DOI": "10.1/shared"},
        {"id": "key-b", "title": "Different Title", "DOI": "10.1/shared"},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))
    entry = {"id": "new", "citekey": "key-a"}
    existing = [{"id": "old", "citekey": "key-b"}]

    matches = handler.find_matches(entry, existing)

    assert len(matches) == 1
    assert matches[0].kind == "duplicate"


def test_find_matches_fuzzy_title_and_same_year_is_duplicate(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "key-a", "title": "Machine Learning Art", "issued": {"date-parts": [[2024]]}},
        {"id": "key-b", "title": "Machine Learning  Art", "issued": {"date-parts": [[2024]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))
    entry = {"id": "new", "citekey": "key-a"}
    existing = [{"id": "old", "citekey": "key-b"}]

    matches = handler.find_matches(entry, existing)

    assert len(matches) == 1


def test_find_matches_no_false_positive_for_unrelated_publications(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "key-a", "title": "Machine Learning Art", "DOI": "10.1/a",
         "issued": {"date-parts": [[2024]]}},
        {"id": "key-b", "title": "Completely Unrelated Topic", "DOI": "10.1/b",
         "issued": {"date-parts": [[2019]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))
    entry = {"id": "new", "citekey": "key-a"}
    existing = [{"id": "old", "citekey": "key-b"}]

    assert handler.find_matches(entry, existing) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_handler_publications.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.handlers.publications'`

- [ ] **Step 3: Implement PublicationsHandler**

```python
# parcours/core/handlers/publications.py
"""The `publications` handler: citekey resolution against a Zotero/Better
BibTeX CSL-JSON export, required-and-must-resolve citekey validation, and
DOI+fuzzy-title dedup (see SPECS.md, "publications (handler:
publications)")."""

import json

from ..matching import fuzzy_match
from ..validation import LintIssue
from .base import CategoryHandler, Match


class PublicationsHandler(CategoryHandler):
    def __init__(self, schema, context):
        super().__init__(schema, context)
        self._csl_by_key = self._load_csl_json()

    def _load_csl_json(self) -> dict:
        json_path = self.context.data_dir / self.schema.options["json"]
        if not json_path.is_file():
            return {}
        with open(json_path, "r", encoding="utf-8") as fh:
            records = json.load(fh)
        return {record["id"]: record for record in records}

    def resolve(self, citekey: str) -> dict | None:
        return self._csl_by_key.get(citekey)

    def validate(self, entry: dict) -> list[LintIssue]:
        citekey = entry.get("citekey") or ""
        if citekey and self.resolve(citekey) is None:
            return [LintIssue(
                self.schema.name, entry.get("id"), "citekey",
                f"citekey '{citekey}' does not resolve in the Zotero export",
            )]
        return []

    def find_matches(self, entry: dict, existing: list[dict]) -> list[Match]:
        matches = []
        entry_record = self.resolve(entry.get("citekey", ""))
        entry_doi = (entry_record or {}).get("DOI")

        for existing_row in existing:
            if existing_row.get("id") == entry.get("id"):
                continue

            if entry.get("citekey") and entry.get("citekey") == existing_row.get("citekey"):
                matches.append(Match(existing_row["id"], "duplicate", "Same citekey"))
                continue

            existing_record = self.resolve(existing_row.get("citekey", ""))
            existing_doi = (existing_record or {}).get("DOI")
            if entry_doi and existing_doi and entry_doi == existing_doi:
                matches.append(Match(existing_row["id"], "duplicate", "Same DOI"))
                continue

            if entry_record and existing_record:
                year_a = _csl_year(entry_record)
                year_b = _csl_year(existing_record)
                titles_match = fuzzy_match(
                    entry_record.get("title", ""), existing_record.get("title", "")
                )
                if year_a is not None and year_a == year_b and titles_match:
                    matches.append(Match(existing_row["id"], "duplicate", "Fuzzy title + same year"))

        return matches


def _csl_year(record: dict) -> int | None:
    try:
        return record["issued"]["date-parts"][0][0]
    except (KeyError, IndexError, TypeError):
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_handler_publications.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/handlers/publications.py tests/unit/test_handler_publications.py
git commit -m "Added PublicationsHandler with Zotero citekey resolution"
```

---

### Task 9: DuckDB-backed category data access

**Files:**
- Create: `parcours/core/data.py`
- Test: `tests/unit/test_data.py`

**Interfaces:**
- Produces: `load_category_rows(data_dir: Path, category_name: str) ->
  list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_data.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.data'`

- [ ] **Step 3: Implement DuckDB data access**

```python
# parcours/core/data.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_data.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/data.py tests/unit/test_data.py
git commit -m "Added DuckDB-backed category CSV loading"
```

---

### Task 10: Lint orchestration + `parco lint` CLI command

**Files:**
- Create: `parcours/core/lint.py`
- Create: `parcours/cli/main.py`
- Test: `tests/unit/test_lint.py`
- Test: `tests/integration/test_cli_lint.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/unit/__init__.py`

**Interfaces:**
- Consumes: everything from Tasks 1–9.
- Produces: `run_lint(data_dir: Path, category_filter: str | None =
  None) -> list[LintIssue]` (lint.py); Typer app `app` with a `lint`
  command (cli/main.py). **Scope note:** this task's lint only checks
  labels-completeness and per-row `validate_common`/handler `validate`
  — it does *not* yet check labels.csv against profile section ids
  (profiles don't exist in code yet) or exchange-rate gaps (currency
  conversion doesn't exist yet); both are noted as follow-up work for
  whichever future plan adds profiles/currency.

- [ ] **Step 1: Write the failing test for `run_lint`**

```python
# tests/unit/test_lint.py
import json

from parcours.core.lint import run_lint


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
    (tmp_path / "labels.csv").write_text("id,category,en,fr\nwidgets,section,Widgets,Widgets\n")
    return tmp_path


def test_no_issues_for_valid_data(tmp_path):
    repo = _setup_data_repo(tmp_path)
    (repo / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")

    assert run_lint(repo) == []


def test_flags_a_missing_required_field(tmp_path):
    repo = _setup_data_repo(tmp_path)
    (repo / "widgets.csv").write_text("id,title_en,status\nwidget-1,,draft\n")

    issues = run_lint(repo)

    assert any(i.field == "title_en" for i in issues)


def test_flags_a_missing_labels_translation(tmp_path):
    repo = _setup_data_repo(tmp_path)
    (repo / "labels.csv").write_text("id,category,en,fr\nwidgets,section,Widgets,\n")
    (repo / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")

    issues = run_lint(repo)

    assert any(i.category == "labels" for i in issues)


def test_category_filter_only_checks_that_category(tmp_path):
    repo = _setup_data_repo(tmp_path)
    (repo / "categories" / "gadgets.yaml").write_text("""
name: gadgets
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en, required: true}
""")
    (repo / "widgets.csv").write_text("id,title_en,status\nwidget-1,,draft\n")
    (repo / "gadgets.csv").write_text("id,title_en\ngadget-1,,\n")

    issues = run_lint(repo, category_filter="widgets")

    assert all(i.category in ("widgets", "labels") for i in issues)
    assert any(i.category == "widgets" for i in issues)


def test_publications_handler_is_wired_up(tmp_path):
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
    (tmp_path / "vocab.yaml").write_text("{}\n")
    (tmp_path / "labels.csv").write_text("id,category,en,fr\n")
    (tmp_path / "zotero").mkdir()
    (tmp_path / "zotero" / "library.json").write_text(json.dumps([]))
    (tmp_path / "publications.csv").write_text("id,citekey\npub-1,nonexistent-key\n")

    issues = run_lint(tmp_path)

    assert any(i.field == "citekey" for i in issues)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_lint.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.lint'`

- [ ] **Step 3: Implement lint orchestration**

```python
# parcours/core/lint.py
"""Ties schema + vocab + labels + handlers + data together into
`parco lint` (see SPECS.md, "CLI" → "Validation"). Returns structured
`LintIssue`s — no printing here, per the core/interface split."""

import importlib
from pathlib import Path

from .data import load_category_rows
from .handlers.base import HandlerContext
from .handlers.generic import GenericHandler
from .handlers.publications import PublicationsHandler
from .labels import load_labels
from .schema import CategorySchema, load_all_schemas
from .validation import LintIssue, validate_common
from .vocab import load_vocab

_BUILTIN_HANDLERS = {
    "generic": GenericHandler,
    "publications": PublicationsHandler,
}


def _load_handler(schema: CategorySchema, context: HandlerContext):
    handler_name = schema.handler
    if ":" in handler_name:
        module_name, class_name = handler_name.split(":")
        module = importlib.import_module(module_name)
        handler_cls = getattr(module, class_name)
    else:
        handler_cls = _BUILTIN_HANDLERS[handler_name]
    return handler_cls(schema, context)


def run_lint(data_dir: Path, category_filter: str | None = None) -> list[LintIssue]:
    issues: list[LintIssue] = []

    schemas = load_all_schemas(data_dir / "categories")
    vocab = load_vocab(data_dir / "vocab.yaml")
    labels = load_labels(data_dir / "labels.csv")

    for entry in labels.missing_translations():
        issues.append(LintIssue(
            "labels", entry.id, entry.category,
            f"labels.csv id '{entry.id}' (category '{entry.category}') is missing a translation",
        ))

    for name, schema in schemas.items():
        if category_filter and name != category_filter:
            continue
        rows = load_category_rows(data_dir, name)
        handler = _load_handler(schema, HandlerContext(data_dir=data_dir))
        for row in rows:
            issues.extend(validate_common(schema, row, vocab))
            issues.extend(handler.validate(row))

    return issues
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_lint.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the failing integration test for the CLI**

```python
# tests/integration/__init__.py
```

```python
# tests/unit/__init__.py
```

```python
# tests/integration/test_cli_lint.py
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
    (tmp_path / "labels.csv").write_text("id,category,en,fr\nwidgets,section,Widgets,Widgets\n")
    return tmp_path


def test_lint_command_reports_no_issues_with_exit_code_zero(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["lint"])

    assert result.exit_code == 0
    assert "No lint issues found" in result.stdout


def test_lint_command_reports_issues_with_nonzero_exit_code(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "widgets.csv").write_text("id,title_en,status\nwidget-1,,draft\n")
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["lint"])

    assert result.exit_code == 1
    assert "title_en" in result.stdout


def test_lint_command_fails_clearly_with_no_data_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "empty_home")

    result = runner.invoke(app, ["lint"])

    assert result.exit_code == 2
    assert "No data repo found" in result.stdout


def test_lint_command_accepts_a_category_filter(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "widgets.csv").write_text("id,title_en,status\nwidget-1,A Widget,draft\n")
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["lint", "widgets"])

    assert result.exit_code == 0
```

- [ ] **Step 6: Run the integration test to verify it fails**

Run: `pytest tests/integration/test_cli_lint.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.cli.main'`

- [ ] **Step 7: Implement the CLI**

```python
# parcours/cli/main.py
"""The Typer app — thin, owns all prompts/printing (see SPECS.md, "Code
architecture: modular core + thin interfaces")."""

import typer

from ..core.lint import run_lint
from ..core.repo import DataRepoNotFound, find_data_repo

app = typer.Typer()


@app.command()
def lint(category: str = typer.Argument(None, help="Only lint this category")):
    """Check category data against its schema, vocab, and labels."""
    try:
        data_dir = find_data_repo()
    except DataRepoNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    issues = run_lint(data_dir, category_filter=category)

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


if __name__ == "__main__":
    app()
```

- [ ] **Step 8: Run all tests to verify everything passes**

Run: `pytest tests/ -v`
Expected: PASS (all tests across every task)

- [ ] **Step 9: Commit**

```bash
git add parcours/core/lint.py parcours/cli/main.py \
        tests/unit/test_lint.py tests/integration/test_cli_lint.py \
        tests/unit/__init__.py tests/integration/__init__.py
git commit -m "Added lint orchestration and the parco lint command"
```

---

## What this plan deliberately does not cover

Follow-up plans, once this foundation exists:
- The wizard (`add`/`edit`), duplicate-match picker, and confirm-before-write
  screen (all CLI-layer prompting on top of `find_matches`, which this
  plan builds and unit-tests but doesn't wire into any command).
- `sync`/`remote` (git operations) and currency conversion/`refresh rates`.
- `build` (profile → RenderCV YAML → rendered output) and `views.yaml`
  loading — needs the entry-type mapping design from SPECS.md's
  "views.yaml (draft)".
- `refresh zotero` and `import ccv` (the actual importers — this plan's
  `PublicationsHandler` only *resolves* an existing citekey against an
  already-exported CSL-JSON file, it doesn't fetch or parse anything new).
- `labels.csv` completeness checked against profile section ids, and the
  exchange-rate-gap lint warning — both need profiles/currency to exist
  first (noted inline on Task 10).
- Custom handlers loaded by dotted import path are supported by
  `_load_handler`'s `":"` branch but have no test coverage here, since
  there's no second real custom handler yet to test against.
- `parco lint --fix` (unambiguous auto-fixes like whitespace) — this
  plan's `lint` command only reports issues, it never writes anything
  back to a CSV.
