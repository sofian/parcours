# parco init Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `parco init [path]` — a wizard-driven command that scaffolds a brand-new parco data repo (all 19 categories, `vocab.yaml`, `translations.csv`, `views.yaml`, `identity.yaml`, `profiles/`) and `git init`s it, so the tool is usable from a fresh clone/pip-install rather than only against a hand-built repo.

**Architecture:** A new pure core module (`parcours/core/init.py`) does all file writing and the git init/commit, reading bundled starter content shipped inside the `parcours` package itself (relocated there in Task 1, since it must survive a `pip install`). The `parco init` Typer command owns all prompting and reuses the wizard's existing numbered-choice / confirm-before-write idioms.

**Tech Stack:** Python ≥3.11, Typer, PyYAML (`safe_load`/`safe_dump` only), `subprocess` for git, `shutil.copy2` for verbatim file copies. No new third-party dependency.

**Spec:** `SPECS.md` — see `## CLI` → `### Init` (the binding user-facing contract), `## Category schemas (drafts)` (source of the 19 category YAML blocks transcribed in Task 2), `## vocab.yaml (draft)`, `## Profiles` (the `extends` mechanism this plan's generated profiles rely on, already implemented), `## views.yaml (draft)` (the starter `views.yaml` this plan copies, already implemented).

## Global Constraints

- **Hexagonal split** (`CLAUDE.md`): `parcours/core/` never does interactive I/O — no `print()`, `input()`, `sys.exit()`, no `typer` import. Takes structured args, returns structured results, or raises typed exceptions. `parcours/cli/main.py` owns **all** prompts, confirmations, and output formatting.
- **No placeholders**: every step below contains real, complete code — no "TODO", no "similar to Task N", no "add appropriate error handling".
- **Commit style** (`CLAUDE.md`): short, one-line imperative messages, past tense, capitalized first letter, no body paragraphs, **no** `Co-Authored-With` lines ever.
- **YAML**: always `yaml.safe_load`/`yaml.safe_dump` — never the plain `Loader`/`Dumper`.
- **IDs**: bare 6-hex-char random tokens (`secrets.token_hex(3)`), never typed by a user — not relevant to this plan directly (init doesn't create category rows), but the empty CSVs this plan creates must have the same header-row shape `add`/`edit` already expect.
- **Tests**: fixtures/temp dirs only, never real user data; core tests touch no git and no filesystem beyond a temp dir except where the module under test IS git integration (Task 3's `scaffold_repo`, which is inherently git-touching — matches the existing precedent in `tests/integration/test_entries_git.py`, which also runs real git commands against `tmp_path`).
- **Model tiering** (for whoever executes this plan via SDD): Task 1 and Task 4 are mechanical/integration — standard model. Task 2 is large-scale faithful transcription with a complete reference embedded below — cheap model is fine, but its review must independently cross-check content against `SPECS.md`, not just confirm the files load (this is the exact lesson from the `parco build` plan's Task 6, which is the direct precedent for this task's shape and risk profile). Task 3 has real design judgment (git testing via env vars, profile-shape branching) — standard model.

---

### Task 1: Relocate `starter_config/` inside the package + package-data config

**Why:** `starter_config/views.yaml` currently lives at the repo root, which `pyproject.toml`'s `[tool.setuptools.packages.find] include = ["parcours*"]` does not bundle into a `pip install`. `parco init` needs to read bundled starter content at runtime from an **installed** package, not just from a source checkout, so this content must move inside `parcours/` and be declared as package data.

**Files:**
- Move: `starter_config/views.yaml` → `parcours/starter_config/views.yaml`
- Modify: `pyproject.toml`
- Modify: `tests/unit/test_starter_views.py` (the one existing reference to the old path)

**Interfaces:**
- Consumes: nothing new.
- Produces: `parcours/starter_config/` as the on-disk location every later task in this plan reads bundled starter content from.

- [ ] **Step 1: Confirm there are no other references to the old path**

Run: `grep -rn "starter_config" --include="*.py" .`
Expected: exactly one hit, `tests/unit/test_starter_views.py:6`. If there are more, update every one of them in Step 3 below, not just the one shown here.

- [ ] **Step 2: Move the file**

```bash
mkdir -p parcours/starter_config
git mv starter_config/views.yaml parcours/starter_config/views.yaml
rmdir starter_config
```

- [ ] **Step 3: Update the one existing reference**

In `tests/unit/test_starter_views.py`, change:
```python
_STARTER_VIEWS_PATH = Path(__file__).parent.parent.parent / "starter_config" / "views.yaml"
```
to:
```python
_STARTER_VIEWS_PATH = Path(__file__).parent.parent.parent / "parcours" / "starter_config" / "views.yaml"
```

- [ ] **Step 4: Add package-data config to `pyproject.toml`**

Add this section (after the existing `[tool.setuptools.packages.find]` block):
```toml
[tool.setuptools.package-data]
parcours = ["starter_config/**/*.yaml", "starter_config/**/*.csv"]
```

- [ ] **Step 5: Run the full suite to confirm the relocation didn't break anything**

Run: `pytest tests/ -v`
Expected: PASS, same count as before this task (no new tests yet — this task is pure relocation).

- [ ] **Step 6: Commit**

```bash
git add starter_config parcours/starter_config pyproject.toml tests/unit/test_starter_views.py
git commit -m "Moved starter_config inside the package and declared it as package data"
```

---

### Task 2: Starter category schemas, vocab.yaml, and translations.csv

**Why:** `parco init` needs real, bundled files to copy into a freshly scaffolded repo — all 19 category schemas and `vocab.yaml` are already fully drafted as prose/YAML in `SPECS.md`, but don't exist as real files yet (only `views.yaml` does, relocated in Task 1). This task is faithful transcription, not new design — every category YAML block below is copied byte-for-byte from `SPECS.md`'s "Category schemas (drafts)" section, and `vocab.yaml`'s content from its "vocab.yaml (draft)" section.

**Files:**
- Create: `parcours/starter_config/categories/publications.yaml`
- Create: `parcours/starter_config/categories/grants.yaml`
- Create: `parcours/starter_config/categories/service.yaml`
- Create: `parcours/starter_config/categories/outreach.yaml`
- Create: `parcours/starter_config/categories/artworks.yaml`
- Create: `parcours/starter_config/categories/students.yaml`
- Create: `parcours/starter_config/categories/teaching.yaml`
- Create: `parcours/starter_config/categories/presentations.yaml`
- Create: `parcours/starter_config/categories/press.yaml`
- Create: `parcours/starter_config/categories/review.yaml`
- Create: `parcours/starter_config/categories/catalog.yaml`
- Create: `parcours/starter_config/categories/education.yaml`
- Create: `parcours/starter_config/categories/positions.yaml`
- Create: `parcours/starter_config/categories/recognitions.yaml`
- Create: `parcours/starter_config/categories/exhibitions.yaml`
- Create: `parcours/starter_config/categories/curatorship.yaml`
- Create: `parcours/starter_config/categories/residencies.yaml`
- Create: `parcours/starter_config/categories/software.yaml`
- Create: `parcours/starter_config/categories/skills.yaml`
- Create: `parcours/starter_config/vocab.yaml`
- Create: `parcours/starter_config/translations.csv`
- Test: `tests/unit/test_starter_categories.py`

**Interfaces:**
- Consumes: `parcours.core.schema.load_category_schema` (existing), `parcours.core.vocab.load_vocab` (existing), `parcours.core.translations.load_translations` (existing).
- Produces: the 21 bundled files Task 3's `scaffold_repo` copies from.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_starter_categories.py
from pathlib import Path

from parcours.core.schema import load_category_schema
from parcours.core.translations import load_translations
from parcours.core.vocab import load_vocab

_STARTER_DIR = Path(__file__).parent.parent.parent / "parcours" / "starter_config"
_CATEGORIES_DIR = _STARTER_DIR / "categories"

_EXPECTED_CATEGORIES = {
    "publications", "review", "catalog", "grants", "artworks", "students",
    "teaching", "service", "outreach", "presentations", "press", "education",
    "positions", "recognitions", "exhibitions", "curatorship", "residencies",
    "software", "skills",
}


def test_starter_categories_directory_has_exactly_the_19_expected_files():
    names = {p.stem for p in _CATEGORIES_DIR.glob("*.yaml")}
    assert names == _EXPECTED_CATEGORIES


def test_every_starter_category_loads_and_matches_its_filename():
    for path in _CATEGORIES_DIR.glob("*.yaml"):
        schema = load_category_schema(path)
        assert schema.name == path.stem


def test_every_vocab_reference_across_starter_categories_exists_in_starter_vocab():
    vocab = load_vocab(_STARTER_DIR / "vocab.yaml")
    for path in _CATEGORIES_DIR.glob("*.yaml"):
        schema = load_category_schema(path)
        for field in schema.fields:
            if field.vocab:
                assert field.vocab in vocab, (
                    f"{schema.name}.{field.name} references vocab '{field.vocab}', "
                    f"not found in starter vocab.yaml"
                )


def test_starter_vocab_has_the_expected_lists():
    vocab = load_vocab(_STARTER_DIR / "vocab.yaml")
    assert vocab["publication_status"] == ["submitted", "under-review", "accepted", "in-press", "published"]
    assert vocab["degree_type"] == ["bachelors", "bachelors-honours", "masters", "doctorate", "postdoc"]
    assert vocab["degree_status"] == ["completed", "in-progress", "withdrawn", "all-but-degree"]
    assert vocab["skill_category"] == [
        "expertise", "programming", "framework", "platform", "software", "spoken-language", "other",
    ]


def test_degree_type_and_degree_status_are_shared_between_students_and_education():
    students = load_category_schema(_CATEGORIES_DIR / "students.yaml")
    education = load_category_schema(_CATEGORIES_DIR / "education.yaml")
    assert students.get_field("degree_type").vocab == education.get_field("degree_type").vocab
    assert students.get_field("degree_status").vocab == education.get_field("degree_status").vocab


def test_starter_translations_has_exactly_the_18_non_skills_section_rows():
    table = load_translations(_STARTER_DIR / "translations.csv")
    entries = table.all()
    assert len(entries) == 18
    assert {e.id for e in entries} == _EXPECTED_CATEGORIES - {"skills"}
    assert all(e.category == "section" for e in entries)


def test_starter_translations_has_no_missing_translations():
    table = load_translations(_STARTER_DIR / "translations.csv")
    assert table.missing_translations() == []


def test_starter_translations_grants_row_matches_the_agreed_wording():
    table = load_translations(_STARTER_DIR / "translations.csv")
    assert table.lookup("section", "grants", "en") == "Grants"
    assert table.lookup("section", "grants", "fr") == "Subventions"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_starter_categories.py -v`
Expected: FAIL — `_CATEGORIES_DIR` doesn't exist yet / `FileNotFoundError` or empty-glob assertion failures.

- [ ] **Step 3: Create every starter category file, `vocab.yaml`, and `translations.csv`**

Create `parcours/starter_config/categories/publications.yaml`:
```yaml
name: publications
handler: publications
options:
  bib: zotero/library.bib        # Better BibTeX auto-exports; absolute or
  json: zotero/library.json      # relative to the data repo
  type_map:                      # CSL type -> CV type; lint flags unmapped types
    article-journal: journal-article
    paper-conference: conference-paper
    chapter: book-chapter
    book: book
fields:
  - {name: id,       generated: true}                       # pub-2026-004
  - {name: weight,   type: int}                             # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: citekey,  required: true}                        # must resolve in the export
  - {name: status,   required: true, vocab: publication_status}
  - {name: refereed, type: bool}
  - {name: invited,  type: bool}
  - {name: featured, type: bool}                            # "selected publications"
  - {name: note_en,  type: text}                            # e.g. "Best paper award"
  - {name: note_fr,  type: text}
```

Create `parcours/starter_config/categories/grants.yaml`:
```yaml
name: grants
handler: generic
fields:
  - {name: id,           generated: true}                   # grant-frqsc-2026
  - {name: weight,       type: int}                         # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: title_en,     required: true}
  - {name: title_fr,     required: true}
  - {name: funder,       required: true}                    # free text
  - {name: program}
  - {name: role,         required: true, vocab: grant_role}     # PI / co-PI / collaborator
  - {name: status,       required: true, vocab: grant_status}   # submitted / awarded / declined
  - {name: start_date,   type: date, precision: month, required: true}
  - {name: end_date,     type: date, precision: month}      # blank = ongoing
  - {name: amount,       type: number}
  - {name: currency,     default: $currency.default}         # from parco.yaml, e.g. CAD
  - {name: co_investigators}
  - {name: note_en}
  - {name: note_fr}
dedup:
  - when: [{exact: funder}, {overlap: [start_date, end_date]}, {fuzzy: [title_en, title_fr]}]
    as: duplicate
```

Create `parcours/starter_config/categories/service.yaml`:
```yaml
name: service
handler: generic
fields:
  - {name: id,           generated: true}                       # svc-2026-004
  - {name: weight,       type: int}                             # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: type,         required: true, vocab: service_type}   # graduate-examination / funding-review / manuscript-review / volunteer / membership / committee / program-development
  - {name: role,         required: true}                        # free text — CCV's own Role field is a controlled list for some
                                                                  # service types and free text for others, so a merged vocab
                                                                  # wouldn't correspond to any single real list
  - {name: organization, required: true}                        # free text — no vocab, too many distinct values
  - {name: start_date,   type: date, precision: month, required: true}
  - {name: end_date,     type: date, precision: month}          # blank = ongoing
  - {name: detail}                                               # student name (graduate-examination) / committee name
                                                                  # (funding-review) / which committee, e.g. "Hiring
                                                                  # Committee" (committee) / program title + description
                                                                  # (program-development) / activity description
                                                                  # (volunteer, membership) — meaning depends on `type`
dedup:
  - when: [{fuzzy: organization}, {fuzzy: role}, {overlap: [start_date, end_date]}]
    as: duplicate
```

Create `parcours/starter_config/categories/outreach.yaml`:
```yaml
name: outreach
handler: generic
fields:
  - {name: id,                 generated: true}                              # outreach-2026-004
  - {name: weight,             type: int}                                    # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: activity_type,      required: true, vocab: outreach_activity_type} # community-engagement / consulting-for-industry / ...
  - {name: target_stakeholder, vocab: outreach_stakeholder}                   # general-public / industry / ...
  - {name: organization,       required: true}                               # free text — "Group/Organization/Business Serviced"
  - {name: role}                                                              # free text
  - {name: start_date,         type: date, precision: month, required: true}
  - {name: end_date,           type: date, precision: month}                 # blank = ongoing
  - {name: description_en}
  - {name: description_fr}                                                   # free-form; unused in the reference export, kept for reuse
  - {name: url}                                                              # References / Citations / Web Sites
dedup:
  - when: [{fuzzy: organization}, {overlap: [start_date, end_date]}]
    as: duplicate
```

Create `parcours/starter_config/categories/artworks.yaml`:
```yaml
name: artworks
handler: generic
fields:
  - {name: id,             generated: true}                     # artwork-2026-004
  - {name: weight,         type: int}                           # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: title_en}
  - {name: title_fr}                                             # usually only one filled — see require_one_of
  - {name: role,           required: true, vocab: artwork_role}  # author / collaborator
  - {name: date,           type: date, precision: year, required: true}  # production year
  - {name: description_en}
  - {name: description_fr}                                       # CCV's "Description / Contribution Value"
  - {name: contributors}                                         # free text names list, like grants' co_investigators
  - {name: url}
require_one_of:
  - [title_en, title_fr]
dedup:
  - when: [{fuzzy: [title_en, title_fr]}, {same_year: date}]
    as: duplicate
```

Create `parcours/starter_config/categories/students.yaml`:
```yaml
name: students
handler: generic
fields:
  - {name: id,                     generated: true}                       # student-2026-004
  - {name: weight,                 type: int}                             # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: student_name,           required: true}                        # free text
  - {name: role,                   required: true, vocab: student_role}   # principal-supervisor / co-supervisor
  - {name: institution}                                                    # free text
  - {name: degree_type,            required: true, vocab: degree_type}    # bachelors-honours / masters / doctorate / postdoc
  - {name: degree_status,          required: true, vocab: degree_status}  # completed / in-progress / withdrawn / all-but-degree
  - {name: supervision_start_date, type: date, precision: month, required: true}
  - {name: supervision_end_date,   type: date, precision: month}          # blank = ongoing
  - {name: degree_start_date,      type: date, precision: month}
  - {name: degree_end_date,        type: date, precision: month}          # actual completion; blank until finished
  - {name: thesis_title}                                                   # no translation
  - {name: present_position}                                               # free text — outcome tracking
  - {name: present_organization}
dedup:
  - when: [{exact: student_name}]
    as: related
```

Create `parcours/starter_config/categories/teaching.yaml`:
```yaml
name: teaching
handler: generic
fields:
  - {name: id,           generated: true}                # teaching-2026-004
  - {name: weight,       type: int}                      # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: course_label, required: true}                 # e.g. EDM1600, COM1001 — CCV has no equivalent, filled in manually
  - {name: title_en}
  - {name: title_fr}
  - {name: role}                                          # free text, e.g. Professor
  - {name: organization, required: true}                  # resolved from CCV's refTable (see CCV export structure)
  - {name: department}
  - {name: date,         type: date, precision: month, required: true}  # term/year of this specific offering
dedup:
  - when: [{exact: course_label}, {exact: organization}, {same_year: date}]
    as: duplicate
```

Create `parcours/starter_config/categories/presentations.yaml`:
```yaml
name: presentations
handler: generic
fields:
  - {name: id,        generated: true}                                  # presentation-2026-004
  - {name: weight,    type: int}                                        # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: title_en}
  - {name: title_fr}                                                    # usually only one filled
  - {name: event_en}
  - {name: event_fr}                                                    # Conference / Event Name — usually only one filled (e.g. "Colloque ACFAS" has no English name)
  - {name: location,  required: true, glossary: location}                                   # city + country as one glossary-backed value, e.g. "Berlin, Germany"
  - {name: invited,   type: bool}
  - {name: keynote,   type: bool}
  - {name: date,      type: date, precision: month, required: true}     # at least year+month, like grants.start_date
  - {name: description_en}
  - {name: description_fr}
  - {name: co_presenters}                                                # free text names list
  - {name: url}
require_one_of:
  - [title_en, title_fr]
  - [event_en, event_fr]
dedup:
  - when: [{fuzzy: [title_en, title_fr]}, {same_year: date}]
    as: duplicate
```

Create `parcours/starter_config/categories/press.yaml`:
```yaml
name: press
handler: generic
options:
  zotero: {bib: zotero/library.bib, json: zotero/library.json}  # for rows that set citekey
fields:
  - {name: id,           generated: true}                    # press-2026-004
  - {name: weight,       type: int}                          # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: citekey}                                            # optional — set when also a Zotero-catalogued item
                                                                 # (e.g. a written review); enables `parco cite` on
                                                                 # this row (see Category handlers: shared Zotero
                                                                 # capability). Blank for podcast/radio/TV/interview
                                                                 # appearances, which aren't Zotero items.
  - {name: author}                                              # free text — who wrote or conducted it
  - {name: outlet,       required: true}                        # free text — publisher, radio/TV station, network
  - {name: program}                                              # free text — the specific show/program, if any
                                                                 # (blank for print/text pieces)
  - {name: date,         type: date, precision: month, required: true}
  - {name: description_en}
  - {name: description_fr}
  - {name: url}
dedup:
  - when: [{exact: citekey}]
    as: duplicate
  - when: [{fuzzy: outlet}, {fuzzy: program}, {same_year: date}]
    as: duplicate
```

Create `parcours/starter_config/categories/review.yaml`:
```yaml
name: review
handler: publications
options:
  bib: zotero/library.bib
  json: zotero/library.json
fields:
  - {name: id,       generated: true}       # review-2026-004
  - {name: weight,   type: int}             # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: citekey,  required: true}        # must resolve in the export, same rule as publications
```

Create `parcours/starter_config/categories/catalog.yaml`:
```yaml
name: catalog
handler: publications
options:
  bib: zotero/library.bib
  json: zotero/library.json
fields:
  - {name: id,       generated: true}       # catalog-2026-004
  - {name: weight,   type: int}             # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: citekey,  required: true}
```

Create `parcours/starter_config/categories/education.yaml`:
```yaml
name: education
handler: generic
fields:
  - {name: id,                generated: true}                       # edu-2026-004
  - {name: weight,            type: int}                             # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: degree_type,       required: true, vocab: degree_type}     # bachelors / bachelors-honours / masters / doctorate / postdoc — shared vocab with students
  - {name: degree_name_en,    required: true}
  - {name: degree_name_fr,    required: true}                         # e.g. "Ph. D. Humanities" / "Ph. D. Sciences humaines"
  - {name: specialization_en}
  - {name: specialization_fr}                                         # e.g. "Fine Arts" / "Beaux-arts"
  - {name: organization,      required: true}                         # resolved from CCV's refTable
  - {name: degree_status,     required: true, vocab: degree_status}   # completed / in-progress / withdrawn / all-but-degree — shared vocab with students
  - {name: start_date,        type: date, precision: month, required: true}
  - {name: end_date,          type: date, precision: month}           # blank = ongoing
  - {name: thesis_title}                                              # no translation; blank for degrees without a thesis (e.g. postdoc, bachelor's)
  - {name: advisor}                                                    # free text — CCV has no equivalent field
  - {name: note_en}
  - {name: note_fr}                                                    # e.g. "Completed with honours"
dedup:
  - when: [{exact: organization}, {exact: degree_type}, {same_year: start_date}]
    as: duplicate
```

Create `parcours/starter_config/categories/positions.yaml`:
```yaml
name: positions
handler: generic
fields:
  - {name: id,               generated: true}                       # pos-2026-004
  - {name: weight,           type: int}                             # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: type,             required: true, vocab: position_type}   # academic / non-academic / affiliation
  - {name: title_en,         required: true}
  - {name: title_fr,         required: true}
  - {name: organization,     required: true}                         # free text — CCV mostly supplies "Other Organization" here, not the refTable
  - {name: faculty}                                                   # free text — e.g. "School of Media"
  - {name: department}                                                # free text
  - {name: position_status,  vocab: position_status}                  # e.g. full-time / part-time / casual
  - {name: start_date,       type: date, precision: month, required: true}
  - {name: end_date,         type: date, precision: month}            # blank = ongoing
dedup:
  - when: [{exact: organization}, {fuzzy: [title_en, title_fr]}, {overlap: [start_date, end_date]}]
    as: duplicate
```

Create `parcours/starter_config/categories/recognitions.yaml`:
```yaml
name: recognitions
handler: generic
fields:
  - {name: id,               generated: true}                          # award-2026-004
  - {name: weight,           type: int}                                # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: recognition_type, required: true, vocab: recognition_type}   # citation / distinction / prize
  - {name: name,             required: true}                            # free text
  - {name: organization,     required: true}                            # free text — refTable or "Other Organization" fallback, same pattern as positions/education
  - {name: role,             vocab: recognition_role, default: recipient}  # recipient / educator — for an award given to a student you supervised
  - {name: date,             type: date, precision: month, required: true}
  - {name: end_date,         type: date, precision: month}              # blank for one-time citations; set for fellowship-like awards with a disbursement period
  - {name: amount,           type: number}
  - {name: currency,         default: $currency.default}
  - {name: description_en}
  - {name: description_fr}
dedup:
  - when: [{exact: organization}, {fuzzy: name}, {same_year: date}]
    as: duplicate
```

Create `parcours/starter_config/categories/exhibitions.yaml`:
```yaml
name: exhibitions
handler: generic
fields:
  - {name: id,           generated: true}                          # exh-2026-004
  - {name: weight,       type: int}                                # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: title_en}
  - {name: title_fr}                                                # usually only one filled
  - {name: event}                                                    # free text — festival/series, e.g. "MUTEK Forum"
  - {name: venue}                                                    # free text — hosting institution, e.g. "National Gallery"
  - {name: location,     required: true, glossary: location}                             # city + country as one glossary-backed value
  - {name: curator}                                                  # free text — credited curator(s)
  - {name: start_date,   type: date, precision: month, required: true}
  - {name: end_date,     type: date, precision: month}              # blank = single-day event or unknown
require_one_of:
  - [title_en, title_fr]
  - [event, venue]
dedup:
  - when: [{fuzzy: [title_en, title_fr]}, {fuzzy: [event, venue]}, {same_year: start_date}]
    as: duplicate
```

Create `parcours/starter_config/categories/curatorship.yaml`:
```yaml
name: curatorship
handler: generic
fields:
  - {name: id,           generated: true}                          # cur-2026-004
  - {name: weight,       type: int}                                # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: title_en}
  - {name: title_fr}
  - {name: event}
  - {name: venue}
  - {name: location,     required: true, glossary: location}                             # city + country as one glossary-backed value
  - {name: curator}                                                  # free text — co-curator(s), if any (your own curatorial role is implicit)
  - {name: start_date,   type: date, precision: month, required: true}
  - {name: end_date,     type: date, precision: month}
require_one_of:
  - [title_en, title_fr]
  - [event, venue]
dedup:
  - when: [{fuzzy: [title_en, title_fr]}, {fuzzy: [event, venue]}, {same_year: start_date}]
    as: duplicate
```

Create `parcours/starter_config/categories/residencies.yaml`:
```yaml
name: residencies
handler: generic
fields:
  - {name: id,           generated: true}                       # res-2026-004
  - {name: weight,       type: int}                             # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: organization, required: true}                        # free text — e.g. "Hexagram", "LABoral"
  - {name: location,     required: true, glossary: location}                         # city + country as one glossary-backed value
  - {name: start_date,   type: date, precision: month, required: true}
  - {name: end_date,     type: date, precision: month}           # blank = short/undated residency
dedup:
  - when: [{exact: organization}, {overlap: [start_date, end_date]}]
    as: duplicate
```

Create `parcours/starter_config/categories/software.yaml`:
```yaml
name: software
handler: generic
fields:
  - {name: id,             generated: true}                       # sw-2026-004
  - {name: weight,         type: int}                             # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: role,           required: true, vocab: software_role}   # lead-developer / co-developer / developer / contributor
  - {name: title,          required: true}                         # project name, e.g. "Plaquette" — a proper noun, no translation
  - {name: description_en, required: true}
  - {name: description_fr, required: true}                         # e.g. "open source framework for creative physical computing" / French
  - {name: start_date,     type: date, precision: month, required: true}
  - {name: end_date,       type: date, precision: month}           # blank = ongoing
  - {name: url}
dedup:
  - when: [{fuzzy: title}, {overlap: [start_date, end_date]}]
    as: duplicate
```

Create `parcours/starter_config/categories/skills.yaml`:
```yaml
name: skills
handler: generic
fields:
  - {name: id,        generated: true}                        # skill-2026-004
  - {name: weight,    type: int}                              # optional; higher = appears earlier — the ordering mechanism here, since skills have no dates at all
  - {name: category,  required: true, vocab: skill_category}   # expertise / programming / framework / platform / software / spoken-language / other
  - {name: name_en}                                             # untranslated technical terms just go here, name_fr left blank
  - {name: name_fr}
  - {name: level,     vocab: language_level}                    # native / fluent / intermediate / basic — spoken-language only
require_one_of:
  - [name_en, name_fr]
dedup:
  - when: [{exact: category}, {fuzzy: [name_en, name_fr]}]
    as: duplicate
```

Create `parcours/starter_config/vocab.yaml`:
```yaml
publication_status: [submitted, under-review, accepted, in-press, published]
publication_type: [journal-article, conference-paper, book, book-chapter, report, thesis, magazine-entry, online-resource]

grant_role: [pi, co-pi, collaborator]
grant_status: [submitted, awarded, declined]

artwork_role: [author, collaborator]

student_role: [principal-supervisor, co-supervisor]
degree_type: [bachelors, bachelors-honours, masters, doctorate, postdoc]        # shared: students, education
degree_status: [completed, in-progress, withdrawn, all-but-degree]              # shared: students, education

service_type: [graduate-examination, funding-review, manuscript-review, volunteer, membership, committee, program-development]

outreach_activity_type: [community-engagement, startup-involvement, technology-improvement, business-innovation, industry-consulting]
outreach_stakeholder: [general-public, private-nonprofit, utility, industry-association, industry-business]

position_type: [academic, non-academic, affiliation]
position_status: [full-time, part-time]

recognition_type: [citation, distinction, prize]
recognition_role: [recipient, educator]

software_role: [lead-developer, co-developer, developer, contributor]

skill_category: [expertise, programming, framework, platform, software, spoken-language, other]
language_level: [native, fluent, intermediate, basic]
```

Create `parcours/starter_config/translations.csv`:
```csv
id,category,en,fr
publications,section,Publications,Publications
review,section,Reviews,Critiques
catalog,section,Catalog Essays,Essais de catalogue
grants,section,Grants,Subventions
artworks,section,Artworks,Œuvres
students,section,Student Supervision,Encadrement d'étudiants
teaching,section,Teaching,Enseignement
service,section,Service,Service
outreach,section,Outreach,Rayonnement
presentations,section,Presentations,Présentations
press,section,Press,Presse
education,section,Education,Formation
positions,section,Positions,Postes
recognitions,section,Recognitions,Distinctions
exhibitions,section,Exhibitions,Expositions
curatorship,section,Curatorship,Commissariat
residencies,section,Residencies,Résidences
software,section,Software,Logiciels
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_starter_categories.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the full suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all prior tests plus this task's 8 new ones)

- [ ] **Step 6: Commit**

```bash
git add parcours/starter_config/categories parcours/starter_config/vocab.yaml \
        parcours/starter_config/translations.csv tests/unit/test_starter_categories.py
git commit -m "Added starter category schemas, vocab.yaml, and translations.csv for all 19 categories"
```

---

### Task 3: `core/init.py` — pure repo scaffolding

**Files:**
- Create: `parcours/core/init.py`
- Test: `tests/integration/test_init.py`

**Interfaces:**
- Consumes: `parcours.core.schema.load_category_schema`/`load_all_schemas` (existing), `parcours.core.views.load_views` (existing, from the `parco build` plan).
- Produces: `InitAnswers`, `RepoAlreadyExists`, `GitInitFailed`, `scaffold_repo(path: Path, answers: InitAnswers) -> None`. Consumed by the CLI `init` command in Task 4.

This task is pure — no `print`/`input`/`typer` anywhere in `init.py`. The one necessary exception, matching the codebase's existing precedent (`core/build.py`'s sanctioned `subprocess.run` call to `rendercv`), is `subprocess.run` for `git init`/`git add`/`git commit` — that's the whole point of this module.

**A note on `order_by` generation**: the generated profile's sections use a fully generic rule — a section gets `order_by: "start_date desc"` if its category's schema declares a `start_date` field, `order_by: "date desc"` if it declares a plain `date` field instead, and no `order_by` at all otherwise. This deliberately does **not** special-case any category by name (e.g. `students`' `supervision_start_date` doesn't match either literal name, so its generated section has no `order_by` — a minor, easily hand-edited cosmetic gap in the *generated starter content*, not a bug in `init` itself; keeping `init.py` fully generic/category-agnostic matters more than a perfectly-ordered `students` section out of the box, per this codebase's "all categories are equal, none special-cased in the core" rule).

- [ ] **Step 1: Write the failing tests**

```python
# tests/integration/test_init.py
import subprocess

import pytest
import yaml

from parcours.core.init import GitInitFailed, InitAnswers, RepoAlreadyExists, scaffold_repo
from parcours.core.schema import load_all_schemas


def _answers(**overrides) -> InitAnswers:
    defaults = dict(
        first_name="Jane",
        last_name="Doe",
        variant_name="academic",
        languages=["en"],
        currency="CAD",
        title_en="Associate Professor",
    )
    defaults.update(overrides)
    return InitAnswers(**defaults)


def _set_git_env(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")


def test_scaffold_repo_creates_every_expected_file(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers())

    assert (repo / "parco.yaml").is_file()
    assert (repo / "vocab.yaml").is_file()
    assert (repo / "translations.csv").is_file()
    assert (repo / "views.yaml").is_file()
    assert (repo / "identity.yaml").is_file()
    assert (repo / "profiles" / "academic-en.yaml").is_file()

    schemas = load_all_schemas(repo / "categories")
    assert len(schemas) == 19
    for name, schema in schemas.items():
        csv_path = repo / f"{name}.csv"
        assert csv_path.is_file()
        header = csv_path.read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",") == schema.field_names()


def test_scaffold_repo_refuses_if_parco_yaml_already_exists(tmp_path):
    repo = tmp_path / "existing"
    repo.mkdir()
    (repo / "parco.yaml").write_text("currency: {default: CAD, report: CAD}\n")

    with pytest.raises(RepoAlreadyExists):
        scaffold_repo(repo, _answers())

    assert not (repo / "vocab.yaml").exists()


def test_scaffold_repo_writes_currency_to_both_default_and_report(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers(currency="EUR"))

    config = yaml.safe_load((repo / "parco.yaml").read_text(encoding="utf-8"))
    assert config == {"currency": {"default": "EUR", "report": "EUR"}}


def test_scaffold_repo_writes_a_flat_profile_for_one_language(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers(languages=["en"]))

    assert (repo / "profiles" / "academic-en.yaml").is_file()
    assert not (repo / "profiles" / "_academic.yaml").exists()
    profile = yaml.safe_load((repo / "profiles" / "academic-en.yaml").read_text(encoding="utf-8"))
    assert profile["meta"]["language"] == "en"
    assert "extends" not in profile
    assert len(profile["sections"]) == 18  # every non-skills view


def test_scaffold_repo_writes_a_base_plus_extends_children_for_two_languages(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers(languages=["en", "fr"], title_fr="Professeure agrégée"))

    base = yaml.safe_load((repo / "profiles" / "_academic.yaml").read_text(encoding="utf-8"))
    assert "language" not in base["meta"]
    assert len(base["sections"]) == 18

    en_child = yaml.safe_load((repo / "profiles" / "academic-en.yaml").read_text(encoding="utf-8"))
    assert en_child == {"extends": "_academic", "meta": {"language": "en"}}
    fr_child = yaml.safe_load((repo / "profiles" / "academic-fr.yaml").read_text(encoding="utf-8"))
    assert fr_child == {"extends": "_academic", "meta": {"language": "fr"}}


def test_scaffold_repo_omits_blank_optional_identity_fields(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers(phone="", homepage=""))

    identity = yaml.safe_load((repo / "identity.yaml").read_text(encoding="utf-8"))
    variant = identity["variants"]["academic"]
    assert "phone" not in variant
    assert "homepage" not in variant
    assert variant["title_en"] == "Associate Professor"


def test_scaffold_repo_generated_sections_use_the_generic_order_by_rule(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers())

    profile = yaml.safe_load((repo / "profiles" / "academic-en.yaml").read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in profile["sections"]}
    assert by_id["grants"]["order_by"] == "start_date desc"
    assert by_id["artworks"]["order_by"] == "date desc"
    assert "order_by" not in by_id["publications"]


def test_scaffold_repo_creates_a_real_git_repo_with_one_commit(tmp_path, monkeypatch):
    _set_git_env(monkeypatch)
    repo = tmp_path / "my-cv"

    scaffold_repo(repo, _answers())

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    assert len(log.splitlines()) == 1
    assert "Initialized parco data repo" in log

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    assert status.strip() == ""


def test_scaffold_repo_wraps_git_failure(tmp_path, monkeypatch):
    def _fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "git", stderr=b"fatal: unable to auto-detect email address")

    monkeypatch.setattr("parcours.core.init.subprocess.run", _fail)
    repo = tmp_path / "my-cv"

    with pytest.raises(GitInitFailed):
        scaffold_repo(repo, _answers())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/integration/test_init.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcours.core.init'`

- [ ] **Step 3: Implement `parcours/core/init.py`**

```python
"""Scaffolds a brand-new parco data repo (see SPECS.md, "CLI" -> "Init").
Core layer: no prompting here — the CLI `init` command owns all wizard
interaction and calls scaffold_repo with the answers it collected. The
one sanctioned exception to "core never shells out interactively" is the
`git init`/`git add`/`git commit` sequence at the end, matching the same
precedent as core/build.py's `rendercv` invocation."""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .schema import CategorySchema, load_all_schemas, load_category_schema
from .views import load_views


class RepoAlreadyExists(Exception):
    """Raised by scaffold_repo when `path/parco.yaml` already exists —
    init is fresh-repo-only in this first cut, never "add missing
    pieces" to an existing one."""


class GitInitFailed(Exception):
    """Raised when `git init`/`git add`/`git commit` fails while
    scaffolding a new repo."""


@dataclass
class InitAnswers:
    first_name: str
    last_name: str
    variant_name: str
    languages: list[str]
    currency: str
    title_en: str = ""
    title_fr: str = ""
    email: str = ""
    phone: str = ""
    homepage: str = ""


def _starter_config_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "starter_config"


def _write_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)


def _write_parco_yaml(path: Path, answers: InitAnswers) -> None:
    _write_yaml(path / "parco.yaml", {
        "currency": {"default": answers.currency, "report": answers.currency},
    })


def _copy_categories_and_csvs(path: Path, starter_dir: Path) -> None:
    categories_dir = path / "categories"
    categories_dir.mkdir(parents=True, exist_ok=True)
    for schema_path in sorted((starter_dir / "categories").glob("*.yaml")):
        dest = categories_dir / schema_path.name
        shutil.copy2(schema_path, dest)
        schema = load_category_schema(dest)
        csv_path = path / f"{schema.name}.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(",".join(schema.field_names()) + "\n")


def _write_identity_yaml(path: Path, answers: InitAnswers) -> None:
    variant: dict[str, str] = {}
    for key, value in [
        ("title_en", answers.title_en),
        ("title_fr", answers.title_fr),
        ("email", answers.email),
        ("phone", answers.phone),
        ("homepage", answers.homepage),
    ]:
        if value:
            variant[key] = value

    _write_yaml(path / "identity.yaml", {
        "name": {"first": answers.first_name, "last": answers.last_name},
        "variants": {answers.variant_name: variant},
    })


def _section_order_by(schema: CategorySchema) -> str | None:
    field_names = schema.field_names()
    if "start_date" in field_names:
        return "start_date desc"
    if "date" in field_names:
        return "date desc"
    return None


def _build_sections(path: Path) -> list[dict]:
    views = load_views(path / "views.yaml")
    schemas = load_all_schemas(path / "categories")

    sections = []
    for view_name, view in views.items():
        section: dict = {"id": view_name, "source": view_name}
        schema = schemas.get(view.source)
        if schema is not None:
            order_by = _section_order_by(schema)
            if order_by:
                section["order_by"] = order_by
        sections.append(section)
    return sections


def _write_profiles(path: Path, answers: InitAnswers) -> None:
    profiles_dir = path / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    sections = _build_sections(path)

    if len(answers.languages) == 1:
        language = answers.languages[0]
        profile = {
            "meta": {
                "name": answers.variant_name,
                "language": language,
                "format": "pdf",
                "theme": "sb2nov",
                "identity_variant": answers.variant_name,
            },
            "sections": sections,
        }
        _write_yaml(profiles_dir / f"{answers.variant_name}-{language}.yaml", profile)
        return

    base_name = f"_{answers.variant_name}"
    base = {
        "meta": {
            "name": answers.variant_name,
            "format": "pdf",
            "theme": "sb2nov",
            "identity_variant": answers.variant_name,
        },
        "sections": sections,
    }
    _write_yaml(profiles_dir / f"{base_name}.yaml", base)
    for language in answers.languages:
        child = {"extends": base_name, "meta": {"language": language}}
        _write_yaml(profiles_dir / f"{answers.variant_name}-{language}.yaml", child)


def _git_init_and_commit(path: Path) -> None:
    try:
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initialized parco data repo"],
            cwd=path, check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        raise GitInitFailed(f"git init failed: {stderr}") from exc


def scaffold_repo(path: Path, answers: InitAnswers) -> None:
    """Scaffolds a brand-new parco data repo at `path` and commits it.
    Raises RepoAlreadyExists (writing nothing) if `path/parco.yaml`
    already exists, or GitInitFailed if the final git init/commit fails."""
    path = Path(path)
    if (path / "parco.yaml").is_file():
        raise RepoAlreadyExists(f"A parco data repo already exists at {path}")

    path.mkdir(parents=True, exist_ok=True)
    starter_dir = _starter_config_dir()

    _write_parco_yaml(path, answers)
    _copy_categories_and_csvs(path, starter_dir)
    shutil.copy2(starter_dir / "vocab.yaml", path / "vocab.yaml")
    shutil.copy2(starter_dir / "translations.csv", path / "translations.csv")
    shutil.copy2(starter_dir / "views.yaml", path / "views.yaml")
    _write_identity_yaml(path, answers)
    _write_profiles(path, answers)
    _git_init_and_commit(path)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/integration/test_init.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Run the full suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all prior tests plus this task's 9 new ones)

- [ ] **Step 6: Commit**

```bash
git add parcours/core/init.py tests/integration/test_init.py
git commit -m "Added core repo-scaffolding for parco init"
```

---

### Task 4: The `parco init` CLI command

**Files:**
- Modify: `parcours/cli/main.py`
- Test: `tests/integration/test_cli_init.py`

**Interfaces:**
- Consumes: `InitAnswers`, `RepoAlreadyExists`, `GitInitFailed`, `scaffold_repo` (Task 3).
- Produces: the `init` Typer command — the plan's final user-facing deliverable.

**A note on prompt ordering vs. SPECS.md's prose**: SPECS.md's "Init" section lists the wizard's questions as name → variant/headline/email/phone/homepage → language(s) → currency, in that prose order. The *headline/title* question genuinely depends on knowing which language(s) were chosen (it asks for `title_en` and/or `title_fr` specifically), so the actual prompt order below asks language(s) **before** headline/title — a necessary implementation ordering, not a change to what's asked or why.

- [ ] **Step 1: Write the failing tests**

```python
# tests/integration/test_cli_init.py
from typer.testing import CliRunner

from parcours.cli.main import app

runner = CliRunner()


def _git_env(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")


def test_init_scaffolds_a_repo_for_a_single_language(tmp_path, monkeypatch):
    _git_env(monkeypatch)
    target = tmp_path / "my-cv"

    # first, last, variant(default), language choice(1=en), title_en,
    # email, phone(skip), homepage(skip), currency, confirm
    result = runner.invoke(
        app,
        ["init", str(target)],
        input="Jane\nDoe\n\n1\nAssociate Professor\njane@example.edu\n\n\nCAD\ny\n",
    )

    assert result.exit_code == 0, result.stdout
    assert (target / "parco.yaml").is_file()
    assert (target / "profiles" / "academic-en.yaml").is_file()
    assert "Initialized a new parco data repo" in result.stdout


def test_init_scaffolds_a_bilingual_repo(tmp_path, monkeypatch):
    _git_env(monkeypatch)
    target = tmp_path / "my-cv"

    # first, last, variant(default), language choice(3=both),
    # title_en, title_fr, email, phone(skip), homepage(skip), currency, confirm
    result = runner.invoke(
        app,
        ["init", str(target)],
        input="Jane\nDoe\n\n3\nAssociate Professor\nProfesseure agrégée\njane@example.edu\n\n\nCAD\ny\n",
    )

    assert result.exit_code == 0, result.stdout
    assert (target / "profiles" / "_academic.yaml").is_file()
    assert (target / "profiles" / "academic-en.yaml").is_file()
    assert (target / "profiles" / "academic-fr.yaml").is_file()


def test_init_aborts_when_confirm_declined(tmp_path, monkeypatch):
    _git_env(monkeypatch)
    target = tmp_path / "my-cv"

    result = runner.invoke(
        app,
        ["init", str(target)],
        input="Jane\nDoe\n\n1\nAssociate Professor\njane@example.edu\n\n\nCAD\nn\n",
    )

    assert result.exit_code == 0
    assert "Aborted" in result.stdout
    assert not (target / "parco.yaml").exists()


def test_init_refuses_before_prompting_if_repo_already_exists(tmp_path, monkeypatch):
    target = tmp_path / "existing"
    target.mkdir()
    (target / "parco.yaml").write_text("currency: {default: CAD, report: CAD}\n")

    result = runner.invoke(app, ["init", str(target)])

    assert result.exit_code == 1
    assert "already exists" in result.stdout


def test_init_defaults_to_the_current_directory(tmp_path, monkeypatch):
    _git_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["init"],
        input="Jane\nDoe\n\n1\nAssociate Professor\njane@example.edu\n\n\nCAD\ny\n",
    )

    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "parco.yaml").is_file()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/integration/test_cli_init.py -v`
Expected: FAIL — no `init` command registered on `app` yet

- [ ] **Step 3: Add the `init` command to `parcours/cli/main.py`**

Add these imports (alongside the existing ones):
```python
from ..core.init import GitInitFailed, InitAnswers, RepoAlreadyExists, scaffold_repo
```

Append this command (before the `if __name__ == "__main__":` guard, or after the `build` command if there's no such guard):
```python
def _prompt_required(label: str) -> str:
    while True:
        value = typer.prompt(label).strip()
        if value:
            return value
        typer.echo(f"'{label}' is required.")


@app.command()
def init(
    path: Path = typer.Argument(None, help="Where to scaffold the new data repo (defaults to the current directory)"),
):
    """Interactively scaffold a brand-new parco data repo."""
    target = (path or Path.cwd()).expanduser().resolve()

    if (target / "parco.yaml").is_file():
        typer.echo(f"A parco data repo already exists at {target}.")
        raise typer.Exit(code=1)

    first_name = _prompt_required("First name")
    last_name = _prompt_required("Last name")
    variant_name = typer.prompt("Identity variant name", default="academic")

    typer.echo("Which language(s) do you want profiles for?")
    typer.echo("  1. English")
    typer.echo("  2. French")
    typer.echo("  3. Both")
    while True:
        choice = typer.prompt("Choice", default="1")
        if choice == "1":
            languages = ["en"]
            break
        if choice == "2":
            languages = ["fr"]
            break
        if choice == "3":
            languages = ["en", "fr"]
            break
        typer.echo("Not a valid choice.")

    title_en = _prompt_required("Headline/title (English)") if "en" in languages else ""
    title_fr = _prompt_required("Headline/title (French)") if "fr" in languages else ""
    email = _prompt_required("Email")
    phone = typer.prompt("Phone ([Enter] to skip)", default="", show_default=False)
    homepage = typer.prompt("Homepage ([Enter] to skip)", default="", show_default=False)
    currency = _prompt_required("Currency (e.g. CAD)")

    typer.echo("\nReview:")
    typer.echo(f"  Name: {first_name} {last_name}")
    typer.echo(f"  Identity variant: {variant_name}")
    typer.echo(f"  Language(s): {', '.join(languages)}")
    if title_en:
        typer.echo(f"  Title (EN): {title_en}")
    if title_fr:
        typer.echo(f"  Title (FR): {title_fr}")
    typer.echo(f"  Email: {email}")
    typer.echo(f"  Phone: {phone or '(skip)'}")
    typer.echo(f"  Homepage: {homepage or '(skip)'}")
    typer.echo(f"  Currency: {currency}")

    if not typer.confirm("Scaffold this repo?"):
        typer.echo("Aborted, nothing written.")
        raise typer.Exit(code=0)

    answers = InitAnswers(
        first_name=first_name,
        last_name=last_name,
        variant_name=variant_name,
        languages=languages,
        currency=currency,
        title_en=title_en,
        title_fr=title_fr,
        email=email,
        phone=phone,
        homepage=homepage,
    )

    try:
        scaffold_repo(target, answers)
    except RepoAlreadyExists as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)
    except GitInitFailed as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    typer.echo(f"\nInitialized a new parco data repo at {target}.")
    typer.echo("Next: `parco add <category>` to start entering data, "
               "`parco build --profile <name>` once you have some.")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/integration/test_cli_init.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full suite to verify everything passes**

Run: `pytest tests/ -v`
Expected: PASS (all tests across every task in every plan)

- [ ] **Step 6: Commit**

```bash
git add parcours/cli/main.py tests/integration/test_cli_init.py
git commit -m "Added the parco init command"
```

---

## What this plan deliberately does not cover

- `skills`'s aggregating (`group_by`) view — the category schema now exists (Task 2), but no view or generated profile section references it; unchanged from the `parco build` plan's own deferred scope.
- "Add missing pieces" to an existing repo — `init` is fresh-only in this first cut; refuses outright if `parco.yaml` already exists at the target.
- `--dry-run` — no preview-without-writing mode.
- Non-interactive `init` via flags — no `--name`/`--email`/etc. pre-fill mechanism (unlike `add`/`edit`'s `--field value` flags); the wizard always runs in full. A flag-driven non-interactive mode is a reasonable future addition, not built here.
- Any currency validation — `currency` is a free-text field written as-is into `parco.yaml`; no ISO-4217 checking.
- `parco query`/`parco stats`/`parco cite` — separate, not yet designed (tracked as the next plan after this one).
