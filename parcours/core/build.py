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
