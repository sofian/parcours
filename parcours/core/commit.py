"""Manually stage and commit whatever's currently pending in the data
repo — for hand-edits outside `parco`, or to finalize a `parco import`
review (see SPECS.md, "Commit"). Core layer: no prompting/printing."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .entries import CommitFailed


@dataclass
class CommitResult:
    committed: bool
    files: list[str]


def commit_pending(data_dir: Path, message: str | None = None) -> CommitResult:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=data_dir, check=True, capture_output=True, text=True,
    )
    if not status.stdout.strip():
        return CommitResult(committed=False, files=[])

    files = sorted({line[3:].strip() for line in status.stdout.splitlines() if line.strip()})

    subprocess.run(["git", "add", "-A"], cwd=data_dir, check=True, capture_output=True)

    if message is None:
        message = f"Updated {', '.join(files)}"

    try:
        subprocess.run(["git", "commit", "-m", message], cwd=data_dir, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if exc.stderr else str(exc)
        raise CommitFailed(f"git commit failed: {stderr}") from exc
    return CommitResult(committed=True, files=files)
