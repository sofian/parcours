"""Every interactive piece of the add/edit/delete wizard: per-field
prompting, the confirm-before-write screen, the duplicate-check prompt,
and search/pick. CLI layer only — nothing here is imported by core (see
SPECS.md, "Data entry" and "Finding a row to edit or delete")."""

from datetime import date

import typer

from ..core.schema import CategorySchema, FieldSpec


def _require_one_of_group(schema: CategorySchema, field_name: str) -> list[str] | None:
    for group in schema.require_one_of:
        if field_name in group:
            return group
    return None


def _ask_vocab_field(field: FieldSpec, choices: list[str], current: str | None) -> str:
    typer.echo(f"{field.name}:")
    for i, choice in enumerate(choices, start=1):
        typer.echo(f"  {i}. {choice}")
    if not field.required:
        typer.echo("  0. [skip]")

    default_number = None
    if current and current in choices:
        default_number = choices.index(current) + 1

    while True:
        answer = typer.prompt("Choice", default=default_number, show_default=default_number is not None)
        try:
            number = int(answer)
        except (TypeError, ValueError):
            typer.echo("Please enter a number.")
            continue
        if number == 0 and not field.required:
            return ""
        if 1 <= number <= len(choices):
            return choices[number - 1]
        typer.echo("Not a valid choice.")


def _ask_plain_field(field: FieldSpec, current: str | None) -> str:
    default = current or ""
    if not current and field.type == "date" and field.required:
        default = str(date.today().year)
    prompt_suffix = "" if field.required else " ([Enter] to skip)"

    while True:
        answer = typer.prompt(f"{field.name}{prompt_suffix}", default=default, show_default=bool(default)).strip()
        if field.required and not answer:
            typer.echo(f"'{field.name}' is required.")
            continue
        return answer


def _ask_field(field: FieldSpec, vocab: dict, current: str | None) -> str:
    if field.vocab:
        choices = vocab.get(field.vocab, [])
        if not choices:
            raise typer.BadParameter(
                f"vocab list '{field.vocab}' for field '{field.name}' is empty or undefined in vocab.yaml"
            )
        return _ask_vocab_field(field, choices, current)
    return _ask_plain_field(field, current)


def collect_field_values(
    schema: CategorySchema, vocab: dict, prefill: dict[str, str] | None = None
) -> dict[str, str]:
    prefill = prefill or {}
    values: dict[str, str] = {}
    handled_groups: set[tuple[str, ...]] = set()

    for field in schema.fields:
        if field.generated:
            continue

        group = _require_one_of_group(schema, field.name)
        if group is not None:
            group_key = tuple(group)
            if group_key in handled_groups:
                continue
            handled_groups.add(group_key)

            while True:
                for name in group:
                    group_field = schema.get_field(name)
                    values[name] = _ask_field(group_field, vocab, prefill.get(name))
                if any(values[name].strip() for name in group):
                    break
                typer.echo(f"At least one of {group} must be filled in.")
            continue

        values[field.name] = _ask_field(field, vocab, prefill.get(field.name))

    return values


def confirm_and_check_duplicates(
    handler, values: dict[str, str], existing_rows: list[dict], self_id: str | None = None
) -> bool:
    """Show the confirm-before-write screen, then run the category
    handler's dedup check. Returns True if the write should proceed."""
    typer.echo("\nReview:")
    for name, value in values.items():
        typer.echo(f"  {name}: {value or '(skip)'}")

    if not typer.confirm("Write this entry?"):
        return False

    candidate = {"id": self_id or "", **values}
    matches = handler.find_matches(candidate, existing_rows)

    for match in matches:
        if match.kind == "related":
            typer.echo(f"Related existing entry {match.existing_row_id}: {match.reason}")

    duplicates = [m for m in matches if m.kind == "duplicate"]
    if duplicates:
        typer.echo("\nPossible duplicates found:")
        for match in duplicates:
            typer.echo(f"  {match.existing_row_id}: {match.reason}")
        if not typer.confirm("Add anyway?"):
            return False

    return True


def _display_fields(schema: CategorySchema) -> list[str]:
    names: list[str] = [f.name for f in schema.fields if f.required]
    for group in schema.require_one_of:
        for name in group:
            if name not in names:
                names.append(name)
    return names


def row_summary(schema: CategorySchema, row: dict) -> str:
    parts = [f"id={row.get('id', '')}"]
    for name in _display_fields(schema):
        value = row.get(name)
        if value:
            parts.append(f"{name}={value}")
    return ", ".join(parts)


def search_rows(rows: list[dict], search_text: str) -> list[dict]:
    needle = search_text.lower()
    return [
        row for row in rows
        if any(needle in str(value).lower() for value in row.values() if value)
    ]


def pick_row(schema: CategorySchema, matches: list[dict]) -> dict | None:
    if not matches:
        # Defensive fallback: main.py checks `if not matches` itself before
        # calling pick_row, so this branch shouldn't currently be hit — but
        # keep it safe (and silent, so no caller can get a double message).
        return None

    for i, row in enumerate(matches, start=1):
        typer.echo(f"  {i}. {row_summary(schema, row)}")

    choice = typer.prompt("Pick a number ([Enter] to cancel)", default="", show_default=False)
    if not choice.strip():
        return None
    try:
        index = int(choice)
    except ValueError:
        typer.echo("Not a valid number.")
        return None
    if not (1 <= index <= len(matches)):
        typer.echo("Not a valid number.")
        return None
    return matches[index - 1]
