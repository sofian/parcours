# parco commit + parco import ccv Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `parco commit` (a manual stage-and-commit command) and `parco import ccv` (a one-time bulk importer from a Canadian Common CV XML export), plus the small conditional-auto-commit change to `add`/`edit`/`delete` that makes the import's "review before committing" workflow possible.

**Architecture:** Two new core modules — `core/commit.py` (stage+commit) and `core/ccv_xml.py` (generic CCV tree-walking primitives) — plus a growing `core/import_ccv.py` (per-category field mappers, dedup integration, and the `plan_import`/`write_import` orchestration pair). `core/entries.py::git_commit` gains one dirty-check. `core/handlers/publications.py` gains a citekey-by-fuzzy-title-match method, reused by the importer for `publications`/`catalog`. The CLI gets a `parco commit` command and an `import` sub-app (`parco import ccv`).

**Tech Stack:** Python ≥3.11, `xml.etree.ElementTree` (stdlib — no new dependency), the existing `CategoryHandler`/`GenericHandler`/`PublicationsHandler` and `core/matching.py::fuzzy_match`/`core/names.py::parse_person_list` machinery.

**Spec:** `SPECS.md` — see "Auto-commit", "Commit", "Import" (under CLI), and "CCV export structure (documented from a real export)" (under Category schemas (drafts)). Every field mapping, CCV field label, and value-format claim in this plan was verified directly against the user's own real CCV export (`cv_data_temp/CCV-79528.xml`, gitignored, never committed) during planning — implementers do **not** have access to that file (it's untracked and won't exist in a fresh worktree) and must not need it: every fact needed is inlined below.

## Global Constraints

- Core layer (`parcours/core/`) never does interactive I/O: no `print()`/`input()`/`sys.exit()`/`typer.echo()`/`typer.confirm()`. CLI (`parcours/cli/main.py`) owns all prompting and output formatting.
- No CCV-specific parsing library — plain `xml.etree.ElementTree`, stdlib only.
- Only the root `<generic-cv>` element carries an XML namespace URI (`{http://www.cihr-irsc.gc.ca/generic-cv/1.0.0}generic-cv`); every descendant element (`section`, `field`, `value`, `lov`, `refTable`, `linkedWith`, `bilingual`, `french`, `english`) uses a **bare, unprefixed tag name** — verified against the real export. Never search descendants with a namespace-prefixed tag.
- A CCV "record" is any `<section>` element carrying a `recordId` attribute, regardless of nesting depth. Its own `label` attribute names its type (e.g. `<section recordId="..." label="Degrees">`).
- The root `<generic-cv lang="en"|"fr" ...>` element's `lang` attribute is the export's default language — verified present on the real export. Used only for: (a) routing a single-language `String`-typed field to `_en`/`_fr` schema field pairs, and (b) the fallback path of `field_bilingual` when the split form is absent/empty.
- Bilingual fields: the split `<bilingual><french>text</french><english>text</english></bilingual>` element is a **sibling** of `<value type="Bilingual">`, both children of the same `<field>` — never nested inside `<value>`. Verified against the real export: **prefer the split sibling** whenever it has any non-blank content; only fall back to the unsplit `<value>` blob (assigned to the root `lang`) when the split sibling is absent or entirely blank.
- CCV date wire formats, verified against the real export: `Year` → `"yyyy"` (matches our own bare-year format, no conversion). `YearMonth` → `"yyyy/M"` or `"yyyy/MM"` (slash-separated, **month not always zero-padded** — must reformat to our `"yyyy-MM"`). `Date` → `"yyyy-MM-dd"` (already matches our own day-precision format exactly, direct passthrough).
- `<lov id="...">Display Text</lov>` — the display text is the element's own `.text`, not an attribute.
- `<linkedWith label="..." value="..." refOrLovId="...">` — the resolved value is the `value` **attribute**, not element text (`refTable`'s own text is always empty/`None`).
- `person_list`-typed target fields (`artworks.co_authors`, `presentations.co_presenters`, `grants.co_investigators`) are filled via **parse-as-validation-gate**: feed the candidate string through `core/names.py::parse_person_list` unchanged; on success, write it verbatim; on `InvalidPersonListError` (or if the candidate is blank), leave the field blank and record a flag for that row. Never attempt to reformat/reorder a name string.
- The importer **never** calls `core/entries.py::add_entry` and never auto-commits. It writes CSVs directly via `core/entries.py::write_all_rows` and leaves the result **uncommitted** — this is the one deliberate exception to the "every write auto-commits" rule (see SPECS.md, "Import").
- Records with a missing-but-required field are still written (blank field) — `parco lint` catches that afterward. Only genuine dedup ambiguity, a failed Zotero match (`publications`/`catalog`), or a failed `person_list` parse gets flagged in the report and excluded from the write.

---

## Task 1: Commit mechanics — `parco commit` and conditional auto-commit

**Files:**
- Create: `parcours/core/commit.py`
- Modify: `parcours/core/entries.py` (the `git_commit` function, lines 49-65)
- Modify: `parcours/cli/main.py` (new `commit` command)
- Test: `tests/unit/test_commit.py` (new), `tests/unit/test_entries.py` (extend), `tests/integration/test_cli_commit.py` (new)

**Interfaces:**
- Produces: `core/commit.py::commit_pending(data_dir: Path, message: str | None = None) -> CommitResult`, `CommitResult` dataclass with `committed: bool` and `files: list[str]`. `core/entries.py::git_commit(data_dir: Path, filename: str, message: str) -> bool` (now returns whether it actually committed — `False` when skipped because the file was already dirty).

- [ ] **Step 1: Write the failing tests for `git_commit`'s dirty-check**

Append to `tests/unit/test_entries.py` (uses the existing `_schema()`/real `git_commit`, not the `_no_commit` monkeypatch helper — these tests exercise the real function against a real temp git repo):

```python
import subprocess


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)


def test_git_commit_commits_when_file_was_clean(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "widgets.csv").write_text("id,title_en\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True, capture_output=True)

    (tmp_path / "widgets.csv").write_text("id,title_en\nabc123,A\n", encoding="utf-8")
    committed = git_commit(tmp_path, "widgets.csv", "Added widgets entry abc123")

    assert committed is True
    log = subprocess.run(["git", "log", "--oneline"], cwd=tmp_path, check=True, capture_output=True, text=True)
    assert "Added widgets entry abc123" in log.stdout


def test_git_commit_skips_when_file_already_dirty(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "widgets.csv").write_text("id,title_en\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True, capture_output=True)

    # Simulate a pending import: the file already has uncommitted content
    # before this write happens.
    (tmp_path / "widgets.csv").write_text("id,title_en\nzzz999,Pending\n", encoding="utf-8")

    (tmp_path / "widgets.csv").write_text("id,title_en\nzzz999,Pending\nabc123,A\n", encoding="utf-8")
    committed = git_commit(tmp_path, "widgets.csv", "Added widgets entry abc123")

    assert committed is False
    log = subprocess.run(["git", "log", "--oneline"], cwd=tmp_path, check=True, capture_output=True, text=True)
    assert "Added widgets entry abc123" not in log.stdout
    # The write itself still happened — nothing was rolled back.
    assert "abc123" in (tmp_path / "widgets.csv").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_entries.py -k dirty -v`
Expected: FAIL (`git_commit` currently always commits and returns `None`, not `False`).

- [ ] **Step 3: Modify `git_commit` in `parcours/core/entries.py`**

Replace the existing `git_commit` function (lines 49-65) with:

```python
def git_commit(data_dir: Path, filename: str, message: str) -> bool:
    """Commits `filename`'s current content, unless it already had
    uncommitted changes *before* this write (e.g. a pending `parco
    import` review, or a hand-edit) — in that case the write still
    happened, but committing now would silently fold every other
    pending change in that file into a message that only names this
    one row. Returns whether it actually committed."""
    status_before = subprocess.run(
        ["git", "status", "--porcelain", "--", filename],
        cwd=data_dir, check=True, capture_output=True,
    )
    was_already_dirty = bool(status_before.stdout.strip())

    subprocess.run(["git", "add", filename], cwd=data_dir, check=True, capture_output=True)

    status_after = subprocess.run(
        ["git", "status", "--porcelain", "--staged", "--", filename],
        cwd=data_dir, check=True, capture_output=True,
    )
    if not status_after.stdout.strip():
        # Nothing changed for this file (e.g. an edit with identical values) —
        # the row is already correctly on disk, so there's nothing to commit.
        return False

    if was_already_dirty:
        return False

    try:
        subprocess.run(["git", "commit", "-m", message], cwd=data_dir, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if exc.stderr else str(exc)
        raise CommitFailed(f"git commit failed: {stderr}") from exc
    return True
```

Note the check-before-write ordering: `status_before` must be read **before** `git add` runs (staging changes the working-tree status), which is why it's captured first into `was_already_dirty`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_entries.py -k dirty -v`
Expected: PASS.

- [ ] **Step 5: Update `add_entry`/`edit_entry`/`delete_entry` callers if needed**

They already just call `git_commit(...)` and ignore its return value (see `core/entries.py` lines 68-98) — no signature change needed there, since a `bool` return is backward-compatible with a previously-`None`-returning call used as a statement. Same for `core/translations.py`'s three `git_commit(...)` calls. No changes needed to either file beyond the function body above.

- [ ] **Step 6: Run the full existing test suite to check for regressions**

Run: `pytest tests/unit/test_entries.py tests/unit/test_translations.py tests/integration/test_cli_add.py tests/integration/test_cli_edit.py tests/integration/test_cli_delete.py -v`
Expected: PASS (existing tests never asserted on `git_commit`'s return value, so this is purely additive).

- [ ] **Step 7: Commit**

```bash
git add parcours/core/entries.py tests/unit/test_entries.py
git commit -m "Skip auto-commit when the target file already had pending changes"
```

- [ ] **Step 8: Write the failing test for `commit_pending`**

Create `tests/unit/test_commit.py`:

```python
import subprocess

from parcours.core.commit import commit_pending


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / "widgets.csv").write_text("id,title_en\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, check=True, capture_output=True)


def test_commit_pending_commits_everything_with_generated_message(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "widgets.csv").write_text("id,title_en\nabc123,A\n", encoding="utf-8")
    (tmp_path / "gadgets.csv").write_text("id,title_en\n", encoding="utf-8")
    (tmp_path / "gadgets.csv").write_text("id,title_en\nzzz999,Z\n", encoding="utf-8")

    result = commit_pending(tmp_path)

    assert result.committed is True
    assert sorted(result.files) == ["gadgets.csv", "widgets.csv"]
    log = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=tmp_path, check=True, capture_output=True, text=True)
    assert "widgets.csv" in log.stdout
    assert "gadgets.csv" in log.stdout


def test_commit_pending_uses_custom_message(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "widgets.csv").write_text("id,title_en\nabc123,A\n", encoding="utf-8")

    result = commit_pending(tmp_path, message="Imported from CCV export")

    assert result.committed is True
    log = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=tmp_path, check=True, capture_output=True, text=True)
    assert log.stdout.strip() == "Imported from CCV export"


def test_commit_pending_does_nothing_on_clean_tree(tmp_path):
    _init_git_repo(tmp_path)

    result = commit_pending(tmp_path)

    assert result.committed is False
    assert result.files == []
```

- [ ] **Step 9: Run the tests to verify they fail**

Run: `pytest tests/unit/test_commit.py -v`
Expected: FAIL (`parcours.core.commit` doesn't exist yet — `ModuleNotFoundError`).

- [ ] **Step 10: Create `parcours/core/commit.py`**

```python
"""Manually stage and commit whatever's currently pending in the data
repo — for hand-edits outside `parco`, or to finalize a `parco import`
review (see SPECS.md, "Commit"). Core layer: no prompting/printing."""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommitResult:
    committed: bool
    files: list[str]


def commit_pending(data_dir: Path, message: str | None = None) -> CommitResult:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=data_dir, check=True, capture_output=True, text=True,
    )
    if not status.stdout.strip():
        return CommitResult(committed=False, files=[])

    files = sorted({line[3:].strip() for line in status.stdout.splitlines() if line.strip()})

    subprocess.run(["git", "add", "-A"], cwd=data_dir, check=True, capture_output=True)

    if message is None:
        message = f"Updated {', '.join(files)}"

    subprocess.run(["git", "commit", "-m", message], cwd=data_dir, check=True, capture_output=True)
    return CommitResult(committed=True, files=files)
```

- [ ] **Step 11: Run the tests to verify they pass**

Run: `pytest tests/unit/test_commit.py -v`
Expected: PASS.

- [ ] **Step 12: Write the failing integration test for `parco commit`**

Create `tests/integration/test_cli_commit.py`. Read the top ~40 lines of `tests/integration/test_cli_list.py` first — it establishes the real convention this codebase uses, repeated identically (never imported across files) in every `tests/integration/test_cli_*.py` file: a `CliRunner`, a **locally-defined** `_setup_data_repo(tmp_path)` helper that writes `parco.yaml`/`categories/<name>.yaml`/`vocab.yaml`/`translations.csv`/`<name>.csv` directly (no `--data-dir` flag exists anywhere in this CLI), and `monkeypatch.chdir(repo)` before `runner.invoke(app, [...])` — the data repo is found by upward search from the current working directory (see `core/repo.py::find_data_repo`), never by an explicit CLI flag. Copy `test_cli_list.py`'s exact `_setup_data_repo` body into this new file (matching every other `test_cli_*.py` file's own local copy), extended with a real git repo (since `commit_pending` shells out to `git`):

```python
import subprocess

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
    (tmp_path / "translations.csv").write_text("id,category,en,fr\n")
    (tmp_path / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First Widget,draft\ndef456,Second Widget,published\n",
        encoding="utf-8",
    )
    return tmp_path


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, check=True, capture_output=True)


def test_commit_stages_and_commits_pending_changes(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    (repo / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First Widget,draft\ndef456,Second Widget,published\nghi789,Third Widget,draft\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["commit"])

    assert result.exit_code == 0
    assert "committed" in result.stdout.lower() or "Updated" in result.stdout
    log = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=repo, check=True, capture_output=True, text=True)
    assert "widgets.csv" in log.stdout


def test_commit_reports_nothing_to_do_on_clean_repo(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["commit"])

    assert result.exit_code == 0
    assert "nothing to commit" in result.stdout.lower()


def test_commit_accepts_custom_message(tmp_path, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    (repo / "widgets.csv").write_text(
        "id,title_en,status\nabc123,First Widget,draft\ndef456,Second Widget,published\nghi789,Third Widget,draft\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["commit", "-m", "Manual fix"])

    assert result.exit_code == 0
    log = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=repo, check=True, capture_output=True, text=True)
    assert log.stdout.strip() == "Manual fix"
```

- [ ] **Step 13: Run the tests to verify they fail**

Run: `pytest tests/integration/test_cli_commit.py -v`
Expected: FAIL (no `commit` command registered yet).

- [ ] **Step 14: Add the `commit` command to `parcours/cli/main.py`**

Add the import at the top (alongside the other `..core.*` imports):

```python
from ..core.commit import commit_pending
```

Add the command (anywhere among the other top-level `@app.command()` functions, e.g. right after `lint`):

```python
@app.command()
def commit(
    message: str = typer.Option(None, "-m", "--message", help="Commit message (auto-generated from changed files if omitted)"),
):
    """Stage and commit whatever's currently pending in the data repo — for hand-edits, or to finalize a `parco import` review."""
    data_dir = _find_repo_or_exit()

    result = commit_pending(data_dir, message=message)
    if not result.committed:
        typer.echo("Nothing to commit.")
        return
    typer.echo(f"Committed: {', '.join(result.files)}")
```

- [ ] **Step 15: Run the tests to verify they pass**

Run: `pytest tests/integration/test_cli_commit.py -v`
Expected: PASS.

- [ ] **Step 16: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 17: Commit**

```bash
git add parcours/core/commit.py parcours/cli/main.py tests/unit/test_commit.py tests/integration/test_cli_commit.py
git commit -m "Added parco commit command"
```

---

## Task 2: CCV XML parsing foundation

**Files:**
- Create: `parcours/core/ccv_xml.py`
- Test: `tests/unit/test_ccv_xml.py` (new)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces (used by every later task):
  - `CcvRecord` dataclass: `element: ET.Element`, `label: str`, `path: tuple[str, ...]`
  - `parse_ccv_export(xml_path: Path) -> tuple[ET.Element, str]` — returns `(root, lang)`
  - `find_records(root: ET.Element) -> list[CcvRecord]` — every `recordId`-bearing element, in document order, with its full ancestor label path (including its own label as the last element)
  - `field_text(record_el, label: str) -> str` — raw text for a `String`/`Number` field; `""` if absent/blank
  - `field_year(record_el, label: str) -> str` — a `Year`-typed field, `""` if absent/blank (already our format, no conversion)
  - `field_yearmonth(record_el, label: str) -> str` — a `YearMonth`-typed field (`"yyyy/M"` or `"yyyy/MM"`), reformatted to `"yyyy-MM"`; `""` if absent/blank
  - `field_date(record_el, label: str) -> str` — a `Date`-typed field (`"yyyy-MM-dd"`), passthrough; `""` if absent/blank
  - `field_lov(record_el, label: str) -> str` — the CCV controlled-vocab display string; `""` if absent/blank
  - `field_bilingual(record_el, label: str, default_lang: str) -> tuple[str, str]` — returns `(french, english)`
  - `field_single_language(record_el, label: str, default_lang: str) -> tuple[str, str]` — for a `String`-typed title with no per-field language marker; returns `(text_for_fr, text_for_en)` with exactly one side non-blank (routed by `default_lang`), or `("", "")` if blank
  - `field_organization(record_el, label: str = "Organization") -> str` — resolves a refTable Organization via its nested `linkedWith`, falling back to `field_text(record_el, "Other Organization")`
  - `sub_records(record_el, label: str) -> list[ET.Element]` — direct child `<section label=label>` elements (e.g. `Supervisors`, `Funding Sources`, `Other Investigators`)
  - `try_person_list(raw: str) -> str | None` — attempts `core.names.parse_person_list(raw)`; returns `raw` unchanged on success, `None` on failure or blank input (the caller decides whether `None` means "leave blank silently" or "flag this row")

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_ccv_xml.py`:

```python
import xml.etree.ElementTree as ET

import pytest

from parcours.core.ccv_xml import (
    field_bilingual,
    field_date,
    field_lov,
    field_organization,
    field_single_language,
    field_text,
    field_yearmonth,
    find_records,
    parse_ccv_export,
    sub_records,
    try_person_list,
)

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
  <section label="Education">
    <section label="Degrees" recordId="rec-1">
      <field label="Degree Type"><lov id="1">Doctorate</lov></field>
      <field label="Degree Name">
        <value type="Bilingual">Fellowship</value>
        <bilingual><french>Bourse</french><english>Fellowship</english></bilingual>
      </field>
      <field label="Thesis Title"><value type="String">A Thesis</value></field>
      <field label="Organization">
        <refTable refValueId="x" label="Organization">
          <linkedWith label="Country" value="Canada" refOrLovId="y"/>
          <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
        </refTable>
      </field>
      <field label="Other Organization Type"></field>
      <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
      <field label="Degree Received Date"><value type="YearMonth">2022/06</value></field>
      <section label="Supervisors" recordId="rec-1-sup-1">
        <field label="Supervisor Name"><value type="String">Jane Smith</value></field>
        <field label="Start Date"><value type="YearMonth">2018/9</value></field>
        <field label="End Date"><value type="YearMonth">2022/06</value></field>
      </section>
    </section>
  </section>
  <section label="Contributions">
    <section label="Artistic Contributions">
      <section label="Visual Artworks" recordId="rec-2">
        <field label="Artwork Title"><value type="String">Untitled</value></field>
        <field label="Publication Date"><value type="YearMonth">2020/3</value></field>
        <field label="Description / Contribution Value">
          <value type="Bilingual"></value>
          <bilingual><french></french><english></english></bilingual>
        </field>
        <field label="Contribution Role"><value type="String">Author</value></field>
        <field label="Contributors"><value type="String">Smith, Jane; Doe, John</value></field>
      </section>
    </section>
  </section>
</generic-cv:generic-cv>
"""


@pytest.fixture
def root(tmp_path):
    xml_path = tmp_path / "export.xml"
    xml_path.write_text(_SAMPLE, encoding="utf-8")
    root, lang = parse_ccv_export(xml_path)
    assert lang == "en"
    return root


def test_find_records_returns_every_recordid_element_with_its_path(root):
    records = find_records(root)
    paths = [r.path for r in records]
    assert ("Education", "Degrees") in paths
    assert ("Education", "Degrees", "Supervisors") in paths
    assert ("Contributions", "Artistic Contributions", "Visual Artworks") in paths


def test_field_lov_reads_display_text(root):
    degrees = find_records(root)[0].element
    assert field_lov(degrees, "Degree Type") == "Doctorate"
    assert field_lov(degrees, "Nonexistent Field") == ""


def test_field_text_reads_string_value(root):
    degrees = find_records(root)[0].element
    assert field_text(degrees, "Thesis Title") == "A Thesis"
    assert field_text(degrees, "Other Organization Type") == ""


def test_field_yearmonth_reformats_slash_to_dash_and_zero_pads(root):
    degrees = find_records(root)[0].element
    assert field_yearmonth(degrees, "Degree Start Date") == "2018-09"
    assert field_yearmonth(degrees, "Degree Received Date") == "2022-06"
    assert field_yearmonth(degrees, "Missing Field") == ""


def test_field_organization_resolves_reftable_linkedwith(root):
    degrees = find_records(root)[0].element
    assert field_organization(degrees) == "Test University"


def test_field_organization_falls_back_to_other_organization(root):
    artwork = find_records(root)[3].element
    # Visual Artworks record has no Organization field at all.
    assert field_organization(artwork) == ""


def test_field_bilingual_prefers_split_form(root):
    degrees = find_records(root)[0].element
    fr, en = field_bilingual(degrees, "Degree Name", default_lang="en")
    assert fr == "Bourse"
    assert en == "Fellowship"


def test_field_bilingual_returns_blank_when_both_blank(root):
    artwork = find_records(root)[3].element
    fr, en = field_bilingual(artwork, "Description / Contribution Value", default_lang="en")
    assert fr == ""
    assert en == ""


def test_field_single_language_routes_by_default_lang(root):
    artwork = find_records(root)[3].element
    fr, en = field_single_language(artwork, "Artwork Title", default_lang="en")
    assert fr == ""
    assert en == "Untitled"


def test_sub_records_finds_direct_children_only(root):
    degrees = find_records(root)[0].element
    supervisors = sub_records(degrees, "Supervisors")
    assert len(supervisors) == 1
    assert field_text(supervisors[0], "Supervisor Name") == "Jane Smith"


def test_try_person_list_returns_raw_on_valid_format():
    assert try_person_list("Smith, Jane; Doe, John") == "Smith, Jane; Doe, John"


def test_try_person_list_returns_none_on_invalid_format():
    assert try_person_list("Jane Smith") is None


def test_try_person_list_returns_none_on_blank():
    assert try_person_list("") is None
    assert try_person_list("   ") is None


def test_field_date_passes_through_iso_date():
    xml = '<r label="X" recordId="1"><field label="D"><value type="Date">2024-05-17</value></field></r>'
    el = ET.fromstring(xml)
    assert field_date(el, "D") == "2024-05-17"
    assert field_date(el, "Missing") == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_ccv_xml.py -v`
Expected: FAIL (`parcours.core.ccv_xml` doesn't exist).

- [ ] **Step 3: Create `parcours/core/ccv_xml.py`**

```python
"""Generic CCV (Canadian Common CV) XML tree-walking primitives — no
category knowledge here, just the wire format (see SPECS.md, "CCV
export structure"). Category field mapping lives in `import_ccv.py`."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .names import InvalidPersonListError, parse_person_list


@dataclass
class CcvRecord:
    element: ET.Element
    label: str
    path: tuple[str, ...]


def parse_ccv_export(xml_path: Path) -> tuple[ET.Element, str]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    lang = root.get("lang") or "en"
    return root, lang


def find_records(root: ET.Element) -> list[CcvRecord]:
    parent_map = {child: parent for parent in root.iter() for child in parent}
    records = []
    for element in root.iter():
        if element.get("recordId") is not None:
            records.append(CcvRecord(
                element=element,
                label=element.get("label"),
                path=tuple(_ancestor_labels(element, parent_map)),
            ))
    return records


def _ancestor_labels(element: ET.Element, parent_map: dict) -> list[str]:
    labels = []
    current = element
    while current is not None:
        label = current.get("label")
        if label:
            labels.append(label)
        current = parent_map.get(current)
    return list(reversed(labels))


def _field_element(record_el: ET.Element, label: str) -> ET.Element | None:
    return record_el.find(f"field[@label='{label}']")


def field_text(record_el: ET.Element, label: str) -> str:
    field = _field_element(record_el, label)
    if field is None:
        return ""
    value = field.find("value")
    if value is None:
        return ""
    return (value.text or "").strip()


def field_year(record_el: ET.Element, label: str) -> str:
    return field_text(record_el, label)


def field_yearmonth(record_el: ET.Element, label: str) -> str:
    raw = field_text(record_el, label)
    if not raw or "/" not in raw:
        return ""
    year, month = raw.split("/", 1)
    return f"{year}-{int(month):02d}"


def field_date(record_el: ET.Element, label: str) -> str:
    return field_text(record_el, label)


def field_lov(record_el: ET.Element, label: str) -> str:
    field = _field_element(record_el, label)
    if field is None:
        return ""
    lov = field.find("lov")
    if lov is None:
        return ""
    return (lov.text or "").strip()


def field_bilingual(record_el: ET.Element, label: str, default_lang: str) -> tuple[str, str]:
    field = _field_element(record_el, label)
    if field is None:
        return "", ""

    bilingual = field.find("bilingual")
    if bilingual is not None:
        french_el = bilingual.find("french")
        english_el = bilingual.find("english")
        french = (french_el.text or "").strip() if french_el is not None else ""
        english = (english_el.text or "").strip() if english_el is not None else ""
        if french or english:
            return french, english

    value = field.find("value")
    blob = (value.text or "").strip() if value is not None else ""
    if not blob:
        return "", ""
    return (blob, "") if default_lang == "fr" else ("", blob)


def field_single_language(record_el: ET.Element, label: str, default_lang: str) -> tuple[str, str]:
    """A `String`-typed field with no per-field language marker (e.g. a
    CCV title field) — routed to (french, english) by the export's own
    default language, exactly one side non-blank."""
    text = field_text(record_el, label)
    if not text:
        return "", ""
    return (text, "") if default_lang == "fr" else ("", text)


def field_organization(record_el: ET.Element, label: str = "Organization") -> str:
    field = _field_element(record_el, label)
    if field is not None:
        ref_table = field.find("refTable")
        if ref_table is not None:
            linked = ref_table.find("linkedWith[@label='Organization']")
            if linked is not None and linked.get("value"):
                return linked.get("value")
    return field_text(record_el, "Other Organization")


def sub_records(record_el: ET.Element, label: str) -> list[ET.Element]:
    return record_el.findall(f"section[@label='{label}']")


def try_person_list(raw: str) -> str | None:
    if not raw or not raw.strip():
        return None
    try:
        parse_person_list(raw)
    except InvalidPersonListError:
        return None
    return raw
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_ccv_xml.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add parcours/core/ccv_xml.py tests/unit/test_ccv_xml.py
git commit -m "Added CCV XML parsing primitives"
```

---

## Task 3: Simple field-mapping categories — education, positions, recognitions, teaching, press, presentations

**Files:**
- Create: `parcours/core/import_ccv.py`
- Test: `tests/unit/test_import_ccv.py` (new — this file grows across Tasks 3, 4, 5, 6, 8)

**Interfaces:**
- Consumes: everything from Task 2 (`core/ccv_xml.py`).
- Produces: one mapper function per CCV leaf record label, each with signature `(record_el: ET.Element, lang: str, ctx: ImportContext) -> MappedRow | FlaggedRecord`, registered in a module-level `MAPPERS: dict[str, Callable]` dict keyed by the record's own `label`. Later tasks add more entries to this same dict.
  - `ImportContext` dataclass (defined in this task, used by every mapper task): `default_currency: str`, `own_name: tuple[str, str]` (last, first — from `identity.yaml`, used in Task 5).
  - `MappedRow` dataclass: `category: str`, `fields: dict[str, str]`, `ccv_label: str`, `flag: str | None = None` (a non-blocking note about this specific row, e.g. "2 Funding Sources found, using the first").
  - `FlaggedRecord` dataclass: `ccv_label: str`, `reason: str` (the whole record is excluded from writing, e.g. "no confident Zotero match for title").

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_import_ccv.py`:

```python
import xml.etree.ElementTree as ET

from parcours.core.import_ccv import ImportContext, MappedRow, map_record


def _record(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def _ctx():
    return ImportContext(default_currency="CAD", own_name=("Doe", "Jane"))


def test_map_education_degree():
    el = _record("""
    <section label="Degrees" recordId="r1">
      <field label="Degree Type"><lov id="1">Doctorate</lov></field>
      <field label="Degree Name">
        <value type="Bilingual">Ph.D.</value>
        <bilingual><french>Ph. D.</french><english>Ph.D.</english></bilingual>
      </field>
      <field label="Specialization">
        <value type="Bilingual"></value>
        <bilingual><french></french><english></english></bilingual>
      </field>
      <field label="Thesis Title"><value type="String">A Study</value></field>
      <field label="Organization">
        <refTable refValueId="x" label="Organization">
          <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
        </refTable>
      </field>
      <field label="Degree Status"><lov id="2">Completed</lov></field>
      <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
      <field label="Degree Received Date"><value type="YearMonth">2022/6</value></field>
      <section label="Supervisors" recordId="r1s1">
        <field label="Supervisor Name"><value type="String">Jane Smith</value></field>
      </section>
      <section label="Supervisors" recordId="r1s2">
        <field label="Supervisor Name"><value type="String">John Doe</value></field>
      </section>
    </section>
    """)
    row = map_record(el, "Degrees", "en", _ctx())
    assert isinstance(row, MappedRow)
    assert row.category == "education"
    assert row.fields["degree_type"] == "doctorate"
    assert row.fields["degree_name_fr"] == "Ph. D."
    assert row.fields["degree_name_en"] == "Ph.D."
    assert row.fields["organization"] == "Test University"
    assert row.fields["degree_status"] == "completed"
    assert row.fields["start_date"] == "2018-09"
    assert row.fields["end_date"] == "2022-06"
    assert row.fields["advisor"] == "Jane Smith; John Doe"
    assert row.fields["thesis_title"] == "A Study"


def test_map_presentation_with_valid_co_presenters():
    el = _record("""
    <section label="Presentations" recordId="r2">
      <field label="Presentation Title"><value type="String">My Talk</value></field>
      <field label="Conference / Event Name"><value type="String">Some Conference</value></field>
      <field label="Invited?"><lov id="1">Yes</lov></field>
      <field label="Keynote?"><lov id="2">No</lov></field>
      <field label="Presentation Year"><value type="Year">2023</value></field>
      <field label="URL"><value type="String">http://example.com</value></field>
      <field label="Co-Presenters"><value type="String">Smith, Jane; Doe, John</value></field>
    </section>
    """)
    row = map_record(el, "Presentations", "en", _ctx())
    assert row.fields["title_en"] == "My Talk"
    assert row.fields["title_fr"] == ""
    assert row.fields["event_en"] == "Some Conference"
    assert row.fields["invited"] == "true"
    assert row.fields["keynote"] == "false"
    assert row.fields["date"] == "2023"
    assert row.fields["co_presenters"] == "Smith, Jane; Doe, John"
    assert row.flag is None


def test_map_presentation_flags_unparseable_co_presenters():
    el = _record("""
    <section label="Presentations" recordId="r3">
      <field label="Presentation Title"><value type="String">Another Talk</value></field>
      <field label="Presentation Year"><value type="Year">2022</value></field>
      <field label="Co-Presenters"><value type="String">Jane Smith and John Doe</value></field>
    </section>
    """)
    row = map_record(el, "Presentations", "en", _ctx())
    assert row.fields["co_presenters"] == ""
    assert row.flag is not None
    assert "co_presenters" in row.flag


def test_map_recognitions():
    el = _record("""
    <section label="Recognitions" recordId="r4">
      <field label="Recognition Type"><lov id="1">Prize / Award</lov></field>
      <field label="Recognition Name"><value type="String">Best Paper</value></field>
      <field label="Other Organization"><value type="String">Some Society</value></field>
      <field label="Effective Date"><value type="YearMonth">2021/5</value></field>
      <field label="Amount"><value type="Number">1000</value></field>
      <field label="Currency"><lov id="2">CAD</lov></field>
      <field label="Description">
        <value type="Bilingual"></value>
        <bilingual><french>Une description</french><english>A description</english></bilingual>
      </field>
    </section>
    """)
    row = map_record(el, "Recognitions", "en", _ctx())
    assert row.fields["recognition_type"] == "prize"
    assert row.fields["name"] == "Best Paper"
    assert row.fields["organization"] == "Some Society"
    assert row.fields["role"] == "recipient"
    assert row.fields["date"] == "2021-05"
    assert row.fields["amount"] == "1000"
    assert row.fields["currency"] == "CAD"
    assert row.fields["description_en"] == "A description"
    assert row.fields["description_fr"] == "Une description"


def test_map_recognitions_defaults_currency_when_ccv_gives_none():
    el = _record("""
    <section label="Recognitions" recordId="r5">
      <field label="Recognition Type"><lov id="1">Citation</lov></field>
      <field label="Recognition Name"><value type="String">Mention</value></field>
      <field label="Effective Date"><value type="YearMonth">2020/1</value></field>
    </section>
    """)
    row = map_record(el, "Recognitions", "en", _ctx())
    assert row.fields["amount"] == ""
    assert row.fields["currency"] == ""


def test_map_teaching_course_development():
    el = _record("""
    <section label="Course Development" recordId="r6">
      <field label="Role"><value type="String">Professor</value></field>
      <field label="Organization">
        <refTable refValueId="x" label="Organization">
          <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
        </refTable>
      </field>
      <field label="Department"><value type="String">Media Studies</value></field>
      <field label="Course Title"><value type="String">Intro to Media</value></field>
      <field label="Date First Taught"><value type="YearMonth">2019/9</value></field>
    </section>
    """)
    row = map_record(el, "Course Development", "en", _ctx())
    assert row.category == "teaching"
    assert row.fields["course_label"] == ""
    assert row.fields["title_en"] == "Intro to Media"
    assert row.fields["role"] == "Professor"
    assert row.fields["organization"] == "Test University"
    assert row.fields["department"] == "Media Studies"
    assert row.fields["date"] == "2019-09"


def test_map_press_broadcast_interview():
    el = _record("""
    <section label="Broadcast Interviews" recordId="r7">
      <field label="Interviewer"><value type="String">A Journalist</value></field>
      <field label="Program"><value type="String">Morning Show</value></field>
      <field label="Network"><value type="String">Test Radio</value></field>
      <field label="First Broadcast Date"><value type="Date">2021-03-14</value></field>
      <field label="Description / Contribution Value">
        <value type="Bilingual"></value>
        <bilingual><french></french><english>A discussion</english></bilingual>
      </field>
      <field label="URL"><value type="String">http://example.com/clip</value></field>
    </section>
    """)
    row = map_record(el, "Broadcast Interviews", "en", _ctx())
    assert row.category == "press"
    assert row.fields["author"] == "A Journalist"
    assert row.fields["outlet"] == "Test Radio"
    assert row.fields["program"] == "Morning Show"
    assert row.fields["date"] == "2021-03-14"
    assert row.fields["description_en"] == "A discussion"


def test_map_press_text_interview_has_no_program():
    el = _record("""
    <section label="Text Interviews" recordId="r8">
      <field label="Interviewer"><value type="String">A Journalist</value></field>
      <field label="Forum"><value type="String">Test Magazine</value></field>
      <field label="Publication Date"><value type="Date">2020-11-02</value></field>
    </section>
    """)
    row = map_record(el, "Text Interviews", "en", _ctx())
    assert row.fields["outlet"] == "Test Magazine"
    assert row.fields["program"] == ""
    assert row.fields["date"] == "2020-11-02"


def test_map_positions_academic():
    el = _record("""
    <section label="Academic Work Experience" recordId="r9">
      <field label="Position Title"><value type="String">Professor</value></field>
      <field label="Organization">
        <refTable refValueId="x" label="Organization">
          <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
        </refTable>
      </field>
      <field label="Faculty / School / Campus"><value type="String">Media</value></field>
      <field label="Department"><value type="String">Studies</value></field>
      <field label="Position Status"><lov id="1">Full-time</lov></field>
      <field label="Start Date"><value type="YearMonth">2015/8</value></field>
    </section>
    """)
    row = map_record(el, "Academic Work Experience", "en", _ctx())
    assert row.category == "positions"
    assert row.fields["type"] == "academic"
    assert row.fields["title_en"] == "Professor"
    assert row.fields["organization"] == "Test University"
    assert row.fields["faculty"] == "Media"
    assert row.fields["department"] == "Studies"
    assert row.fields["position_status"] == "full-time"
    assert row.fields["start_date"] == "2015-08"


def test_map_positions_affiliation_title_is_truly_bilingual():
    el = _record("""
    <section label="Affiliations" recordId="r10">
      <field label="Position Title">
        <value type="Bilingual">Member</value>
        <bilingual><french>Membre</french><english>Member</english></bilingual>
      </field>
      <field label="Other Organization"><value type="String">Some Institute</value></field>
      <field label="Department"><value type="String">N/A</value></field>
      <field label="Start Date"><value type="YearMonth">2017/1</value></field>
    </section>
    """)
    row = map_record(el, "Affiliations", "en", _ctx())
    assert row.fields["type"] == "affiliation"
    assert row.fields["title_en"] == "Member"
    assert row.fields["title_fr"] == "Membre"
    assert row.fields["organization"] == "Some Institute"


def test_map_positions_non_academic_uses_unit_division_as_department():
    el = _record("""
    <section label="Non-academic Work Experience" recordId="r11">
      <field label="Position Title"><value type="String">Consultant</value></field>
      <field label="Other Organization"><value type="String">Some Company</value></field>
      <field label="Unit / Division"><value type="String">R&amp;D</value></field>
      <field label="Start Date"><value type="YearMonth">2014/1</value></field>
      <field label="End Date"><value type="YearMonth">2015/1</value></field>
    </section>
    """)
    row = map_record(el, "Non-academic Work Experience", "en", _ctx())
    assert row.fields["type"] == "non-academic"
    assert row.fields["organization"] == "Some Company"
    assert row.fields["department"] == "R&D"
    assert row.fields["faculty"] == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_import_ccv.py -v`
Expected: FAIL (`parcours.core.import_ccv` doesn't exist).

- [ ] **Step 3: Create `parcours/core/import_ccv.py` with the shared scaffolding plus this task's six mappers**

```python
"""CCV (Canadian Common CV) → parco category field mapping, per-record
dedup, and the plan/write orchestration for `parco import ccv` (see
SPECS.md, "Import" and "CCV export structure"). Core layer: no
prompting/printing — see `cli/main.py`'s `import_app` for that."""

from dataclasses import dataclass, field
from typing import Callable

from . import ccv_xml as x


@dataclass
class ImportContext:
    default_currency: str
    own_name: tuple[str, str]  # (last, first)


@dataclass
class MappedRow:
    category: str
    fields: dict[str, str]
    ccv_label: str
    flag: str | None = None


@dataclass
class FlaggedRecord:
    ccv_label: str
    reason: str


MAPPERS: dict[str, Callable] = {}


def _register(*labels: str):
    def decorator(fn):
        for label in labels:
            MAPPERS[label] = fn
        return fn
    return decorator


def map_record(record_el, label: str, lang: str, ctx: ImportContext):
    """Dispatches to the mapper registered for `label`. Callers (Task 8)
    handle an unregistered label as either a known sub-record (ignored)
    or a genuinely unmapped record (reported as skipped)."""
    mapper = MAPPERS[label]
    return mapper(record_el, lang, ctx)


_DEGREE_TYPE = {
    "Bachelor's": "bachelors",
    "Bachelor’s Honours": "bachelors-honours",
    "Bachelor's Honours": "bachelors-honours",
    "Master's Thesis": "masters",
    "Master’s Thesis": "masters",
    "Doctorate": "doctorate",
    "Post-doctorate": "postdoc",
}

_DEGREE_STATUS = {
    "Completed": "completed",
    "In Progress": "in-progress",
    "Withdrawn": "withdrawn",
    "All But Degree": "all-but-degree",
}

_RECOGNITION_TYPE = {
    "Citation": "citation",
    "Distinction": "distinction",
    "Prize / Award": "prize",
}

_POSITION_STATUS = {
    "Full-time": "full-time",
    "Part-time": "part-time",
}

_YES_NO = {"Yes": "true", "No": "false"}


def _normalize_apostrophe(text: str) -> str:
    return text.replace("’", "'")


@_register("Degrees")
def _map_education(record_el, lang, ctx) -> MappedRow:
    degree_type_raw = _normalize_apostrophe(x.field_lov(record_el, "Degree Type"))
    degree_status_raw = x.field_lov(record_el, "Degree Status")
    specialization_fr, specialization_en = x.field_bilingual(record_el, "Specialization", lang)
    degree_name_fr, degree_name_en = x.field_bilingual(record_el, "Degree Name", lang)

    supervisor_names = [
        x.field_text(sup, "Supervisor Name")
        for sup in x.sub_records(record_el, "Supervisors")
    ]
    advisor = "; ".join(name for name in supervisor_names if name)

    return MappedRow(
        category="education",
        ccv_label="Degrees",
        fields={
            "degree_type": _DEGREE_TYPE.get(degree_type_raw, ""),
            "degree_name_en": degree_name_en,
            "degree_name_fr": degree_name_fr,
            "specialization_en": specialization_en,
            "specialization_fr": specialization_fr,
            "organization": x.field_organization(record_el),
            "degree_status": _DEGREE_STATUS.get(degree_status_raw, ""),
            "start_date": x.field_yearmonth(record_el, "Degree Start Date"),
            "end_date": x.field_yearmonth(record_el, "Degree Received Date"),
            "thesis_title": x.field_text(record_el, "Thesis Title"),
            "advisor": advisor,
            "note_en": "",
            "note_fr": "",
        },
    )


@_register("Presentations")
def _map_presentation(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, "Presentation Title", lang)
    event_fr, event_en = x.field_single_language(record_el, "Conference / Event Name", lang)
    description_fr, description_en = x.field_bilingual(record_el, "Description / Contribution Value", lang)

    raw_co_presenters = x.field_text(record_el, "Co-Presenters")
    co_presenters = x.try_person_list(raw_co_presenters)
    flag = None
    if raw_co_presenters and co_presenters is None:
        flag = f"co_presenters could not be parsed as 'Last, First' from CCV's raw value: {raw_co_presenters!r}"

    return MappedRow(
        category="presentations",
        ccv_label="Presentations",
        fields={
            "title_en": title_en,
            "title_fr": title_fr,
            "event_en": event_en,
            "event_fr": event_fr,
            "location": "",
            "invited": _YES_NO.get(x.field_lov(record_el, "Invited?"), ""),
            "keynote": _YES_NO.get(x.field_lov(record_el, "Keynote?"), ""),
            "date": x.field_year(record_el, "Presentation Year"),
            "description_en": description_en,
            "description_fr": description_fr,
            "co_presenters": co_presenters or "",
            "url": x.field_text(record_el, "URL"),
        },
        flag=flag,
    )


@_register("Recognitions")
def _map_recognitions(record_el, lang, ctx) -> MappedRow:
    recognition_type_raw = x.field_lov(record_el, "Recognition Type")
    description_fr, description_en = x.field_bilingual(record_el, "Description", lang)

    return MappedRow(
        category="recognitions",
        ccv_label="Recognitions",
        fields={
            "recognition_type": _RECOGNITION_TYPE.get(recognition_type_raw, ""),
            "name": x.field_text(record_el, "Recognition Name"),
            "organization": x.field_organization(record_el),
            "role": "recipient",
            "date": x.field_yearmonth(record_el, "Effective Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
            "amount": x.field_text(record_el, "Amount"),
            "currency": x.field_lov(record_el, "Currency"),
            "description_en": description_en,
            "description_fr": description_fr,
        },
    )


@_register("Course Development")
def _map_teaching(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, "Course Title", lang)

    return MappedRow(
        category="teaching",
        ccv_label="Course Development",
        fields={
            "course_label": "",
            "title_en": title_en,
            "title_fr": title_fr,
            "role": x.field_text(record_el, "Role"),
            "organization": x.field_organization(record_el),
            "department": x.field_text(record_el, "Department"),
            "date": x.field_yearmonth(record_el, "Date First Taught"),
        },
    )


@_register("Broadcast Interviews")
def _map_press_broadcast(record_el, lang, ctx) -> MappedRow:
    description_fr, description_en = x.field_bilingual(record_el, "Description / Contribution Value", lang)
    return MappedRow(
        category="press",
        ccv_label="Broadcast Interviews",
        fields={
            "citekey": "",
            "author": x.field_text(record_el, "Interviewer"),
            "outlet": x.field_text(record_el, "Network"),
            "program": x.field_text(record_el, "Program"),
            "date": x.field_date(record_el, "First Broadcast Date"),
            "description_en": description_en,
            "description_fr": description_fr,
            "url": x.field_text(record_el, "URL"),
        },
    )


@_register("Text Interviews")
def _map_press_text(record_el, lang, ctx) -> MappedRow:
    description_fr, description_en = x.field_bilingual(record_el, "Description / Contribution Value", lang)
    return MappedRow(
        category="press",
        ccv_label="Text Interviews",
        fields={
            "citekey": "",
            "author": x.field_text(record_el, "Interviewer"),
            "outlet": x.field_text(record_el, "Forum"),
            "program": "",
            "date": x.field_date(record_el, "Publication Date"),
            "description_en": description_en,
            "description_fr": description_fr,
            "url": x.field_text(record_el, "URL"),
        },
    )


@_register("Academic Work Experience")
def _map_positions_academic(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, "Position Title", lang)
    return MappedRow(
        category="positions",
        ccv_label="Academic Work Experience",
        fields={
            "type": "academic",
            "title_en": title_en,
            "title_fr": title_fr,
            "organization": x.field_organization(record_el),
            "faculty": x.field_text(record_el, "Faculty / School / Campus"),
            "department": x.field_text(record_el, "Department"),
            "position_status": _POSITION_STATUS.get(x.field_lov(record_el, "Position Status"), ""),
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
        },
    )


@_register("Non-academic Work Experience")
def _map_positions_non_academic(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, "Position Title", lang)
    return MappedRow(
        category="positions",
        ccv_label="Non-academic Work Experience",
        fields={
            "type": "non-academic",
            "title_en": title_en,
            "title_fr": title_fr,
            "organization": x.field_organization(record_el),
            "faculty": "",
            "department": x.field_text(record_el, "Unit / Division"),
            "position_status": "",
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
        },
    )


@_register("Affiliations")
def _map_positions_affiliation(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_bilingual(record_el, "Position Title", lang)
    return MappedRow(
        category="positions",
        ccv_label="Affiliations",
        fields={
            "type": "affiliation",
            "title_en": title_en,
            "title_fr": title_fr,
            "organization": x.field_organization(record_el),
            "faculty": "",
            "department": x.field_text(record_el, "Department"),
            "position_status": "",
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
        },
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_import_ccv.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add parcours/core/import_ccv.py tests/unit/test_import_ccv.py
git commit -m "Added CCV field mapping for education, presentations, recognitions, teaching, press, positions"
```

---

## Task 4: Unify-with-type categories — service, outreach, students

**Files:**
- Modify: `parcours/core/import_ccv.py` (append mappers, extend `MAPPERS`)
- Test: `tests/unit/test_import_ccv.py` (append tests)

**Interfaces:**
- Consumes: `ImportContext`, `MappedRow`, `_register`, `x` (the `ccv_xml` module alias) from Task 3 — same file, same module-level names.
- Produces: five more `MAPPERS` entries (`"Graduate Examination Activities"`, `"Research Funding Application Assessment Activities"`, `"Community and Volunteer Activities"`, `"Committee Memberships"`, `"Program Development"`) for `service`, one (`"Knowledge and Technology Translation"`) for `outreach`, one (`"Student/Postdoctoral Supervision"`) for `students`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_import_ccv.py`:

```python
def test_map_service_graduate_examination():
    el = _record("""
    <section label="Graduate Examination Activities" recordId="s1">
      <field label="Graduate Examination Activity Role"><lov id="1">Thesis Defense Examiner</lov></field>
      <field label="Organization">
        <refTable refValueId="x" label="Organization">
          <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
        </refTable>
      </field>
      <field label="Start Date"><value type="YearMonth">2020/1</value></field>
      <field label="End Date"><value type="YearMonth">2020/1</value></field>
      <field label="Student Name"><value type="String">A Student</value></field>
    </section>
    """)
    row = map_record(el, "Graduate Examination Activities", "en", _ctx())
    assert row.category == "service"
    assert row.fields["type"] == "graduate-examination"
    assert row.fields["role"] == "Thesis Defense Examiner"
    assert row.fields["organization"] == "Test University"
    assert row.fields["detail"] == "A Student"
    assert row.fields["start_date"] == "2020-01"


def test_map_service_funding_review():
    el = _record("""
    <section label="Research Funding Application Assessment Activities" recordId="s2">
      <field label="Funding Reviewer Role"><lov id="1">External Reviewer</lov></field>
      <field label="Other Organization"><value type="String">Some Agency</value></field>
      <field label="Committee Name"><value type="String">Panel A</value></field>
      <field label="Start Date"><value type="YearMonth">2019/1</value></field>
    </section>
    """)
    row = map_record(el, "Research Funding Application Assessment Activities", "en", _ctx())
    assert row.fields["type"] == "funding-review"
    assert row.fields["role"] == "External Reviewer"
    assert row.fields["organization"] == "Some Agency"
    assert row.fields["detail"] == "Panel A"


def test_map_service_volunteer():
    el = _record("""
    <section label="Community and Volunteer Activities" recordId="s3">
      <field label="Role"><value type="String">Board Member</value></field>
      <field label="Other Organization"><value type="String">Local Charity</value></field>
      <field label="Start Date"><value type="YearMonth">2018/1</value></field>
      <field label="Activity Description">
        <value type="Bilingual"></value>
        <bilingual><french></french><english>Helped organize events</english></bilingual>
      </field>
    </section>
    """)
    row = map_record(el, "Community and Volunteer Activities", "en", _ctx())
    assert row.fields["type"] == "volunteer"
    assert row.fields["role"] == "Board Member"
    assert row.fields["detail"] == "Helped organize events"


def test_map_service_committee_membership():
    el = _record("""
    <section label="Committee Memberships" recordId="s4">
      <field label="Role"><lov id="1">Committee Member</lov></field>
      <field label="Committee Name"><value type="String">Hiring Committee</value></field>
      <field label="Other Organization"><value type="String">Test University</value></field>
      <field label="Membership Start Date"><value type="YearMonth">2021/1</value></field>
      <field label="Membership End Date"><value type="YearMonth">2022/1</value></field>
    </section>
    """)
    row = map_record(el, "Committee Memberships", "en", _ctx())
    assert row.fields["type"] == "committee"
    assert row.fields["role"] == "Committee Member"
    assert row.fields["detail"] == "Hiring Committee"
    assert row.fields["start_date"] == "2021-01"
    assert row.fields["end_date"] == "2022-01"


def test_map_service_program_development():
    el = _record("""
    <section label="Program Development" recordId="s5">
      <field label="Role"><value type="String">Chair</value></field>
      <field label="Other Organization"><value type="String">Test University</value></field>
      <field label="Program Title"><value type="String">New MFA Program</value></field>
      <field label="Program Description">
        <value type="Bilingual"></value>
        <bilingual><french></french><english>A revised curriculum</english></bilingual>
      </field>
      <field label="Date First Taught"><value type="YearMonth">2020/9</value></field>
    </section>
    """)
    row = map_record(el, "Program Development", "en", _ctx())
    assert row.category == "service"
    assert row.fields["type"] == "program-development"
    assert row.fields["start_date"] == "2020-09"
    assert row.fields["end_date"] == ""
    assert "New MFA Program" in row.fields["detail"]
    assert "A revised curriculum" in row.fields["detail"]


def test_map_outreach():
    el = _record("""
    <section label="Knowledge and Technology Translation" recordId="o1">
      <field label="Role"><value type="String">Consultant</value></field>
      <field label="Knowledge and Technology Translation Activity Type"><lov id="1">Consulting for Industry</lov></field>
      <field label="Group/Organization/Business Serviced"><value type="String">A Company</value></field>
      <field label="Target Stakeholder"><lov id="2">Industrial Association/Producer Group</lov></field>
      <field label="References / Citations / Web Sites"><value type="String">http://example.com</value></field>
      <field label="Start Date"><value type="YearMonth">2017/1</value></field>
      <field label="Activity Description">
        <value type="Bilingual"></value>
        <bilingual><french>Une activite</french><english>An activity</english></bilingual>
      </field>
    </section>
    """)
    row = map_record(el, "Knowledge and Technology Translation", "en", _ctx())
    assert row.category == "outreach"
    assert row.fields["activity_type"] == "industry-consulting"
    assert row.fields["target_stakeholder"] == "industry-association"
    assert row.fields["organization"] == "A Company"
    assert row.fields["role"] == "Consultant"
    assert row.fields["url"] == "http://example.com"
    assert row.fields["description_en"] == "An activity"
    assert row.fields["description_fr"] == "Une activite"


def test_map_students():
    el = _record("""
    <section label="Student/Postdoctoral Supervision" recordId="st1">
      <field label="Supervision Role"><lov id="1">Principal Supervisor</lov></field>
      <field label="Supervision Start Date"><value type="YearMonth">2019/9</value></field>
      <field label="Supervision End Date"><value type="YearMonth">2023/6</value></field>
      <field label="Student Name"><value type="String">A Student</value></field>
      <field label="Student Institution"><value type="String">Test University</value></field>
      <field label="Degree Type or Postdoctoral Status"><lov id="2">Doctorate</lov></field>
      <field label="Student Degree Status"><lov id="3">Completed</lov></field>
      <field label="Student Degree Start Date"><value type="YearMonth">2019/9</value></field>
      <field label="Student Degree Received Date"><value type="YearMonth">2023/6</value></field>
      <field label="Thesis/Project Title"><value type="String">A Dissertation</value></field>
      <field label="Present Position"><value type="String">Postdoc</value></field>
      <field label="Present Organization"><value type="String">Another University</value></field>
    </section>
    """)
    row = map_record(el, "Student/Postdoctoral Supervision", "en", _ctx())
    assert row.category == "students"
    assert row.fields["student_name"] == "A Student"
    assert row.fields["role"] == "principal-supervisor"
    assert row.fields["degree_type"] == "doctorate"
    assert row.fields["degree_status"] == "completed"
    assert row.fields["supervision_start_date"] == "2019-09"
    assert row.fields["supervision_end_date"] == "2023-06"
    assert row.fields["degree_start_date"] == "2019-09"
    assert row.fields["degree_end_date"] == "2023-06"
    assert row.fields["thesis_title"] == "A Dissertation"
    assert row.fields["present_position"] == "Postdoc"
    assert row.fields["present_organization"] == "Another University"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_import_ccv.py -v`
Expected: FAIL for the new tests (`KeyError` from `MAPPERS`).

- [ ] **Step 3: Append the mappers to `parcours/core/import_ccv.py`**

Add near the other translation dicts:

```python
_SUPERVISION_ROLE = {
    "Principal Supervisor": "principal-supervisor",
    "Co-Supervisor": "co-supervisor",
}

_OUTREACH_ACTIVITY_TYPE = {
    "Business Innovation": "business-innovation",
    "Community Engagement": "community-engagement",
    "Consulting for Industry": "industry-consulting",
    "Involvement in/Creation of Start-up": "startup-involvement",
    "Technology, Product, Process, Service Improvement/Development": "technology-improvement",
}

_OUTREACH_STAKEHOLDER = {
    "General Public": "general-public",
    "Industrial Association/Producer Group": "industry-association",
    "Industry/Business-Medium (100 to 500 employees)": "industry-business",
    "Private Not-for-Profit Organization": "private-nonprofit",
    "Utility": "utility",
}
```

Add the mapper functions:

```python
@_register("Graduate Examination Activities")
def _map_service_graduate_examination(record_el, lang, ctx) -> MappedRow:
    return MappedRow(
        category="service",
        ccv_label="Graduate Examination Activities",
        fields={
            "type": "graduate-examination",
            "role": x.field_lov(record_el, "Graduate Examination Activity Role"),
            "organization": x.field_organization(record_el),
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
            "detail": x.field_text(record_el, "Student Name"),
        },
    )


@_register("Research Funding Application Assessment Activities")
def _map_service_funding_review(record_el, lang, ctx) -> MappedRow:
    return MappedRow(
        category="service",
        ccv_label="Research Funding Application Assessment Activities",
        fields={
            "type": "funding-review",
            "role": x.field_lov(record_el, "Funding Reviewer Role"),
            "organization": x.field_organization(record_el),
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
            "detail": x.field_text(record_el, "Committee Name"),
        },
    )


@_register("Community and Volunteer Activities")
def _map_service_volunteer(record_el, lang, ctx) -> MappedRow:
    description_fr, description_en = x.field_bilingual(record_el, "Activity Description", lang)
    detail = description_en or description_fr
    return MappedRow(
        category="service",
        ccv_label="Community and Volunteer Activities",
        fields={
            "type": "volunteer",
            "role": x.field_text(record_el, "Role"),
            "organization": x.field_organization(record_el),
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
            "detail": detail,
        },
    )


@_register("Committee Memberships")
def _map_service_committee(record_el, lang, ctx) -> MappedRow:
    return MappedRow(
        category="service",
        ccv_label="Committee Memberships",
        fields={
            "type": "committee",
            "role": x.field_lov(record_el, "Role"),
            "organization": x.field_organization(record_el),
            "start_date": x.field_yearmonth(record_el, "Membership Start Date"),
            "end_date": x.field_yearmonth(record_el, "Membership End Date"),
            "detail": x.field_text(record_el, "Committee Name"),
        },
    )


@_register("Program Development")
def _map_service_program_development(record_el, lang, ctx) -> MappedRow:
    description_fr, description_en = x.field_bilingual(record_el, "Program Description", lang)
    program_title = x.field_text(record_el, "Program Title")
    description = description_en or description_fr
    detail = f"{program_title}: {description}" if description else program_title
    return MappedRow(
        category="service",
        ccv_label="Program Development",
        fields={
            "type": "program-development",
            "role": x.field_text(record_el, "Role"),
            "organization": x.field_organization(record_el),
            "start_date": x.field_yearmonth(record_el, "Date First Taught"),
            "end_date": "",
            "detail": detail,
        },
    )


@_register("Knowledge and Technology Translation")
def _map_outreach(record_el, lang, ctx) -> MappedRow:
    description_fr, description_en = x.field_bilingual(record_el, "Activity Description", lang)
    return MappedRow(
        category="outreach",
        ccv_label="Knowledge and Technology Translation",
        fields={
            "activity_type": _OUTREACH_ACTIVITY_TYPE.get(
                x.field_lov(record_el, "Knowledge and Technology Translation Activity Type"), ""
            ),
            "target_stakeholder": _OUTREACH_STAKEHOLDER.get(x.field_lov(record_el, "Target Stakeholder"), ""),
            "organization": x.field_text(record_el, "Group/Organization/Business Serviced"),
            "role": x.field_text(record_el, "Role"),
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
            "description_en": description_en,
            "description_fr": description_fr,
            "url": x.field_text(record_el, "References / Citations / Web Sites"),
        },
    )


@_register("Student/Postdoctoral Supervision")
def _map_students(record_el, lang, ctx) -> MappedRow:
    degree_type_raw = _normalize_apostrophe(x.field_lov(record_el, "Degree Type or Postdoctoral Status"))
    degree_status_raw = x.field_lov(record_el, "Student Degree Status")
    return MappedRow(
        category="students",
        ccv_label="Student/Postdoctoral Supervision",
        fields={
            "student_name": x.field_text(record_el, "Student Name"),
            "role": _SUPERVISION_ROLE.get(x.field_lov(record_el, "Supervision Role"), ""),
            "institution": x.field_text(record_el, "Student Institution"),
            "degree_type": _DEGREE_TYPE.get(degree_type_raw, ""),
            "degree_status": _DEGREE_STATUS.get(degree_status_raw, ""),
            "supervision_start_date": x.field_yearmonth(record_el, "Supervision Start Date"),
            "supervision_end_date": x.field_yearmonth(record_el, "Supervision End Date"),
            "degree_start_date": x.field_yearmonth(record_el, "Student Degree Start Date"),
            "degree_end_date": x.field_yearmonth(record_el, "Student Degree Received Date"),
            "thesis_title": x.field_text(record_el, "Thesis/Project Title"),
            "present_position": x.field_text(record_el, "Present Position"),
            "present_organization": x.field_text(record_el, "Present Organization"),
        },
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_import_ccv.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add parcours/core/import_ccv.py tests/unit/test_import_ccv.py
git commit -m "Added CCV field mapping for service, outreach, students"
```

---

## Task 5: Artistic Contributions split — artworks, exhibitions

**Files:**
- Modify: `parcours/core/import_ccv.py`
- Test: `tests/unit/test_import_ccv.py` (append)

**Interfaces:**
- Consumes: same shared scaffolding as Tasks 3-4, plus `ctx.own_name: tuple[str, str]` (last, first) for self-filtering `Contributors`.
- Produces: `MAPPERS["Visual Artworks"]`, `MAPPERS["Audio Recordings"]`, `MAPPERS["Artistic Exhibitions"]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_import_ccv.py`:

```python
def test_map_visual_artwork_contributors_parses_and_filters_self():
    el = _record("""
    <section label="Visual Artworks" recordId="a1">
      <field label="Artwork Title"><value type="String">Untitled</value></field>
      <field label="Publication Date"><value type="YearMonth">2020/3</value></field>
      <field label="Description / Contribution Value">
        <value type="Bilingual"></value>
        <bilingual><french></french><english>A description</english></bilingual>
      </field>
      <field label="URL"><value type="String">http://example.com</value></field>
      <field label="Contribution Role"><value type="String">Artist</value></field>
      <field label="Contributors"><value type="String">Doe, Jane; Smith, John</value></field>
    </section>
    """)
    row = map_record(el, "Visual Artworks", "en", _ctx())
    assert row.category == "artworks"
    assert row.fields["title_en"] == "Untitled"
    assert row.fields["date"] == "2020"
    assert row.fields["role"] == "author"
    assert row.fields["co_authors"] == "Smith, John"
    assert row.fields["collaborators"] == ""
    assert row.flag is None


def test_map_visual_artwork_flags_unparseable_contributors():
    el = _record("""
    <section label="Visual Artworks" recordId="a2">
      <field label="Artwork Title"><value type="String">Another Piece</value></field>
      <field label="Publication Date"><value type="YearMonth">2019/1</value></field>
      <field label="Contribution Role"><value type="String">Collaborator</value></field>
      <field label="Contributors"><value type="String">John Smith and Jane Doe</value></field>
    </section>
    """)
    row = map_record(el, "Visual Artworks", "en", _ctx())
    assert row.fields["role"] == "collaborator"
    assert row.fields["co_authors"] == ""
    assert row.flag is not None


def test_map_visual_artwork_unrecognized_role_defaults_to_author():
    el = _record("""
    <section label="Visual Artworks" recordId="a3">
      <field label="Artwork Title"><value type="String">A Piece</value></field>
      <field label="Publication Date"><value type="YearMonth">2018/1</value></field>
    </section>
    """)
    row = map_record(el, "Visual Artworks", "en", _ctx())
    assert row.fields["role"] == "author"


def test_map_audio_recording_uses_piece_title_and_release_date_year():
    el = _record("""
    <section label="Audio Recordings" recordId="a4">
      <field label="Piece Title"><value type="String">A Track</value></field>
      <field label="Release Date"><value type="Date">2017-06-01</value></field>
    </section>
    """)
    row = map_record(el, "Audio Recordings", "en", _ctx())
    assert row.category == "artworks"
    assert row.fields["title_en"] == "A Track"
    assert row.fields["date"] == "2017"


def test_map_artistic_exhibition():
    el = _record("""
    <section label="Artistic Exhibitions" recordId="e1">
      <field label="Title of Work"><value type="String">A Show</value></field>
      <field label="Venue"><value type="String">A Gallery</value></field>
      <field label="Date of First Performance"><value type="Date">2021-04-10</value></field>
    </section>
    """)
    row = map_record(el, "Artistic Exhibitions", "en", _ctx())
    assert row.category == "exhibitions"
    assert row.fields["title_en"] == "A Show"
    assert row.fields["venue"] == "A Gallery"
    assert row.fields["start_date"] == "2021-04-10"
    assert row.fields["event"] == ""
    assert row.fields["location"] == ""
    assert row.fields["curator"] == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_import_ccv.py -v`
Expected: FAIL for the new tests.

- [ ] **Step 3: Append to `parcours/core/import_ccv.py`**

```python
_ARTWORK_ROLE = {
    "Author": "author",
    "Auteur": "author",
    "Artist": "author",
    "Principal investigator": "author",
    "Collaborator": "collaborator",
    "Artist collaborator": "collaborator",
}


def _remove_self_from_contributors(raw: str, own_name: tuple[str, str]) -> str:
    """`own_name` is (last, first). Removes an exact 'Last, First' match
    (whitespace-normalized) before the parse-as-validation-gate runs —
    `co_authors` never includes you (see SPECS.md, `artworks` notes)."""
    if not raw:
        return raw
    own_last, own_first = own_name
    own_formatted = f"{own_last}, {own_first}".strip().lower()
    remaining = [
        chunk for chunk in (part.strip() for part in raw.split(";"))
        if chunk and chunk.lower() != own_formatted
    ]
    return "; ".join(remaining)


def _map_artwork_common(record_el, lang, ctx, title_label: str, date_field, date_label: str, ccv_label: str) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, title_label, lang)
    description_fr, description_en = x.field_bilingual(record_el, "Description / Contribution Value", lang)
    role_raw = x.field_text(record_el, "Contribution Role")

    raw_contributors = x.field_text(record_el, "Contributors")
    filtered_contributors = _remove_self_from_contributors(raw_contributors, ctx.own_name)
    co_authors = x.try_person_list(filtered_contributors)
    flag = None
    if filtered_contributors and co_authors is None:
        flag = f"co_authors could not be parsed as 'Last, First' from CCV's raw Contributors value: {raw_contributors!r}"

    return MappedRow(
        category="artworks",
        ccv_label=ccv_label,
        fields={
            "title_en": title_en,
            "title_fr": title_fr,
            "role": _ARTWORK_ROLE.get(role_raw, "author"),
            "date": date_field(record_el, date_label)[:4],
            "description_en": description_en,
            "description_fr": description_fr,
            "co_authors": co_authors or "",
            "collaborators": "",
            "url": x.field_text(record_el, "URL"),
        },
        flag=flag,
    )


@_register("Visual Artworks")
def _map_visual_artwork(record_el, lang, ctx) -> MappedRow:
    return _map_artwork_common(record_el, lang, ctx, "Artwork Title", x.field_yearmonth, "Publication Date", "Visual Artworks")


@_register("Audio Recordings")
def _map_audio_recording(record_el, lang, ctx) -> MappedRow:
    return _map_artwork_common(record_el, lang, ctx, "Piece Title", x.field_date, "Release Date", "Audio Recordings")


@_register("Artistic Exhibitions")
def _map_exhibition(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, "Title of Work", lang)
    return MappedRow(
        category="exhibitions",
        ccv_label="Artistic Exhibitions",
        fields={
            "title_en": title_en,
            "title_fr": title_fr,
            "event": "",
            "venue": x.field_text(record_el, "Venue"),
            "location": "",
            "curator": "",
            "start_date": x.field_date(record_el, "Date of First Performance"),
            "end_date": "",
        },
    )
```

Note the `date_field(record_el, date_label)[:4]` truncation for `artworks.date` (`precision: year`): both `field_yearmonth` (`"yyyy-MM"`) and `field_date` (`"yyyy-MM-dd"`) put the 4-digit year first, so slicing the first 4 characters works for both without a type-specific branch — verified this is correct for both wire shapes (YearMonth for Visual Artworks' `Publication Date`, Date for Audio Recordings' `Release Date`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_import_ccv.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add parcours/core/import_ccv.py tests/unit/test_import_ccv.py
git commit -m "Added CCV field mapping for artworks and exhibitions"
```

---

## Task 6: grants (Research Funding History + Funding Sources + Other Investigators)

**Files:**
- Modify: `parcours/core/import_ccv.py`
- Test: `tests/unit/test_import_ccv.py` (append)

**Interfaces:**
- Produces: `MAPPERS["Research Funding History"]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_import_ccv.py`:

```python
def test_map_grant_single_funding_source():
    el = _record("""
    <section label="Research Funding History" recordId="g1">
      <field label="Funding Title"><value type="String">A Grant</value></field>
      <field label="Funding Role"><lov id="1">Principal Investigator</lov></field>
      <field label="Funding Status"><lov id="2">Awarded</lov></field>
      <field label="Funding Start Date"><value type="YearMonth">2021/4</value></field>
      <field label="Funding End Date"><value type="YearMonth">2024/3</value></field>
      <field label="Project Description">
        <value type="Bilingual"></value>
        <bilingual><french></french><english>A project</english></bilingual>
      </field>
      <field label="Research Uptake">
        <value type="Bilingual"></value>
        <bilingual><french></french><english>Some uptake</english></bilingual>
      </field>
      <section label="Funding Sources" recordId="g1f1">
        <field label="Funding Organization"><lov id="3">Test Funder</lov></field>
        <field label="Program Name"><value type="String">Test Program</value></field>
        <field label="Total Funding"><value type="Number">50000</value></field>
        <field label="Currency of Total Funding"><lov id="4">CAD</lov></field>
      </section>
    </section>
    """)
    row = map_record(el, "Research Funding History", "en", _ctx())
    assert row.category == "grants"
    assert row.fields["title_en"] == "A Grant"
    assert row.fields["funder"] == "Test Funder"
    assert row.fields["program"] == "Test Program"
    assert row.fields["role"] == "pi"
    assert row.fields["status"] == "awarded"
    assert row.fields["start_date"] == "2021-04"
    assert row.fields["end_date"] == "2024-03"
    assert row.fields["amount"] == "50000"
    assert row.fields["currency"] == "CAD"
    assert "A project" in row.fields["note_en"]
    assert "Some uptake" in row.fields["note_en"]
    assert row.fields["co_investigators"] == ""
    assert row.flag is None


def test_map_grant_completed_status_collapses_to_awarded():
    el = _record("""
    <section label="Research Funding History" recordId="g2">
      <field label="Funding Title"><value type="String">Another Grant</value></field>
      <field label="Funding Role"><lov id="1">Co-investigator</lov></field>
      <field label="Funding Status"><lov id="2">Completed</lov></field>
      <field label="Funding Start Date"><value type="YearMonth">2015/1</value></field>
    </section>
    """)
    row = map_record(el, "Research Funding History", "en", _ctx())
    assert row.fields["role"] == "co-pi"
    assert row.fields["status"] == "awarded"


def test_map_grant_flags_multiple_funding_sources():
    el = _record("""
    <section label="Research Funding History" recordId="g3">
      <field label="Funding Title"><value type="String">Multi-source Grant</value></field>
      <field label="Funding Start Date"><value type="YearMonth">2016/1</value></field>
      <section label="Funding Sources" recordId="g3f1">
        <field label="Funding Organization"><lov id="1">Funder A</lov></field>
        <field label="Total Funding"><value type="Number">10000</value></field>
      </section>
      <section label="Funding Sources" recordId="g3f2">
        <field label="Funding Organization"><lov id="2">Funder B</lov></field>
        <field label="Total Funding"><value type="Number">5000</value></field>
      </section>
    </section>
    """)
    row = map_record(el, "Research Funding History", "en", _ctx())
    assert row.fields["funder"] == "Funder A"
    assert row.fields["amount"] == "10000"
    assert row.flag is not None
    assert "Funding Sources" in row.flag


def test_map_grant_flags_other_investigators_unparseable():
    el = _record("""
    <section label="Research Funding History" recordId="g4">
      <field label="Funding Title"><value type="String">Team Grant</value></field>
      <field label="Funding Start Date"><value type="YearMonth">2017/1</value></field>
      <section label="Other Investigators" recordId="g4i1">
        <field label="Investigator Name"><value type="String">Jane Smith</value></field>
      </section>
      <section label="Other Investigators" recordId="g4i2">
        <field label="Investigator Name"><value type="String">John Doe</value></field>
      </section>
    </section>
    """)
    row = map_record(el, "Research Funding History", "en", _ctx())
    assert row.fields["co_investigators"] == ""
    assert row.flag is not None
    assert "co_investigators" in row.flag
    assert "Jane Smith" in row.flag
    assert "John Doe" in row.flag
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_import_ccv.py -v`
Expected: FAIL for the new tests.

- [ ] **Step 3: Append to `parcours/core/import_ccv.py`**

```python
_GRANT_ROLE = {
    "Principal Applicant": "pi",
    "Principal Investigator": "pi",
    "Co-applicant": "co-pi",
    "Co-investigator": "co-pi",
    "Collaborator": "collaborator",
}

_GRANT_STATUS = {
    "Awarded": "awarded",
    "Completed": "awarded",
    "Declined": "declined",
}


@_register("Research Funding History")
def _map_grant(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, "Funding Title", lang)
    project_description_fr, project_description_en = x.field_bilingual(record_el, "Project Description", lang)
    research_uptake_fr, research_uptake_en = x.field_bilingual(record_el, "Research Uptake", lang)
    note_en = "\n\n".join(part for part in (project_description_en, research_uptake_en) if part)
    note_fr = "\n\n".join(part for part in (project_description_fr, research_uptake_fr) if part)

    funding_sources = x.sub_records(record_el, "Funding Sources")
    flags = []
    funder = program = amount = currency = ""
    if funding_sources:
        first_source = funding_sources[0]
        funder = x.field_lov(first_source, "Funding Organization") or x.field_text(first_source, "Other Funding Organization")
        program = x.field_text(first_source, "Program Name")
        amount = x.field_text(first_source, "Total Funding")
        currency = x.field_lov(first_source, "Currency of Total Funding")
        if len(funding_sources) > 1:
            flags.append(
                f"{len(funding_sources)} Funding Sources found for this grant — "
                f"using the first ({funder!r}); the rest need manual review"
            )

    other_investigators = x.sub_records(record_el, "Other Investigators")
    co_investigators = ""
    if other_investigators:
        names = [x.field_text(inv, "Investigator Name") for inv in other_investigators]
        names = [n for n in names if n]
        joined = "; ".join(names)
        parsed = x.try_person_list(joined)
        if parsed:
            co_investigators = parsed
        else:
            flags.append(
                f"co_investigators needs manual entry — CCV gives unsplit investigator name(s): {', '.join(names)}"
            )

    return MappedRow(
        category="grants",
        ccv_label="Research Funding History",
        fields={
            "title_en": title_en,
            "title_fr": title_fr,
            "funder": funder,
            "program": program,
            "role": _GRANT_ROLE.get(x.field_lov(record_el, "Funding Role"), ""),
            "status": _GRANT_STATUS.get(x.field_lov(record_el, "Funding Status"), ""),
            "start_date": x.field_yearmonth(record_el, "Funding Start Date"),
            "end_date": x.field_yearmonth(record_el, "Funding End Date"),
            "amount": amount,
            "currency": currency or ctx.default_currency,
            "co_investigators": co_investigators,
            "note_en": note_en,
            "note_fr": note_fr,
        },
        flag="; ".join(flags) or None,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_import_ccv.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add parcours/core/import_ccv.py tests/unit/test_import_ccv.py
git commit -m "Added CCV field mapping for grants"
```

---

## Task 7: Zotero-match for publications and catalog

**Files:**
- Modify: `parcours/core/handlers/publications.py` (add `match_citekey_by_title`)
- Modify: `parcours/core/import_ccv.py` (add title/year extraction for Zotero-matched categories)
- Test: `tests/unit/test_handler_publications.py` (append), `tests/unit/test_import_ccv.py` (append)

**Interfaces:**
- Produces: `PublicationsHandler.match_citekey_by_title(title: str, year: int | None) -> str | None` (returns the citekey on exactly one confident fuzzy-title[+year] match, else `None`). `core/import_ccv.py::extract_zotero_candidate(record_el, label, lang) -> ZoteroCandidate` (dataclass: `title: str`, `year: int | None`, `ccv_label: str`) for each of the 9 CCV record types that need Zotero matching instead of direct field mapping — these are **not** added to `MAPPERS`, since they don't produce a `MappedRow` directly (Task 8's orchestration calls `extract_zotero_candidate` for these specific labels, then calls the handler's match method).

- [ ] **Step 1: Write the failing test for `match_citekey_by_title`**

`tests/unit/test_handler_publications.py` already has `_write_csl_json(tmp_path, records) -> json_rel_path` and `_schema(json_rel_path) -> CategorySchema` helpers at its top — reuse both unchanged (do not invent a new fixture pattern). Append:

```python
def test_match_citekey_by_title_returns_confident_match(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "smith2020widget", "title": "A Widget Study", "issued": {"date-parts": [[2020]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    citekey = handler.match_citekey_by_title("A Widget Study", 2020)

    assert citekey == "smith2020widget"


def test_match_citekey_by_title_returns_none_when_no_match(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "smith2020widget", "title": "A Widget Study", "issued": {"date-parts": [[2020]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    citekey = handler.match_citekey_by_title("Completely Unrelated Title", 2020)

    assert citekey is None


def test_match_citekey_by_title_rejects_a_year_mismatch(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "smith2020widget", "title": "A Widget Study", "issued": {"date-parts": [[2020]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    citekey = handler.match_citekey_by_title("A Widget Study", 2019)

    assert citekey is None


def test_match_citekey_by_title_returns_none_when_ambiguous(tmp_path):
    json_path = _write_csl_json(tmp_path, [
        {"id": "smith2020widget", "title": "A Widget Study", "issued": {"date-parts": [[2020]]}},
        {"id": "jones2020widget", "title": "A Widget Study II", "issued": {"date-parts": [[2020]]}},
    ])
    handler = PublicationsHandler(_schema(json_path), HandlerContext(data_dir=tmp_path))

    citekey = handler.match_citekey_by_title("A Widget Study", 2020)

    assert citekey is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_handler_publications.py -k match_citekey -v`
Expected: FAIL (`AttributeError: 'PublicationsHandler' object has no attribute 'match_citekey_by_title'`).

- [ ] **Step 3: Add the method to `parcours/core/handlers/publications.py`**

Add this method to the `PublicationsHandler` class (anywhere after `resolve`):

```python
    def match_citekey_by_title(self, title: str, year: int | None) -> str | None:
        """Fuzzy-title(+year) match against the loaded CSL-JSON export —
        used by the CCV importer to resolve a citekey for a record CCV
        never gives one for (see SPECS.md, "Import"). Returns the
        citekey on exactly one confident match, None on no match or an
        ambiguous (more than one) match."""
        candidates = []
        for citekey, record in self._csl_by_key.items():
            if not fuzzy_match(title, record.get("title", "")):
                continue
            record_year = _csl_year(record)
            if year is not None and record_year is not None and record_year != year:
                continue
            candidates.append(citekey)
        if len(candidates) == 1:
            return candidates[0]
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_handler_publications.py -k match_citekey -v`
Expected: PASS.

- [ ] **Step 5: Write the failing tests for `extract_zotero_candidate`**

Append to `tests/unit/test_import_ccv.py`:

```python
from parcours.core.import_ccv import extract_zotero_candidate


def test_extract_zotero_candidate_journal_article():
    el = _record("""
    <section label="Journal Articles" recordId="p1">
      <field label="Article Title"><value type="String">A Widget Study</value></field>
      <field label="Year"><value type="Year">2020</value></field>
    </section>
    """)
    candidate = extract_zotero_candidate(el, "Journal Articles", "en")
    assert candidate.title == "A Widget Study"
    assert candidate.year == 2020
    assert candidate.ccv_label == "Journal Articles"


def test_extract_zotero_candidate_book():
    el = _record('<section label="Books" recordId="p2">'
                 '<field label="Book Title"><value type="String">A Book</value></field>'
                 '<field label="Year"><value type="Year">2018</value></field>'
                 '</section>')
    candidate = extract_zotero_candidate(el, "Books", "en")
    assert candidate.title == "A Book"
    assert candidate.year == 2018


def test_extract_zotero_candidate_thesis_uses_completion_year():
    el = _record('<section label="Thesis/Dissertation" recordId="p3">'
                 '<field label="Dissertation Title"><value type="String">A Thesis</value></field>'
                 '<field label="Completion Year"><value type="Year">2015</value></field>'
                 '</section>')
    candidate = extract_zotero_candidate(el, "Thesis/Dissertation", "en")
    assert candidate.title == "A Thesis"
    assert candidate.year == 2015


def test_extract_zotero_candidate_exhibition_catalogue_uses_yearmonth():
    el = _record('<section label="Exhibition Catalogues" recordId="p4">'
                 '<field label="Catalogue Title"><value type="String">A Catalogue</value></field>'
                 '<field label="Publication Date"><value type="YearMonth">2019/6</value></field>'
                 '</section>')
    candidate = extract_zotero_candidate(el, "Exhibition Catalogues", "en")
    assert candidate.title == "A Catalogue"
    assert candidate.year == 2019


def test_extract_zotero_candidate_blank_year_is_none():
    el = _record('<section label="Online Resources" recordId="p5">'
                 '<field label="Title"><value type="String">A Resource</value></field>'
                 '</section>')
    candidate = extract_zotero_candidate(el, "Online Resources", "en")
    assert candidate.year is None
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `pytest tests/unit/test_import_ccv.py -k zotero_candidate -v`
Expected: FAIL (`extract_zotero_candidate` doesn't exist).

- [ ] **Step 7: Append to `parcours/core/import_ccv.py`**

```python
@dataclass
class ZoteroCandidate:
    title: str
    year: int | None
    ccv_label: str


_ZOTERO_CANDIDATE_FIELDS = {
    "Journal Articles": ("Article Title", x.field_year, "Year"),
    "Books": ("Book Title", x.field_year, "Year"),
    "Book Chapters": ("Chapter Title", x.field_year, "Year"),
    "Thesis/Dissertation": ("Dissertation Title", x.field_year, "Completion Year"),
    "Magazine Entries": ("Article Title", x.field_year, "Year"),
    "Reports": ("Report Title", x.field_year, "Year Submitted"),
    "Online Resources": ("Title", x.field_year, "Year posted online"),
    "Conference Publications": ("Publication Title", x.field_year, "Year"),
    "Exhibition Catalogues": ("Catalogue Title", x.field_yearmonth, "Publication Date"),
}

ZOTERO_MATCHED_LABELS = frozenset(_ZOTERO_CANDIDATE_FIELDS)


def extract_zotero_candidate(record_el, label: str, lang: str) -> ZoteroCandidate:
    title_field, year_fn, year_label = _ZOTERO_CANDIDATE_FIELDS[label]
    title_fr, title_en = x.field_single_language(record_el, title_field, lang)
    title = title_en or title_fr
    raw_year = year_fn(record_el, year_label)
    year = int(raw_year[:4]) if raw_year else None
    return ZoteroCandidate(title=title, year=year, ccv_label=label)
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `pytest tests/unit/test_import_ccv.py -k zotero_candidate -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add parcours/core/handlers/publications.py parcours/core/import_ccv.py tests/unit/test_handler_publications.py tests/unit/test_import_ccv.py
git commit -m "Added Zotero fuzzy-title-match citekey resolution for CCV publications/catalog import"
```

---

## Task 8: Orchestration — dedup integration, plan_import, write_import

**Files:**
- Modify: `parcours/core/import_ccv.py`
- Test: `tests/unit/test_import_ccv.py` (append)

**Interfaces:**
- Consumes: `MAPPERS`, `ZOTERO_MATCHED_LABELS`, `extract_zotero_candidate`, `map_record`, `MappedRow`, `FlaggedRecord`, `ImportContext` from Tasks 3-7. `core/ccv_xml.py::parse_ccv_export`/`find_records`. `core/schema.py::load_all_schemas`. `core/data.py::load_category_rows`. `core/handlers::load_handler`, `HandlerContext`. `core/entries.py::generate_id`, `write_all_rows`.
- Produces:
  - `SUB_RECORD_LABELS: frozenset[str]` — labels that are never dispatched standalone (consumed by their parent's own mapper): `{"Supervisors", "Funding Sources", "Other Investigators", "Areas of Research", "Research Disciplines", "Fields of Application", "Disciplines Trained In", "Research Specialization Keywords", "Student Country of Citizenship", "Project Funding Sources"}`.
  - `ImportReport` dataclass: `to_write: list[MappedRow]`, `flagged: list[FlaggedRecord]`, `skipped_labels: dict[str, int]` (unmapped CCV label → count), `dedup_matches: dict[int, list]` (index into `to_write` → list of `Match` from the category handler, for rows with a `duplicate`/`related` hit — these still get written, per SPECS.md: dedup is a soft flag here exactly like everywhere else in this codebase, never a hard block).
  - `plan_import(data_dir: Path, xml_path: Path) -> ImportReport` — no writes, no prompts.
  - `write_import(data_dir: Path, report: ImportReport) -> list[str]` — writes every `report.to_write` row to its category CSV (grouped by category, one `write_all_rows` call per touched category), returns the list of touched category CSV filenames. **Never commits.**

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_import_ccv.py`:

```python
import textwrap

from parcours.core.import_ccv import ImportReport, plan_import, write_import
from parcours.core.schema import CategorySchema, FieldSpec


def _minimal_data_dir(tmp_path):
    (tmp_path / "categories").mkdir()
    education_schema = tmp_path / "categories" / "education.yaml"
    education_schema.write_text(textwrap.dedent("""
        name: education
        handler: generic
        fields:
          - {name: id, generated: true}
          - {name: degree_type, required: true}
          - {name: degree_name_en}
          - {name: degree_name_fr}
          - {name: specialization_en}
          - {name: specialization_fr}
          - {name: organization, required: true}
          - {name: degree_status, required: true}
          - {name: start_date, type: date, precision: month, required: true}
          - {name: end_date, type: date, precision: month}
          - {name: thesis_title}
          - {name: advisor}
          - {name: note_en}
          - {name: note_fr}
        dedup:
          - when: [{exact: organization}, {exact: degree_type}, {same_year: start_date}]
            as: duplicate
    """), encoding="utf-8")
    (tmp_path / "education.csv").write_text(
        "id,degree_type,degree_name_en,degree_name_fr,specialization_en,specialization_fr,"
        "organization,degree_status,start_date,end_date,thesis_title,advisor,note_en,note_fr\n",
        encoding="utf-8",
    )
    identity = tmp_path / "identity.yaml"
    identity.write_text("name:\n  first: Jane\n  last: Doe\n", encoding="utf-8")
    parco_yaml = tmp_path / "parco.yaml"
    parco_yaml.write_text("currency:\n  default: CAD\n  report: CAD\n", encoding="utf-8")
    return tmp_path


def _write_xml(tmp_path, xml: str):
    path = tmp_path / "export.xml"
    path.write_text(xml, encoding="utf-8")
    return path


def test_plan_import_maps_a_known_record():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        data_dir = _minimal_data_dir(Path(d))
        xml_path = _write_xml(data_dir, """<?xml version="1.0"?>
        <generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
          <section label="Education">
            <section label="Degrees" recordId="r1">
              <field label="Degree Type"><lov id="1">Doctorate</lov></field>
              <field label="Organization">
                <refTable refValueId="x" label="Organization">
                  <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
                </refTable>
              </field>
              <field label="Degree Status"><lov id="2">Completed</lov></field>
              <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
            </section>
          </section>
        </generic-cv:generic-cv>
        """)
        report = plan_import(data_dir, xml_path)
        assert isinstance(report, ImportReport)
        assert len(report.to_write) == 1
        assert report.to_write[0].category == "education"
        assert report.to_write[0].fields["organization"] == "Test University"


def test_plan_import_ignores_known_sub_records_without_reporting_them_skipped():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        data_dir = _minimal_data_dir(Path(d))
        xml_path = _write_xml(data_dir, """<?xml version="1.0"?>
        <generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
          <section label="Education">
            <section label="Degrees" recordId="r1">
              <field label="Degree Type"><lov id="1">Doctorate</lov></field>
              <field label="Degree Status"><lov id="2">Completed</lov></field>
              <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
              <section label="Supervisors" recordId="r1s1">
                <field label="Supervisor Name"><value type="String">Jane Smith</value></field>
              </section>
            </section>
          </section>
        </generic-cv:generic-cv>
        """)
        report = plan_import(data_dir, xml_path)
        assert "Supervisors" not in report.skipped_labels


def test_plan_import_reports_genuinely_unmapped_records_as_skipped():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        data_dir = _minimal_data_dir(Path(d))
        xml_path = _write_xml(data_dir, """<?xml version="1.0"?>
        <generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
          <section label="Personal Information">
            <section label="Address" recordId="addr1">
              <field label="City"><value type="String">Somewhere</value></field>
            </section>
          </section>
        </generic-cv:generic-cv>
        """)
        report = plan_import(data_dir, xml_path)
        assert report.skipped_labels.get("Address") == 1


def test_plan_import_flags_dedup_duplicate_but_still_writes_it():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        data_dir = _minimal_data_dir(Path(d))
        # Seed an existing row that will collide via the dedup rule
        # (exact organization, exact degree_type, same_year start_date).
        (data_dir / "education.csv").write_text(
            "id,degree_type,degree_name_en,degree_name_fr,specialization_en,specialization_fr,"
            "organization,degree_status,start_date,end_date,thesis_title,advisor,note_en,note_fr\n"
            "exist1,doctorate,,,,,Test University,completed,2018-09,,,,,\n",
            encoding="utf-8",
        )
        xml_path = _write_xml(data_dir, """<?xml version="1.0"?>
        <generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
          <section label="Education">
            <section label="Degrees" recordId="r1">
              <field label="Degree Type"><lov id="1">Doctorate</lov></field>
              <field label="Organization">
                <refTable refValueId="x" label="Organization">
                  <linkedWith label="Organization" value="Test University" refOrLovId="z"/>
                </refTable>
              </field>
              <field label="Degree Status"><lov id="2">Completed</lov></field>
              <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
            </section>
          </section>
        </generic-cv:generic-cv>
        """)
        report = plan_import(data_dir, xml_path)
        assert len(report.to_write) == 1
        assert 0 in report.dedup_matches
        assert report.dedup_matches[0][0].kind == "duplicate"


def test_write_import_writes_rows_and_never_commits():
    import subprocess
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        data_dir = _minimal_data_dir(Path(d))
        subprocess.run(["git", "init"], cwd=data_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=data_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=data_dir, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=data_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=data_dir, check=True, capture_output=True)

        xml_path = _write_xml(data_dir, """<?xml version="1.0"?>
        <generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
          <section label="Education">
            <section label="Degrees" recordId="r1">
              <field label="Degree Type"><lov id="1">Doctorate</lov></field>
              <field label="Degree Status"><lov id="2">Completed</lov></field>
              <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
            </section>
          </section>
        </generic-cv:generic-cv>
        """)
        report = plan_import(data_dir, xml_path)
        touched = write_import(data_dir, report)

        assert touched == ["education.csv"]
        content = (data_dir / "education.csv").read_text(encoding="utf-8")
        assert "doctorate" in content

        status = subprocess.run(["git", "status", "--porcelain"], cwd=data_dir, check=True, capture_output=True, text=True)
        assert "education.csv" in status.stdout  # uncommitted
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_import_ccv.py -k "plan_import or write_import" -v`
Expected: FAIL (`plan_import`/`write_import`/`ImportReport` don't exist).

- [ ] **Step 3: Append the orchestration to `parcours/core/import_ccv.py`**

Add the imports at the top of the file:

```python
from pathlib import Path

from .data import load_category_rows
from .entries import generate_id, write_all_rows
from .handlers import load_handler
from .handlers.base import HandlerContext
from .identity import load_identity
from .repo import load_repo_config
from .schema import load_all_schemas
```

Add near `MAPPERS`:

```python
SUB_RECORD_LABELS = frozenset({
    "Supervisors", "Funding Sources", "Other Investigators",
    "Areas of Research", "Research Disciplines", "Fields of Application",
    "Disciplines Trained In", "Research Specialization Keywords",
    "Student Country of Citizenship", "Project Funding Sources",
})


@dataclass
class ImportReport:
    to_write: list[MappedRow] = field(default_factory=list)
    flagged: list[FlaggedRecord] = field(default_factory=list)
    skipped_labels: dict[str, int] = field(default_factory=dict)
    dedup_matches: dict[int, list] = field(default_factory=dict)
```

Add the orchestration functions at the end of the file. **Note before writing `write_import`**: `generate_id` (from `core/entries.py`) determines a new id by reading the category's CSV *on disk* — so if two new rows in the same category were both generated before either was written, they could theoretically collide. `write_import` below avoids this by writing each row's CSV immediately after generating its id (re-reading the CSV once per new row), the same read-then-write-immediately pattern `add_entry` already uses — never batch-generate ids across multiple rows before writing.

```python
def plan_import(data_dir: Path, xml_path: Path) -> ImportReport:
    root, lang = x.parse_ccv_export(xml_path)
    records = x.find_records(root)

    identity = load_identity(data_dir / "identity.yaml")
    own_name = (identity["name"]["last"], identity["name"]["first"])
    repo_config = load_repo_config(data_dir)
    default_currency = repo_config.get("currency", {}).get("default", "")
    ctx = ImportContext(default_currency=default_currency, own_name=own_name)

    schemas = load_all_schemas(data_dir / "categories")
    handlers = {
        name: load_handler(schema, HandlerContext(data_dir=data_dir))
        for name, schema in schemas.items()
    }
    existing_rows_by_category = {
        name: load_category_rows(data_dir, name) for name in schemas
    }

    report = ImportReport()

    for record in records:
        label = record.label
        if label in SUB_RECORD_LABELS:
            continue

        if label in ZOTERO_MATCHED_LABELS:
            candidate = extract_zotero_candidate(record.element, label, lang)
            category = "catalog" if label == "Exhibition Catalogues" else "publications"
            handler = handlers.get(category)
            citekey = handler.match_citekey_by_title(candidate.title, candidate.year) if handler else None
            if citekey is None:
                report.flagged.append(FlaggedRecord(
                    ccv_label=label,
                    reason=f"No confident Zotero match for {candidate.title!r} ({candidate.year}) — needs a citekey",
                ))
                continue
            schema = schemas[category]
            row_id = generate_id(data_dir, category)
            mapped = MappedRow(
                category=category,
                ccv_label=label,
                fields={name: "" for name in schema.field_names() if name != "id"} | {"citekey": citekey},
            )
        elif label in MAPPERS:
            mapped = map_record(record.element, label, lang, ctx)
        else:
            report.skipped_labels[label] = report.skipped_labels.get(label, 0) + 1
            continue

        if mapped.flag:
            report.flagged.append(FlaggedRecord(ccv_label=mapped.ccv_label, reason=mapped.flag))

        row_index = len(report.to_write)
        report.to_write.append(mapped)

        handler = handlers.get(mapped.category)
        if handler is not None:
            candidate_row = {"id": "", **mapped.fields}
            matches = handler.find_matches(candidate_row, existing_rows_by_category[mapped.category])
            if matches:
                report.dedup_matches[row_index] = matches

    return report


def write_import(data_dir: Path, report: ImportReport) -> list[str]:
    schemas = load_all_schemas(data_dir / "categories")
    touched: set[str] = set()

    for mapped in report.to_write:
        schema = schemas[mapped.category]
        rows = load_category_rows(data_dir, mapped.category)
        row_id = generate_id(data_dir, mapped.category)
        rows.append({"id": row_id, **mapped.fields})
        write_all_rows(data_dir / f"{mapped.category}.csv", schema.field_names(), rows)
        touched.add(f"{mapped.category}.csv")

    return sorted(touched)
```

This re-reads and rewrites a category's CSV once per new row in that category (correct, if not maximally efficient; import runs are one-time/periodic and row counts are in the tens-to-hundreds, not a performance concern).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_import_ccv.py -v`
Expected: PASS (full file, all tasks' tests included).

- [ ] **Step 5: Run the full unit test suite**

Run: `pytest tests/unit/ -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add parcours/core/import_ccv.py tests/unit/test_import_ccv.py
git commit -m "Added CCV import orchestration: dedup integration, plan_import, write_import"
```

---

## Task 9: CLI command — `parco import ccv`

**Files:**
- Modify: `parcours/cli/main.py`
- Test: `tests/integration/test_cli_import.py` (new)

**Interfaces:**
- Consumes: `core/import_ccv.py::plan_import`, `write_import`, `ImportReport`.

- [ ] **Step 1: Write the failing integration tests**

Create `tests/integration/test_cli_import.py`. Following the same locally-defined-`_setup_data_repo` convention as every other `tests/integration/test_cli_*.py` file (see Task 1's note on this), build a fixture with everything `plan_import` needs: `parco.yaml` (with a `currency` block, since `plan_import` reads it), `identity.yaml`, an `education` category schema+CSV, and a real git repo committed once (since the import writes must be checkable as uncommitted afterward):

```python
import subprocess

from typer.testing import CliRunner

from parcours.cli.main import app

runner = CliRunner()

_EDUCATION_SCHEMA = """
name: education
handler: generic
fields:
  - {name: id, generated: true}
  - {name: degree_type, required: true}
  - {name: degree_name_en}
  - {name: degree_name_fr}
  - {name: specialization_en}
  - {name: specialization_fr}
  - {name: organization, required: true}
  - {name: degree_status, required: true}
  - {name: start_date, type: date, precision: month, required: true}
  - {name: end_date, type: date, precision: month}
  - {name: thesis_title}
  - {name: advisor}
  - {name: note_en}
  - {name: note_fr}
dedup:
  - when: [{exact: organization}, {exact: degree_type}, {same_year: start_date}]
    as: duplicate
"""

_SAMPLE_XML = """<?xml version="1.0"?>
<generic-cv:generic-cv xmlns:generic-cv="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0" lang="en">
  <section label="Education">
    <section label="Degrees" recordId="r1">
      <field label="Degree Type"><lov id="1">Doctorate</lov></field>
      <field label="Degree Status"><lov id="2">Completed</lov></field>
      <field label="Degree Start Date"><value type="YearMonth">2018/9</value></field>
    </section>
  </section>
</generic-cv:generic-cv>
"""


def _setup_data_repo(tmp_path):
    (tmp_path / "parco.yaml").write_text("currency:\n  default: CAD\n  report: CAD\n", encoding="utf-8")
    (tmp_path / "categories").mkdir()
    (tmp_path / "categories" / "education.yaml").write_text(_EDUCATION_SCHEMA, encoding="utf-8")
    (tmp_path / "education.csv").write_text(
        "id,degree_type,degree_name_en,degree_name_fr,specialization_en,specialization_fr,"
        "organization,degree_status,start_date,end_date,thesis_title,advisor,note_en,note_fr\n",
        encoding="utf-8",
    )
    (tmp_path / "identity.yaml").write_text("name:\n  first: Jane\n  last: Doe\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_import_ccv_dry_run_writes_nothing(tmp_path, tmp_path_factory, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    # The export file must live OUTSIDE the git repo under test — writing it
    # inside `tmp_path` would show up as an untracked file in every
    # `git status --porcelain` assertion below, regardless of command behavior.
    xml_path = tmp_path_factory.mktemp("ccv_export") / "export.xml"
    xml_path.write_text(_SAMPLE_XML, encoding="utf-8")

    result = runner.invoke(app, ["import", "ccv", "--file", str(xml_path), "--dry-run"])

    assert result.exit_code == 0
    assert "education" in result.stdout.lower()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True)
    assert status.stdout.strip() == ""


def test_import_ccv_confirm_writes_uncommitted(tmp_path, tmp_path_factory, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    xml_path = tmp_path_factory.mktemp("ccv_export") / "export.xml"
    xml_path.write_text(_SAMPLE_XML, encoding="utf-8")

    result = runner.invoke(app, ["import", "ccv", "--file", str(xml_path)], input="y\n")

    assert result.exit_code == 0
    content = (repo / "education.csv").read_text(encoding="utf-8")
    assert "doctorate" in content
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True)
    assert "education.csv" in status.stdout
    assert "parco commit" in result.stdout


def test_import_ccv_decline_writes_nothing(tmp_path, tmp_path_factory, monkeypatch):
    repo = _setup_data_repo(tmp_path)
    monkeypatch.chdir(repo)
    xml_path = tmp_path_factory.mktemp("ccv_export") / "export.xml"
    xml_path.write_text(_SAMPLE_XML, encoding="utf-8")

    result = runner.invoke(app, ["import", "ccv", "--file", str(xml_path)], input="n\n")

    assert result.exit_code == 0
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True)
    assert status.stdout.strip() == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/integration/test_cli_import.py -v`
Expected: FAIL (no `import ccv` command registered).

- [ ] **Step 3: Add the `import` sub-app to `parcours/cli/main.py`**

Add the import at the top:

```python
from ..core.import_ccv import ImportReport, plan_import, write_import
```

Add the sub-app (near `translation_app`, e.g. right before it):

```python
import_app = typer.Typer(help="Bulk-seed data from a one-time export file (see SPECS.md, \"Import\").")
app.add_typer(import_app, name="import")


def _print_import_report(report: ImportReport) -> None:
    by_category: dict[str, int] = {}
    for mapped in report.to_write:
        by_category[mapped.category] = by_category.get(mapped.category, 0) + 1

    typer.echo("Import plan:")
    for category, count in sorted(by_category.items()):
        typer.echo(f"  {category}: {count} entr{'y' if count == 1 else 'ies'}")

    if report.dedup_matches:
        typer.echo(f"\n{len(report.dedup_matches)} possible duplicate(s) found (will still be written):")
        for row_index, matches in report.dedup_matches.items():
            mapped = report.to_write[row_index]
            for match in matches:
                typer.echo(f"  {mapped.category} ({mapped.ccv_label}): {match.reason}")

    if report.flagged:
        typer.echo(f"\n{len(report.flagged)} record(s) flagged for manual review (not imported):")
        for flagged in report.flagged:
            typer.echo(f"  {flagged.ccv_label}: {flagged.reason}")

    if report.skipped_labels:
        total_skipped = sum(report.skipped_labels.values())
        typer.echo(f"\n{total_skipped} record(s) skipped (no category mapping):")
        for label, count in sorted(report.skipped_labels.items()):
            typer.echo(f"  {label}: {count}")


@import_app.command(name="ccv")
def import_ccv(
    file: Path = typer.Option(..., "--file", help="Path to the CCV XML export"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would be imported without writing anything"),
):
    """Bulk-import from a Canadian Common CV XML export."""
    data_dir = _find_repo_or_exit()

    report = plan_import(data_dir, file)
    _print_import_report(report)

    if not report.to_write:
        typer.echo("\nNothing to import.")
        return

    if dry_run:
        return

    total = len(report.to_write)
    categories = len({mapped.category for mapped in report.to_write})
    if not typer.confirm(f"\nWrite {total} entries across {categories} categories to your working tree?"):
        return

    touched = write_import(data_dir, report)
    typer.echo(f"\nWrote {total} entries to: {', '.join(touched)} (not committed).")
    typer.echo("Review with `git diff`, `parco lint`, and `parco edit <category> --search ...`.")
    typer.echo("When you're happy with it: parco commit")
    typer.echo("To discard the import entirely: git checkout -- .")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/integration/test_cli_import.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add parcours/cli/main.py tests/integration/test_cli_import.py
git commit -m "Added parco import ccv command"
```

---

## Post-plan note for the final whole-branch reviewer

Two things worth double-checking that this plan couldn't verify without the real export file (gitignored, not present in the implementation worktree):

1. Every CCV field **label string** used in `import_ccv.py` (e.g. `"Degree Type"`, `"Funding Reviewer Role"`) was transcribed from a structural dump of the user's real export during planning, not guessed — but a transcription error is still possible. If the user runs `parco import ccv --dry-run` after this lands and gets an unexpectedly empty report, the first thing to check is a label typo, not the tree-walking logic.
2. The `_DEGREE_TYPE`/`_GRANT_ROLE`/etc. translation dicts cover every `lov` display string **observed in the real export** — not necessarily every value CCV's schema allows. A value outside these dicts maps to `""` silently (not an error, not a flag) and `parco lint` catches it afterward as a blank required field. This is the intended, documented behavior (see Global Constraints), not a gap to fix reactively.
