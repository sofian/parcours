"""Assembles a RenderCV YAML input from a profile + views.yaml + category
data (see SPECS.md, "Build / query" and "views.yaml (draft)"). Core
layer: no prompting, no interactive I/O — the one sanctioned exception
is `run_build`'s subprocess call out to the external `rendercv` CLI,
treated like Pandoc elsewhere in this codebase."""

import subprocess
import tempfile
from pathlib import Path

import yaml

from .data import query_category_rows
from .handlers import load_handler
from .handlers.base import HandlerContext
from .handlers.publications import PublicationsHandler
from .identity import load_identity, resolve_identity
from .lint import run_lint
from .profiles import Profile
from .schema import load_all_schemas
from .templating import resolve_template
from .translations import load_translations, translations_csv_path
from .views import ViewSpec, load_views


def _csl_date_to_iso(record: dict) -> str | None:
    """Real Better BibTeX CSL-JSON exports mix int and numeric-string
    date-parts within one file (see `handlers/publications.py::_csl_year`),
    so each part is normalized to int; a non-numeric part means no date
    rather than a crash."""
    try:
        parts = [int(part) for part in record["issued"]["date-parts"][0]]
    except (KeyError, IndexError, TypeError, ValueError):
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
    """Authors as display names — an institutional author is a single
    `literal` name in CSL-JSON. An edited volume or exhibition catalog
    often has only `editor`s, and a broadcast only a `director` or `host`,
    which are used instead of leaving the entry author-less (RenderCV
    rejects a PublicationEntry without authors)."""
    def _names(people: list[dict]) -> list[str]:
        names = []
        for person in people:
            full_name = person.get("literal") or " ".join(
                part for part in [person.get("given", ""), person.get("family", "")] if part
            )
            if full_name:
                names.append(full_name)
        return names

    for role in ("author", "editor", "director", "host"):
        names = _names(record.get(role, []))
        if names:
            return names
    return []


def _merge_zotero_fields(handler: PublicationsHandler, row: dict) -> dict:
    citekey = row.get("citekey") or ""
    record = handler.resolve(citekey) if citekey else None
    if record is None:
        return row

    merged = dict(row)
    merged["zotero_title"] = record.get("title", "")
    merged["zotero_authors"] = _csl_authors_to_list(record)
    merged["zotero_author_text"] = ", ".join(merged["zotero_authors"])
    merged["zotero_journal"] = record.get("container-title", "")
    merged["zotero_outlet"] = (
        record.get("container-title") or record.get("collection-title") or record.get("publisher") or ""
    )
    merged["zotero_doi"] = record.get("DOI", "")
    merged["zotero_url"] = record.get("URL", "")
    merged["zotero_date"] = _csl_date_to_iso(record) or ""
    return merged


def _order_value(field_name: str, value: str):
    # Mirrors `query_category_rows`' numeric-then-text ordering, except
    # that `zotero_*` values always sort as text: a year-only export date
    # ("2015") has to stay in line with its fuller neighbours ("2015-06").
    if not field_name.startswith("zotero_"):
        try:
            return (0, float(value), "")
        except ValueError:
            pass
    return (1, 0.0, str(value))


def _order_merged_rows(rows: list[dict], order_by: str) -> list[dict]:
    """`order_by` for a section sorting on a `zotero_*` field, which only
    exists once rows are merged with the citation export, so DuckDB can't
    sort on it. Applied last key first, relying on sort stability; blank
    values go last in either direction."""
    for key in reversed(order_by.split(",")):
        parts = key.split()
        if not parts:
            continue
        field_name = parts[0]
        direction = parts[1].lower() if len(parts) > 1 else "asc"
        if direction not in ("asc", "desc"):
            raise ValueError(f"Invalid order_by direction '{parts[1]}' (expected 'asc' or 'desc')")
        filled = [row for row in rows if row.get(field_name)]
        blank = [row for row in rows if not row.get(field_name)]
        filled.sort(key=lambda row: _order_value(field_name, row[field_name]), reverse=direction == "desc")
        rows = filled + blank
    return rows


def _map_row_to_entry(view: ViewSpec, row: dict, language: str) -> dict:
    entry = {}
    for field_name, template in view.fields.items():
        value = resolve_template(template, row, language)
        if value:
            entry[field_name] = value
    return entry


def _resolve_glossary_fields(schema, row: dict, translations, language: str) -> dict:
    """Replaces every `glossary:`-marked field's raw value with its
    translated form (see SPECS.md: `build` is what actually *consumes*
    the glossary, not just `lint`). Unmatched values fall back to the
    literal, per `resolve_or_literal`."""
    glossary_fields = [f for f in schema.fields if f.glossary]
    if not glossary_fields:
        return row
    resolved = dict(row)
    for field_spec in glossary_fields:
        raw_value = row.get(field_spec.name)
        if raw_value:
            resolved[field_spec.name] = translations.resolve_or_literal(
                field_spec.glossary, raw_value, language
            )
    return resolved


def _build_section_entries(
    data_dir: Path, schema, view: ViewSpec, section: dict, language: str, translations
) -> list[dict]:
    handler = load_handler(schema, HandlerContext(data_dir=data_dir))
    order_by = section.get("order_by")
    limit = section.get("limit")
    orders_after_merge = isinstance(handler, PublicationsHandler) and "zotero_" in (order_by or "")

    rows = query_category_rows(
        data_dir,
        view.source,
        filters=section.get("filter"),
        order_by=None if orders_after_merge else order_by,
        limit=None if orders_after_merge else limit,
    )
    rows = [_resolve_glossary_fields(schema, row, translations, language) for row in rows]

    if isinstance(handler, PublicationsHandler):
        rows = [_merge_zotero_fields(handler, row) for row in rows]

    if orders_after_merge:
        rows = _order_merged_rows(rows, order_by)
        if limit is not None:
            rows = rows[:limit]

    return [_map_row_to_entry(view, row, language) for row in rows]


# RenderCV's `locale` block is a discriminated union keyed on a spelled-out
# language *name* ("english", "french", ... — see `available_locales` in
# rendercv.schema.models.locale), not an ISO code, and it's what localizes
# month names on rendered dates.
_RENDERCV_LOCALES = {"en": "english", "fr": "french"}


def _rendercv_locale(language: str) -> str:
    return _RENDERCV_LOCALES.get(language, "english")


def build_rendercv_data(data_dir: Path, profile: Profile) -> dict:
    """Assembles the full RenderCV-YAML-ready dict for one profile. Pure
    (no subprocess, no writing) — the caller writes it to a file and
    invokes `rendercv render` separately."""
    schemas = load_all_schemas(data_dir / "categories")
    views = load_views(data_dir / "views.yaml")
    translations = load_translations(translations_csv_path(data_dir))
    identity = load_identity(data_dir / "identity.yaml")

    language = profile.meta["language"]
    cv = resolve_identity(identity, profile.meta["identity_variant"], language)

    sections = {}
    for section in profile.sections:
        # A section's `source` names a *view*; the view's own `source`
        # names the underlying category — the two are only incidentally
        # equal (e.g. a `grants-recent` view still reads `grants`).
        view = views[section["source"]]
        schema = schemas[view.source]
        entries = _build_section_entries(
            data_dir, schema, view, section, language, translations
        )
        if not entries:
            # A category with no rows yet gets no section at all, not an
            # empty heading — the common case for a freshly-scaffolded
            # repo (see SPECS.md, "Init"), and no CV format wants a
            # visible section with nothing under it.
            continue
        title = translations.resolve_or_literal("section", section["id"], language)
        sections[title] = entries

    cv["sections"] = sections

    return {
        "cv": cv,
        "design": {"theme": profile.meta["theme"]},
        "locale": {"language": _rendercv_locale(language)},
    }


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
        views = load_views(data_dir / "views.yaml")
        category_names = {views[section["source"]].source for section in profile.sections}
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
            # RenderCV prints its validation-error table to stdout, not
            # stderr — dropping stdout throws away the actual diagnosis.
            detail = "\n".join(part for part in [exc.stdout, exc.stderr] if part)
            raise BuildError(f"rendercv render failed: {detail}") from exc

    return output_path
