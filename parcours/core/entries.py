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


class CommitFailed(Exception):
    """Raised when `git commit` fails for a reason other than there being
    nothing to commit (no repo, missing user.email/user.name, a rejecting
    pre-commit hook, etc). The row has already been written to the CSV by
    the time this is raised."""


def generate_id(data_dir: Path, category_name: str) -> str:
    existing_ids = {row.get("id") for row in load_category_rows(data_dir, category_name)}
    while True:
        candidate = secrets.token_hex(_ID_BYTES)
        if candidate not in existing_ids:
            return candidate


def _csv_path(data_dir: Path, category_name: str) -> Path:
    return data_dir / f"{category_name}.csv"


def write_all_rows(csv_path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def is_file_dirty(data_dir: Path, filename: str) -> bool:
    """True if `filename` already had uncommitted changes relative to
    HEAD (staged or unstaged) *before* whatever write is about to
    happen. Callers MUST call this before `write_all_rows` — once the
    write has landed on disk, git can no longer distinguish "dirty
    before this write" from "dirty because of this write" for an
    already-tracked file. A brand-new, never-tracked file does not
    count as dirty (there's nothing pre-existing to protect against
    folding together)."""
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", filename],
        cwd=data_dir, check=True, capture_output=True,
    )
    return bool(status.stdout) and not status.stdout.startswith(b"??")


def git_commit(data_dir: Path, filename: str, message: str, was_already_dirty: bool) -> bool:
    """Commits `filename`'s current content, unless `was_already_dirty`
    (computed by the caller via `is_file_dirty`, BEFORE writing) — in
    that case the write still happened, but committing now would
    silently fold every other pending change in that file into a
    message that only names this one row. Returns whether it actually
    committed."""
    subprocess.run(["git", "add", filename], cwd=data_dir, check=True, capture_output=True)

    status_after = subprocess.run(
        ["git", "status", "--porcelain", "--", filename],
        cwd=data_dir, check=True, capture_output=True,
    )
    if not status_after.stdout.strip():
        # Nothing changed for this file (e.g. an edit with identical values) —
        # the row is already correctly on disk, so there's nothing to commit.
        return False

    if was_already_dirty:
        return False

    try:
        subprocess.run(["git", "commit", "-m", message], cwd=data_dir, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if exc.stderr else str(exc)
        raise CommitFailed(f"git commit failed: {stderr}") from exc
    return True


def add_entry(data_dir: Path, schema: CategorySchema, values: dict) -> dict:
    row_id = generate_id(data_dir, schema.name)
    row = {"id": row_id, **values}
    filename = f"{schema.name}.csv"

    rows = load_category_rows(data_dir, schema.name)
    rows.append(row)
    was_already_dirty = is_file_dirty(data_dir, filename)
    write_all_rows(_csv_path(data_dir, schema.name), schema.field_names(), rows)
    git_commit(data_dir, filename, f"Added {schema.name} entry {row_id}", was_already_dirty)
    return row


def edit_entry(data_dir: Path, schema: CategorySchema, row_id: str, values: dict) -> dict:
    rows = load_category_rows(data_dir, schema.name)
    if not any(row.get("id") == row_id for row in rows):
        raise EntryNotFound(f"No {schema.name} entry with id '{row_id}'")

    filename = f"{schema.name}.csv"
    updated_row = {"id": row_id, **values}
    new_rows = [updated_row if row.get("id") == row_id else row for row in rows]
    was_already_dirty = is_file_dirty(data_dir, filename)
    write_all_rows(_csv_path(data_dir, schema.name), schema.field_names(), new_rows)
    git_commit(data_dir, filename, f"Edited {schema.name} entry {row_id}", was_already_dirty)
    return updated_row


def delete_entry(data_dir: Path, schema: CategorySchema, row_id: str) -> None:
    rows = load_category_rows(data_dir, schema.name)
    if not any(row.get("id") == row_id for row in rows):
        raise EntryNotFound(f"No {schema.name} entry with id '{row_id}'")

    filename = f"{schema.name}.csv"
    new_rows = [row for row in rows if row.get("id") != row_id]
    was_already_dirty = is_file_dirty(data_dir, filename)
    write_all_rows(_csv_path(data_dir, schema.name), schema.field_names(), new_rows)
    git_commit(data_dir, filename, f"Deleted {schema.name} entry {row_id}", was_already_dirty)
