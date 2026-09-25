# parcours/cli/main.py
"""The Typer app — thin, owns all prompts/printing (see SPECS.md, "Code
architecture: modular core + thin interfaces")."""

import csv
import json
import sys
from pathlib import Path

import typer

from ..core.build import BuildError, run_build
from ..core.ccv_xml import CcvParseError
from ..core.citations import UnknownCitationStyle, render_citations, resolve_style
from ..core.commit import commit_pending
from ..core.data import (
    NotASelectQuery,
    category_csv_path,
    format_table,
    load_category_rows,
    query_category_rows,
    run_select_query,
)
from ..core.entries import CommitFailed, add_entry, delete_entry, edit_entry, is_file_dirty
from ..core.handlers import load_handler
from ..core.handlers.base import CategoryHandler, HandlerContext
from ..core.handlers.publications import PublicationsHandler
from ..core.import_ccv import ImportReport, plan_import, write_import
from ..core.init import (
    GitIdentityMissing,
    GitInitFailed,
    InitAnswers,
    RepoAlreadyExists,
    ScaffoldInsideSourceRepo,
    check_git_identity_configured,
    check_not_inside_source_repo,
    scaffold_repo,
)
from ..core.lint import ConfigError, run_lint
from ..core.profiles import load_profile
from ..core.repo import DataRepoNotFound, find_data_repo, load_repo_config
from ..core.schema import CategorySchema, load_all_schemas
from ..core.stats import UnknownStatsField, aggregate_counts
from ..core.translations import (
    TranslationExists,
    TranslationNotFound,
    add_translation,
    delete_translation,
    edit_translation,
    load_translations,
    translations_csv_path,
)
from ..core.vocab import VocabError, load_vocab
from .wizard import (
    ask_field_by_name,
    ask_group_fields,
    collect_field_values,
    confirm_and_check_duplicates,
    order_rows,
    pick_row,
    row_summary,
    search_rows,
)

app = typer.Typer()


@app.callback()
def main():
    """Parcours: a personal, git-tracked academic/artistic CV data system."""


def _find_repo_or_exit() -> Path:
    try:
        return find_data_repo()
    except DataRepoNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)


@app.command()
def lint(
    category: str = typer.Argument(None, help="Only lint this category"),
    fix_interactive: bool = typer.Option(
        False, "--fix-interactive", help="Walk flagged rows one by one and fix them interactively"
    ),
):
    """Check category data against its schema, vocab, and translations."""
    data_dir = _find_repo_or_exit()

    try:
        issues = run_lint(data_dir, category_filter=category)
    except ConfigError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    if fix_interactive:
        _run_lint_fix_interactive(data_dir, issues)
        return

    if not issues:
        typer.echo("No lint issues found.")
        raise typer.Exit(code=0)

    for issue in issues:
        location = issue.category
        if issue.row_id:
            location += f"[{issue.row_id}]"
        if issue.field:
            location += f".{issue.field}"
        typer.echo(f"{issue.severity.upper()}: {location}: {issue.message}")

    error_count = sum(1 for i in issues if i.severity == "error")
    raise typer.Exit(code=1 if error_count else 0)


def _ask_fix_choice(default: str = "f") -> str:
    prompt = "  [f]ix / [s]kip / [q]uit" if default == "f" else "  [a]dd translation / [s]kip / [q]uit"
    return typer.prompt(prompt, default=default).strip().lower()[:1]


def _run_lint_fix_interactive(data_dir: Path, issues: list) -> None:
    """Walks lint issues one row at a time, prompting only for the
    field(s) actually flagged rather than the whole schema (see SPECS.md-
    adjacent design discussion: bulk-fixing 40+ rows through the full
    add/edit wizard would mean re-confirming every untouched field too).
    Glossary warnings get an inline `parco translation add`-equivalent
    instead of a row edit, since the value itself isn't wrong — it just
    has no translation yet. Repo-wide `translations.csv`-completeness
    issues have no row to edit, so they're listed at the end instead."""
    repo_wide = [i for i in issues if i.category == "translations"]
    row_issues = [i for i in issues if i.category != "translations"]

    if not row_issues and not repo_wide:
        typer.echo("No lint issues found.")
        return

    if not row_issues:
        typer.echo("No row-fixable issues found.")
    else:
        try:
            vocab = load_vocab(data_dir / "vocab.yaml")
        except (VocabError, FileNotFoundError, KeyError) as exc:
            typer.echo(f"Config error: {exc}")
            raise typer.Exit(code=2)

        schemas = load_all_schemas(data_dir / "categories")
        handlers: dict[str, CategoryHandler] = {}
        rows_by_category: dict[str, list[dict]] = {}
        groups: dict[tuple[str, str], list] = {}
        order: list[tuple[str, str]] = []
        for issue in row_issues:
            key = (issue.category, issue.row_id)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(issue)

        fixed = 0
        skipped = 0
        translations_added = 0
        quit_requested = False

        for category, row_id in order:
            if quit_requested:
                break
            schema = schemas.get(category)
            if schema is None:
                continue
            if category not in handlers:
                handlers[category] = load_handler(schema, HandlerContext(data_dir=data_dir))
            if category not in rows_by_category:
                rows_by_category[category] = load_category_rows(data_dir, category)
            existing_rows = rows_by_category[category]
            original_row = next((r for r in existing_rows if r.get("id") == row_id), None)
            if original_row is None:
                continue
            row = dict(original_row)
            row_changed = False

            typer.echo(f"\n{category}[{row_id}]: {row_summary(schema, row)}")

            for issue in groups[(category, row_id)]:
                field_spec = schema.get_field(issue.field) if issue.field else None

                if issue.severity == "warning" and field_spec is not None and field_spec.glossary:
                    translations_path = translations_csv_path(data_dir)
                    translations = load_translations(translations_path) if translations_path.is_file() else None
                    value = row.get(issue.field, "")
                    if translations is not None and translations.exists(field_spec.glossary, value):
                        continue  # resolved earlier this session
                    typer.echo(f"  {issue.message}")
                    choice = _ask_fix_choice(default="a")
                    if choice == "q":
                        quit_requested = True
                        break
                    if choice == "s":
                        skipped += 1
                        continue
                    en = typer.prompt("  en ([Enter] to skip)", default="", show_default=False)
                    fr = typer.prompt("  fr ([Enter] to skip)", default="", show_default=False)
                    try:
                        add_translation(data_dir, field_spec.glossary, value, en, fr)
                        translations_added += 1
                        typer.echo(f"  Added translation {field_spec.glossary}:{value}.")
                    except TranslationExists:
                        typer.echo("  Already exists — skipping.")
                    except CommitFailed as exc:
                        typer.echo(f"  Translation written, but the commit failed: {exc}")
                    continue

                if issue.field is None:
                    group = next(
                        (g for g in schema.require_one_of if not any((row.get(n) or "").strip() for n in g)),
                        None,
                    )
                    if group is None:
                        continue  # already resolved by an earlier fix on this row
                    typer.echo(f"  {issue.message}")
                    choice = _ask_fix_choice()
                    if choice == "q":
                        quit_requested = True
                        break
                    if choice == "s":
                        skipped += 1
                        continue
                    row.update(ask_group_fields(schema, vocab, group, prefill=row))
                    row_changed = True
                    continue

                typer.echo(f"  {issue.message}")
                choice = _ask_fix_choice()
                if choice == "q":
                    quit_requested = True
                    break
                if choice == "s":
                    skipped += 1
                    continue
                row[issue.field] = ask_field_by_name(schema, vocab, issue.field, row.get(issue.field))
                row_changed = True

            if row_changed:
                values = {
                    name: row.get(name, "")
                    for name in schema.field_names()
                    if schema.get_field(name) and not schema.get_field(name).generated
                }
                if confirm_and_check_duplicates(handlers[category], values, existing_rows, self_id=row_id):
                    try:
                        edit_entry(data_dir, schema, row_id, values)
                        fixed += 1
                        rows_by_category[category] = load_category_rows(data_dir, category)
                    except CommitFailed as exc:
                        typer.echo(f"  Row written, but the commit failed: {exc}")
                else:
                    typer.echo("  Discarded, nothing written for this row.")

        typer.echo(
            f"\n{fixed} row(s) fixed, {skipped} issue(s) skipped, {translations_added} translation(s) added."
        )

    if repo_wide:
        typer.echo(f"\n{len(repo_wide)} translation-completeness issue(s) need `parco translation edit ...`:")
        for issue in repo_wide:
            typer.echo(f"  {issue.category}[{issue.row_id}].{issue.field}: {issue.message}")


@app.command()
def commit(
    message: str = typer.Option(None, "-m", "--message", help="Commit message (auto-generated from changed files if omitted)"),
):
    """Stage and commit whatever's currently pending in the data repo — for hand-edits, or to finalize a `parco import` review."""
    data_dir = _find_repo_or_exit()

    try:
        result = commit_pending(data_dir, message=message)
    except CommitFailed as exc:
        typer.echo(f"Commit failed: {exc}")
        raise typer.Exit(code=1)

    if not result.committed:
        typer.echo("Nothing to commit.")
        return
    typer.echo(f"Committed: {', '.join(result.files)}")


def _print_csv(columns: list[str], rows: list[dict]) -> None:
    writer = csv.writer(sys.stdout)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(col, "") for col in columns])


@app.command()
def query(
    sql: str = typer.Argument(..., help="A SELECT (or WITH...SELECT) query, e.g. \"SELECT year, count(*) FROM publications GROUP BY year\""),
    fmt: str = typer.Option("table", "--format", help="Output format: table, csv, or json"),
):
    """Run a read-only SQL query directly against your category CSVs."""
    data_dir = _find_repo_or_exit()

    if fmt not in ("table", "csv", "json"):
        typer.echo(f"Unknown format: '{fmt}' (expected table, csv, or json)")
        raise typer.Exit(code=2)

    try:
        columns, rows = run_select_query(data_dir, sql)
    except NotASelectQuery as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    if fmt == "table":
        typer.echo(format_table(columns, rows))
    elif fmt == "csv":
        _print_csv(columns, rows)
    else:
        typer.echo(json.dumps(rows, indent=2))


@app.command()
def stats(
    category: str = typer.Argument(None, help="Category to aggregate"),
    by: str = typer.Option(..., "--by", help="Field to group by, or 'year' for the category's date field"),
    search: str = typer.Option(None, "--search", help="Only count entries matching this text"),
    filter_flags: list[str] = typer.Option(None, "--filter", help="field=value, repeatable"),
    after: str = typer.Option(None, "--after", help="Inclusive lower bound on the category's date field"),
    before: str = typer.Option(None, "--before", help="Inclusive upper bound on the category's date field"),
):
    """Count entries in a category, grouped by a field (or 'year')."""
    data_dir = _find_repo_or_exit()
    schema = _require_category_or_exit(data_dir, category)

    filters = _parse_filter_flags(schema, filter_flags or [])
    date_range = _resolve_date_range(schema, after, before)

    rows = query_category_rows(data_dir, category, filters=filters, date_range=date_range)
    if search:
        rows = search_rows(rows, search)

    try:
        counts = aggregate_counts(schema, rows, by)
    except UnknownStatsField as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    if not counts:
        typer.echo("No entries found.")
        raise typer.Exit(code=0)

    for value, count in counts:
        typer.echo(f"{value}: {count}")


@app.command(name="list")
def list_command(
    category: str = typer.Argument(None, help="Category to list (omit to see available categories)"),
    search: str = typer.Option(None, "--search", help="Only show entries matching this text"),
    order_by: str = typer.Option(None, "--order-by", help="Sort by this field"),
    desc: bool = typer.Option(False, "--desc", help="Sort descending (requires --order-by)"),
    filter_flags: list[str] = typer.Option(None, "--filter", help="field=value, repeatable"),
    after: str = typer.Option(None, "--after", help="Inclusive lower bound on the category's date field"),
    before: str = typer.Option(None, "--before", help="Inclusive upper bound on the category's date field"),
    fmt: str = typer.Option("table", "--format", help="Output format: table or citation"),
    style: str = typer.Option(None, "--style", help="Citation style: apa, chicago-author-date, mla, or a path to a .csl file"),
):
    """List entries in a category, optionally filtered/sorted, as summaries or citations."""
    data_dir = _find_repo_or_exit()

    if category is None:
        _print_available_categories(data_dir)
        raise typer.Exit(code=0)

    schema = _load_schema_or_exit(data_dir, category)

    if fmt not in ("table", "citation"):
        typer.echo(f"Unknown format: '{fmt}' (expected table or citation)")
        raise typer.Exit(code=2)

    handler = None
    if fmt == "citation":
        handler = load_handler(schema, HandlerContext(data_dir=data_dir))
        if not isinstance(handler, PublicationsHandler):
            capable = _citation_capable_categories(data_dir)
            typer.echo(
                f"'{category}' doesn't support --format citation. "
                f"Categories that do: {', '.join(capable) or '(none configured)'}"
            )
            raise typer.Exit(code=2)

    if desc and not order_by:
        typer.echo("--desc requires --order-by")
        raise typer.Exit(code=2)
    if order_by and schema.get_field(order_by) is None:
        typer.echo(f"Unknown field: '{order_by}'")
        raise typer.Exit(code=2)

    filters = _parse_filter_flags(schema, filter_flags or [])
    date_range = _resolve_date_range(schema, after, before)

    rows = query_category_rows(data_dir, category, filters=filters, date_range=date_range)
    if search:
        rows = search_rows(rows, search)
    if order_by:
        rows = order_rows(schema, rows, order_by, descending=desc)

    if not rows:
        typer.echo("No entries found.")
        raise typer.Exit(code=0)

    if fmt == "citation":
        _print_citations(data_dir, rows, handler, style)
        return

    extra_fields = [order_by] if order_by else None
    for row in rows:
        typer.echo(row_summary(schema, row, extra_fields=extra_fields))


def _citation_capable_categories(data_dir: Path) -> list[str]:
    capable = []
    for name, category_schema in sorted(load_all_schemas(data_dir / "categories").items()):
        category_handler = load_handler(category_schema, HandlerContext(data_dir=data_dir))
        if isinstance(category_handler, PublicationsHandler):
            capable.append(name)
    return capable


def _print_citations(
    data_dir: Path, rows: list[dict], handler: PublicationsHandler, style: str | None
) -> None:
    style_name = style or load_repo_config(data_dir).get("citation_style", "apa")
    try:
        style_path = resolve_style(style_name)
    except UnknownCitationStyle as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

    # citeproc-py's own bibliography.register() dedupes by citekey
    # internally, so two rows sharing one citekey would otherwise
    # desynchronize a positional zip against render_citations()'s
    # output — verified live: it silently mis-attributes an earlier
    # row's citation to a later one, then crashes with StopIteration.
    # Deduping here and keying the rendered output by id avoids this.
    resolved_by_key: dict[str, dict] = {}
    row_keys: list[str | None] = []
    for row in rows:
        citekey = row.get("citekey") or ""
        record = handler.resolve(citekey) if citekey else None
        if record is not None:
            resolved_by_key.setdefault(record["id"], record)
            row_keys.append(record["id"])
        else:
            row_keys.append(None)

    citations_by_key = dict(zip(
        resolved_by_key.keys(), render_citations(list(resolved_by_key.values()), style_path)
    ))
    for row, key in zip(rows, row_keys):
        if key is not None:
            typer.echo(citations_by_key[key])
        else:
            typer.echo(f"[citekey '{row.get('citekey') or ''}' not found in citation export]")


def _available_categories(data_dir: Path) -> list[str]:
    return sorted(load_all_schemas(data_dir / "categories").keys())


def _print_available_categories(data_dir: Path) -> None:
    for name in _available_categories(data_dir):
        typer.echo(f"  {name}")


def _load_schema_or_exit(data_dir: Path, category: str) -> CategorySchema:
    schemas = load_all_schemas(data_dir / "categories")
    if category not in schemas:
        typer.echo(f"Unknown category: '{category}'.")
        typer.echo("Available categories:")
        _print_available_categories(data_dir)
        raise typer.Exit(code=2)
    return schemas[category]


def _require_category_or_exit(data_dir: Path, category: str | None) -> CategorySchema:
    """For commands where a category is mandatory (add/edit/delete) —
    omitting it is a real error, not a request to see what's available
    (that's `list`'s job)."""
    if category is None:
        typer.echo("A category is required for this command.")
        typer.echo("Available categories:")
        _print_available_categories(data_dir)
        raise typer.Exit(code=2)
    return _load_schema_or_exit(data_dir, category)


def _parse_filter_flags(schema: CategorySchema, filter_flags: list[str]) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for flag in filter_flags:
        if "=" not in flag:
            typer.echo(f"Invalid --filter '{flag}' (expected field=value)")
            raise typer.Exit(code=2)
        field_name, value = flag.split("=", 1)
        if schema.get_field(field_name) is None:
            typer.echo(f"Unknown field: '{field_name}'")
            raise typer.Exit(code=2)
        filters.setdefault(field_name, []).append(value)
    return filters


def _resolve_date_range(
    schema: CategorySchema, after: str | None, before: str | None
) -> tuple[str, str | None, str | None] | None:
    if after is None and before is None:
        return None
    date_field = schema.default_date_field()
    if date_field is None:
        typer.echo(f"'{schema.name}' has no date field to filter on with --after/--before.")
        raise typer.Exit(code=2)
    return (date_field, after, before)


def _load_vocab_and_handler_or_exit(
    data_dir: Path, schema: CategorySchema
) -> tuple[dict, CategoryHandler]:
    try:
        vocab = load_vocab(data_dir / "vocab.yaml")
        handler = load_handler(schema, HandlerContext(data_dir=data_dir))
    except (VocabError, FileNotFoundError, KeyError) as exc:
        typer.echo(f"Config error: {exc}")
        raise typer.Exit(code=2)
    return vocab, handler


def _parse_prefill_flags(args: list[str]) -> dict[str, str]:
    prefill: dict[str, str] = {}
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            raise typer.BadParameter(f"Expected a --field flag, got '{token}'")
        name = token[2:]
        if i + 1 >= len(args):
            raise typer.BadParameter(f"Missing value for --{name}")
        prefill[name] = args[i + 1]
        i += 2
    return prefill


def _reject_unknown_fields(schema: CategorySchema, prefill: dict[str, str]) -> None:
    unknown = [
        name for name in prefill
        if schema.get_field(name) is None or schema.get_field(name).generated
    ]
    if unknown:
        typer.echo(f"Unknown or non-writable field(s): {', '.join(unknown)}")
        raise typer.Exit(code=2)


@app.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
def add(ctx: typer.Context, category: str = typer.Argument(None, help="Category to add an entry to")):
    """Interactively add a new entry to a category. Extra --field value flags pre-fill the wizard."""
    data_dir = _find_repo_or_exit()
    schema = _require_category_or_exit(data_dir, category)
    prefill = _parse_prefill_flags(ctx.args)
    _reject_unknown_fields(schema, prefill)

    vocab, handler = _load_vocab_and_handler_or_exit(data_dir, schema)
    existing_rows = load_category_rows(data_dir, category)

    values = collect_field_values(schema, vocab, prefill=prefill)
    if not confirm_and_check_duplicates(handler, values, existing_rows):
        typer.echo("Aborted, nothing written.")
        raise typer.Exit(code=0)

    filename = category_csv_path(data_dir, category).relative_to(data_dir).as_posix()
    was_dirty_before = is_file_dirty(data_dir, filename)
    try:
        row = add_entry(data_dir, schema, values)
    except CommitFailed as exc:
        typer.echo(f"Row written, but the commit failed: {exc}")
        raise typer.Exit(code=1)
    if was_dirty_before:
        typer.echo(
            f"Added {category} entry {row['id']} (not committed — {filename} has other "
            "pending changes; run 'parco commit' when ready)."
        )
    else:
        typer.echo(f"Added {category} entry {row['id']}.")


@app.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
def edit(
    ctx: typer.Context,
    category: str = typer.Argument(None, help="Category to edit an entry in"),
    search: str = typer.Option(..., "--search", help="Text to search for"),
):
    """Search for an entry and interactively edit it."""
    data_dir = _find_repo_or_exit()
    schema = _require_category_or_exit(data_dir, category)
    prefill_flags = _parse_prefill_flags(ctx.args)
    _reject_unknown_fields(schema, prefill_flags)

    existing_rows = load_category_rows(data_dir, category)
    matches = search_rows(existing_rows, search)
    if not matches:
        typer.echo("No matching entries found.")
        raise typer.Exit(code=0)
    row = pick_row(schema, matches)
    if row is None:
        typer.echo("Nothing selected.")
        raise typer.Exit(code=0)

    vocab, handler = _load_vocab_and_handler_or_exit(data_dir, schema)

    prefill = {**row, **prefill_flags}
    values = collect_field_values(schema, vocab, prefill=prefill)
    if not confirm_and_check_duplicates(handler, values, existing_rows, self_id=row["id"]):
        typer.echo("Aborted, nothing written.")
        raise typer.Exit(code=0)

    filename = category_csv_path(data_dir, category).relative_to(data_dir).as_posix()
    was_dirty_before = is_file_dirty(data_dir, filename)
    try:
        updated = edit_entry(data_dir, schema, row["id"], values)
    except CommitFailed as exc:
        typer.echo(f"Row written, but the commit failed: {exc}")
        raise typer.Exit(code=1)
    if was_dirty_before:
        typer.echo(
            f"Edited {category} entry {updated['id']} (not committed — {filename} has other "
            "pending changes; run 'parco commit' when ready)."
        )
    else:
        typer.echo(f"Edited {category} entry {updated['id']}.")


@app.command()
def delete(
    category: str = typer.Argument(None, help="Category to delete an entry from"),
    search: str = typer.Option(..., "--search", help="Text to search for"),
):
    """Search for an entry and delete it after one confirmation."""
    data_dir = _find_repo_or_exit()
    schema = _require_category_or_exit(data_dir, category)
    existing_rows = load_category_rows(data_dir, category)
    matches = search_rows(existing_rows, search)
    if not matches:
        typer.echo("No matching entries found.")
        raise typer.Exit(code=0)
    row = pick_row(schema, matches)
    if row is None:
        typer.echo("Nothing selected.")
        raise typer.Exit(code=0)

    if not typer.confirm(
        f"Delete {category} entry {row['id']}? This cannot be undone via the CLI (git history keeps it)."
    ):
        typer.echo("Aborted, nothing deleted.")
        raise typer.Exit(code=0)

    filename = category_csv_path(data_dir, category).relative_to(data_dir).as_posix()
    was_dirty_before = is_file_dirty(data_dir, filename)
    try:
        delete_entry(data_dir, schema, row["id"])
    except CommitFailed as exc:
        typer.echo(f"Row written, but the commit failed: {exc}")
        raise typer.Exit(code=1)
    if was_dirty_before:
        typer.echo(
            f"Deleted {category} entry {row['id']} (not committed — {filename} has other "
            "pending changes; run 'parco commit' when ready)."
        )
    else:
        typer.echo(f"Deleted {category} entry {row['id']}.")


import_app = typer.Typer(help="Bulk-seed data from a one-time export file (see SPECS.md, \"Import\").")
app.add_typer(import_app, name="import")


def _print_import_report(report: ImportReport) -> None:
    by_category: dict[str, int] = {}
    for mapped in report.to_write:
        by_category[mapped.category] = by_category.get(mapped.category, 0) + 1

    if report.warnings:
        for warning in report.warnings:
            typer.echo(f"Warning: {warning}")
        typer.echo()

    typer.echo("Import plan:")
    for category, count in sorted(by_category.items()):
        typer.echo(f"  {category}: {count} entr{'y' if count == 1 else 'ies'}")

    if report.dedup_matches:
        typer.echo(f"\n{len(report.dedup_matches)} possible duplicate(s) found (will still be written):")
        for row_index, matches in report.dedup_matches.items():
            mapped = report.to_write[row_index]
            for match in matches:
                typer.echo(f"  {mapped.category} ({mapped.ccv_label}): {match.reason}")

    if report.notes:
        typer.echo(f"\n{len(report.notes)} imported row(s) need a manual fix:")
        for note in report.notes:
            typer.echo(f"  {note.ccv_label}: {note.reason}")

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
    file: Path = typer.Option(
        ..., "--file", exists=True, dir_okay=False, readable=True,
        help="Path to the CCV XML export",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would be imported without writing anything"),
):
    """Bulk-import from a Canadian Common CV XML export."""
    data_dir = _find_repo_or_exit()

    try:
        report = plan_import(data_dir, file)
    except CcvParseError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)
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


translation_app = typer.Typer(
    help="Manage translations.csv: UI section titles and content glossaries (e.g. place names)."
)
app.add_typer(translation_app, name="translation")

_CATEGORY_HELP = (
    "The translations.csv category this belongs to (e.g. 'section' or 'city') "
    "— not a data category like 'publications'."
)


@translation_app.command(name="add")
def translation_add(
    category: str = typer.Argument(..., help=_CATEGORY_HELP),
    entry_id: str = typer.Argument(..., metavar="ID", help="The glossary key / label id"),
    en: str = typer.Option(None, "--en", help="English text"),
    fr: str = typer.Option(None, "--fr", help="French text"),
):
    """Add a new translation entry to translations.csv."""
    data_dir = _find_repo_or_exit()

    if en is None:
        en = typer.prompt("en ([Enter] to skip)", default="", show_default=False)
    if fr is None:
        fr = typer.prompt("fr ([Enter] to skip)", default="", show_default=False)

    filename = "entries/translations.csv"
    was_dirty_before = is_file_dirty(data_dir, filename)
    try:
        entry = add_translation(data_dir, category, entry_id, en, fr)
    except TranslationExists as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)
    except CommitFailed as exc:
        typer.echo(f"Row written, but the commit failed: {exc}")
        raise typer.Exit(code=1)
    if was_dirty_before:
        typer.echo(
            f"Added translation {entry.category}:{entry.id} (not committed — {filename} has other "
            "pending changes; run 'parco commit' when ready)."
        )
    else:
        typer.echo(f"Added translation {entry.category}:{entry.id}.")


@translation_app.command(name="edit")
def translation_edit(
    category: str = typer.Argument(..., help=_CATEGORY_HELP),
    entry_id: str = typer.Argument(..., metavar="ID", help="The glossary key / label id"),
    en: str = typer.Option(None, "--en", help="English text"),
    fr: str = typer.Option(None, "--fr", help="French text"),
):
    """Edit an existing translation entry in translations.csv."""
    data_dir = _find_repo_or_exit()

    translations_path = translations_csv_path(data_dir)
    current = load_translations(translations_path).get(category, entry_id) if translations_path.is_file() else None
    if current is None:
        typer.echo(f"No translation for category '{category}' id '{entry_id}'")
        raise typer.Exit(code=2)

    if en is None:
        en = typer.prompt("en", default=current.en, show_default=bool(current.en))
    if fr is None:
        fr = typer.prompt("fr", default=current.fr, show_default=bool(current.fr))

    filename = "entries/translations.csv"
    was_dirty_before = is_file_dirty(data_dir, filename)
    try:
        entry = edit_translation(data_dir, category, entry_id, en, fr)
    except TranslationNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)
    except CommitFailed as exc:
        typer.echo(f"Row written, but the commit failed: {exc}")
        raise typer.Exit(code=1)
    if was_dirty_before:
        typer.echo(
            f"Edited translation {entry.category}:{entry.id} (not committed — {filename} has other "
            "pending changes; run 'parco commit' when ready)."
        )
    else:
        typer.echo(f"Edited translation {entry.category}:{entry.id}.")


@translation_app.command(name="delete")
def translation_delete(
    category: str = typer.Argument(..., help=_CATEGORY_HELP),
    entry_id: str = typer.Argument(..., metavar="ID", help="The glossary key / label id"),
):
    """Delete a translation entry from translations.csv after one confirmation."""
    data_dir = _find_repo_or_exit()

    translations_path = translations_csv_path(data_dir)
    exists = translations_path.is_file() and load_translations(translations_path).exists(category, entry_id)
    if not exists:
        typer.echo(f"No translation for category '{category}' id '{entry_id}'")
        raise typer.Exit(code=2)

    if not typer.confirm(
        f"Delete translation {category}:{entry_id}? "
        "This cannot be undone via the CLI (git history keeps it)."
    ):
        typer.echo("Aborted, nothing deleted.")
        raise typer.Exit(code=0)

    filename = "entries/translations.csv"
    was_dirty_before = is_file_dirty(data_dir, filename)
    try:
        delete_translation(data_dir, category, entry_id)
    except TranslationNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)
    except CommitFailed as exc:
        typer.echo(f"Row written, but the commit failed: {exc}")
        raise typer.Exit(code=1)
    if was_dirty_before:
        typer.echo(
            f"Deleted translation {category}:{entry_id} (not committed — {filename} has other "
            "pending changes; run 'parco commit' when ready)."
        )
    else:
        typer.echo(f"Deleted translation {category}:{entry_id}.")


@translation_app.command(name="list")
def translation_list(
    category: str = typer.Option(None, "--category", help="Only show this translations.csv category"),
    search: str = typer.Option(None, "--search", help="Only show entries matching this text"),
):
    """List translation entries, optionally filtered by --category and/or --search."""
    data_dir = _find_repo_or_exit()

    translations_path = translations_csv_path(data_dir)
    entries = load_translations(translations_path).all() if translations_path.is_file() else []

    if category:
        entries = [e for e in entries if e.category == category]
    if search:
        needle = search.lower()
        entries = [
            e for e in entries
            if needle in e.id.lower() or needle in e.en.lower() or needle in e.fr.lower()
        ]

    if not entries:
        typer.echo("No translations found.")
        raise typer.Exit(code=0)

    for e in entries:
        typer.echo(f"category={e.category}, id={e.id}, en={e.en or '(blank)'}, fr={e.fr or '(blank)'}")


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


def _prompt_required(label: str) -> str:
    while True:
        value = typer.prompt(label).strip()
        if value:
            return value
        typer.echo(f"'{label}' is required.")


def _prompt_variant_name() -> str:
    while True:
        value = typer.prompt("Identity variant name", default="academic").strip()
        if not value:
            typer.echo("Identity variant name is required.")
            continue
        if "/" in value or "\\" in value:
            typer.echo("Identity variant name can't contain '/' or '\\'.")
            continue
        return value


@app.command()
def init(
    path: Path = typer.Argument(None, help="Where to scaffold the new data repo (defaults to the current directory)"),
):
    """Interactively scaffold a brand-new parco data repo."""
    target = (path or Path.cwd()).expanduser().resolve()

    if (target / "parco.yaml").is_file():
        typer.echo(f"A parco data repo already exists at {target}.")
        raise typer.Exit(code=1)

    try:
        check_not_inside_source_repo(target)
    except ScaffoldInsideSourceRepo as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    try:
        check_git_identity_configured()
    except GitIdentityMissing as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    first_name = _prompt_required("First name")
    last_name = _prompt_required("Last name")
    variant_name = _prompt_variant_name()

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
    phone = typer.prompt(
        "Phone, international format e.g. +1 514 987 3000 ([Enter] to skip)",
        default="", show_default=False,
    )
    homepage = typer.prompt("Homepage ([Enter] to skip)", default="", show_default=False)
    currency = _prompt_required("Currency (e.g. CAD)")
    citation_export_path = typer.prompt(
        "Path to an existing citation export (CSL-JSON), if you have one already "
        "([Enter] to skip and use the default)",
        default="", show_default=False,
    )

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
    typer.echo(f"  Citation export: {citation_export_path or '(default: reference/library.json)'}")

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
        citation_export_path=citation_export_path,
    )

    try:
        scaffold_repo(target, answers)
    except RepoAlreadyExists as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)
    except ScaffoldInsideSourceRepo as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)
    except GitIdentityMissing as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)
    except GitInitFailed as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    typer.echo(f"\nInitialized a new parco data repo at {target}.")
    typer.echo("Next: `parco add <category>` to start entering data, "
               "`parco build --profile <name>` once you have some.")


if __name__ == "__main__":
    app()
