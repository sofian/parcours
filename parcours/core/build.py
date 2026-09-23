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
    rows = query_category_rows(
        data_dir,
        view.source,
        filters=section.get("filter"),
        order_by=section.get("order_by"),
        limit=section.get("limit"),
    )
    rows = [_resolve_glossary_fields(schema, row, translations, language) for row in rows]

    handler = load_handler(schema, HandlerContext(data_dir=data_dir))
    if isinstance(handler, PublicationsHandler):
        rows = [_merge_zotero_fields(handler, row) for row in rows]

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
    translations = load_translations(data_dir / "translations.csv")
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
        title = translations.resolve_or_literal("section", section["id"], language)
        sections[title] = _build_section_entries(
            data_dir, schema, view, section, language, translations
        )

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
