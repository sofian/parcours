"""Locates the data repo `parco` operates on (separate from this code repo)."""

import os
from pathlib import Path

import yaml

MARKER_FILENAME = "parco.yaml"


class DataRepoNotFound(Exception):
    """Raised when no data repo can be located by any resolution method."""


def find_data_repo(
    start: Path | None = None,
    env: dict | None = None,
    explicit: Path | str | None = None,
) -> Path:
    """Locate the data repo directory.

    Resolution order: `explicit` path, then `PARCO_DATA_DIR` env var, then
    a `parco.yaml` marker file searched upward from `start`, then
    `~/.config/parco/config.yaml`'s `data_dir` value.
    """
    if explicit is not None:
        return _validate_repo(Path(explicit))

    env = os.environ if env is None else env
    if "PARCO_DATA_DIR" in env:
        return _validate_repo(Path(env["PARCO_DATA_DIR"]))

    current = Path(start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / MARKER_FILENAME).is_file():
            return candidate

    config_path = Path.home() / ".config" / "parco" / "config.yaml"
    if config_path.is_file():
        with open(config_path, "r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
        if "data_dir" in config:
            return _validate_repo(Path(config["data_dir"]).expanduser())

    raise DataRepoNotFound(
        f"No data repo found. Searched upward from {current} for "
        f"'{MARKER_FILENAME}', and checked {config_path}."
    )


def _validate_repo(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.is_dir():
        raise DataRepoNotFound(f"Data repo path does not exist: {path}")
    return path


def load_repo_config(data_dir: Path) -> dict:
    """Reads `parco.yaml`'s own content (distinct from just checking it
    exists, which `find_data_repo` already does) — e.g. `citation_style`
    for `list --format citation`'s default. Returns {} if the file is
    missing or empty, never raises."""
    config_path = data_dir / MARKER_FILENAME
    if not config_path.is_file():
        return {}
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
