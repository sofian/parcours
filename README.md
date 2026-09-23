# Parcours

A personal, portable system for maintaining academic and artistic CV data as structured, git-tracked plain text — with a command-line tool (`parco`) to enter data through a wizard, validate it, and generate CV documents in multiple versions and languages.

> **Status:** the core is implemented and usable today — scaffold a new data repo with `parco init`, enter data with `parco add`/`edit`/`delete`/`list`, validate it with `parco lint`, and render a CV with `parco build`. Querying, statistics, and citation formatting (`parco query`/`stats`/`cite`) and remote sync/import (`parco sync`/`refresh`/`import`) are still being designed and aren't built yet — see [`SPECS.md`](SPECS.md)'s "Design status" section for the current, authoritative breakdown of what's built vs. planned.

## Why

Academic and artistic CVs get rebuilt from scratch for every grant, job, and institution, each wanting a different length, language, and format. Parcours keeps the data in one place as plain CSV files and treats each CV as a *view* over that data.

- **Plain text, git-tracked:** every change is diffable, and git history is the undo mechanism.
- **Multiple CVs from one dataset:** a long academic CV, a short one, English, French — each defined by a small YAML profile, sharing whatever isn't language-specific via `extends`.
- **Bilingual by design:** every UI-facing string comes from a translation table, and a missing translation fails loudly instead of silently falling back.
- **Reusable:** built for one user, but categories, vocabularies, translations, and profiles are all configuration, so other academics can use it with their own data.

## How it works

```
CSV files (source of truth, git-tracked)
        │
        ▼
   DuckDB (SQL directly on the CSVs, no import step)
        │
        ├──► RenderCV (YAML) ──► PDF / Typst / HTML         (parco build)
        ├──► Pandoc          ──► DOCX                        (parco build --format docx, planned)
        ├──► citeproc + CSL  ──► formatted citations         (parco cite, planned)
        ├──► SQL result tables ──► stats / ad-hoc queries    (parco stats / parco query, planned)
        └──► (future) MCP-DuckDB server ──► read-only chatbot
```

Bibliographic metadata lives in [Zotero](https://www.zotero.org/) (kept in sync on disk with Better BibTeX auto-export). The publications CSV stores a citekey linking to it, plus CV-specific fields Zotero doesn't track.

## Usage

```bash
# Scaffold a brand-new data repo (wizard-driven: name, identity, language(s), currency)
parco init ~/my-cv

# Add, edit, delete, and browse entries through an interactive wizard
parco add publications
parco edit grants --search "FRQSC"
parco delete presentations --search "ACFAS"
parco list                          # no category given: shows what's available
parco list artworks --order-by date --desc

# Validate your data
parco lint
parco lint grants                   # scope to one category

# Render a CV
parco build --profile academic-en --format pdf

# Manage translations.csv (section titles, content glossaries like place names)
parco translation add location montreal --en "Montreal, Canada" --fr "Montréal, Canada"
parco translation list
```

`add`/`edit`/`delete`/`list` never hardcode a category list — `categories/*.yaml` in your data repo defines what exists, and every one of these commands shows you the available categories if you omit one or type it wrong. `add`/`edit` also accept `--field value` flags to pre-fill the wizard (e.g. `parco add grants --funder FRQSC`) without skipping it.

**Not built yet** — designed in [`SPECS.md`](SPECS.md) but not implemented:

```bash
parco query "SELECT year, count(*) FROM publications GROUP BY year"
parco stats --type publications --by year
parco cite --key audry2024 --style apa
parco refresh zotero --collection "CV"
parco refresh rates
parco import ccv --file export.xml --dry-run
parco sync
```

## Data layout

Your data lives in a **separate, private repository** (grant amounts and student outcomes are sensitive); this repo holds only the tool. `parco init` scaffolds one for you.

| File | Purpose |
|------|---------|
| `parco.yaml` | Marker file: `parco` finds your data by searching upward from the current directory for it (falling back to `~/.config/parco/config.yaml`; `--data-dir` / `PARCO_DATA_DIR` override) |
| `categories/*.yaml` | One schema per category — all 19: publications, grants, artworks, students, teaching, service, outreach, presentations, press, review, catalog, education, positions, recognitions, exhibitions, curatorship, residencies, software, skills |
| `*.csv` (one per category) | The actual entries, one row per record |
| `vocab.yaml` | Controlled vocabularies (publication type, grant role, …), enforced on write and by `parco lint` |
| `translations.csv` | Translations (`id, category, en, fr`) for section titles and content glossaries (e.g. place names) |
| `identity.yaml` | Your name and one or more identity variants (e.g. "academic") — email, phone, headline per variant |
| `views.yaml` | Named views that profiles draw from: table, field mapping, and RenderCV entry type |
| `profiles/*.yaml` | One file per CV variant/language: metadata, theme, and an ordered list of sections — a base profile can hold everything a language doesn't need to repeat, via `extends` |

A profile section references a named data view with simple filters, never raw SQL:

```yaml
meta:
  name: academic
  language: en
  format: pdf
  theme: sb2nov
  identity_variant: academic
sections:
  - id: publications
    source: publications
    filter: { status: [published] }
    order_by: date desc
    limit: 10
```

## Architecture

The code is a core library with no interface baked in, plus thin clients on top, so a web API or GUI can be added later without a rewrite.

```
parcours/
  core/            # schema/vocab/data access, lint, entries, build,
                   # init, identity, profiles, views, dates, names,
                   # matching, handlers — no printing or prompting
  cli/             # Typer app: owns all prompts, wizards, and output
  starter_config/  # bundled starter categories/vocab/translations/
                   # views, copied into a repo by `parco init`
  web/             # future: FastAPI over the same core
  gui/             # future
```

## Development

Python 3.11+, Typer, DuckDB, PyYAML, [RenderCV](https://rendercv.com/) (an external CLI, invoked via subprocess — like Pandoc for the planned DOCX output), pytest.

```bash
python3 -m venv venv
venv/bin/pip install -e ".[dev]"
venv/bin/pytest tests/ -v
```

Tests use fixture data only — never real CV data — and core tests touch no git repo beyond a temp dir except where the module under test *is* git integration (e.g. `init`'s own `git init`). CI isn't wired up yet.

## Roadmap

See [`SPECS.md`](SPECS.md)'s "Design status" and "Explicitly deferred / out of scope for v1" sections for the current, living list of what's built, what's designed but not built, and what's deliberately out of scope — that list changes as the project moves, so it isn't duplicated here.

## License

GNU General Public License v3.0 — see [`LICENSE`](LICENSE).
