# Parcours

A personal, portable system for maintaining academic and artistic CV data as structured, git-tracked plain text — with a command-line tool (`parco`) to generate CV documents in multiple versions and languages, run statistics and queries, and format citations.

> **Status: design phase.** No code has been written yet. This README describes the planned system; see [`SPECS.md`](SPECS.md) for the full design spec. Commands below are the intended interface, not something you can run today.

## Why

Academic and artistic CVs get rebuilt from scratch for every grant, job, and institution, each wanting a different length, language, and format. Parcours keeps the data in one place as plain CSV files and treats each CV as a *view* over that data.

- **Plain text, git-tracked:** every change is diffable, and git history is the undo mechanism.
- **Multiple CVs from one dataset:** a long academic CV, a short one, English, French — each defined by a small YAML profile.
- **Bilingual by design:** every UI-facing string comes from a label table, and a missing translation fails loudly instead of silently falling back.
- **Reusable:** built for one user, but categories, vocabularies, labels, and profiles are all configuration, so other academics can use it with their own data.

## How it works

```
CSV files (source of truth, git-tracked)
        │
        ▼
   DuckDB (SQL directly on the CSVs, no import step)
        │
        ├──► RenderCV (YAML) ──► LaTeX / PDF / Typst / HTML   (parco build)
        ├──► Pandoc          ──► DOCX                          (parco build --format docx)
        ├──► citeproc + CSL  ──► formatted citations           (parco cite)
        ├──► SQL result tables ──► stats / ad-hoc queries      (parco stats / parco query)
        └──► (future) MCP-DuckDB server ──► read-only chatbot
```

Bibliographic metadata lives in [Zotero](https://www.zotero.org/) (kept in sync on disk with Better BibTeX auto-export). The publications CSV stores a citekey linking to it, plus CV-specific fields Zotero doesn't track.

## Planned usage

```bash
# Generate a CV
parco build --profile short --lang en --format pdf

# Add and edit entries through an interactive wizard
parco add publication
parco edit publication --search "latent space"
parco delete grant --search "FRQSC"

# Query and report
parco query "SELECT year, count(*) FROM publications GROUP BY year"
parco stats --type publications --by year
parco cite --key audry2024 --style apa

# Catch up with external sources that update on their own
parco refresh zotero --collection "CV"
parco refresh rates

# Seed from a one-time file export
parco import ccv --file export.xml --dry-run

# Validate and back up
parco lint
parco sync
```

`add` and `edit` share one wizard: numbered choices for controlled-vocabulary fields, sensible defaults, a confirm-before-write screen, and a soft duplicate check. Every write auto-commits to git.

## Data layout

Your data lives in a **separate, private repository** (grant amounts and student outcomes are sensitive); this repo holds only the tool.

| File | Purpose |
|------|---------|
| `parco.yaml` | Marker file: `parco` finds your data by searching upward from the current directory for it (falling back to `~/.config/parco/config.yaml`; `--data-dir` / `PARCO_DATA_DIR` override) |
| `*.csv` (one per category) | Entries for the nine v1 categories: publications, grants, artworks, students, teaching, service, outreach, presentations, press |
| `vocab.yaml` | Controlled vocabularies (publication type, grant role, …), enforced on write and by `parco lint` |
| `labels.csv` | Translations (`id, category, en, fr`) for section titles, field labels, and category values |
| `views.yaml` | Named views that profiles draw from: table, columns, and RenderCV entry type |
| `profiles/*.yaml` | One file per CV variant: metadata, theme, and an ordered list of sections |
| `sync.yaml` | Git remotes to push to |

A profile section references a named data view with simple filters, never raw SQL:

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

## Architecture

The code is a core library with no interface baked in, plus thin clients on top, so a web API or GUI can be added later without a rewrite.

```
parcours/
  core/   # data, entries, lint, build, cite, sync, vocab — no printing or prompting
  cli/    # Typer app: owns all prompts and output
  web/    # future: FastAPI over the same core
  gui/    # future
```

## Development

Planned stack: Python 3.11+, Typer, DuckDB, pytest, plus Pandoc for DOCX output. Tests run against fixture data only, on Linux, macOS, and Windows via GitHub Actions.

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Roadmap

Not in v1: cross-references between tables (including grant association and project-based extraction), CRediT contributor roles, media attachments, and a hosted multi-user chatbot server. Open questions (per-category schemas, CCV XML structure, RenderCV Markdown quality for DOCX) are tracked at the end of [`SPECS.md`](SPECS.md).

## License

GNU General Public License v3.0 — see [`LICENSE`](LICENSE).
