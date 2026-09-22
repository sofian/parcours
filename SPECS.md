# Academic CV Data System — Design Spec

**Project name:** Parcours. **CLI command:** `parco` (short alias for
daily typing; the project/package identity stays "Parcours").

**Contents:** [Purpose](#purpose) · [Architecture overview](#architecture-overview)
· [Data layer](#data-layer) · [Category handlers](#category-handlers)
· [Category schemas (drafts)](#category-schemas-drafts) · [Labels / translations](#labels--translations)
· [vocab.yaml (draft)](#vocabyaml-draft) · [Identity / personal-info config](#identity--personal-info-config)
· [Profiles](#profiles) · [views.yaml (draft)](#viewsyaml-draft)
· [Citation formatting](#citation-formatting) · [Output formats](#output-formats)
· [Code architecture](#code-architecture-modular-core--thin-interfaces) · [Testing & CI](#testing--ci)
· [CLI](#cli) · [Backup / hosting](#backup--hosting)
· [Deferred / out of scope](#explicitly-deferred--out-of-scope-for-v1)
· [Design status](#design-status) · [Open questions](#open-questions-to-resolve-during-implementation)

## Purpose

A personal, portable system for maintaining academic/artistic CV data as
structured, git-tracked plain text, with a CLI to generate CV documents
(multiple versions/languages), run statistics/queries, format citations,
and eventually support a read-only chatbot interface over the same data.

Designed for one user (Sofian Audry) but intended to be reusable by other
academics — no hardcoded assumptions specific to one person's data should
live in code; category lists, vocab, and profiles are all config.

---

## Architecture overview

```
CSV files (source of truth, git-tracked)
     │
        ▼
   DuckDB (SQL queries run directly on CSVs, no import step)
        │
        ├──► RenderCV (YAML) ──► LaTeX/PDF/Typst/HTML   (parco build)
        ├──► Pandoc            ──► DOCX                  (parco build --format docx)
        ├──► citeproc + CSL    ──► formatted citations   (parco cite)
        ├──► SQL result tables ──► stats / ad-hoc queries (parco stats / parco query)
        └──► (future) MCP-DuckDB server ──► chatbot querying (read-only)
```

Zotero (with Better BibTeX auto-export) is the canonical source for full
bibliographic metadata; the publications CSV holds a citekey linking to it
plus CV-specific fields Zotero doesn't track.

---

## Data layer

- **Format:** plain CSV, UTF-8, one file per category (e.g.
  `publications.csv`, `grants.csv`, `artworks.csv`, `students.csv`).
  Chosen over YAML/ODS for portability, git-diffability, and native
  spreadsheet-app editability.
- **No cross-references between tables for v1** (explicit decision — no
  foreign keys, no relational joins between e.g. publications and grants).
- **IDs:** a bare 6-hex-character random token (e.g. `a3f9c2`), generated
  by `parco add` via Python's `secrets` module and re-rolled on the
  (astronomically unlikely) collision against existing ids already in
  that category's CSV. No category prefix and no year: the category is
  already established by which CSV the row lives in and is always shown
  alongside the id in any output (lint issues, error messages), so a
  prefix would be redundant; a year would misleadingly suggest the id
  encodes the entry's own date rather than just when it was created.
  Exists for internal stability (git history, future cross-referencing)
  — users never need to type or remember them; all interaction is via
  substring search (`parco edit publications --search "..."`).
- **Controlled vocabularies:** `vocab.yaml` — one list per constrained
  field (`publication_type`, `publication_status`, `grant_role`,
  `degree_status`, etc. — see the full compiled draft under vocab.yaml,
  after Category schemas). Enforced at write time (`add`/`edit` reject
  invalid values) and re-checked by `parco lint`.
- **Bilingual fields:** paired `_en`/`_fr` fields for content that's
  genuinely translated (most category titles are proper nouns and
  aren't — see `require_one_of` under Category schemas).
- **Status field is required for publications** — see `publication_status`
  in vocab.yaml (draft) — and determines what's CV-ready vs. in-progress.
- **Explicitly out of scope for v1:** cross-references/foreign keys,
  CRediT contributor roles, media/image attachments.
- **Categories (v1):** nineteen — publications, grants, artworks,
  students, teaching, service, outreach, presentations, press, review,
  catalog, education, positions, recognitions, exhibitions, curatorship,
  residencies, software, skills. All drafted (see Category schemas);
  each category's schema is a config file, not code.
- **Data repo discovery:** `parco` operates on a data repo separate from
  the code repo. It searches upward from the current directory for a
  marker file (`parco.yaml`), falling back to a path stored in
  `~/.config/parco/config.yaml`. `--data-dir` / `PARCO_DATA_DIR`
  override both. Auto-commit and sync act on the data repo.

## Category handlers

All categories are on equal footing: each is defined by a schema file in
the data repo, and none is special-cased in the core. What differs is
the **handler** — a module named in the schema (`handler: generic`, the
default) that defines how the category handles its fields. The tool ships
two: `generic` (used by most categories) and `publications` (citekey /
Zotero / citation behavior, DOI+fuzzy-title dedup, CSL `type_map`). A
schema may also name a custom handler by dotted import path
(`handler: mypackage.handlers:Residencies`).

- **A handler owns:** extra field validation beyond required/vocab checks,
  dedup matchers (the `generic` handler reads the declarative `dedup:`
  rules from the schema; `publications` implements DOI/citekey + fuzzy
  matching itself), defaults for the wizard, and the mapping to
  view/RenderCV entry fields.
- **Optional capabilities:** a handler may expose extra operations.
  `parco cite` and `parco refresh zotero` operate on whichever
  categories' handlers provide the capability, rather than naming
  `publications` in the core. Importers/refreshers likewise name their
  target category in config.
- **Zotero-citekey resolution is a shared capability, not exclusive to
  `publications`.** Any category whose schema declares a `citekey`
  field plus Zotero `options` (bib/json paths) gets it resolved against
  the export and becomes `Citable` — this is how `press` optionally
  links a row to its Zotero record without needing its own handler.
- **The `publications` handler is reused by categories other than
  `publications`.** `review` and `catalog` also use
  `handler: publications` — not just the shared citekey capability, but
  its full behavior (citekey required and must always resolve,
  DOI+fuzzy-title dedup) — because a review of your work or a catalog
  featuring it is authored by someone else, not you, so it doesn't
  belong in your own `publications` table, but is exactly as
  Zotero-linked. The handler's CSL `type_map` → `type` derivation is
  **optional**: it only runs when a schema declares both `options.type_map`
  and a `type` field, which `review`/`catalog` don't (they need no
  further subdivision; the category itself says what they are).
- **Interface stays interface-free:** handlers live in the core layer, so
  they never prompt or print. They describe the fields the wizard should
  ask about, return structured validation and dedup results, and raise
  typed exceptions. The CLI does all asking.
- **Required fields are per-field schema config**, not handler code —
  e.g. `status` is a required field in the publications schema rather
  than a rule baked into the core.
- **Trust boundary:** custom handlers are resolved as importable Python
  modules only. `parco` never auto-executes code found in the data repo.
### Handler interface (draft)

A base class whose defaults are the generic behavior, plus separate
`runtime_checkable` Protocols for optional capabilities, discovered with
`isinstance` (so `parco cite` finds any handler that is `Citable`):

```python
class CategoryHandler:                        # generic behavior by default
    def __init__(self, schema, context): ...   # context: data dir + schema `options:`
    def field_specs(self, entry=None): ...     # what the wizard should ask; edit pre-fills
    def validate(self, entry): ...             # -> list[LintIssue]
    def find_matches(self, entry, existing):   # -> list[Match(kind=duplicate|related, ...)]
    def view_rows(self, view, rows): ...       # -> rows mapped to RenderCV entry fields

class Citable(Protocol):    def citation(self, key, style, lang) -> str
class Importable(Protocol): def plan_import(self, source, options) -> ImportPlan
```

Handler options (e.g. export paths) live in the schema's `options:` block.

## Category schemas (drafts)

One file per category at `categories/<name>.yaml` in the data repo.
Field keys: `name`, `type` (`string` default, `int`, `number`, `bool`,
`text`, `date`), `required`, `vocab`, `default`, `generated`,
`precision` (`date` fields only). `date` fields always hold ISO
partial dates (`2024`, `2024-09`, `2024-09-30`) — `precision` sets the
**minimum** acceptable granularity (`year`, `month`, or `day`), never a
maximum: a field declared `precision: year` still accepts a full
`2024-09-30` if you happen to know it, it just doesn't require one. The
wizard asks for a date at the field's minimum granularity and offers to
go more precise (year → month → day) rather than demanding a fixed
format, since real recall is uneven — some dates you'll remember to the
day, most only to the year.

**Dedup rules** (used by the `generic` handler): each rule is a list of
conditions that must all hold, plus an outcome (`duplicate` or
`related`). Matchers: `exact` (field), `fuzzy` (one or more fields;
matches if any does), `overlap` (start and end date fields, compared as
intervals; a blank end is ongoing), `same_year` (one date field; for
categories with a single point-in-time date rather than a range).

**`require_one_of`** (schema-level, alongside `fields`/`dedup`): a list
of field-name lists, each requiring **at least one** field in that
list to be non-blank, without forcing all of them. This is for content
that's often genuinely single-language rather than translated — most
artwork/exhibition titles are proper nouns given in whichever language
they were made or shown in, not translated pairs — as well as fields
like an exhibition's `event`/`venue`, which aren't always both tracked.
This is **distinct from `labels.csv`'s "missing translation = fail
loudly" rule** (see Labels / translations below): that rule is about a
small, finite set of UI-facing strings (section names, vocab value
labels) that genuinely should exist in both languages, not about
per-row content fields on category data, where forcing both sides
would mean inventing translations that don't really exist. `lint` warns
only if **no** field in a `require_one_of` group is filled — not if
only one is.

**`weight`** (a standard optional `int` field, present in every schema
right after `id`): a manual ordering hint, higher = appears earlier.
Not every CV entry has a precise date — decades-old material especially
often has only a rough date, or none at all — but the *relative order*
between entries is usually still known (e.g. from where they sat in a
previously hand-maintained CV document). `weight` captures that
knowledge explicitly rather than relying on CSV row order, which isn't
reliably preserved through edits. `order_by` in profiles/views can
reference it as a tiebreaker alongside date-based ordering (e.g.
`order_by: date desc, weight desc`), or, for `skills` (which has no
dates at all), as the only ordering mechanism.

### CCV export structure (documented from a real export)

Grounds the CCV importer (see Import, under CLI) and every category
schema that mirrors it, below. The Tri-agency "generic CV" XML export
(`xmlns="http://www.cihr-irsc.gc.ca/generic-cv/1.0.0"`) is not a flat
per-category file — it is a tree of `<section>` elements, and **a record
is any `<section>` that carries a `recordId` attribute**, regardless of
nesting depth (some, like grants, are direct children of the root; others,
like publications, sit several wrapper-levels down, e.g. root →
Contributions → Publications → Journal Articles → record). The importer
walks the whole tree and treats every `recordId`-bearing section as one
record, using its chain of ancestor `label`s to identify its type. Inside
a record, `<field label="…">` values appear as plain text on
`<value type="String"|"Number"|"Year"|"YearMonth">` (dates as `yyyy` or
`yyyy/MM`, matching our `precision: year`/`month`), as `<lov>` (CCV's
own controlled-vocabulary display string, needing a translation table
into our `vocab.yaml`, the same pattern as the Zotero `type_map`), or as
`<refTable refValueId="…">` — a reference into CCV's own institution
database, resolved via nested `<linkedWith label="Organization"
value="…">` children (also carrying `Country`/`Subdivision`/
`Organization Type`), **not** by the `refTable` element's own text,
which is always empty.

Bilingual fields (`<field><value type="Bilingual">…`) have **two forms
on the wire**, and an importer must check both: the text can be split
into a sibling `<bilingual><french>text</french><english>text</english>
</bilingual>` element, **or** it can sit directly on the `<value
type="Bilingual">` element itself as one unsplit blob (used when
someone entered the field without the language-split UI). Checking only
the split form silently misses real content.

No CCV-specific parsing library is used — this is plain XML, parsed
with `lxml`/`ElementTree`; the CCV-specific knowledge (the section-label
paths and field mapping below) lives in one importer module
(`core/import_ccv.py`), not spread through the core.

Category ↔ CCV section mapping found by inspecting a real export:

| Category | CCV path |
|---|---|
| publications | Contributions → Publications → {Journal Articles, Conference Publications, Books, Book Chapters, Reports, Online Resources, Thesis/Dissertation, Magazine Entries} |
| grants | Research Funding History (each nests one Funding Sources record for funder/amount/currency) |
| artworks | Contributions → Artistic Contributions |
| students | Activities → Supervisory Activities → Student/Postdoctoral Supervision |
| teaching | Activities → Teaching Activities → Course Development |
| service | Activities → Assessment and Review Activities (→ Graduate Examination Activities, Research Funding Application Assessment Activities), Community and Volunteer Activities, Memberships, Teaching Activities → Program Development |
| outreach | Activities → Knowledge and Technology Translation |
| presentations | Contributions → Presentations |
| press | Contributions → Interviews and Media Relations (→ Broadcast Interviews, Text Interviews) |
| review | *(none — Zotero-only; CCV tracks your own contributions, not third-party reception of them)* |
| catalog | *(none — Zotero-only, same reasoning as `review`)* |
| education | Education → Degrees |
| positions | Employment → Academic Work Experience, Non-academic Work Experience, Affiliations |
| recognitions | Recognitions |
| exhibitions | *(none)* |
| curatorship | *(none)* |
| residencies | *(none)* |
| software | *(none)* |
| skills | *(none)* |

`service` and `outreach` were split from a single "service" candidate
after comparing actual field shapes: Assessment/Review, Community and
Volunteer, and Memberships share one role+organization+date-range shape;
Knowledge and Technology Translation has a distinct impact/engagement
shape (target stakeholder, outcome, evidence of uptake) and enough
records (30 in the reference export) to warrant its own category.
Similarly, CCV's "Teaching Activities" wrapper contains two genuinely
different record types — `Course Development` (an actual course taught)
and `Program Development` (developing/reviewing a program — service,
not teaching, and distinct from the everyday running of a program) —
identified by each record's own `label`, not by field-shape guessing,
once it was checked directly. By contrast, CCV's `Broadcast Interviews`
and `Text Interviews` (both under "Interviews and Media Relations")
stay merged into one `press` category rather than being split like
`service`/`outreach` or `teaching`/`service` — they're the same kind of
activity (third-party coverage) with a minor field difference
(`program`, only meaningful for broadcast, is simply left blank for
text pieces) rather than a distinct shape or purpose.

### publications (handler: publications)

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

- The CSV holds only the citekey and CV-only fields. Title, authors,
  year, venue, DOI and CV `type` (via `type_map`) are read from the
  exported CSL-JSON and joined on the citekey when building views. This
  is a join between the CSV and the export, not between tables.
- **Every row's citekey must resolve in the export** — no local fallback
  fields. In-progress work is added to Zotero first (manuscript/preprint
  item types); `status` tracks the stage. `lint` flags unresolved keys.
- Zotero's exports are the pair of files Better BibTeX keeps in sync
  (BibTeX for citekeys, CSL-JSON for full metadata). No live Zotero
  connection is needed. The export location is configurable (there is no
  fixed default); files inside the data repo are versioned and synced
  with it, files outside are not.
- **Dedup:** same citekey already in the CSV → `duplicate`; different
  citekey with the same DOI as an existing row → `duplicate` (usually a
  doubled Zotero item); fuzzy title + same year → `duplicate` (weaker
  secondary signal).
- **Wizard:** `add publication` lists exported items not yet in the CSV
  for you to pick, then asks for status and the flags. It never asks you
  to type a title.

### grants (handler: generic)

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

- Views resolve `title` to `title_en` / `title_fr` from the profile's
  language, so profiles never mention suffixes. A blank required `_fr` or
  `_en` field is a lint error (missing translation).
- Amounts are stored, which is one reason the data repo is private.
  Converted amounts are described under Currency conversion below.
- RenderCV mapping (in `views.yaml`): a grant becomes a `NormalEntry` —
  title as name, date range as date, funder/role/amount as highlights.

### service (handler: generic)

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

- `type` unifies CCV's Graduate Examination Activities, Research Funding
  Application Assessment Activities, Community and Volunteer Activities,
  Memberships, and Program Development — one shared shape, several
  type-specific values. `manuscript-review` and `committee` are included
  even though the reference export has no such records, since they're
  real, distinct service activities:
  - **`committee`** — ongoing institutional committee membership of any
    kind (hiring, program, tenure, curriculum, admissions, …), one type
    rather than a new vocab value per committee kind, with the specific
    committee named in `detail`.
  - **`program-development`** — developing or reviewing a program
    (a bounded activity, distinct from ongoing `committee` membership;
    CCV's actual "Program Development" records map here, e.g. role
    "Member of the program revision committee").
- `Number of Applications Assessed` and `Funding Organization` (from
  CCV's funding-review fields) are dropped — the latter duplicates
  `organization`, and the former isn't worth a field.
- `program-development` (from CCV's Program Development records, filed
  under CCV's "Teaching Activities" wrapper but service in substance —
  see CCV export structure) uses CCV's "Date First Taught" field as
  `start_date` — a mislabeled field for this record type, an artifact of
  the shared CCV wrapper — with `end_date` left blank, since CCV doesn't
  track when this kind of review work ended. Program title and
  description fold into `detail`.

### outreach (handler: generic)

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

- `activity_type` and `target_stakeholder` are small, CCV-controlled
  lists (5 distinct values each in the reference export) — good vocab
  candidates, unlike `organization`.
- CCV's `Outcome / Deliverable` and `Evidence of Uptake/Impact` fields
  (bilingual; 30/30 and 22/30 filled in the reference export
  respectively) are dropped, along with the earlier note about keeping
  them separate rather than merged — not tracked here.

### artworks (handler: generic)

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

- `title_en`/`title_fr` were originally both `required: true`; loosened
  to `require_one_of` (see Category schemas above) once it became clear
  most artwork titles are proper nouns in one language only, and forcing
  a translation would mean inventing one.
- `role` is vocab-constrained to just `author`/`collaborator` — CCV's
  actual values (Author, Auteur, Artist, Principal investigator,
  Collaborator, Artist collaborator) collapse to those two on import
  (`Auteur`/`Artist`/`Principal investigator` → `author`; `Artist
  collaborator` → `collaborator`).
- CCV's `Title of Work` is a single field, not bilingual — import fills
  whichever of `title_en`/`title_fr` matches the export's language and
  leaves the other blank, which is fine given `require_one_of` above.
- No separate medium/type field: CCV has none, and the bilingual
  `description` carries whatever detail is needed instead.
- `Number of Contributors` is dropped — blank in 53 of 56 reference
  records, and derivable from `contributors` anyway.
- `venue` is dropped — not tracked here.
- `date` is the **production year**, not a performance/exhibition date —
  `precision: year` (a floor, not a ceiling, per Category schemas above:
  a more precise date is still fine if known, just not required).

### students (handler: generic)

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

- **Dedup is `related`, not `duplicate`** — a repeat student name flags
  "existing person, new record" (e.g. a new degree), never a hard
  duplicate.
- `degree_status` is what the original spec called `student_outcome` —
  renamed to match the actual CCV field
  (`completed`/`in-progress`/`withdrawn`/`all-but-degree`).
- `thesis_title` is a single, untranslated field — a thesis title isn't
  translated, unlike some other single-CCV-field titles elsewhere.
- **Dropped:** CCV's `Degree Name` and `Specialization` (bilingual,
  near-empty in the reference export, redundant with `degree_type`),
  `Degree Expected Date` (sparse; a blank `degree_end_date` already
  conveys "still in progress"), `Student Canadian Residency Status`, and
  `Project Description` (bilingual).

### teaching (handler: generic)

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

- **One row per offering, not per course** — the same `course_label`
  legitimately repeats across rows for different years it was taught
  (e.g. 2022, 2023, 2025). `same_year` in the dedup rule catches an
  accidental re-entry of the same year without flagging genuine repeat
  offerings.
- CCV's "Course Development" records are the source (not "Program
  Development", which is service work — see the `service` schema); CCV
  itself only records one date per course record ("Date First Taught"),
  so importing multiple years taught, beyond the one CCV gives, is a
  manual follow-up, not something the importer can do alone.
- `description_en`/`description_fr` and `level` (undergraduate/graduate)
  are dropped, despite being present in CCV, as not worth tracking here.

### presentations (handler: generic)

```yaml
name: presentations
handler: generic
fields:
  - {name: id,        generated: true}                                  # presentation-2026-004
  - {name: weight,    type: int}                                        # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: title_en}
  - {name: title_fr}                                                    # usually only one filled
  - {name: event,     required: true}                                   # Conference / Event Name, free text
  - {name: location,  required: true}                                   # city + country as one glossary-backed value, e.g. "Berlin, Germany"
  - {name: invited,   type: bool}
  - {name: keynote,   type: bool}
  - {name: date,      type: date, precision: month, required: true}     # at least year+month, like grants.start_date
  - {name: description_en}
  - {name: description_fr}
  - {name: co_presenters}                                                # free text names list
  - {name: url}
require_one_of:
  - [title_en, title_fr]
dedup:
  - when: [{fuzzy: [title_en, title_fr]}, {same_year: date}]
    as: duplicate
```

- `date`'s `precision: month` requires at least year+month (a bare year
  is rejected), matching `grants.start_date` — a floor, not a ceiling
  (see Category schemas above), so a full day is still fine if you know
  it. CCV's own `Presentation Year` field is year-only, so import writes
  a value below this floor; those rows need the month filled in by hand
  (flagged by `lint`, same treatment as any other required-field gap
  from a path that bypasses the wizard).
- `title` follows the artworks pattern: CCV's single `Presentation
  Title` splits to `title_en`/`title_fr`, import fills the matching side
  and leaves the other blank — `require_one_of` covers the common case
  where only one language is ever given.
- **`location` was originally two fields** (a country and a city,
  matching CCV's own split) — collapsed into one after settling how
  place names get translated (see Labels / translations): a single
  glossary-backed value covers both parts together as one unit (e.g.
  "Berlin, Germany" / "Berlin, Allemagne"), which also correctly
  handles cities whose name itself changes between languages (e.g. The
  Hague / La Haye), which a separate city+country split couldn't. CCV's
  fixed internal country list is not replicated in `vocab.yaml` — the
  glossary approach makes that unnecessary. `"Online"` (one of CCV's
  actual location values) is simply literal fallback text, no glossary
  entry needed.
- `Competitive?` is dropped — blank in 44 of 45 reference records.
- `Main Audience` (CCV's `researcher`/`knowledge-user`/`general-public`
  list) is dropped — not tracked here.

### press (handler: generic)

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

- No `type` field for now — CCV's Broadcast/Text distinction is
  captured well enough by `program` being blank for text pieces, without
  needing a controlled value; can be added later if needed.
- `outlet`/`program` split mirrors CCV's own `Network`+`Program` (kept as
  two fields rather than merged, unlike the earlier draft), with
  `outlet` also covering CCV's `Forum` for text pieces (a text piece has
  no `Program` equivalent, so it's left blank).
- CCV's `End Date` (Broadcast Interviews only) is dropped — checked
  against all 3 reference records and always identical to `First
  Broadcast Date`, i.e. not a real range.

### review (handler: publications)

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

A review of your work, authored by someone else — same shape as
`publications` (title/authors/venue/year read from Zotero via citekey,
DOI+fuzzy-title dedup), just a different table, since these aren't your
own authored output. No CCV equivalent (CCV tracks your own
contributions, not third-party reception of them) — Zotero-only.

### catalog (handler: publications)

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

An exhibition/museum catalog that documents your work as part of an
exhibition or body of work, generally not authored (or co-authored) by
you. Same reasoning and handler reuse as `review`. No CCV equivalent.

### education (handler: generic)

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

- `degree_type`/`degree_status` deliberately reuse the same vocab lists
  as `students.degree_type`/`students.degree_status` — same real-world
  concept (degree types and outcomes), just applied to you instead of
  someone you supervised, so one `vocab.yaml` entry serves both schemas.
- `degree_name` and `specialization` are kept as two fields, matching
  CCV, even though the CV typically renders them combined (e.g.
  "Humanities (Fine Arts)") — that combination is a `views.yaml`
  rendering concern, not a schema one.
- **Dropped:** CCV's `Other Organization`/`Other Organization Type`
  (organization resolves via `refTable`), `Degree Expected Date`
  (mirrors the same drop in `students`), and "Transferred to PhD
  without completing Masters?" — all blank across all 5 reference
  records.
- `advisor` is free text (not structured per-person), consistent with
  how other schemas keep named collaborators as plain text rather than
  their own rows.

### positions (handler: generic)

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

- One category unified with a `type` (academic/non-academic/affiliation),
  the same unify-with-type pattern as `service`/`outreach`. CCV's
  `Leaves of Absence` record type is **not** included — only 1 reference
  record, and it's a genuinely different shape (a sabbatical, not a
  position held) not worth building for now.
- `organization` is free text rather than resolved-only-via-`refTable`
  — checked against the data: non-academic and affiliation rows almost
  always use CCV's free-text `Other Organization` field instead (Hexagram,
  mXlab, Perte de Signal, Koumbit aren't in CCV's institution list), so
  the importer should read whichever CCV field actually has a value.
- `faculty` and `department` are kept as two separate fields rather
  than merged — checked against the data: both are filled
  *simultaneously* in the same academic records (11/11 and 7/11), so
  merging would lose information genuinely present at once, the same
  reasoning as `outreach`'s outcome/evidence fields.
- **Dropped:** `Academic Rank`, `Tenure Status` and tenure dates, and
  `Work Description`/`Activity Description` (bilingual highlights) —
  the latter is 0% filled across all 26 reference records regardless of
  type, meaning CCV never carries this text even though the LaTeX CV's
  professional-experience entries are full of it; that text would need
  manual entry either way, so it isn't a CCV-import gap, just a field
  this schema doesn't track.
- `title` is bilingual (`title_en`/`title_fr`) for every row, even
  though CCV's academic/non-academic subtypes use a single string
  (`Affiliations` is already bilingual in CCV) — matches the pattern
  used for `education`/`artworks`/`presentations`.

### recognitions (handler: generic)

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

- `recognition_type` (Citation/Distinction/Prize-Award) is a small,
  confirmed set from the reference export (all 7 records fall into one
  of three values).
- `end_date` and `amount`/`currency` are only set together, and only for
  3 of the 7 reference records — the ones that are effectively
  fellowship-like awards with a disbursement period (a postdoctoral
  fellowship, a doctoral award, an entrance scholarship), as opposed to
  a one-time citation/mention with neither. `amount`/`currency` follow
  the same shape as `grants`, so the same currency-conversion machinery
  (see Currency conversion) applies without change.
- `description_en`/`description_fr` are genuinely used (7/7 in the
  reference export, once the bilingual-extraction bug above was fixed)
  — unlike `positions`, where the equivalent field really was unused.
- `role` defaults to `recipient` so it rarely needs setting; `educator`
  is the one real exception the LaTeX CV shows (an award given to a
  student you supervised, with you credited as their mentor).
- `organization` follows the same free-text-with-refTable-or-fallback
  pattern as `positions`/`education`, since CCV again mixes the two
  sources across records.

### exhibitions (handler: generic)

No CCV equivalent — grounded entirely in the LaTeX CV.

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
  - {name: location,     required: true}                             # city + country as one glossary-backed value
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

- `location` is one glossary-backed value covering city and country
  together (see Labels / translations), not separate fields.
- Scoped strictly to exhibitions **you exhibited in** — no `role`
  field; a separate `curatorship` category below covers when you were
  the curator instead.
- Modeled as a **date range** (`start_date`/`end_date`), not a single
  point in time like `artworks` — the LaTeX source's own comments show
  real multi-month exhibition runs (e.g. a show spanning several
  months), unlike a single performance date.
- `event`/`venue` are kept separate (a festival like MUTEK is not the
  same thing as the gallery hosting a given show within it) but neither
  is individually required — `require_one_of` covers the common case
  where historically only one was tracked.
- `title_en`/`title_fr` use the same `require_one_of` treatment as the
  (now-corrected) `artworks` schema, for the same reason.

### curatorship (handler: generic)

Same shape as `exhibitions` — a curated show is still an exhibition,
just one where you're credited as curator rather than as the exhibiting
artist, so it gets its own table rather than a `role` field mixed into
`exhibitions`.

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
  - {name: location,     required: true}                             # city + country as one glossary-backed value
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

### residencies (handler: generic)

No CCV equivalent. Simpler than `exhibitions` — every LaTeX entry is
just organization + place + year(s), no title/curator/event needed (the
organization name doubles as the program name).

```yaml
name: residencies
handler: generic
fields:
  - {name: id,           generated: true}                       # res-2026-004
  - {name: weight,       type: int}                             # optional; higher = appears earlier, refines/overrides date-based ordering
  - {name: organization, required: true}                        # free text — e.g. "Hexagram", "LABoral"
  - {name: location,     required: true}                         # city + country as one glossary-backed value
  - {name: start_date,   type: date, precision: month, required: true}
  - {name: end_date,     type: date, precision: month}           # blank = short/undated residency
dedup:
  - when: [{exact: organization}, {overlap: [start_date, end_date]}]
    as: duplicate
```

### software (handler: generic)

No CCV equivalent, grounded in the LaTeX CV's "Software development"
section (6 entries).

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

- `title` is a single field, not `title_en`/`title_fr` — a project
  name like "Plaquette" or "MapMap" doesn't get translated, unlike
  `description`, which genuinely is bilingual in all 6 reference
  entries (unlike `artworks`/`exhibitions`, where titles are the
  untranslated part and descriptions are the bilingual part — the
  opposite split, but the same underlying principle: only translate
  what's actually written in two languages).
- `role` is confirmed from the user's own `.trsl` glossary: exactly
  `Lead developer`/`Co-developer`/`Developer`/`Contributor`, no other
  values in decades of entries.
- `url` is set for 3 of 6 reference entries (the singular, nameable
  projects); the other 3 (a general "several libraries for Arduino"
  entry, a list of contributed-to frameworks) don't have one clean URL,
  which is fine since it's optional.

### skills (handler: generic)

No CCV equivalent found. One row per skill, not per skill-group —
the quirk is that some content translates (expertise areas, spoken
languages, soft-skill notes) and some doesn't (programming languages,
frameworks, platforms, software names — "Python" is "Python" in French
too).

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

- No separate untranslated `name` field — since `require_one_of`
  already means only one side needs filling, an untranslated technical
  term (e.g. "Python") just goes in `name_en` and leaves `name_fr`
  blank, rather than needing a third field for that case.
- No dates — unlike every other category, skills aren't dated CV
  entries, so `weight` is the *only* ordering mechanism here (elsewhere
  it refines or overrides date-based order; here it's the whole story),
  matching how the original LaTeX lists them in a curated,
  non-alphabetical order.
- `level` only applies to `spoken-language` rows; blank otherwise.

**identity/personal-info config (not a CSV category)**: needed
regardless of category count — see Identity / personal-info config,
below Labels / translations, for the confirmed design (name, alias,
address, phone, email, title, with three variants: artist/
job-application/academic).

### Currency conversion

Amounts can be converted to a reporting currency, mainly for statistics.

- **Config:** `parco.yaml` has `currency: {default: CAD, report: CAD}`.
  `default` pre-fills the wizard's `currency` field; `report` is the
  currency statistics convert into. Both are configurable.
- **Rates are reference data, not a category:** a tracked `rates.csv` in
  the data repo (`month, from, to, rate`), like `labels.csv`. No wizard,
  no dedup.
- **Source:** the ECB's published historical euro reference-rate file
  (42 currencies against the euro, since 1999). `parco` downloads it,
  averages the daily rates per month, and writes monthly rows to
  `rates.csv`; cross-rates between two non-euro currencies are computed
  as `amount / rate_from × rate_to`. No conversion library is used —
  conversion has to run as a SQL join in DuckDB, and rates must be
  versioned in the data repo rather than embedded in a package.
  Currencies outside the ECB list are unsupported in v1.
- **Fetched on demand by whatever needs it:** `stats`, `build` and
  `query` (anything that reads a converted `amount_<report>` value)
  fetch before computing if a needed (currency, month) rate is missing,
  then proceed. Since the source is one bulk historical file rather than
  a per-date API, a fetch redownloads it, recomputes all monthly
  averages, and appends any new **complete months** not already in
  `rates.csv` — existing rows are never rewritten, so numbers already
  computed cannot change. New rates auto-commit to the data repo
  (`Updated exchange rates`). `parco refresh rates` runs the same fetch
  explicitly, with no other command involved.
- **`parco lint` stays network-free:** it only warns for each grant whose
  start month has no rate for its currency and names the grants — it
  never fetches. This keeps `lint` fast and reproducible for CI (see
  Testing & CI). `stats`/`build` print a one-line notice if, after
  fetching, an amount is still missing (e.g. the month hasn't ended yet),
  so totals are never silently understated.
- **Core boundary:** fetching lives in core as a function that returns a
  structured result (rows added, failure reason); the CLI reports it.
  Tests mock the HTTP call.
- **Convention:** a grant is converted at the monthly rate for its
  `start_date` month (always defined, since `start_date` is required and
  month-precise). One rate per grant; the amount is not spread across
  the term.
- **Lookup:** a core `convert(amount, from, to, month)` function, plus a
  derived `amount_<report>` column (e.g. `amount_cad`) in the `grants`
  view, computed by joining on (currency, month) in DuckDB. Like the
  Zotero join, this is a join with reference data, not between tables.
- **Missing rates:** the converted value is blank (NULL) and `parco lint`
  warns — surfaced at the sync lint gate. Nothing is guessed or
  estimated; it resolves automatically next time a rate-needing command
  runs after the month ends and ECB publishes (or immediately via
  `parco refresh rates`).

## Labels / translations

- `labels.csv` — flat lookup table for **all** UI-facing strings, not just
  section titles: section names, field labels, category value labels.
  Fields: `id, category, en, fr` (category distinguishes e.g. `section`
  vs `role` vs `pub-type` so the flat table stays organized).
- **Missing translation = fail loudly** (or at minimum warn), never
  silently fall back to another language — checked by `parco lint`. This
  rule applies to `labels.csv`'s own finite set of UI-facing strings; it
  does **not** apply to per-row content fields on category data (see
  `require_one_of` under Category schemas), where a missing translation
  is often not an oversight at all.
- **`labels.csv` also serves as a content glossary**, not just UI chrome
  — e.g. `category: location` rows translate a whole place name in one
  unit (id `the-hague`: en "The Hague, Netherlands", fr "La Haye,
  Pays-Bas"), the same pattern as the user's existing LaTeX `\gtr{}`
  glossary. Any category's `location` field (see `exhibitions`,
  `curatorship`, `residencies`, `presentations`) is looked up against
  these rows when rendering; an unmatched value (an obscure place with
  no glossary entry) falls back to the literal text as typed — the
  glossary is an enhancement, never a requirement, so entering an
  unrecognized place never blocks data entry. This is why the "missing
  translation" lint rule above doesn't extend to these fields: most
  places will never have a glossary entry, and that's expected, not an
  error.

## vocab.yaml (draft)

Compiled from every `vocab:` reference across the 19 category schemas.
Two lists were found to disagree between two schemas that are meant to
share them (`degree_type`, `degree_status` — `students` vs. `education`
had drifted to slightly different comment text over the course of
drafting); reconciled here to one canonical list each, used by both.
Values are the union of what real CCV data showed, kept even where only
one schema's reference records happened to use them.

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

Notes on values not directly lifted from a CCV `lov` list:

- `publication_status` and `publication_type` predate the CCV audit —
  `publication_type` is the CSL-type-derived list documented under
  `publications`'s `type_map`; `publication_status` keeps the original
  spec's four CV-readiness stages plus `in-press`, a real intermediate
  stage the original four didn't cover. `review`/`catalog` are excluded
  here since they moved to their own categories.
- `outreach_activity_type`/`outreach_stakeholder` are lightly
  generalized from the reference export's exact `lov` text (e.g.
  CCV's overly specific "Industry/Business-Medium (100 to 500
  employees)" collapses to `industry-business`, dropping the
  company-size qualifier — too granular for a personal CV tool, and
  not tracked anywhere else in this schema).
- `position_status` — `full-time`/`part-time` are confirmed from the
  reference export (4 and 7 records respectively); no third value was
  observed, so none is guessed here. `parco lint`/`vocab.yaml` are
  meant to be edited by hand as real gaps show up, so adding a value
  later (e.g. `casual`) is a one-line change, not a schema change.
- `recognition_type`'s `prize` collapses CCV's own `"Prize / Award"`
  label to one slug.
- `service_type`'s `manuscript-review` and `committee`'s `program-development`
  companion value have no reference-export record (see their schema
  notes) but are included as real, expected activities.

Not vocab-constrained even though `degree_type` might suggest it should
be: `organization`, `venue`, `location`, and other free-text fields
throughout — deliberately open, per each schema's own notes (too many
distinct real-world values to enumerate, e.g. every institution or
venue that's ever hosted something).

## Identity / personal-info config

Not a CSV category — a small singleton config, `identity.yaml` in the
data repo, holding what every CV needs regardless of section content:
name, alias, address, phone, email, homepage, and a job title. Grounded
in the LaTeX CV's own header, which has **three distinct variants**
(not one static block) depending on audience: artist-facing,
job-application, and academic/default — differing in email, address,
phone, and title.

```yaml
name:
  first: Jane
  last: Doe
alias: J. R. Doe               # shown as an "aka" note

variants:
  artist:
    email: contact@example.com
    homepage: example.com
    # no title — falls back to a generic "Curriculum Vitae" heading (from labels.csv), not a fake job title
  job-application:
    email: jobs@example.com
    homepage: example.com
    address_line1: "123 Example Street"
    address_line2: "Example City, EX"
    address_line3: "A1A 1A1 (Country)"
    phone: "+1 555-000-0000"
    title_en: "Associate Professor of Interactive Media"
    title_fr: "Professeure agrégée en Médias interactifs"
  academic:
    email: jane.doe@example.edu
    homepage: example.com
    address_line1_en: "456 Example Ave"
    address_line1_fr: "456 avenue Exemple"
    address_line2: "Department of Media, Example University"
    address_line3: "Example City, EX A2A 2A2 (Country)"
    phone: "+1 555-000-1111 ext 1234"
    title_en: "Associate Professor"
    title_fr: "Professeur agrégé"
```

(Real values — your own name, address, and contact info — go in the
actual `identity.yaml`, in the private data repo, not here.)

- Each `profiles/*.yaml` names which variant to use (e.g.
  `identity_variant: academic`) in its `meta` block.
- The rarer `\ifjss` legacy toggle in the LaTeX source (flipping to the
  birth name as primary) is deliberately **not** modeled — it's
  commented out in the user's own source and adds real complexity for a
  case not currently in use.

## Profiles

- YAML config files, one per CV variant/language combination
  (`profiles/academic-en.yaml`, `profiles/short-fr.yaml`, etc.).
- Each profile has `meta` (name, language, format, RenderCV theme,
  `identity_variant`) and a `sections` list. Each section references a
  `source` (a named, fixed view over the data — never raw SQL in
  profile files), plus optional `filter` (simple key→value, not
  arbitrary SQL), `order_by`, `limit`, `group_by`, `citation_style`.
- Section `title` is **not** hardcoded per profile — resolved from
  `labels.csv` via the section's `id`, keyed to `meta.language`.
- **Views are defined in `views.yaml` in the data repo**, not in code.
  Each named view maps to a table, its fields, and a RenderCV entry
  type (see views.yaml (draft), below). The tool ships a starter
  `views.yaml`; no category names are hardcoded.

Example:
```yaml
meta:
  name: short
  language: en
  format: pdf
  theme: sb2nov
sections:
  - id: publications
    source: publications
    filter: { type: [journal-article], status: [published] }
    order_by: year desc
    limit: 10
    citation_style: apa
```

## views.yaml (draft)

RenderCV's actual entry types and fields, verified against the
installed package source (RenderCV 2.8), not assumed from memory:
`EducationEntry` (institution, area, degree, +dates/location/summary/
highlights), `ExperienceEntry` (company, position, +same), `NormalEntry`
(name, +same), `PublicationEntry` (title, authors, summary, doi, url,
journal, +date only — no start/end range), `OneLineEntry` (label,
details — no dates), `BulletEntry` (bullet), `TextEntry` (a raw
string, not a structured entry).

**Mechanism:** each view maps a category's fields onto one entry
type's fields. A field value is either a literal field name (direct
copy) or a `"{field}"` template string (composed/formatted). A bare
`{title}` in a template auto-resolves to `title_en`/`title_fr` — or
just `title` if the field isn't a bilingual pair — based on the
profile's own language, the same resolution `labels.csv` already uses;
this is the general rule for every bilingual field, not something each
view has to spell out.

Entry type per category:

| Category | Entry type | Notes |
|---|---|---|
| publications, review, catalog | `PublicationEntry` | title/authors/journal/doi from Zotero via citekey |
| grants | `NormalEntry` | highlights: funder+role, amount+currency, co_investigators |
| artworks | `NormalEntry` | single `date` (production year); highlights: role, contributors |
| students | `NormalEntry` | start/end = supervision dates; highlights: degree_type/status, institution, thesis_title |
| teaching | `ExperienceEntry` | company=organization, position=course_label+title; single `date` per offering |
| service | `ExperienceEntry` | company=organization, position=role; highlights: type, detail |
| outreach | `ExperienceEntry` | summary=outcome; highlights: evidence, description |
| presentations | `NormalEntry` | single `date`; summary=event; highlights: invited/keynote |
| press | `NormalEntry` | single `date`; highlights: author, program |
| education | `EducationEntry` | institution=organization, area=specialization, degree=degree_name; summary=thesis_title; highlights: advisor, note |
| positions | `ExperienceEntry` | company=organization, position=title; highlights: faculty, department, position_status |
| recognitions | `NormalEntry` | highlights: organization, amount+currency, description |
| exhibitions, curatorship | `NormalEntry` | highlights: event, venue, curator |
| residencies | `NormalEntry` | name=organization; no highlights needed |
| software | `NormalEntry` | summary=description; highlights: role, url |
| skills | `OneLineEntry` or `TextEntry` | **the one exception — see below** |

Worked example (`grants`):
```yaml
grants:
  source: grants
  entry_type: NormalEntry
  fields:
    name: "{title}"                        # resolves title_en/title_fr by profile language
    start_date: start_date
    end_date: end_date
    highlights:
      - "{funder} — {role}"
      - "{amount} {currency}"
      - "{co_investigators}"
```

**`skills` is the one view that isn't a flat row-to-entry mapping.**
Every other view is 1:1 (one CSV row → one rendered entry); `skills`
has several rows per `category` value that need aggregating into one
entry per category, via `GROUP BY category` in the view — the row-level
data (one skill per row, matching everything else's grain) and the
rendered shape (one line per skill group) genuinely differ here:

```yaml
skills-terms:                              # programming / framework / platform / software
  source: skills
  filter: { category: [programming, framework, platform, software] }
  group_by: category
  entry_type: OneLineEntry
  fields:
    label: "{category}"                    # resolved via labels.csv, e.g. "Programming"
    details: "{name_en, joined by ', '}"   # GROUP_CONCAT over the group's rows, in row order
skills-language:
  source: skills
  filter: { category: [spoken-language] }
  group_by: category
  entry_type: OneLineEntry
  fields:
    label: "Languages"
    details: "{name_en} ({level}), joined by ', '"
skills-text:                               # expertise / other
  source: skills
  filter: { category: [expertise, other] }
  group_by: category
  entry_type: TextEntry
  fields:
    text: "{name_en, joined by '; '}"       # or name_fr, by profile language
```

## Citation formatting

- Standard stack: **CSL** (style definitions) + **citeproc** (rendering
  engine, e.g. citeproc-py or Pandoc).
- **Zotero + Better BibTeX auto-export** keeps a `.bib`/CSL-JSON file
  continuously in sync on disk — no manual export step required.
- Publications CSV stores a citekey (linking to the Zotero/BBT record)
  plus fields Zotero doesn't track (CV-relevant flags). Grant
  association is deferred along with cross-references generally (see
  Explicitly deferred / out of scope for v1).

## Output formats

- **PDF/LaTeX/Typst/HTML** via **RenderCV** (YAML data → chosen theme).
- **DOCX** via **Pandoc**, converting RenderCV's Markdown output with a
  user-editable `reference.docx` for styling — some funding agencies
  require Word, not PDF. Pandoc is an external dependency (CI must
  install it on all three OSes).
- **Spike result (RenderCV 2.8 → Pandoc 3.11, a representative sample
  covering all entry types):** viable. Section/entry titles map to real
  Word `Heading 1`/`Heading 2` styles (restylable via `reference.docx`);
  bold/italic survive; DOI/URL links become real clickable Word
  hyperlinks, not plain text; highlight bullets use genuine Word list
  numbering (`w:numPr`), not literal dashes; numbered lists (patents,
  talks) renumber correctly even though RenderCV repeats `1.` for every
  item in the Markdown source; no stray empty paragraphs from the
  source's blank-line spacing; `OneLineEntry` (the shape `skills` uses)
  renders as one clean line — bold label, plain details.
  **One real limitation:** `EducationEntry`/`ExperienceEntry`/
  `NormalEntry`/`PublicationEntry` put each sub-field (location, date
  range, thesis/authors/DOI) on its own paragraph rather than composing
  them onto one compact line (e.g. "Princeton, NJ" and
  "Sept 2018 – May 2023" are two separate lines, not one joined by a
  separator) — content and structure are intact, but the DOCX reads
  more vertically spread out than a typical polished one-page CV.
  Acceptable for v1 as-is (funders generally need legible, correctly
  structured content, not a specific visual density); a cheap partial
  mitigation is a zero-space-after tweak on the `Body Text`/
  `First Paragraph` styles in `reference.docx`; a fuller fix (`parco`
  composing its own compact Markdown from view data instead of using
  RenderCV's literal `.md` file) is a bigger lift and a second render
  path to maintain — worth it only if a real funder submission is
  rejected or criticized for the spacing.

---

## Code architecture: modular core + thin interfaces

The CLI is one interface among several planned (CLI now; web API and/or
GUI later). To keep that possible without a rewrite, the codebase splits
into a **core library with no interface baked in**, and thin per-interface
clients that call into it.

- **Core layer never does interactive I/O** — no `print()`, `input()`,
  `sys.exit()`. Functions take structured arguments, return structured
  results, or raise typed exceptions (e.g. `DuplicateCandidates(matches=[...])`
  rather than printing a warning and prompting).
- **All prompting/confirmation/output formatting lives in the interface
  layer.** The wizard's step-by-step prompts, the duplicate-match picker,
  the "Sync anyway? [y/N]" confirmation — all CLI-only. A future web API
  would return the same structured data (e.g. duplicate candidates as
  JSON) and let its own frontend decide how to ask the equivalent
  question.
- **Test for the boundary:** could a web API return this as JSON, or a
  GUI show it as a dialog, without touching this function? If yes → core.
  If the function's whole job is asking the user something and reading
  their answer → interface-layer only.

```
parcours/
  core/
    data.py       # CSV/DuckDB access, queries
    entries.py    # add/edit/delete logic
    lint.py        # returns a list of LintIssue objects
    build.py         # profile → RenderCV YAML → rendered output
    cite.py            # citeproc wrapper
    sync.py              # git operations, remote reconciliation
    vocab.py               # loads/validates against vocab.yaml
    handlers/                # per-category behavior: generic.py, publications.py
  cli/
    main.py       # Typer app — thin, owns all prompts/printing
  web/            # future: FastAPI wrapping the same core functions
  gui/            # future: same core functions, different frontend
```

This is the standard hexagonal/ports-and-adapters pattern — no exotic
tooling required, just discipline about the boundary from day one.

## Testing & CI

- **pytest**, with unit tests against the core layer and integration
  tests against the CLI (using Typer's `CliRunner` to simulate input
  non-interactively).
- **All tests run against temporary, fixture-based CSVs/vocab/labels**
  — never real data. Core-layer tests never touch git or the real
  filesystem beyond a temp directory; sync/git tests use mocked git
  operations.
- Suggested layout:
  ```
  tests/
    unit/          # test_entries.py, test_dedup.py, test_lint.py,
                    # test_vocab.py, test_build.py, test_cite.py
    integration/   # test_cli_add.py, test_sync.py
    fixtures/      # sample_publications.csv, sample_grants.csv,
                    # vocab.yaml, labels.csv
  ```
- **Cross-platform CI via GitHub Actions** — matrix build across
  `ubuntu-latest` / `macos-latest` / `windows-latest` and a couple of
  Python versions, run on every push/PR:
  ```yaml
  name: Tests
  on: [push, pull_request]
  jobs:
    test:
      strategy:
        matrix:
          os: [ubuntu-latest, macos-latest, windows-latest]
          python-version: ["3.11", "3.12"]
      runs-on: ${{ matrix.os }}
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: ${{ matrix.python-version }}
        - run: pip install -e ".[dev]"
        - run: pytest tests/ -v
  ```
  Free on GitHub's public runners for an open-source repo, which fits
  since the code (not the data) is meant to be public.
- **Cross-platform-specific test worth including:** CSV read/write
  round-tripping and line-ending handling, since this is a common source
  of subtle Windows-vs-Unix bugs that unit tests on Linux alone won't
  catch.
- **CI also runs `parco lint` against fixture data** as a
  basic regression check that the tool's own validation logic still
  behaves correctly — cheap to add given the fixtures already exist for
  other tests.

## CLI

Python-based (Typer), single package, no server/daemon — reads
CSVs + runs DuckDB fresh on each invocation, no persistent state to get
out of sync.

### Build / query
```
parco build --profile <name> --lang <fr|en> --format <pdf|docx>
parco query "<SQL>"
parco stats --type <category> --by <dimension>
parco cite --key <citekey> --style <chicago|apa|...>
```

### Data entry (wizard-first, not flag-required)
```
parco add <category>                       # interactive wizard, one field at a time
parco add <category> --field value ...     # flags pre-fill wizard defaults, don't replace it
parco edit <category> --search "<text>"    # substring search, pick from numbered matches
parco delete <category> --search "<text>"  # confirm once; git history is the undo mechanism
```
Wizard behavior:
- Walks the schema's fields in declared order; `generated` fields (`id`)
  are skipped entirely, assigned automatically (see IDs, under Data
  layer).
- `[skip]` on optional fields. A `require_one_of` group is asked
  field-by-field with `[skip]` allowed on each individually, but
  re-prompts the group if every field in it ends up blank (the schema
  requires at least one).
- Numbered choices for any `vocab.yaml`-constrained field (no free typing
  of controlled values).
- Sensible defaults shown inline in the prompt (e.g. a date field hints
  the current year) — a CLI-layer convenience, not a new schema or
  handler concept.
- `--field value` flags pre-fill answers; the wizard still walks every
  field (skipping ones already answered) rather than bypassing itself.
- **Confirm-before-write screen** showing every field about to be
  written, `[y/N]` to proceed.
- **Duplicate check runs after confirmation, before the actual write**
  (see below) — soft warning, never a hard block; user always retains
  "these are different, add anyway."
- On confirm (and past any duplicate warning), the row is written and
  the write is auto-committed to the data repo (see Auto-commit, below).
- Same wizard code path serves both `add` and `edit` (edit pre-fills
  current values, sourced by search — see below).

### Finding a row to edit or delete (substring search, no display-field config)
`--search "<text>"` matches case-insensitively as a substring against
every field's value — no per-category "display field" concept needed.
Matches are shown as a numbered list; each row's summary line shows its
`id` plus every field that's either declared `required` or belongs to a
`require_one_of` group and is non-blank for that row (so a proper-noun-
only title still shows, without listing every optional field). The user
picks a number; `edit` re-enters the wizard pre-filled with that row's
values, `delete` asks one confirmation and removes the row.

### Duplicate detection (per-category matching, not generic)
Rules are **declared in each category's schema file** (see each
category under Category schemas for its actual rule), built from a
small matcher set — `exact`, `fuzzy`, `overlap`, `same_year` (defined
under Category schemas). Each rule declares an outcome: `duplicate`
(soft warning, "add anyway" allowed) or `related` (informational —
`students` is the one category that uses this, for "existing person,
new record" rather than a true duplicate). Same logic reused
non-interactively during `parco refresh` and `parco import` (auto-skip
high-confidence matches, flag ambiguous ones for review rather than
blocking the whole run).

### Auto-commit (per-write, not the same thing as `sync`)
Every `add`/`edit`/`delete` that reaches a write commits it to the data
repo immediately — `git add <category>.csv && git commit -m "..."` —
because git history *is* the undo mechanism (see Behavioral requirements
in CLAUDE.md; no soft-delete exists anywhere in this tool). This is a
plain local commit with no remote interaction, owned by `entries.py`
itself (not `sync.py`, which is the separate, larger, future piece that
reconciles remotes and prompts "Sync anyway? [y/N]"). Commit messages
are generated, not user-authored: `Added <category> entry <id>`,
`Edited <category> entry <id>`, `Deleted <category> entry <id>`.

### Refresh (catch up with an external source that updates on its own)
```
parco refresh zotero --collection "<name>"   # sync publications.csv against a Zotero collection
parco refresh rates                           # (re-)fetch monthly exchange rates into rates.csv
parco refresh all                             # run every refreshable source
```
- **What "refresh" means here:** the source updates on its own schedule
  (Better BibTeX auto-exports continuously; the ECB publishes new months)
  and `parco` just needs to catch up with it — no file to hand it. This
  is distinct from `parco import` below, which seeds data from a
  one-time file you provide.
- **`refresh zotero`:** dedup via DOI/citekey matching against the named
  collection (insert new publication rows, update changed CV-only
  linkage, skip identical) — always explicit, since ambiguous matches
  need review; never triggered as a side effect of another command.
- **`refresh rates`:** downloads the ECB historical file, recomputes
  monthly averages, and appends any new **complete months** not already
  in `rates.csv` (existing rows are never rewritten). Unlike
  `refresh zotero`, this one is also triggered **automatically on
  demand** by `stats`, `build` and `query` when a needed rate is missing
  — see Currency conversion. `parco lint` never triggers it, staying
  network-free (see Testing & CI).
- **`refresh all`:** runs every refreshable source in sequence
  (currently `zotero` and `rates`), reporting each result; safe to script
  since both are already non-interactive (auto-skip/flag rather than
  block).

### Import (one-time/periodic bulk-seed from a file you provide)
```
parco import ccv --file <export.xml> --dry-run
```
- Dedup via the same per-category matcher rules as `refresh` and the
  wizard (insert new, update changed, skip identical).
- CCV XML importer is a planned one-time/periodic bulk-seed tool. The
  export structure and category mapping are documented (see CCV export
  structure, under Category schemas), from a real exported file; the
  per-field mapping is finalized alongside each remaining category's
  schema.

### Validation
```
parco lint                # check all tables
parco lint <category>      # check one table
parco lint --fix           # only unambiguous fixes (e.g. whitespace) — never guesses vocab/translation values
```
Checks: vocab conformance, `labels.csv` completeness against all profile
section ids, date sanity, required fields non-blank, and (warning) money
amounts whose month has no exchange rate in `rates.csv`.

**Expected to pass silently almost always** — `add`/`edit` already
validate at entry time, so lint failures should mainly come from paths
that bypass the CLI: manual CSV edits, imports, or a new profile section
added without its label.

### Sync / remotes
```
parco remote add [--name <n> --url <u>]     # wizard if no flags; writes sync.yaml AND runs `git remote add`
parco remote list                            # shows configured remotes + sync status
parco remote remove <name>                   # removes from sync.yaml; separately asks before removing from git

parco sync                     # commit pending changes, push to every remote in sync.yaml
parco sync --remote <name>     # push to just one
parco sync --non-interactive   # never wait for input; proceeds automatically past lint warnings if needed
```
- `sync.yaml` is declarative; `parco sync` reconciles git's actual remotes
  to match it: **missing remote → add automatically** (no prompt);
  **mismatched URL → warn and confirm**; **extra remote not in config →
  leave alone**. Additive, never silently destructive.
- **`parco sync` is gated by `parco lint`:** if lint fails, show the problems
  and prompt "Sync anyway? [y/N]" — interactive by default, since lint
  failures should be rare enough that this is a meaningful checkpoint,
  not routine friction.
- `--non-interactive` is for unattended runs (cron etc.) — same lint
  output, but proceeds automatically instead of waiting for a prompt
  that will never come. Overridden lint failures are also appended to a
  log in the platform user state dir (e.g. `~/.local/state/parco/sync.log`,
  via `platformdirs`) — never in the data repo — and printed to stderr
  (e.g. for cron mail).
- Every `add`/`edit`/`delete` auto-commits to git with a descriptive
  message — this **is** the undo/audit mechanism; no separate trash or
  soft-delete needed.

---

## Backup / hosting

- **Multiple git remotes**, not a single point of failure:
  - Private repo (data — grant amounts, student outcomes are sensitive)
  - Self-hosted remote (Gitea/Forgejo on existing Tailscale
    infrastructure) as an option, given Sofian already self-hosts
  - GitHub/GitLab private repo as an additional off-site mirror
- **Code (the CLI tool itself) can be public**; **data repo stays
  private** — two separate repos, not one with mixed visibility.

---

## Explicitly deferred / out of scope for v1

- Cross-references between tables (foreign keys, joins), including grant
  association on publications and project-based extraction
  (`parco extract --project`)
- CRediT contributor-role taxonomy
- Media/image attachments (artwork documentation photos, etc.)
- Hosted/multi-user MCP chatbot server (local-only querying is the v1
  target; the read-only `mcp-server-duckdb` project is the reference
  implementation to adopt when this is revisited)

## Design status

All schema and config design for v1 is complete: nineteen category
schemas (see Category schemas), `vocab.yaml` (draft), `views.yaml`
(draft), and `identity.yaml` (see Identity / personal-info config) are
all drafted, cross-checked against a real CCV export and the user's own
LaTeX CV. The foundation layer is implemented (see Code architecture):
schema/vocab/labels loading, ISO partial dates, common field validation,
the handler architecture (`GenericHandler`, `PublicationsHandler`),
DuckDB-backed CSV access, and `parco lint`. What remains is the rest of
the CLI (add/edit wizard, sync, build, refresh/import) — see CLI.

## Known limitations / follow-up from the foundation implementation

Parked during the foundation plan's final review as Minor (non-blocking)
findings — pick these up in whichever future plan next touches the area:

- Several core loaders disagree on error handling for missing/malformed
  *config* files (some raise raw `OSError`/`KeyError`, one path
  (`load_all_schemas` on a missing `categories/` dir) silently succeeds
  with no schemas at all, meaning a misconfigured repo can lint clean).
  `parco lint`'s own config errors are now caught (`ConfigError`, exit
  code 2), but the underlying loaders were not made consistent with each
  other. Worth a documented, uniform loader contract before the next
  loader is added.
- `DedupRule.outcome` (from a schema's `dedup: - when: ... as: ...`) is
  not validated against `{"duplicate", "related"}` at load time — a typo
  (`as: duplicat`) silently produces a `Match.kind` the duplicate-picker
  (not yet built) won't recognize.
- `validate_common` only checks date validity for a `type: date` field
  when the field also declares `precision:` — currently harmless since
  every real schema's date fields declare one, but worth tightening.
- `run_lint`'s labels-completeness check constructs `LintIssue` with the
  label's `category` column in the `field` position, which means
  something different (a CSV column name) at every other call site.
- No lint check yet for duplicate `id` values within a single category,
  even though `id` is the primary key `find_matches` relies on.
- No `.github/workflows/` CI exists yet, despite Testing & CI's
  requirement (pytest × 3 OSes × 2 Pythons, plus `parco lint` against
  fixture data). This was never scheduled in the foundation plan and
  should be picked up explicitly, not silently deferred again.

## Open questions to resolve during implementation

1. ~~Whether RenderCV's Markdown output is good enough as the Pandoc
   input for DOCX~~ — resolved by a spike (see Output formats): viable,
   with one known, acceptable-for-v1 limitation (vertical spacing, not
   data loss).
2. The CCV importer (`core/import_ccv.py`, see CCV export structure)
   still needs to be built and tested against a real exported file —
   the structure and category mapping are documented, but the parser
   itself doesn't exist yet.
