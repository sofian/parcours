# Build Pipeline (First Cut) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `parco build` — profile → RenderCV YAML → rendered CV — covering all 18 non-`skills` categories, PDF/Typst/HTML output, with `skills` aggregation, `docx`, citeproc-styled citations, and currency conversion explicitly deferred.

**Architecture:** Five small, independently-testable core modules (`data.py`'s query extension, `templating.py`, `identity.py`, `profiles.py`, `views.py`) feed a `build.py` orchestrator that assembles a RenderCV-ready dict and shells out to the `rendercv` CLI (an external dependency, like Pandoc — never imported directly, since its PDF path needs an extra `rendercv_fonts` package a plain install doesn't pull in). A `parco build` command in `cli/main.py` wires it together with lint-gating and file output.

**Tech Stack:** Same as prior plans — Python ≥3.11, DuckDB, Typer, pytest — plus `rendercv[full]>=2.8` (new dependency; the `[full]` extra is required for PDF generation to work at all).

**Spec:** SPECS.md (repo root) — see "Profiles", "views.yaml (draft)", "Translations" (the `glossary:` mechanism this plan consumes), "Build / query" under CLI, and "Identity / personal-info config".

## Global Constraints

- `parcours/core/` never does interactive I/O — no `print()`, `input()`, `sys.exit()`. `build.py` may shell out to `rendercv` via `subprocess` (that's an external tool invocation, not user interaction, same category as `entries.py`'s git calls) and read files, but never prints or prompts; the CLI owns all of that.
- No LaTeX output — RenderCV 2.8 renders through Typst, not LaTeX (verified against the real installed package's CLI, which has no `--latex-path`/`--tex-path` flag at all). Supported formats for this plan: `pdf`, `typst`, `html`. `docx` is explicitly rejected with a clear "not yet supported" message.
- The `{field}` template mini-language (`core/templating.py`): a template with **no** `{` anywhere is a literal field name — direct copy of `row.get(template)`, any type. A **bare** `"{field}"` (nothing else in the string) auto-resolves a bilingual pair (`<field>_en`/`<field>_fr`) by the profile's language, falling back to the other language if the profile's own side is blank — never dropping a value just from a language mismatch — or to a plain (non-suffixed) field if no bilingual pair exists for that name; if the resolved value is already a Python list, it passes through unchanged (needed for `PublicationEntry.authors: list[str]`). Any **compound** template (multiple `{field}`s and/or literal text mixed in) always produces a string, with each placeholder resolved via the same bilingual-fallback rule. A **list** of templates (used for `highlights`) resolves each item independently and drops falsy/empty results.
- Zotero-backed categories (`publications`, `review`, `catalog`, i.e. any category whose handler is `PublicationsHandler`): before templating, `build` resolves the row's `citekey` via `PublicationsHandler.resolve()` and merges normalized fields into the row under fixed keys — `zotero_title`, `zotero_authors` (a `list[str]` of `"Given Family"`, not joined into one string), `zotero_journal`, `zotero_doi`, `zotero_url`, `zotero_date` (an ISO partial date string). An unresolved `citekey` simply means those keys are absent — already an `error`-severity `parco lint` issue, so `build` refuses to run past it unless `--force`.
- A RenderCV `Section` dict is keyed by the **literal displayed title** (RenderCV auto-detects entry type from each entry's field shape — no explicit type tag in the YAML). Section titles must be resolved from `translations.csv` (`category: "section"`, id = the profile section's own `id`) via `TranslationsTable.resolve_or_literal` **before** assembling the `sections` dict — never after.
- `parco build` refuses to run if `parco lint`, scoped to each category the profile's sections reference, reports any `error`-severity issue — unless `--force`. Lint warnings (e.g. the `glossary:` check) never block.
- `profiles/*.yaml`'s `extends` merge is a single, shallow level: the child's top-level keys (`meta`, `sections`) replace the base's wholesale where present; no chained `extends`, no per-section deep merge.
- `meta.output`'s default is `"cv-{name}-{language}"` when the profile doesn't set one; it uses the same `{field}` template engine, resolved against the profile's own `meta` dict (no bilingual fields there, so this always takes the direct/fallback plain-lookup path).
- CSV writes/reads throughout this plan follow the same conventions as prior plans: `ALL_VARCHAR=TRUE` via DuckDB for reads (ISO partial date strings, ints, everything stays a string until a specific consumer needs otherwise).

---

### Task 1: `core/data.py` — filtered, ordered, limited category queries

**Files:**
- Modify: `parcours/core/data.py` (add a new function; `load_category_rows` stays untouched)
- Test: `tests/unit/test_data.py` (extend the existing file)

**Interfaces:**
- Consumes: nothing new (same DuckDB/`ALL_VARCHAR` pattern `load_category_rows` already uses).
- Produces: `query_category_rows(data_dir: Path, category_name: str, filters: dict[str, list[str]] | None = None, order_by: str | None = None, limit: int | None = None) -> list[dict]` — later consumed by `build.py` (Task 7) to run a profile section's `filter`/`order_by`/`limit` against a category's CSV.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_data.py`:

```python
import duckdb
import pytest

from parcours.core.data import query_category_rows


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_data.py -v`
Expected: FAIL with `ImportError: cannot import name 'query_category_rows'`

- [ ] **Step 3: Implement `query_category_rows`**

Append to `parcours/core/data.py` (leave `load_category_rows` exactly as it is):

```python
def query_category_rows(
    data_dir: Path,
    category_name: str,
    filters: dict[str, list[str]] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    csv_path = data_dir / f"{category_name}.csv"
    if not csv_path.is_file():
        return []

    query = "SELECT * FROM read_csv_auto(?, ALL_VARCHAR=TRUE)"
    params: list = [str(csv_path)]

    if filters:
        clauses = []
        for field_name, allowed_values in filters.items():
            placeholders = ", ".join("?" for _ in allowed_values)
            clauses.append(f'"{field_name}" IN ({placeholders})')
            params.extend(allowed_values)
        query += " WHERE " + " AND ".join(clauses)

    if order_by:
        parts = order_by.split()
        field_name = parts[0]
        direction = parts[1].upper() if len(parts) > 1 else "ASC"
        if direction not in ("ASC", "DESC"):
            raise ValueError(
                f"Invalid order_by direction '{direction}' for category '{category_name}' "
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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_data.py -v`
Expected: PASS (9 new tests, plus the 3 existing ones unchanged)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/data.py tests/unit/test_data.py
git commit -m "Added filtered/ordered/limited category queries"
```

---

### Task 2: `core/templating.py` — the `{field}` mini-language

**Files:**
- Create: `parcours/core/templating.py`
- Test: `tests/unit/test_templating.py`

**Interfaces:**
- Consumes: nothing (pure functions over plain dicts).
- Produces: `resolve_field(row: dict, field_name: str, language: str)` and `resolve_template(template, row: dict, language: str)` — consumed by `core/identity.py` (Task 3, `resolve_field` only), `core/profiles.py` (Task 4, `resolve_template` for `meta.output`), and `core/build.py` (Task 7, `resolve_template` for view field mappings).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_templating.py
from parcours.core.templating import resolve_field, resolve_template


def test_resolve_field_prefers_the_requested_language():
    row = {"title_en": "English Title", "title_fr": "Titre français"}
    assert resolve_field(row, "title", "en") == "English Title"
    assert resolve_field(row, "title", "fr") == "Titre français"


def test_resolve_field_falls_back_to_the_other_language_when_blank():
    row = {"title_en": "", "title_fr": "Titre français"}
    assert resolve_field(row, "title", "en") == "Titre français"


def test_resolve_field_falls_back_to_a_plain_field_with_no_bilingual_pair():
    row = {"organization": "Acme"}
    assert resolve_field(row, "organization", "en") == "Acme"


def test_resolve_field_returns_none_when_nothing_matches():
    row = {}
    assert resolve_field(row, "title", "en") is None


def test_resolve_template_with_no_braces_is_a_direct_field_copy():
    row = {"start_date": "2020-01", "weight": "5"}
    assert resolve_template("start_date", row, "en") == "2020-01"


def test_resolve_template_direct_copy_of_a_missing_field_is_none():
    assert resolve_template("start_date", {}, "en") is None


def test_resolve_template_bare_placeholder_resolves_bilingual():
    row = {"title_en": "English", "title_fr": "Français"}
    assert resolve_template("{title}", row, "fr") == "Français"


def test_resolve_template_bare_placeholder_passes_through_a_list_unchanged():
    row = {"zotero_authors": ["Jane Doe", "John Smith"]}
    assert resolve_template("{zotero_authors}", row, "en") == ["Jane Doe", "John Smith"]


def test_resolve_template_compound_string_substitutes_each_placeholder():
    row = {"funder": "FRQSC", "role": "PI"}
    assert resolve_template("{funder} — {role}", row, "en") == "FRQSC — PI"


def test_resolve_template_compound_string_treats_blank_fields_as_empty():
    row = {"funder": "FRQSC", "role": ""}
    assert resolve_template("{funder} — {role}", row, "en") == "FRQSC — "


def test_resolve_template_list_resolves_each_item_and_drops_blanks():
    row = {"funder": "FRQSC", "role": "PI", "co_investigators": ""}
    result = resolve_template(
        ["{funder} — {role}", "{co_investigators}", "amount"], row, "en"
    )
    assert result == ["FRQSC — PI"]


def test_resolve_template_non_string_non_list_passes_through():
    assert resolve_template(None, {"x": "y"}, "en") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_templating.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.templating'`

- [ ] **Step 3: Implement `templating.py`**

```python
# parcours/core/templating.py
"""The `{field}` template mini-language used by `views.yaml`'s field
mappings, `profiles/*.yaml`'s `meta.output`, and identity variant
resolution (see SPECS.md, "views.yaml (draft)"). Pure functions over
plain dicts — no file I/O, no category/schema knowledge."""

import re

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def resolve_field(row: dict, field_name: str, language: str):
    """Returns the raw resolved value (any type) for one field name,
    auto-resolving a bilingual pair (`<field>_en`/`<field>_fr`) by
    language — falling back to the other language if the profile's own
    is blank, so a value is never dropped just from a language mismatch
    — or to a plain (non-suffixed) field if no bilingual pair exists."""
    primary_key = f"{field_name}_{language}"
    if primary_key in row:
        value = row.get(primary_key)
        if value:
            return value
        other_language = "fr" if language == "en" else "en"
        other_value = row.get(f"{field_name}_{other_language}")
        if other_value:
            return other_value
        return value
    return row.get(field_name)


def resolve_template(template, row: dict, language: str):
    """`template` is a plain field name with no braces at all (direct
    copy, any type), a bare `"{field}"` (bilingual-resolved via
    `resolve_field`; passed through unchanged if the resolved value is
    already a list — needed for `PublicationEntry.authors`), a compound
    string mixing `{field}`s and literal text (always stringified), or a
    list of any of the above (each resolved independently, blank/falsy
    results dropped — used for `highlights`)."""
    if isinstance(template, list):
        resolved = [resolve_template(item, row, language) for item in template]
        return [value for value in resolved if value]

    if not isinstance(template, str):
        return template

    if "{" not in template:
        return row.get(template)

    bare_match = _PLACEHOLDER.fullmatch(template)
    if bare_match:
        return resolve_field(row, bare_match.group(1), language)

    def _substitute(match):
        value = resolve_field(row, match.group(1), language)
        return str(value) if value else ""

    return _PLACEHOLDER.sub(_substitute, template)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_templating.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/templating.py tests/unit/test_templating.py
git commit -m "Added the field template mini-language"
```

---

### Task 3: `core/identity.py` — identity.yaml loading + variant resolution

**Files:**
- Create: `parcours/core/identity.py`
- Test: `tests/unit/test_identity.py`

**Interfaces:**
- Consumes: `resolve_field` from `core/templating.py` (Task 2).
- Produces: `load_identity(path: Path) -> dict`, `resolve_identity(identity: dict, variant_name: str, language: str) -> dict`, `IdentityVariantNotFound` — consumed by `core/build.py` (Task 7) to populate RenderCV's `cv:` name/headline/email/phone/website.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_identity.py
import pytest

from parcours.core.identity import IdentityVariantNotFound, load_identity, resolve_identity


def _write_identity(tmp_path):
    path = tmp_path / "identity.yaml"
    path.write_text("""
name:
  first: Jane
  last: Doe
variants:
  artist:
    email: contact@example.com
    homepage: example.com
  academic:
    email: jane.doe@example.edu
    homepage: example.com
    phone: "+1 555-000-1111"
    title_en: "Associate Professor"
    title_fr: "Professeure agrégée"
""", encoding="utf-8")
    return path


def test_load_identity_reads_the_yaml(tmp_path):
    identity = load_identity(_write_identity(tmp_path))
    assert identity["name"]["first"] == "Jane"


def test_resolve_identity_builds_full_name_and_contact_fields(tmp_path):
    identity = load_identity(_write_identity(tmp_path))

    cv = resolve_identity(identity, "academic", "en")

    assert cv["name"] == "Jane Doe"
    assert cv["email"] == "jane.doe@example.edu"
    assert cv["phone"] == "+1 555-000-1111"
    assert cv["website"] == "example.com"


def test_resolve_identity_resolves_bilingual_title_by_language():
    identity = {
        "name": {"first": "Jane", "last": "Doe"},
        "variants": {"academic": {"title_en": "Associate Professor", "title_fr": "Professeure agrégée"}},
    }

    assert resolve_identity(identity, "academic", "en")["headline"] == "Associate Professor"
    assert resolve_identity(identity, "academic", "fr")["headline"] == "Professeure agrégée"


def test_resolve_identity_omits_headline_when_variant_has_no_title(tmp_path):
    identity = load_identity(_write_identity(tmp_path))

    cv = resolve_identity(identity, "artist", "en")

    assert "headline" not in cv


def test_resolve_identity_raises_for_unknown_variant(tmp_path):
    identity = load_identity(_write_identity(tmp_path))

    with pytest.raises(IdentityVariantNotFound, match="job-application"):
        resolve_identity(identity, "job-application", "en")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_identity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.identity'`

- [ ] **Step 3: Implement `identity.py`**

```python
# parcours/core/identity.py
"""Loads `identity.yaml`: the singleton (not a CSV category) config
holding what every CV needs regardless of section content — name,
contact info, and audience-specific variants (see SPECS.md, "Identity /
personal-info config")."""

from pathlib import Path

import yaml

from .templating import resolve_field


class IdentityVariantNotFound(Exception):
    """Raised when a profile names an `identity_variant` that doesn't
    exist in identity.yaml."""


def load_identity(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def resolve_identity(identity: dict, variant_name: str, language: str) -> dict:
    variants = identity.get("variants", {})
    if variant_name not in variants:
        raise IdentityVariantNotFound(f"No identity variant '{variant_name}' in identity.yaml")
    variant_fields = variants[variant_name]

    name = identity.get("name", {})
    full_name = " ".join(part for part in [name.get("first"), name.get("last")] if part)

    cv = {"name": full_name}

    headline = resolve_field(variant_fields, "title", language)
    if headline:
        cv["headline"] = headline

    for source_key, cv_key in [("email", "email"), ("phone", "phone"), ("homepage", "website")]:
        value = variant_fields.get(source_key)
        if value:
            cv[cv_key] = value

    return cv
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_identity.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/identity.py tests/unit/test_identity.py
git commit -m "Added identity.yaml loading and variant resolution"
```

---

### Task 4: `core/profiles.py` — profile loading with `extends` + output templating

**Files:**
- Create: `parcours/core/profiles.py`
- Test: `tests/unit/test_profiles.py`

**Interfaces:**
- Consumes: `resolve_template` from `core/templating.py` (Task 2).
- Produces: `Profile` (dataclass: `meta: dict`, `sections: list[dict]`, `.output` property), `load_profile(profiles_dir: Path, name: str) -> Profile` — consumed by `core/build.py` (Task 7) and the CLI `build` command (Task 8).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_profiles.py
from parcours.core.profiles import load_profile


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_load_profile_without_extends(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "short.yaml", """
meta:
  name: short
  language: en
  format: pdf
  theme: sb2nov
  identity_variant: academic
sections:
  - id: publications
    source: publications
""")

    profile = load_profile(profiles_dir, "short")

    assert profile.meta["name"] == "short"
    assert profile.meta["language"] == "en"
    assert len(profile.sections) == 1
    assert profile.sections[0]["id"] == "publications"


def test_load_profile_merges_extends_base(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "_academic.yaml", """
meta:
  name: academic
  format: pdf
  theme: sb2nov
  identity_variant: academic
sections:
  - id: publications
    source: publications
  - id: grants
    source: grants
""")
    _write(profiles_dir / "academic-en.yaml", """
extends: _academic
meta:
  language: en
""")

    profile = load_profile(profiles_dir, "academic-en")

    assert profile.meta["name"] == "academic"
    assert profile.meta["format"] == "pdf"
    assert profile.meta["theme"] == "sb2nov"
    assert profile.meta["language"] == "en"
    assert len(profile.sections) == 2


def test_load_profile_child_can_override_a_base_meta_field(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "_academic.yaml", """
meta:
  name: academic
  theme: sb2nov
sections: []
""")
    _write(profiles_dir / "academic-short.yaml", """
extends: _academic
meta:
  language: en
  theme: engineeringresumes
""")

    profile = load_profile(profiles_dir, "academic-short")

    assert profile.meta["theme"] == "engineeringresumes"
    assert profile.meta["name"] == "academic"


def test_load_profile_child_can_fully_replace_sections(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "_academic.yaml", """
meta:
  name: academic
sections:
  - id: publications
    source: publications
  - id: grants
    source: grants
""")
    _write(profiles_dir / "academic-short.yaml", """
extends: _academic
meta:
  language: en
sections:
  - id: publications
    source: publications
""")

    profile = load_profile(profiles_dir, "academic-short")

    assert len(profile.sections) == 1


def test_profile_output_defaults_to_name_and_language(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "academic-en.yaml", """
meta:
  name: academic
  language: en
sections: []
""")

    profile = load_profile(profiles_dir, "academic-en")

    assert profile.output == "cv-academic-en"


def test_profile_output_uses_a_custom_template_from_meta(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "academic-en.yaml", """
meta:
  name: academic
  language: en
  output: "my-custom-cv"
sections: []
""")

    profile = load_profile(profiles_dir, "academic-en")

    assert profile.output == "my-custom-cv"


def test_profile_output_template_inherited_from_base_fills_child_language(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write(profiles_dir / "_academic.yaml", """
meta:
  name: academic
  output: "cv-{name}-{language}"
sections: []
""")
    _write(profiles_dir / "academic-fr.yaml", """
extends: _academic
meta:
  language: fr
""")

    profile = load_profile(profiles_dir, "academic-fr")

    assert profile.output == "cv-academic-fr"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_profiles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.profiles'`

- [ ] **Step 3: Implement `profiles.py`**

```python
# parcours/core/profiles.py
"""Loads `profiles/*.yaml`: one CV variant/language combination, with an
optional `extends` merge against a shared base file (see SPECS.md,
"Profiles"). A single, shallow merge level — no chained `extends`, no
per-section deep merge."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .templating import resolve_template

_DEFAULT_OUTPUT_TEMPLATE = "cv-{name}-{language}"


@dataclass
class Profile:
    meta: dict[str, Any]
    sections: list[dict] = field(default_factory=list)

    @property
    def output(self) -> str:
        template = self.meta.get("output", _DEFAULT_OUTPUT_TEMPLATE)
        return resolve_template(template, self.meta, self.meta["language"])


def _load_raw(profiles_dir: Path, name: str) -> dict:
    with open(profiles_dir / f"{name}.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_profile(profiles_dir: Path, name: str) -> Profile:
    raw = _load_raw(profiles_dir, name)

    base_name = raw.get("extends")
    if base_name:
        base = _load_raw(profiles_dir, base_name)
        merged = {**base, **raw}
        merged["meta"] = {**base.get("meta", {}), **raw.get("meta", {})}
    else:
        merged = raw

    return Profile(
        meta=merged.get("meta", {}),
        sections=merged.get("sections", []),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_profiles.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/profiles.py tests/unit/test_profiles.py
git commit -m "Added profile loading with extends merge and output templating"
```

---

### Task 5: `core/views.py` — views.yaml loading

**Files:**
- Create: `parcours/core/views.py`
- Test: `tests/unit/test_views.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ViewSpec` (dataclass: `name: str`, `source: str`, `entry_type: str`, `fields: dict`, `group_by: str | None`), `load_views(path: Path) -> dict[str, ViewSpec]` — consumed by `core/build.py` (Task 7) and the starter `views.yaml` content test (Task 6).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_views.py
from parcours.core.views import load_views


def test_load_views_parses_source_entry_type_and_fields(tmp_path):
    path = tmp_path / "views.yaml"
    path.write_text("""
grants:
  source: grants
  entry_type: NormalEntry
  fields:
    name: "{title}"
    start_date: start_date
    end_date: end_date
    highlights:
      - "{funder} — {role}"
""", encoding="utf-8")

    views = load_views(path)

    assert set(views.keys()) == {"grants"}
    view = views["grants"]
    assert view.name == "grants"
    assert view.source == "grants"
    assert view.entry_type == "NormalEntry"
    assert view.fields["name"] == "{title}"
    assert view.fields["highlights"] == ["{funder} — {role}"]
    assert view.group_by is None


def test_load_views_parses_group_by(tmp_path):
    path = tmp_path / "views.yaml"
    path.write_text("""
skills-terms:
  source: skills
  entry_type: OneLineEntry
  group_by: category
  fields:
    label: "{category}"
""", encoding="utf-8")

    views = load_views(path)

    assert views["skills-terms"].group_by == "category"


def test_load_views_supports_multiple_views(tmp_path):
    path = tmp_path / "views.yaml"
    path.write_text("""
grants:
  source: grants
  entry_type: NormalEntry
  fields: {name: "{title}"}
education:
  source: education
  entry_type: EducationEntry
  fields: {institution: organization}
""", encoding="utf-8")

    views = load_views(path)

    assert set(views.keys()) == {"grants", "education"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_views.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.views'`

- [ ] **Step 3: Implement `views.py`**

```python
# parcours/core/views.py
"""Loads `views.yaml`: the category → RenderCV entry-type field mapping
(see SPECS.md, "views.yaml (draft)")."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ViewSpec:
    name: str
    source: str
    entry_type: str
    fields: dict[str, Any] = field(default_factory=dict)
    group_by: str | None = None


def load_views(path: Path) -> dict[str, ViewSpec]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    views = {}
    for name, view_raw in raw.items():
        views[name] = ViewSpec(
            name=name,
            source=view_raw["source"],
            entry_type=view_raw["entry_type"],
            fields=view_raw.get("fields", {}),
            group_by=view_raw.get("group_by"),
        )
    return views
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_views.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add parcours/core/views.py tests/unit/test_views.py
git commit -m "Added views.yaml loading"
```

---

### Task 6: Starter `views.yaml` — all 18 non-skills categories

**Files:**
- Create: `starter_config/views.yaml` (repo root — a reference/example asset, not Python package code; there is no `parco init` command yet to auto-copy it into a data repo, so for now it's a correct, tested reference a user copies into their own data repo by hand, same as every other config file this project has produced so far)
- Test: `tests/unit/test_starter_views.py`

**Interfaces:**
- Consumes: `load_views` from `core/views.py` (Task 5) — this task's only job is to prove the content loads and matches SPECS.md's entry-type table, not to add any new code.
- Produces: nothing new for other tasks to import — `starter_config/views.yaml` is data, not code. Task 7/8's own tests use small inline fixture views (not this file), exactly like every prior plan's tests use small fixture schemas rather than the full drafted category set.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_starter_views.py
from pathlib import Path

from parcours.core.views import load_views

_STARTER_VIEWS_PATH = Path(__file__).parent.parent.parent / "starter_config" / "views.yaml"

_EXPECTED_ENTRY_TYPES = {
    "publications": "PublicationEntry",
    "review": "PublicationEntry",
    "catalog": "PublicationEntry",
    "grants": "NormalEntry",
    "artworks": "NormalEntry",
    "students": "NormalEntry",
    "teaching": "ExperienceEntry",
    "service": "ExperienceEntry",
    "outreach": "ExperienceEntry",
    "presentations": "NormalEntry",
    "press": "NormalEntry",
    "education": "EducationEntry",
    "positions": "ExperienceEntry",
    "recognitions": "NormalEntry",
    "exhibitions": "NormalEntry",
    "curatorship": "NormalEntry",
    "residencies": "NormalEntry",
    "software": "NormalEntry",
}


def test_starter_views_covers_every_non_skills_category():
    views = load_views(_STARTER_VIEWS_PATH)
    assert set(views.keys()) == set(_EXPECTED_ENTRY_TYPES.keys())


def test_starter_views_use_the_documented_entry_type_per_category():
    views = load_views(_STARTER_VIEWS_PATH)
    for category_name, expected_entry_type in _EXPECTED_ENTRY_TYPES.items():
        assert views[category_name].entry_type == expected_entry_type, category_name


def test_starter_views_source_matches_the_view_name_for_every_category():
    views = load_views(_STARTER_VIEWS_PATH)
    for category_name, view in views.items():
        assert view.source == category_name


def test_zotero_backed_views_reference_only_zotero_fields():
    views = load_views(_STARTER_VIEWS_PATH)
    for category_name in ("publications", "review", "catalog"):
        view = views[category_name]
        for field_value in view.fields.values():
            assert "zotero_" in field_value, (category_name, field_value)


def test_authors_field_is_a_bare_placeholder_not_a_compound_template():
    # Required so the templating engine's list-passthrough rule applies
    # (see Global Constraints) — "authors" must map PublicationEntry's
    # list[str] field directly, not stringify it.
    views = load_views(_STARTER_VIEWS_PATH)
    for category_name in ("publications", "review", "catalog"):
        assert views[category_name].fields["authors"] == "{zotero_authors}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_starter_views.py -v`
Expected: FAIL with `FileNotFoundError` (the file doesn't exist yet)

- [ ] **Step 3: Write the starter `views.yaml`**

```yaml
# starter_config/views.yaml
#
# Reference views.yaml for the 18 non-skills category schemas drafted in
# SPECS.md's "Category schemas (drafts)" and mapped in "views.yaml
# (draft)". Copy into your data repo as `views.yaml`. `skills` is not
# included — its GROUP BY-aggregating view is a deferred follow-up (see
# SPECS.md's "First-cut scope").

publications:
  source: publications
  entry_type: PublicationEntry
  fields:
    title: "{zotero_title}"
    authors: "{zotero_authors}"
    journal: "{zotero_journal}"
    doi: "{zotero_doi}"
    url: "{zotero_url}"
    date: "{zotero_date}"

review:
  source: review
  entry_type: PublicationEntry
  fields:
    title: "{zotero_title}"
    authors: "{zotero_authors}"
    journal: "{zotero_journal}"
    doi: "{zotero_doi}"
    url: "{zotero_url}"
    date: "{zotero_date}"

catalog:
  source: catalog
  entry_type: PublicationEntry
  fields:
    title: "{zotero_title}"
    authors: "{zotero_authors}"
    journal: "{zotero_journal}"
    doi: "{zotero_doi}"
    url: "{zotero_url}"
    date: "{zotero_date}"

grants:
  source: grants
  entry_type: NormalEntry
  fields:
    name: "{title}"
    start_date: start_date
    end_date: end_date
    highlights:
      - "{funder} — {role}"
      - "{amount} {currency}"
      - "{co_investigators}"

artworks:
  source: artworks
  entry_type: NormalEntry
  fields:
    name: "{title}"
    date: date
    highlights:
      - "{role}"
      - "{contributors}"

students:
  source: students
  entry_type: NormalEntry
  fields:
    name: "{student_name}"
    start_date: supervision_start_date
    end_date: supervision_end_date
    highlights:
      - "{degree_type} — {degree_status}"
      - "{institution}"
      - "{thesis_title}"

teaching:
  source: teaching
  entry_type: ExperienceEntry
  fields:
    company: organization
    position: "{course_label} — {title}"
    date: date
    highlights:
      - "{department}"

service:
  source: service
  entry_type: ExperienceEntry
  fields:
    company: organization
    position: "{role}"
    start_date: start_date
    end_date: end_date
    highlights:
      - "{type}"
      - "{detail}"

outreach:
  source: outreach
  entry_type: ExperienceEntry
  fields:
    company: organization
    position: "{role}"
    start_date: start_date
    end_date: end_date
    summary: "{description}"

presentations:
  source: presentations
  entry_type: NormalEntry
  fields:
    name: "{title}"
    date: date
    summary: "{event}"
    highlights:
      - "{location}"
      - "{co_presenters}"

press:
  source: press
  entry_type: NormalEntry
  fields:
    name: "{outlet}"
    date: date
    highlights:
      - "{author}"
      - "{program}"

education:
  source: education
  entry_type: EducationEntry
  fields:
    institution: organization
    area: "{specialization}"
    degree: "{degree_name}"
    start_date: start_date
    end_date: end_date
    summary: "{thesis_title}"
    highlights:
      - "{advisor}"
      - "{note}"

positions:
  source: positions
  entry_type: ExperienceEntry
  fields:
    company: organization
    position: "{title}"
    start_date: start_date
    end_date: end_date
    highlights:
      - "{faculty}"
      - "{department}"

recognitions:
  source: recognitions
  entry_type: NormalEntry
  fields:
    name: "{name}"
    date: date
    highlights:
      - "{organization}"
      - "{amount} {currency}"
      - "{description}"

exhibitions:
  source: exhibitions
  entry_type: NormalEntry
  fields:
    name: "{title}"
    start_date: start_date
    end_date: end_date
    location: "{location}"
    highlights:
      - "{event}"
      - "{venue}"
      - "{curator}"

curatorship:
  source: curatorship
  entry_type: NormalEntry
  fields:
    name: "{title}"
    start_date: start_date
    end_date: end_date
    location: "{location}"
    highlights:
      - "{event}"
      - "{venue}"
      - "{curator}"

residencies:
  source: residencies
  entry_type: NormalEntry
  fields:
    name: "{organization}"
    location: "{location}"
    start_date: start_date
    end_date: end_date

software:
  source: software
  entry_type: NormalEntry
  fields:
    name: title
    summary: "{description}"
    start_date: start_date
    end_date: end_date
    highlights:
      - "{role}"
      - "{url}"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/unit/test_starter_views.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all prior tests plus this task's 5 new ones)

- [ ] **Step 6: Commit**

```bash
git add starter_config/views.yaml tests/unit/test_starter_views.py
git commit -m "Added the starter views.yaml for all 18 non-skills categories"
```

---

### Task 7: `core/build.py` — pure RenderCV data assembly

**Files:**
- Create: `parcours/core/build.py`
- Test: `tests/unit/test_build.py`

**Interfaces:**
- Consumes: `query_category_rows` (Task 1), `resolve_template` (Task 2), `load_identity`/`resolve_identity` (Task 3), `Profile`/`load_profile` (Task 4), `ViewSpec`/`load_views` (Task 5), `parcours.core.schema.load_all_schemas`, `parcours.core.translations.load_translations`, `parcours.core.handlers.load_handler`, `parcours.core.handlers.base.HandlerContext`, `parcours.core.handlers.publications.PublicationsHandler`.
- Produces: `build_rendercv_data(data_dir: Path, profile: Profile) -> dict` — the full RenderCV-YAML-ready dict, no file I/O, no subprocess. Consumed by `run_build` (Task 8, same module) and the CLI `build` command (Task 8).

This task is deliberately scoped to the **pure** assembly step only — no lint-gating, no file writing, no `rendercv` invocation (that's Task 8, since it has real side effects and needs its own test strategy).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_build.py
import json

from parcours.core.build import build_rendercv_data
from parcours.core.profiles import Profile


def _setup_data_repo(tmp_path):
    (tmp_path / "categories").mkdir()
    (tmp_path / "categories" / "grants.yaml").write_text("""
name: grants
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en}
  - {name: title_fr}
  - {name: funder, required: true}
  - {name: role, required: true}
  - {name: start_date, type: date, precision: month, required: true}
  - {name: end_date, type: date, precision: month}
  - {name: amount}
  - {name: currency}
  - {name: co_investigators}
""")
    (tmp_path / "categories" / "publications.yaml").write_text("""
name: publications
handler: publications
options:
  json: zotero/library.json
fields:
  - {name: id, generated: true}
  - {name: citekey, required: true}
""")
    (tmp_path / "translations.csv").write_text(
        "id,category,en,fr\n"
        "grants,section,Grants,Subventions\n"
        "publications,section,Publications,Publications\n"
    )
    (tmp_path / "identity.yaml").write_text("""
name:
  first: Jane
  last: Doe
variants:
  academic:
    email: jane@example.edu
    title_en: "Associate Professor"
    title_fr: "Professeure agrégée"
""")
    return tmp_path


def _grants_view():
    from parcours.core.views import ViewSpec
    return ViewSpec(
        name="grants", source="grants", entry_type="NormalEntry",
        fields={
            "name": "{title}",
            "start_date": "start_date",
            "end_date": "end_date",
            "highlights": ["{funder} — {role}"],
        },
    )


def _publications_view():
    from parcours.core.views import ViewSpec
    return ViewSpec(
        name="publications", source="publications", entry_type="PublicationEntry",
        fields={
            "title": "{zotero_title}",
            "authors": "{zotero_authors}",
            "date": "{zotero_date}",
        },
    )


def test_build_resolves_identity_into_cv_block(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "views.yaml").write_text("")
    profile = Profile(meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"}, sections=[])
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {})

    data = build_rendercv_data(repo, profile)

    assert data["cv"]["name"] == "Jane Doe"
    assert data["cv"]["headline"] == "Associate Professor"
    assert data["cv"]["email"] == "jane@example.edu"
    assert data["design"]["theme"] == "sb2nov"


def test_build_resolves_a_section_title_from_translations(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date,amount,currency,co_investigators\n"
        "g1,Big Grant,Grande subvention,FRQSC,PI,2020-01,2022-01,50000,CAD,\n"
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "grants", "source": "grants"}],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {"grants": _grants_view()})

    data = build_rendercv_data(repo, profile)

    assert "Grants" in data["cv"]["sections"]
    assert "Subventions" not in data["cv"]["sections"]


def test_build_maps_grant_rows_into_normal_entries(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date,amount,currency,co_investigators\n"
        "g1,Big Grant,Grande subvention,FRQSC,PI,2020-01,2022-01,50000,CAD,\n"
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "grants", "source": "grants"}],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {"grants": _grants_view()})

    data = build_rendercv_data(repo, profile)

    entries = data["cv"]["sections"]["Grants"]
    assert len(entries) == 1
    assert entries[0]["name"] == "Big Grant"
    assert entries[0]["start_date"] == "2020-01"
    assert entries[0]["end_date"] == "2022-01"
    assert entries[0]["highlights"] == ["FRQSC — PI"]


def test_build_respects_section_filter_order_by_and_limit(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date,amount,currency,co_investigators\n"
        "g1,First,Premier,FRQSC,PI,2020-01,2021-01,,,\n"
        "g2,Second,Deuxieme,SSHRC,co-PI,2019-01,2020-06,,,\n"
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "grants", "source": "grants", "order_by": "start_date desc", "limit": 1}],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {"grants": _grants_view()})

    data = build_rendercv_data(repo, profile)

    entries = data["cv"]["sections"]["Grants"]
    assert len(entries) == 1
    assert entries[0]["name"] == "First"


def test_build_merges_zotero_fields_for_publications_backed_handler(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "zotero").mkdir()
    (repo / "zotero" / "library.json").write_text(json.dumps([
        {
            "id": "doe2024widgets",
            "title": "On Widgets",
            "author": [{"given": "Jane", "family": "Doe"}],
            "issued": {"date-parts": [[2024, 3]]},
        }
    ]))
    (repo / "publications.csv").write_text("id,citekey\np1,doe2024widgets\n")
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "publications", "source": "publications"}],
    )
    monkeypatch.setattr(
        "parcours.core.build.load_views", lambda path: {"publications": _publications_view()}
    )

    data = build_rendercv_data(repo, profile)

    entries = data["cv"]["sections"]["Publications"]
    assert len(entries) == 1
    assert entries[0]["title"] == "On Widgets"
    assert entries[0]["authors"] == ["Jane Doe"]
    assert entries[0]["date"] == "2024-03"


def test_build_leaves_zotero_fields_absent_for_an_unresolved_citekey(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "zotero").mkdir()
    (repo / "zotero" / "library.json").write_text(json.dumps([]))
    (repo / "publications.csv").write_text("id,citekey\np1,nonexistent-key\n")
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "publications", "source": "publications"}],
    )
    monkeypatch.setattr(
        "parcours.core.build.load_views", lambda path: {"publications": _publications_view()}
    )

    data = build_rendercv_data(repo, profile)

    entries = data["cv"]["sections"]["Publications"]
    assert len(entries) == 1
    assert "title" not in entries[0]
    assert "authors" not in entries[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_build.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.build'`

- [ ] **Step 3: Implement the pure assembly step in `build.py`**

```python
# parcours/core/build.py
"""Assembles a RenderCV YAML input from a profile + views.yaml + category
data (see SPECS.md, "Build / query" and "views.yaml (draft)"). Core
layer: no prompting, no subprocess here — see the CLI `build` command
for lint-gating and the `rendercv` invocation."""

from pathlib import Path

from .data import query_category_rows
from .handlers import load_handler
from .handlers.base import HandlerContext
from .handlers.publications import PublicationsHandler
from .identity import load_identity, resolve_identity
from .profiles import Profile
from .schema import load_all_schemas
from .templating import resolve_template
from .translations import load_translations
from .views import ViewSpec, load_views


def _csl_date_to_iso(record: dict) -> str | None:
    try:
        parts = record["issued"]["date-parts"][0]
    except (KeyError, IndexError, TypeError):
        return None
    if not parts:
        return None
    year = parts[0]
    if len(parts) >= 3:
        return f"{year:04d}-{parts[1]:02d}-{parts[2]:02d}"
    if len(parts) == 2:
        return f"{year:04d}-{parts[1]:02d}"
    return f"{year:04d}"


def _csl_authors_to_list(record: dict) -> list[str]:
    names = []
    for author in record.get("author", []):
        given = author.get("given", "")
        family = author.get("family", "")
        full_name = " ".join(part for part in [given, family] if part)
        if full_name:
            names.append(full_name)
    return names


def _merge_zotero_fields(handler: PublicationsHandler, row: dict) -> dict:
    citekey = row.get("citekey") or ""
    record = handler.resolve(citekey) if citekey else None
    if record is None:
        return row

    merged = dict(row)
    merged["zotero_title"] = record.get("title", "")
    merged["zotero_authors"] = _csl_authors_to_list(record)
    merged["zotero_journal"] = record.get("container-title", "")
    merged["zotero_doi"] = record.get("DOI", "")
    merged["zotero_url"] = record.get("URL", "")
    merged["zotero_date"] = _csl_date_to_iso(record) or ""
    return merged


def _map_row_to_entry(view: ViewSpec, row: dict, language: str) -> dict:
    entry = {}
    for field_name, template in view.fields.items():
        value = resolve_template(template, row, language)
        if value:
            entry[field_name] = value
    return entry


def _build_section_entries(
    data_dir: Path, schema, view: ViewSpec, section: dict, language: str
) -> list[dict]:
    rows = query_category_rows(
        data_dir,
        view.source,
        filters=section.get("filter"),
        order_by=section.get("order_by"),
        limit=section.get("limit"),
    )

    handler = load_handler(schema, HandlerContext(data_dir=data_dir))
    if isinstance(handler, PublicationsHandler):
        rows = [_merge_zotero_fields(handler, row) for row in rows]

    return [_map_row_to_entry(view, row, language) for row in rows]


def build_rendercv_data(data_dir: Path, profile: Profile) -> dict:
    """Assembles the full RenderCV-YAML-ready dict for one profile. Pure
    (no subprocess, no writing) — the caller writes it to a file and
    invokes `rendercv render` separately."""
    schemas = load_all_schemas(data_dir / "categories")
    views = load_views(data_dir / "views.yaml")
    translations = load_translations(data_dir / "translations.csv")
    identity = load_identity(data_dir / "identity.yaml")

    language = profile.meta["language"]
    cv = resolve_identity(identity, profile.meta["identity_variant"], language)

    sections = {}
    for section in profile.sections:
        source = section["source"]
        view = views[source]
        schema = schemas[source]
        title = translations.resolve_or_literal("section", section["id"], language)
        sections[title] = _build_section_entries(data_dir, schema, view, section, language)

    cv["sections"] = sections

    return {
        "cv": cv,
        "design": {"theme": profile.meta["theme"]},
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_build.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all prior tests plus this task's 6 new ones)

- [ ] **Step 6: Commit**

```bash
git add parcours/core/build.py tests/unit/test_build.py
git commit -m "Added pure RenderCV data assembly (build_rendercv_data)"
```

---

### Task 8: Lint-gating, `rendercv` invocation, and the `parco build` command

**Files:**
- Modify: `parcours/core/build.py` (add `run_build` and `BuildError`)
- Modify: `parcours/cli/main.py` (add the `build` command)
- Modify: `pyproject.toml` (add the `rendercv[full]>=2.8` dependency)
- Test: `tests/unit/test_build.py` (extend with `run_build`'s lint-gate behavior, mocking the `rendercv` subprocess call)
- Test: `tests/integration/test_cli_build.py`

**Interfaces:**
- Consumes: `build_rendercv_data` (Task 7, same module), `parcours.core.lint.run_lint`, `parcours.core.profiles.load_profile`, `parcours.core.repo.find_data_repo`/`DataRepoNotFound`.
- Produces: `run_build(data_dir: Path, profile: Profile, fmt: str, output_dir: Path, force: bool = False) -> Path`, `BuildError` (in `core/build.py`); the `build` Typer command (in `cli/main.py`).

- [ ] **Step 1: Add the `rendercv` dependency**

The `[full]` extra is required — a plain `rendercv` install is missing the `rendercv_fonts` package its PDF rendering path needs (verified against the real installed package: `pip install rendercv` alone leaves `rendercv render` unable to import `rendercv.renderer.pdf_png`).

In `pyproject.toml`, replace:

```toml
dependencies = [
    "typer>=0.12",
    "duckdb>=1.0",
    "pyyaml>=6.0",
    "platformdirs>=4.0",
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
]
```

- [ ] **Step 2: Write the failing tests for `run_build`'s lint-gate**

Append to `tests/unit/test_build.py`:

```python
import pytest

from parcours.core.build import BuildError, run_build


def test_run_build_refuses_when_a_referenced_category_has_a_lint_error(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "views.yaml").write_text("")
    # A grant missing its required `funder` — a real lint error.
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date,amount,currency,co_investigators\n"
        "g1,Big Grant,Grande subvention,,PI,2020-01,2022-01,,,\n"
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov"},
        sections=[{"id": "grants", "source": "grants"}],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {"grants": _grants_view()})

    with pytest.raises(BuildError, match="grants"):
        run_build(repo, profile, "pdf", tmp_path / "out", force=False)


def test_run_build_force_skips_the_lint_gate(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "views.yaml").write_text("")
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date,amount,currency,co_investigators\n"
        "g1,Big Grant,Grande subvention,,PI,2020-01,2022-01,,,\n"
    )
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov", "output": "cv-test"},
        sections=[{"id": "grants", "source": "grants"}],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {"grants": _grants_view()})
    monkeypatch.setattr("parcours.core.build.subprocess.run", lambda *a, **k: None)

    output_dir = tmp_path / "out"
    result = run_build(repo, profile, "pdf", output_dir, force=True)

    assert result == output_dir / "cv-test.pdf"


def test_run_build_rejects_unsupported_format(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "views.yaml").write_text("")
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov", "output": "cv-test"},
        sections=[],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {})

    with pytest.raises(BuildError, match="docx"):
        run_build(repo, profile, "docx", tmp_path / "out", force=True)


def test_run_build_wraps_a_rendercv_failure(tmp_path, monkeypatch):
    import subprocess

    repo = _setup_data_repo(tmp_path)
    (repo / "vocab.yaml").write_text("{}\n")
    (repo / "views.yaml").write_text("")
    profile = Profile(
        meta={"language": "en", "identity_variant": "academic", "theme": "sb2nov", "output": "cv-test"},
        sections=[],
    )
    monkeypatch.setattr("parcours.core.build.load_views", lambda path: {})

    def _fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "rendercv", stderr="bad theme")

    monkeypatch.setattr("parcours.core.build.subprocess.run", _fail)

    with pytest.raises(BuildError, match="bad theme"):
        run_build(repo, profile, "pdf", tmp_path / "out", force=True)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/unit/test_build.py -v`
Expected: FAIL with `ImportError: cannot import name 'run_build'` (and `BuildError`)

- [ ] **Step 4: Implement `run_build` in `build.py`**

Append to `parcours/core/build.py` (add these imports to the existing import block at the top: `import subprocess`, `import tempfile`, and `import yaml`; add `from .lint import run_lint` to the existing relative imports):

```python
class BuildError(Exception):
    """Raised when `parco build` can't run — a lint error on a
    referenced category (unless `force`), or a failed `rendercv render`
    invocation."""


_FORMAT_EXTENSIONS = {"pdf": "pdf", "typst": "typ", "html": "html"}
_FORMAT_PATH_FLAGS = {"pdf": "--pdf-path", "typst": "--typst-path", "html": "--html-path"}


def run_build(
    data_dir: Path,
    profile: Profile,
    fmt: str,
    output_dir: Path,
    force: bool = False,
) -> Path:
    if fmt not in _FORMAT_EXTENSIONS:
        raise BuildError(f"Format '{fmt}' is not yet supported (docx needs the Pandoc integration)")

    if not force:
        category_names = {section["source"] for section in profile.sections}
        for category_name in category_names:
            issues = run_lint(data_dir, category_filter=category_name)
            error_issues = [issue for issue in issues if issue.severity == "error"]
            if error_issues:
                raise BuildError(
                    f"'{category_name}' has {len(error_issues)} lint error(s) — "
                    "fix them or pass --force to build anyway"
                )

    rendercv_data = build_rendercv_data(data_dir, profile)

    output_dir.mkdir(parents=True, exist_ok=True)
    extension = _FORMAT_EXTENSIONS[fmt]
    # An absolute path, since RenderCV's --*-path flags resolve relative
    # to the *input* YAML file (a scratch tempfile, below) otherwise.
    output_path = (output_dir / f"{profile.output}.{extension}").resolve()

    # Every format RenderCV doesn't explicitly disable still gets
    # generated into a default `rendercv_output/` folder relative to
    # cwd unless redirected — `--output-folder` catches all of those
    # byproducts in a scratch dir instead of guessing which
    # `--dont-generate-*` flags are safe (PDF likely renders *through*
    # Typst internally, so blindly disabling Typst risks breaking PDF).
    with tempfile.TemporaryDirectory() as scratch_dir_name:
        scratch_dir = Path(scratch_dir_name)
        input_path = scratch_dir / "input.yaml"
        with open(input_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(rendercv_data, fh, allow_unicode=True, sort_keys=False)

        try:
            subprocess.run(
                [
                    "rendercv", "render", str(input_path),
                    _FORMAT_PATH_FLAGS[fmt], str(output_path),
                    "--output-folder", str(scratch_dir / "rendercv_output"),
                ],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise BuildError(f"rendercv render failed: {exc.stderr}") from exc

    return output_path
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_build.py -v`
Expected: PASS (10 tests: 6 from Task 7 + 4 new)

- [ ] **Step 6: Write the failing integration tests for `parco build`**

```python
# tests/integration/test_cli_build.py
from typer.testing import CliRunner

from parcours.cli.main import app

runner = CliRunner()


def _setup_data_repo(tmp_path):
    (tmp_path / "parco.yaml").write_text("name: test-repo\n")
    (tmp_path / "categories").mkdir()
    (tmp_path / "categories" / "grants.yaml").write_text("""
name: grants
handler: generic
fields:
  - {name: id, generated: true}
  - {name: title_en, required: true}
  - {name: title_fr}
  - {name: funder, required: true}
  - {name: role, required: true}
  - {name: start_date, type: date, precision: month, required: true}
  - {name: end_date, type: date, precision: month}
""")
    (tmp_path / "vocab.yaml").write_text("{}\n")
    (tmp_path / "translations.csv").write_text(
        "id,category,en,fr\ngrants,section,Grants,Subventions\n"
    )
    (tmp_path / "identity.yaml").write_text("""
name:
  first: Jane
  last: Doe
variants:
  academic:
    email: jane@example.edu
""")
    (tmp_path / "views.yaml").write_text("""
grants:
  source: grants
  entry_type: NormalEntry
  fields:
    name: "{title}"
    start_date: start_date
    end_date: end_date
""")
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles" / "academic-en.yaml").write_text("""
meta:
  name: academic
  language: en
  format: pdf
  theme: sb2nov
  identity_variant: academic
sections:
  - id: grants
    source: grants
""")
    return tmp_path


def test_build_writes_the_rendered_file(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date\n"
        "g1,Big Grant,Grande subvention,FRQSC,PI,2020-01,2022-01\n"
    )
    monkeypatch.chdir(repo)

    def _fake_render(cmd, check, capture_output, text):
        # cmd = ["rendercv", "render", <input>, path_flag, <output>, ...disable_flags]
        output_path = cmd[4]
        __import__("pathlib").Path(output_path).write_bytes(b"fake pdf bytes")

    monkeypatch.setattr("parcours.core.build.subprocess.run", _fake_render)

    result = runner.invoke(app, ["build", "--profile", "academic-en"])

    assert result.exit_code == 0, result.stdout
    assert (repo / "build" / "cv-academic-en.pdf").is_file()


def test_build_refuses_on_lint_error_without_force(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date\n"
        "g1,,,,,2020-01,2022-01\n"
    )
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["build", "--profile", "academic-en"])

    assert result.exit_code == 1, result.stdout
    assert "lint error" in result.stdout


def test_build_force_bypasses_lint_gate(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date\n"
        "g1,,,,,2020-01,2022-01\n"
    )
    monkeypatch.chdir(repo)

    def _fake_render(cmd, check, capture_output, text):
        output_path = cmd[4]
        __import__("pathlib").Path(output_path).write_bytes(b"fake pdf bytes")

    monkeypatch.setattr("parcours.core.build.subprocess.run", _fake_render)

    result = runner.invoke(app, ["build", "--profile", "academic-en", "--force"])

    assert result.exit_code == 0, result.stdout


def test_build_rejects_docx(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date\n"
        "g1,Big Grant,Grande subvention,FRQSC,PI,2020-01,2022-01\n"
    )
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["build", "--profile", "academic-en", "--format", "docx"])

    assert result.exit_code == 1
    assert "not yet supported" in result.stdout


def test_build_unknown_profile_exits_cleanly(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["build", "--profile", "nonexistent"])

    assert result.exit_code == 2
    assert "profile" in result.stdout.lower()


def test_build_respects_custom_output_dir(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    (repo / "grants.csv").write_text(
        "id,title_en,title_fr,funder,role,start_date,end_date\n"
        "g1,Big Grant,Grande subvention,FRQSC,PI,2020-01,2022-01\n"
    )
    monkeypatch.chdir(repo)

    def _fake_render(cmd, check, capture_output, text):
        output_path = cmd[4]
        __import__("pathlib").Path(output_path).write_bytes(b"fake pdf bytes")

    monkeypatch.setattr("parcours.core.build.subprocess.run", _fake_render)

    result = runner.invoke(
        app, ["build", "--profile", "academic-en", "--output-dir", str(tmp_path / "custom")]
    )

    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "custom" / "cv-academic-en.pdf").is_file()
```

- [ ] **Step 7: Run the integration tests to verify they fail**

Run: `pytest tests/integration/test_cli_build.py -v`
Expected: FAIL — no `build` command registered on `app` yet

- [ ] **Step 8: Add the `build` command to `main.py`**

Add these imports to `parcours/cli/main.py` (alongside the existing ones):

```python
from ..core.build import BuildError, run_build
from ..core.profiles import load_profile
```

Append this command (before the `if __name__ == "__main__":` guard):

```python
@app.command()
def build(
    profile: str = typer.Option(..., "--profile", help="Profile name (profiles/<name>.yaml, no extension)"),
    fmt: str = typer.Option(None, "--format", help="Output format: pdf, typst, or html (defaults to the profile's own meta.format)"),
    force: bool = typer.Option(False, "--force", help="Build even if parco lint reports errors"),
    output_dir: Path = typer.Option(None, "--output-dir", help="Where to write the rendered file (defaults to <data repo>/build)"),
):
    """Render a CV from a profile via RenderCV."""
    data_dir = _find_repo_or_exit()

    try:
        loaded_profile = load_profile(data_dir / "profiles", profile)
    except FileNotFoundError:
        typer.echo(f"Unknown profile: '{profile}'")
        raise typer.Exit(code=2)

    resolved_format = fmt or loaded_profile.meta.get("format", "pdf")
    resolved_output_dir = output_dir or (data_dir / "build")

    try:
        output_path = run_build(data_dir, loaded_profile, resolved_format, resolved_output_dir, force=force)
    except BuildError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    typer.echo(f"Built {output_path}")
```

- [ ] **Step 9: Run the integration tests to verify they pass**

Run: `pytest tests/integration/test_cli_build.py -v`
Expected: PASS (6 tests)

- [ ] **Step 10: Run the full suite to verify everything passes**

Run: `pytest tests/ -v`
Expected: PASS (all tests across every task in every plan)

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml parcours/core/build.py parcours/cli/main.py \
        tests/unit/test_build.py tests/integration/test_cli_build.py
git commit -m "Added lint-gated build orchestration, rendercv invocation, and the parco build command"
```

---

## What this plan deliberately does not cover

Follow-up plans, once this exists:
- `skills`' `GROUP BY`-aggregating view (the one category this plan's `views.yaml` omits — every other view is a flat 1:1 row-to-entry mapping, `skills` genuinely isn't).
- `docx` output (a working RenderCV-Markdown-to-Pandoc spike already exists — see SPECS.md's "Output formats" — this plan only wires PDF/Typst/HTML).
- Citeproc-styled `citation_style` (a profile section's `citation_style` key is accepted in the YAML but never read by this plan — RenderCV's own `PublicationEntry` layout doesn't need it; it only matters for the separate, not-yet-built `parco cite` command).
- Currency conversion (`grants.amount`/`recognitions.amount` render as plain strings, unconverted; no `rates.csv` fetching exists in any form yet).
- A `parco init` command to scaffold a new data repo (this plan's `starter_config/views.yaml` is a reference file a user copies in by hand, same as every other config file so far).
- `parco query`/`parco stats`/`parco cite` (separate CLI commands `SPECS.md` lists alongside `build`, out of scope for this plan).
- `sync`/`refresh`/`import` (unrelated to build; still undesigned per SPECS.md's Design status).
