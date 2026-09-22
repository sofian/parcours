"""Row-level add/edit/delete for a category's CSV: id generation, the
actual CSV rewrite, and the per-write auto-commit to the data repo (see
SPECS.md, "Data entry" and "Auto-commit"). Core layer: no prompting or
printing — the CLI wizard owns all of that."""

import csv
import secrets
import subprocess
from pathlib import Path

from .data import load_category_rows
from .schema import CategorySchema

_ID_BYTES = 3  # secrets.token_hex(3) -> 6 hex characters


class EntryNotFound(Exception):
    """Raised by edit_entry/delete_entry for an id that doesn't exist in
    that category's CSV."""


def generate_id(data_dir: Path, category_name: str) -> str:
    existing_ids = {row.get("id") for row in load_category_rows(data_dir, category_name)}
    while True:
        candidate = secrets.token_hex(_ID_BYTES)
        if candidate not in existing_ids:
            return candidate


def _csv_path(data_dir: Path, category_name: str) -> Path:
    return data_dir / f"{category_name}.csv"


def _write_all_rows(csv_path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _git_commit(data_dir: Path, filename: str, message: str) -> None:
    subprocess.run(["git", "add", filename], cwd=data_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=data_dir, check=True, capture_output=True)


def add_entry(data_dir: Path, schema: CategorySchema, values: dict) -> dict:
    row_id = generate_id(data_dir, schema.name)
    row = {"id": row_id, **values}

    rows = load_category_rows(data_dir, schema.name)
    rows.append(row)
    _write_all_rows(_csv_path(data_dir, schema.name), schema.field_names(), rows)
    _git_commit(data_dir, f"{schema.name}.csv", f"Added {schema.name} entry {row_id}")
    return row


def edit_entry(data_dir: Path, schema: CategorySchema, row_id: str, values: dict) -> dict:
    rows = load_category_rows(data_dir, schema.name)
    if not any(row.get("id") == row_id for row in rows):
        raise EntryNotFound(f"No {schema.name} entry with id '{row_id}'")

    updated_row = {"id": row_id, **values}
    new_rows = [updated_row if row.get("id") == row_id else row for row in rows]
    _write_all_rows(_csv_path(data_dir, schema.name), schema.field_names(), new_rows)
    _git_commit(data_dir, f"{schema.name}.csv", f"Edited {schema.name} entry {row_id}")
    return updated_row


def delete_entry(data_dir: Path, schema: CategorySchema, row_id: str) -> None:
    rows = load_category_rows(data_dir, schema.name)
    if not any(row.get("id") == row_id for row in rows):
        raise EntryNotFound(f"No {schema.name} entry with id '{row_id}'")

    new_rows = [row for row in rows if row.get("id") != row_id]
    _write_all_rows(_csv_path(data_dir, schema.name), schema.field_names(), new_rows)
    _git_commit(data_dir, f"{schema.name}.csv", f"Deleted {schema.name} entry {row_id}")
