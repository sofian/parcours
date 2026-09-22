# parcours/cli/main.py
"""The Typer app — thin, owns all prompts/printing (see SPECS.md, "Code
architecture: modular core + thin interfaces")."""

from pathlib import Path

import typer

from ..core.data import load_category_rows
from ..core.entries import CommitFailed, add_entry, delete_entry, edit_entry
from ..core.handlers import load_handler
from ..core.handlers.base import CategoryHandler, HandlerContext
from ..core.labels import (
    TranslationExists,
    TranslationNotFound,
    add_translation,
    delete_translation,
    edit_translation,
    load_labels,
)
from ..core.lint import ConfigError, run_lint
from ..core.repo import DataRepoNotFound, find_data_repo
from ..core.schema import CategorySchema, load_all_schemas
from ..core.vocab import VocabError, load_vocab
from .wizard import (
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
def lint(category: str = typer.Argument(None, help="Only lint this category")):
    """Check category data against its schema, vocab, and labels."""
    data_dir = _find_repo_or_exit()

    try:
        issues = run_lint(data_dir, category_filter=category)
    except ConfigError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)

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


@app.command(name="list")
def list_command(
    category: str = typer.Argument(..., help="Category to list"),
    search: str = typer.Option(None, "--search", help="Only show entries matching this text"),
    order_by: str = typer.Option(None, "--order-by", help="Sort by this field"),
    desc: bool = typer.Option(False, "--desc", help="Sort descending (requires --order-by)"),
):
    """List entries in a category, optionally filtered by --search text and sorted by --order-by."""
    data_dir = _find_repo_or_exit()
    schema = _load_schema_or_exit(data_dir, category)

    if desc and not order_by:
        typer.echo("--desc requires --order-by")
        raise typer.Exit(code=2)
    if order_by and schema.get_field(order_by) is None:
        typer.echo(f"Unknown field: '{order_by}'")
        raise typer.Exit(code=2)

    rows = load_category_rows(data_dir, category)
    if search:
        rows = search_rows(rows, search)
    if order_by:
        rows = order_rows(schema, rows, order_by, descending=desc)

    if not rows:
        typer.echo("No entries found.")
        raise typer.Exit(code=0)

    extra_fields = [order_by] if order_by else None
    for row in rows:
        typer.echo(row_summary(schema, row, extra_fields=extra_fields))


def _load_schema_or_exit(data_dir: Path, category: str) -> CategorySchema:
    schemas = load_all_schemas(data_dir / "categories")
    if category not in schemas:
        typer.echo(f"Unknown category: '{category}'")
        raise typer.Exit(code=2)
    return schemas[category]


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
def add(ctx: typer.Context, category: str = typer.Argument(..., help="Category to add an entry to")):
    """Interactively add a new entry to a category. Extra --field value flags pre-fill the wizard."""
    data_dir = _find_repo_or_exit()
    schema = _load_schema_or_exit(data_dir, category)
    prefill = _parse_prefill_flags(ctx.args)
    _reject_unknown_fields(schema, prefill)

    vocab, handler = _load_vocab_and_handler_or_exit(data_dir, schema)
    existing_rows = load_category_rows(data_dir, category)

    values = collect_field_values(schema, vocab, prefill=prefill)
    if not confirm_and_check_duplicates(handler, values, existing_rows):
        typer.echo("Aborted, nothing written.")
        raise typer.Exit(code=0)

    try:
        row = add_entry(data_dir, schema, values)
    except CommitFailed as exc:
        typer.echo(f"Row written, but the commit failed: {exc}")
        raise typer.Exit(code=1)
    typer.echo(f"Added {category} entry {row['id']}.")


@app.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
def edit(
    ctx: typer.Context,
    category: str = typer.Argument(..., help="Category to edit an entry in"),
    search: str = typer.Option(..., "--search", help="Text to search for"),
):
    """Search for an entry and interactively edit it."""
    data_dir = _find_repo_or_exit()
    schema = _load_schema_or_exit(data_dir, category)
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

    try:
        updated = edit_entry(data_dir, schema, row["id"], values)
    except CommitFailed as exc:
        typer.echo(f"Row written, but the commit failed: {exc}")
        raise typer.Exit(code=1)
    typer.echo(f"Edited {category} entry {updated['id']}.")


@app.command()
def delete(
    category: str = typer.Argument(..., help="Category to delete an entry from"),
    search: str = typer.Option(..., "--search", help="Text to search for"),
):
    """Search for an entry and delete it after one confirmation."""
    data_dir = _find_repo_or_exit()
    schema = _load_schema_or_exit(data_dir, category)
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

    try:
        delete_entry(data_dir, schema, row["id"])
    except CommitFailed as exc:
        typer.echo(f"Row written, but the commit failed: {exc}")
        raise typer.Exit(code=1)
    typer.echo(f"Deleted {category} entry {row['id']}.")


translation_app = typer.Typer(
    help="Manage labels.csv: UI section titles and content glossaries (e.g. place names)."
)
app.add_typer(translation_app, name="translation")

_CATEGORY_HELP = (
    "The labels.csv category this belongs to (e.g. 'section' or 'location') "
    "— not a data category like 'publications'."
)


@translation_app.command(name="add")
def translation_add(
    category: str = typer.Argument(..., help=_CATEGORY_HELP),
    entry_id: str = typer.Argument(..., metavar="ID", help="The glossary key / label id"),
    en: str = typer.Option(None, "--en", help="English text"),
    fr: str = typer.Option(None, "--fr", help="French text"),
):
    """Add a new translation entry to labels.csv."""
    data_dir = _find_repo_or_exit()

    if en is None:
        en = typer.prompt("en ([Enter] to skip)", default="", show_default=False)
    if fr is None:
        fr = typer.prompt("fr ([Enter] to skip)", default="", show_default=False)

    try:
        entry = add_translation(data_dir, category, entry_id, en, fr)
    except TranslationExists as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)
    except CommitFailed as exc:
        typer.echo(f"Row written, but the commit failed: {exc}")
        raise typer.Exit(code=1)
    typer.echo(f"Added translation {entry.category}:{entry.id}.")


@translation_app.command(name="edit")
def translation_edit(
    category: str = typer.Argument(..., help=_CATEGORY_HELP),
    entry_id: str = typer.Argument(..., metavar="ID", help="The glossary key / label id"),
    en: str = typer.Option(None, "--en", help="English text"),
    fr: str = typer.Option(None, "--fr", help="French text"),
):
    """Edit an existing translation entry in labels.csv."""
    data_dir = _find_repo_or_exit()

    labels_path = data_dir / "labels.csv"
    current = load_labels(labels_path).get(category, entry_id) if labels_path.is_file() else None
    if current is None:
        typer.echo(f"No translation for category '{category}' id '{entry_id}'")
        raise typer.Exit(code=2)

    if en is None:
        en = typer.prompt("en", default=current.en, show_default=bool(current.en))
    if fr is None:
        fr = typer.prompt("fr", default=current.fr, show_default=bool(current.fr))

    try:
        entry = edit_translation(data_dir, category, entry_id, en, fr)
    except TranslationNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)
    except CommitFailed as exc:
        typer.echo(f"Row written, but the commit failed: {exc}")
        raise typer.Exit(code=1)
    typer.echo(f"Edited translation {entry.category}:{entry.id}.")


@translation_app.command(name="delete")
def translation_delete(
    category: str = typer.Argument(..., help=_CATEGORY_HELP),
    entry_id: str = typer.Argument(..., metavar="ID", help="The glossary key / label id"),
):
    """Delete a translation entry from labels.csv after one confirmation."""
    data_dir = _find_repo_or_exit()

    labels_path = data_dir / "labels.csv"
    exists = labels_path.is_file() and load_labels(labels_path).exists(category, entry_id)
    if not exists:
        typer.echo(f"No translation for category '{category}' id '{entry_id}'")
        raise typer.Exit(code=2)

    if not typer.confirm(
        f"Delete translation {category}:{entry_id}? "
        "This cannot be undone via the CLI (git history keeps it)."
    ):
        typer.echo("Aborted, nothing deleted.")
        raise typer.Exit(code=0)

    try:
        delete_translation(data_dir, category, entry_id)
    except TranslationNotFound as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2)
    except CommitFailed as exc:
        typer.echo(f"Row written, but the commit failed: {exc}")
        raise typer.Exit(code=1)
    typer.echo(f"Deleted translation {category}:{entry_id}.")


@translation_app.command(name="list")
def translation_list(
    category: str = typer.Option(None, "--category", help="Only show this labels.csv category"),
    search: str = typer.Option(None, "--search", help="Only show entries matching this text"),
):
    """List translation entries, optionally filtered by --category and/or --search."""
    data_dir = _find_repo_or_exit()

    labels_path = data_dir / "labels.csv"
    entries = load_labels(labels_path).all() if labels_path.is_file() else []

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


if __name__ == "__main__":
    app()
