# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Pre-implementation: the repo contains only `SPECS.md` (the design spec) and `LICENSE`. There is no code, build system, or test suite yet. `SPECS.md` is the source of truth — read it before making architectural decisions, and update it when a decision changes.

**Parcours** is a personal, git-tracked academic/artistic CV data system (CLI command: `parco`). CSV files are the source of truth; DuckDB queries them in place; output goes to RenderCV (PDF/LaTeX/Typst/HTML) or Pandoc (DOCX), with citeproc + CSL for citations. Built for one user but meant to be reusable, so **nothing person-specific may be hardcoded** — categories, vocab, translations, and profiles are all config.

## Planned stack and commands

Python ≥3.11, Typer CLI, DuckDB, pytest, `platformdirs`. Pandoc is an external dependency (DOCX output; CI must install it on all three OSes). Once scaffolded, the spec expects:

```
pip install -e ".[dev]"
pytest tests/ -v
pytest tests/unit/test_entries.py::test_name   # single test
```

CI (GitHub Actions) runs pytest on ubuntu/macos/windows × Python 3.11/3.12, plus `parco lint` against fixture data as a regression check.

## Architecture: core + thin interfaces

Hexagonal split, enforced from day one so a web API (FastAPI) or GUI can be added without a rewrite:

- `parcours/core/` — `data.py`, `entries.py`, `lint.py`, `build.py`, `cite.py`, `sync.py`, `vocab.py`. **Never does interactive I/O**: no `print()`, `input()`, `sys.exit()`. Takes structured args, returns structured results (e.g. `lint` returns `LintIssue` objects), or raises typed exceptions (e.g. `DuplicateCandidates(matches=[...])`) instead of warning and prompting.
- `parcours/cli/main.py` — thin Typer app that owns **all** prompts, confirmations, and output formatting (wizard steps, duplicate picker, "Sync anyway? [y/N]").
- `web/`, `gui/` — future, wrapping the same core functions.

Boundary test: could a web API return this as JSON, or a GUI show it as a dialog, without touching the function? If yes → core. If the function's whole job is asking the user something → CLI only.

## Data model decisions

- One UTF-8 CSV per category (`publications.csv`, `grants.csv`, `artworks.csv`, `students.csv`, …), stored under `entries/` in the data repo alongside `entries/translations.csv` — grouped together because both are literal CSVs of rows, as opposed to the repo-root config (`parco.yaml`, `vocab.yaml`, `views.yaml`, `identity.yaml`) or the `categories/` schema definitions. `reference/` (citation export, exchange rates) stays separate: fetched/derived data, not user-authored entries. **No cross-references/foreign keys between tables in v1.**
- IDs are bare 6-hex-char random tokens (e.g. `a3f9c2`), auto-generated on `add`; users interact via substring search (`--search`), never type IDs.
- `vocab.yaml` holds controlled vocabularies, enforced at write time (`add`/`edit` reject invalid values) and re-checked by `parco lint`.
- Bilingual fields are paired fields (`title_fr` / `title_en`) applied consistently across tables.
- Publications require a `status` (see `publication_status` in `vocab.yaml`), which decides CV-readiness.
- `translations.csv` (`id, category, en, fr`) holds **all** UI-facing strings. A missing translation must fail loudly (or warn) — never silently fall back to another language.
- A CSL-JSON export is canonical for bibliographic metadata — Zotero + Better BibTeX is the reference/most-tested path, but any tool that can produce a CSL-JSON file (EndNote, Mendeley, Paperpile, a hand-maintained file, etc.) works identically, since `PublicationsHandler` only ever reads that JSON file, never Zotero itself. The publications CSV stores a citekey (the exported record's own `id`) plus CV-only fields.
- All categories are equal — none is special-cased in the core. Each schema names a `handler` module (default `generic`; `publications` for citekey/Zotero/citation behavior, DOI+fuzzy dedup, CSL `type_map`; custom ones by dotted import path, never auto-loaded from the data repo). Handlers live in the core layer (no prompting/printing); a `CategoryHandler` base class (generic defaults) plus `runtime_checkable` capability Protocols (`Citable`, `Importable`) found via `isinstance`. Zotero-citekey resolution is a **shared capability** (any schema with a `citekey` field + Zotero `options`), not exclusive to the `publications` handler — `press` uses just the capability; `review` and `catalog` reuse the full `publications` handler (its `type_map`→`type` derivation is optional, skipped when a schema declares neither).
- **Design status: complete for v1.** All nineteen category schemas, `vocab.yaml`, `views.yaml`, and `identity.yaml` are drafted in `SPECS.md`, cross-checked against a real CCV export and the user's own LaTeX CV. What's left is implementation, not design — see SPECS.md's "Design status" section.
- **Categories:** publications, grants, artworks, students, teaching, service, outreach, presentations, press, review, catalog, education, positions, recognitions, exhibitions, curatorship, residencies, software, skills. Full field-by-field detail lives in SPECS.md's "Category schemas" — don't duplicate it here; a few things worth remembering when touching this area:
  - `review`/`catalog` reuse the `publications` handler (third-party reception of your work, not your own output).
  - `education` shares its `degree_type`/`degree_status` vocab with `students`; `recognitions` shares its `amount`/`currency` shape with `grants`.
  - `exhibitions`/`curatorship` are identical in shape but separate tables (exhibited-in vs. curated), not one table with a `role` field.
  - `software` inverts the usual bilingual pattern: `title` is untranslated, `description` is bilingual.
  - `skills` is one row per skill (not per skill-group) and is the only category with no dates.
- **Cross-cutting mechanisms** (apply across many schemas, not category-specific):
  - `require_one_of` (schema-level, alongside `fields`/`dedup`): at least one of a group of fields must be filled, not all — used for `title_en`/`title_fr` pairs (most titles are single-language proper nouns) and `exhibitions`'/`curatorship`'s `event`/`venue`. Distinct from `translations.csv`'s stricter both-required rule, which only applies to the small fixed set of UI-facing strings.
  - Place names use two fields, `city` and `country` (e.g. "The Hague" / "Netherlands"), each backed by its own `translations.csv` glossary (`category: city`, `category: country`) with literal-text fallback when unmatched — rendered together as `"{city}, {country}"`. A field declares which glossary category it's backed by with `glossary: <category>` (parallel to `vocab: <name>`, but soft — `parco lint` only warns, never blocks, on a glossary-backed value with no matching `translations.csv` entry). `country` is pre-populated with ~195 EN/FR rows at `parco init` from a table bundled with the tool, since countries are a small closed set; `city` has no such bounded list and stays entirely manual — a split city/country design was tried once before and merged into one field on the mistaken belief it couldn't handle a translatable city name, then split back once pre-populated country translation became worth having (it can: `city` keeps the same glossary/fallback behavior on its own).
  - `precision` on date fields is a **minimum**, never a ceiling — a field can always hold a more precise date than its declared floor.
  - `weight` (standard optional `int` field, present in every schema right after `id`): a manual ordering hint, higher = appears earlier — refines/overrides date-based `order_by` when dates are missing or imprecise; for `skills` (no dates at all) it's the only ordering mechanism.
  - CCV's "Bilingual" field type has two on-the-wire forms (split `<bilingual>` children, or an unsplit blob directly on `<value>`) — an importer must check both, per a bug caught while drafting `recognitions`.
- The data repo is found by searching upward from the cwd for a `parco.yaml` marker, falling back to a path in `~/.config/parco/config.yaml`; `--data-dir` / `PARCO_DATA_DIR` override both. Auto-commit and sync act on that repo, not this one.

## Currency conversion

`parco.yaml` sets `currency: {default, report}`. Exchange rates live in a tracked `reference/rates.csv` (reference data, not a category — grouped under `reference/` alongside other external-tool data like a citation export), derived as monthly averages from the ECB's historical file — no conversion library, since conversion runs as a DuckDB join. `stats`/`build`/`query` fetch rates **on demand** when a needed one is missing (append-only, complete-months-only — existing rows are never rewritten); `parco refresh rates` runs the same fetch explicitly, and `parco refresh all` runs every refreshable source (currently `zotero` and `rates`). `lint` stays network-free — it only warns which grants lack a rate, kept fast/reproducible for CI. A grant converts at its `start_date` month; a still-missing rate after fetching gives a blank converted value plus a notice, never a guess or an error.

## Profiles

YAML per CV variant/language (`profiles/academic-en.yaml`). Sections reference a named, fixed `source` view defined in `views.yaml` in the data repo (table, fields, RenderCV entry type; the tool ships a starter file) — **never raw SQL in profile files** — with optional simple `filter` (key→value), `order_by`, `limit`, `group_by`, `citation_style`. Section titles come from `translations.csv` keyed by section `id` and `meta.language`, not from the profile. Load YAML with `SafeLoader`.

## Behavioral requirements worth preserving

- `add`/`edit` share one wizard code path (edit pre-fills). Flags pre-fill defaults rather than replacing the wizard. Vocab fields use numbered choices; a confirm-before-write screen is shown.
- Duplicate detection: the `generic` handler reads rules **declared in each category's own schema** (other handlers, like `publications`, implement their own) from a small matcher set (`exact`, `fuzzy`, `overlap`, `same_year`), each with an outcome of `duplicate` (soft warning) or `related` (informational — `students` is the one category that uses this). Never a hard block; the same logic is reused non-interactively by `parco refresh` (Zotero, rates) and `parco import` (CCV).
- Every `add`/`edit`/`delete` auto-commits to git with a descriptive message — git history *is* the undo mechanism (no soft-delete).
- `parco lint --fix` only applies unambiguous fixes (e.g. whitespace); it never guesses vocab or translation values.
- **`refresh` vs `import`:** `refresh <source>` catches data up with an external source that updates on its own schedule (Zotero's continuous export, ECB's periodic rates) — no file to hand it. `import <source>` seeds data from a one-time file you provide (CCV XML). `refresh zotero` is always explicit (dedup needs review); `refresh rates` also runs automatically on demand. `refresh all` runs every refreshable source.
- `parco sync` is gated by lint (prompts "Sync anyway? [y/N]"; `--non-interactive` proceeds automatically, appending overridden failures to a log in the platform user state dir — never in the data repo — and printing to stderr). `sync.yaml` is declarative and additive: missing remote → add silently; URL mismatch → warn and confirm; extra remotes → leave alone.

## Testing rules

- Tests use temporary fixture CSVs/vocab/translations (`tests/fixtures/`), **never real data**. Core tests touch no git and no filesystem beyond a temp dir; sync tests mock git.
- Unit tests target core; integration tests drive the CLI via Typer's `CliRunner`.
- Include CSV round-trip and line-ending tests (Windows vs Unix).

## Repo split

Code is intended to be public; the user's actual CV data (grant amounts, student outcomes) lives in a separate **private** repo — never commit real data here.

## Out of scope for v1

Foreign keys/joins (including grant association on publications and `parco extract --project`), CRediT roles, media attachments, hosted MCP chatbot server (local read-only `mcp-server-duckdb` is the future reference).
