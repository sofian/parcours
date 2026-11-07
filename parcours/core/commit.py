"""Manually stage and commit whatever's currently pending in the data
repo — for hand-edits outside `parco`, or to finalize a `parco import`
review (see SPECS.md, "Commit"). Core layer: no prompting/printing."""

import fnmatch
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .entries import CommitFailed


# Repo-root files and top-level directories that parco itself manages.
# A new (untracked) file is only picked up if it lives in one of these,
# or in a directory that already holds tracked files (e.g. a user's own
# `csl/` styles folder) — anything else, like a scratch CSV dropped at
# the repo root, is left alone and reported as skipped.
MANAGED_ROOT_FILES = {
    ".gitignore", "parco.yaml", "vocab.yaml", "views.yaml", "identity.yaml", "sync.yaml",
}
MANAGED_DIRS = {"categories", "entries", "profiles", "themes", "reference"}

# Editor/office lock, backup and OS metadata files — never committed,
# wherever they are (LibreOffice drops `.~lock.<name>#` next to any CSV
# it opens, Excel `~$<name>`).
JUNK_PATTERNS = [
    ".~lock.*#", "~$*", "*~", ".*.swp", ".*.swo", "#*#", ".DS_Store", "Thumbs.db", "desktop.ini",
]


@dataclass
class CommitResult:
    committed: bool
    files: list[str]
    skipped: list[str] = field(default_factory=list)


def is_junk_file(path: str) -> bool:
    name = PurePosixPath(path).name
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in JUNK_PATTERNS)


def _git_lines(data_dir: Path, *args: str) -> list[str]:
    out = subprocess.run(
        ["git", *args, "-z"], cwd=data_dir, check=True, capture_output=True, text=True,
    ).stdout
    return [p for p in out.split("\0") if p]


def _is_managed_location(path: str, tracked_dirs: set[str]) -> bool:
    parts = PurePosixPath(path).parts
    if len(parts) == 1:
        return path in MANAGED_ROOT_FILES
    return parts[0] in MANAGED_DIRS or str(PurePosixPath(path).parent) in tracked_dirs


def commit_pending(data_dir: Path, message: str | None = None) -> CommitResult:
    """Stages changes to tracked files (edits and deletions) plus new
    files in parco-managed locations, then commits. Junk files (locks,
    backups) and untracked files elsewhere are never staged; they are
    returned in `skipped` so the caller can report them."""
    tracked = _git_lines(data_dir, "ls-files")
    tracked_dirs = {str(PurePosixPath(p).parent) for p in tracked if "/" in p}
    modified = _git_lines(data_dir, "ls-files", "--modified")
    deleted = set(_git_lines(data_dir, "ls-files", "--deleted"))
    untracked = _git_lines(data_dir, "ls-files", "--others", "--exclude-standard")

    # A junk file that was committed by mistake still gets its deletion
    # staged (so it drops out of the repo), never its modifications.
    to_stage = {p for p in modified if not is_junk_file(p) or p in deleted} | deleted
    skipped = []
    for path in untracked:
        if not is_junk_file(path) and _is_managed_location(path, tracked_dirs):
            to_stage.add(path)
        else:
            skipped.append(path)

    if to_stage:
        subprocess.run(
            ["git", "add", "-A", "--", *sorted(to_stage)],
            cwd=data_dir, check=True, capture_output=True,
        )

    # Report what's actually staged — includes anything the user staged
    # themselves beforehand with `git add`.
    files = sorted(set(_git_lines(data_dir, "diff", "--cached", "--name-only")))
    if not files:
        return CommitResult(committed=False, files=[], skipped=sorted(skipped))

    if message is None:
        message = f"Updated {', '.join(files)}"

    try:
        subprocess.run(["git", "commit", "-m", message], cwd=data_dir, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if exc.stderr else str(exc)
        raise CommitFailed(f"git commit failed: {stderr}") from exc
    return CommitResult(committed=True, files=files, skipped=sorted(skipped))
